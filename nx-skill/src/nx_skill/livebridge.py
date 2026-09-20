"""Client for the live bridge that runs *inside* an open NX session.

Two ways to drive NX exist and they are not interchangeable:

* **Batch** (:mod:`nx_skill.journal`) starts a private NX process. It is reliable
  for file work but never touches the window the user is looking at.
* **Live** (this module) talks to a listener hosted inside the running NX
  process, so commands change the Work Part and the Part Navigator in front of
  the user, and every feature stays editable.

The listener is a .NET Remoting server loaded from the NX custom directory; the
client is a small console executable because .NET Remoting has no practical
Python client. Both are built from the C# sources in `scripts/dotnet_bridge`.

The transport is a single request/response pair per call: the client sends a
Base64-encoded UTF-8 JSON payload and prints a JSON reply on stdout. That means
one call is one atomic operation, which is why every command is a discrete verb
rather than a script.
"""

from __future__ import annotations

import base64
import json
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .config import Settings
from .contracts import BridgeOffline, BridgeTimeout, SkillError
from .discovery import NxInstall
from .process import nx_gui_processes

DEFAULT_CALL_TIMEOUT = 3600
PING_TIMEOUT = 15

#: Commands the compiled .NET client actually implements. Verified against
#: scripts/dotnet_bridge/client/NxLiveBridgeClient.cs -- the client throws
#: "Unknown live command" for anything else, so this set must match it exactly
#: rather than describing what would be nice to have.
#:
#: Note what is deliberately *absent*: `module-list` is answered from the
#: installation on disk (see nx_skill.modules) and `run-python-inline` is a
#: convenience that writes a file and calls `run-python`, because neither exists
#: in the bridge protocol. Both are offered at the API level without pretending
#: to be wire commands.
LIVE_COMMANDS = frozenset(
    {
        "ping",
        "status",
        "create-modeling-part",
        "create-block",
        "prepare-session",
        "run-python",
    }
)


@dataclass(frozen=True)
class LiveResponse:
    command: str
    payload: dict[str, Any]
    duration_seconds: float

    @property
    def ok(self) -> bool:
        return bool(self.payload.get("ok", True))

    def to_dict(self) -> dict[str, Any]:
        return {"command": self.command, "durationSeconds": round(self.duration_seconds, 3), **self.payload}


class LiveBridge:
    """Synchronous client for the in-NX live bridge."""

    def __init__(self, install: NxInstall, settings: Settings) -> None:
        self.install = install
        self.settings = settings

    # -- availability -----------------------------------------------------
    @property
    def client(self) -> Path:
        return self.settings.bridge_client()

    def client_available(self) -> bool:
        return self.client.is_file()

    def require_client(self) -> Path:
        client = self.client
        if not client.is_file():
            raise BridgeOffline(
                f"The live bridge client is not built: {client}",
                suggestion=(
                    "Build it once with: powershell -NoProfile -ExecutionPolicy Bypass "
                    "-File scripts/build_dotnet_bridge.ps1  (requires .NET Framework 4.x). "
                    "Batch journal work does not need it."
                ),
                details={"expected": str(client)},
            )
        return client

    # -- transport --------------------------------------------------------
    def _invoke(self, command: str, params: Mapping[str, Any], timeout: int) -> LiveResponse:
        client = self.require_client()
        if command not in LIVE_COMMANDS:
            raise SkillError(
                f"Unknown live command {command!r}.",
                code="INVALID_ARGUMENT",
                suggestion=f"Expected one of: {', '.join(sorted(LIVE_COMMANDS))}",
            )

        encoded = base64.b64encode(
            json.dumps(dict(params), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).decode("ascii")

        started = time.monotonic()
        try:
            completed = subprocess.run(
                [
                    str(client),
                    "-Command",
                    command,
                    "-ParamsJsonBase64",
                    encoded,
                    "-NxRoot",
                    str(self.install.root),
                    "-Port",
                    str(self.settings.live_port),
                ],
                cwd=str(self.settings.ensure_workspace()),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise BridgeTimeout(
                f"The live command {command!r} did not return within {timeout} seconds.",
                suggestion=(
                    "NX may still be executing it. Inspect the open part before reissuing the "
                    "command; do not assume it failed."
                ),
                details={"command": command, "port": self.settings.live_port},
            ) from exc
        except OSError as exc:
            raise BridgeOffline(
                f"Could not start the live bridge client: {exc}",
                suggestion="Check that the client executable exists and is not blocked by antivirus.",
            ) from exc

        duration = time.monotonic() - started
        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()

        if completed.returncode != 0 and not stdout:
            raise BridgeOffline(
                stderr or f"The live bridge client exited with code {completed.returncode}.",
                suggestion=(
                    "Confirm an NX session is open and the bridge listener is running "
                    "(NX Skill > Start Live Bridge in the NX menu)."
                ),
                details={"command": command, "port": self.settings.live_port, "stderr": stderr[-2000:]},
            )

        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise SkillError(
                f"The live bridge returned a response that is not JSON: {stdout[:400]!r}",
                code="NX_BRIDGE_PROTOCOL_ERROR",
                details={"command": command, "stdout": stdout[:4000], "stderr": stderr[-2000:]},
            ) from exc

        response = LiveResponse(command=command, payload=payload, duration_seconds=duration)
        if not response.ok:
            raise SkillError(
                str(payload.get("message") or payload.get("error") or "The live command failed."),
                code="NX_LIVE_COMMAND_FAILED",
                details=response.to_dict(),
            )
        return response

    # -- commands ---------------------------------------------------------
    def ping(self, *, timeout: int = PING_TIMEOUT) -> bool:
        """Return whether a live listener is answering, without raising."""
        if not self.client_available():
            return False
        try:
            return bool(self._invoke("ping", {}, timeout).payload.get("ok"))
        except SkillError:
            return False

    def call(self, command: str, params: Mapping[str, Any] | None = None, *, timeout: int = DEFAULT_CALL_TIMEOUT) -> LiveResponse:
        return self._invoke(command, params or {}, timeout)

    def status(self, *, timeout: int = 60) -> dict[str, Any]:
        return self._invoke("status", {}, timeout).payload

    def module_list(self) -> dict[str, Any]:
        """Inventory this installation's NXOpen modules.

        Answered from disk rather than over the bridge: it needs no running NX,
        no licence and no bridge, and it describes the installation rather than
        whichever session happens to be open.
        """
        from .modules import inventory

        return inventory(self.install).to_dict()

    def create_modeling_part(self, part_path: str, *, save: bool = True, timeout: int = DEFAULT_CALL_TIMEOUT) -> LiveResponse:
        return self._invoke("create-modeling-part", {"part_path": part_path, "save": save}, timeout)

    def create_block(
        self,
        length: float,
        width: float,
        height: float,
        *,
        feature_name: str | None = None,
        save: bool = True,
        timeout: int = DEFAULT_CALL_TIMEOUT,
    ) -> LiveResponse:
        params: dict[str, Any] = {"length": length, "width": width, "height": height, "save": save}
        if feature_name:
            params["feature_name"] = feature_name
        return self._invoke("create-block", params, timeout)

    def run_python_inline(
        self,
        code: str,
        *,
        stage_name: str | None = None,
        timeout: int = DEFAULT_CALL_TIMEOUT,
    ) -> LiveResponse:
        """Run inline NXOpen code in the live session.

        The bridge protocol has no inline verb, so the code is written to a file
        in the workspace and executed through `run-python`. Keeping the file
        (when NX_SKILL_DELETE_GENERATED is off) is deliberate: it is the only
        artefact available to inspect when a step fails inside NX.
        """
        if not str(code).strip():
            raise SkillError("No code was provided.", code="INVALID_ARGUMENT")

        safe_stage = re.sub(r"[^A-Za-z0-9_-]+", "_", str(stage_name or "")).strip("_")
        name = f"inline_{safe_stage}.py" if safe_stage else "inline_step.py"
        target = self.settings.generated_root() / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(code), encoding="utf-8")

        params: dict[str, Any] = {"path": str(target)}
        if stage_name:
            params["stage_name"] = str(stage_name)
        try:
            return self._invoke("run-python", params, timeout)
        finally:
            if self.settings.delete_generated:
                try:
                    target.unlink()
                except OSError:
                    pass

    def run_python_file(self, path: str | Path, *, timeout: int = DEFAULT_CALL_TIMEOUT) -> LiveResponse:
        """Run a journal file in the *live* session (not the batch path)."""
        target = Path(path).expanduser()
        if not target.is_absolute():
            target = self.settings.ensure_workspace() / target
        if not target.is_file():
            raise SkillError(
                f"No such script in the workspace: {target}",
                code="INVALID_ARGUMENT",
                suggestion="Paths are relative to NX_SKILL_WORKSPACE.",
            )
        return self._invoke("run-python", {"path": str(target)}, timeout)

    # -- lifecycle --------------------------------------------------------
    def launch_gui(self, *, timeout: int | None = None) -> None:
        """Start an interactive NX session with this package's custom directory loaded."""
        ugraf = self.install.ugraf
        if not ugraf.exists():
            raise SkillError(
                f"The NX graphical executable was not found at {ugraf}.",
                code="NX_NOT_FOUND",
                suggestion="Check NX_SKILL_NX_ROOT points at a complete installation.",
            )

        from .journal import JournalRunner  # local import avoids a cycle

        env = JournalRunner(self.install, self.settings).environment(load_runtime=True)
        try:
            subprocess.Popen([str(ugraf)], cwd=str(self.install.nxbin), env=env, close_fds=True)
        except OSError as exc:
            raise SkillError(f"Could not launch NX: {exc}", code="NX_LAUNCH_FAILED") from exc

        if timeout:
            self.wait_online(timeout)

    def wait_online(self, timeout: int) -> bool:
        """Poll the bridge until it answers or *timeout* elapses."""
        deadline = time.monotonic() + max(10, timeout)
        while time.monotonic() < deadline:
            if self.ping():
                return True
            time.sleep(3)
        return False

    def ensure_online(self, *, timeout: int | None = None) -> dict[str, Any]:
        """Make sure a live bridge is reachable, launching NX when configured to.

        Returns a small report describing what had to happen. Raises
        :class:`BridgeOffline` when the bridge cannot be reached and launching is
        either disabled or failed -- callers should fall back to batch journals
        rather than pretending the live path worked.
        """
        wait = timeout if timeout is not None else self.settings.auto_launch_timeout
        report: dict[str, Any] = {
            "clientBuilt": self.client_available(),
            "port": self.settings.live_port,
            "nxRunning": bool(nx_gui_processes()),
            "launched": False,
            "online": False,
        }

        if self.ping():
            report["online"] = True
            return report

        if not self.client_available():
            raise BridgeOffline(
                f"The live bridge client is not built: {self.client}",
                suggestion="Run scripts/build_dotnet_bridge.ps1, or use batch journals instead.",
                details=report,
            )

        if not report["nxRunning"]:
            if not self.settings.auto_launch:
                raise BridgeOffline(
                    "NX is not running and automatic launch is disabled.",
                    suggestion=(
                        "Start NX yourself, or set NX_SKILL_AUTO_LAUNCH=true. "
                        "Batch journals work without an open session."
                    ),
                    details=report,
                )
            self.launch_gui()
            report["launched"] = True

        if self.wait_online(wait):
            report["online"] = True
            return report

        raise BridgeOffline(
            f"No live bridge answered on port {self.settings.live_port} within {wait} seconds.",
            suggestion=(
                "If NX is open, start the listener from its menu: NX Skill > Start Live Bridge. "
                "If the window is showing a modal dialog, close it. "
                "Batch journals remain available without a live session."
            ),
            details=report,
        )
