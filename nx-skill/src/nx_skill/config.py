"""Environment-driven configuration for nx-skill.

Every setting is resolved from the environment (or an explicit argument) at call
time. Nothing in this package is hardcoded to a machine, a user, an NX release,
or a directory layout: an NX installation this package has never seen must work
after setting one variable, and a machine with no NX at all must still import
the package and run diagnostics.

Canonical namespace
-------------------
    NX_SKILL_NX_ROOT              NX install root (the directory containing NXBIN)
    NX_SKILL_WORKSPACE            where .prt files and scratch output live
    NX_SKILL_LIVE_PORT            TCP port for the in-NX live bridge
    NX_SKILL_AUTO_LAUNCH          launch NX when a live command needs it
    NX_SKILL_AUTO_LAUNCH_TIMEOUT  seconds to wait for the bridge after launching
    NX_SKILL_REQUIRE_ONLINE       fail fast when the live bridge is unreachable
    NX_SKILL_DELETE_GENERATED     delete generated journals after they run
    NX_SKILL_SKIP_GLOBAL_SEARCH   skip the filesystem-wide NXBIN scan
    NX_SKILL_PYTHON               interpreter used to serve MCP
    NX_SKILL_LOG_LEVEL            DEBUG | INFO | WARNING | ERROR

Legacy variables from the original NX/Codex plugins are still read (never
written) so existing installs keep working: NX2512_*, DC2512_*, UGII_BASE_DIR,
UGII_ROOT_DIR, NX_ROOT, NXBIN, SIEMENS_NX_ROOT.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Mapping

PREFIX = "NX_SKILL_"

#: Legacy variable names accepted per canonical setting, in priority order.
LEGACY_ALIASES: Mapping[str, tuple[str, ...]] = {
    "NX_ROOT": (
        "NX2512_ROOT",
        "DC2512_ROOT",
        "UGII_BASE_DIR",
        "NX_ROOT",
        "SIEMENS_NX_ROOT",
    ),
    "NX_BIN": ("NX2512_BIN", "DC2512_BIN", "UGII_ROOT_DIR", "NXBIN"),
    "WORKSPACE": ("NX2512_PROJECT_ROOT", "DC2512_PROJECT_ROOT"),
    "LIVE_PORT": ("NX2512_LIVE_PORT",),
    "AUTO_LAUNCH": ("NX2512_AUTO_LAUNCH",),
    "AUTO_LAUNCH_TIMEOUT": ("NX2512_AUTO_LAUNCH_TIMEOUT",),
    "REQUIRE_ONLINE": ("NX2512_REQUIRE_ONLINE",),
    "DELETE_GENERATED": ("NX2512_DELETE_GENERATED_SCRIPTS",),
    "SKIP_GLOBAL_SEARCH": ("NX2512_SKIP_GLOBAL_SEARCH",),
    "PYTHON": ("CODEX_PYTHON",),
    # NOTE: CONFIG_DIR deliberately has no legacy alias. The earlier plugins had no
    # such variable, and inventing one would be a false compatibility claim.
}

_TRUTHY = {"1", "true", "yes", "on", "y"}
_FALSY = {"0", "false", "no", "off", "n"}


class ConfigError(ValueError):
    """Raised when an environment value cannot be interpreted."""


def env_lookup(name: str, env: Mapping[str, str] | None = None) -> str | None:
    """Return the canonical value for *name*, falling back to legacy aliases."""
    source = os.environ if env is None else env
    canonical = PREFIX + name
    value = source.get(canonical)
    if value is not None and value.strip() != "":
        return value.strip()
    for alias in LEGACY_ALIASES.get(name, ()):
        value = source.get(alias)
        if value is not None and value.strip() != "":
            return value.strip()
    return None


def env_bool(name: str, default: bool, env: Mapping[str, str] | None = None) -> bool:
    raw = env_lookup(name, env)
    if raw is None:
        return default
    lowered = raw.casefold()
    if lowered in _TRUTHY:
        return True
    if lowered in _FALSY:
        return False
    raise ConfigError(f"{PREFIX}{name}={raw!r} is not a boolean (use true/false)")


def env_int(name: str, default: int, env: Mapping[str, str] | None = None) -> int:
    raw = env_lookup(name, env)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{PREFIX}{name}={raw!r} is not an integer") from exc


def env_path(name: str, default: Path | None, env: Mapping[str, str] | None = None) -> Path | None:
    raw = env_lookup(name, env)
    if raw is None:
        return default
    return Path(raw).expanduser()


def package_root() -> Path:
    """Repository/package root: the directory holding src/, docs/ and nx_runtime/."""
    return Path(__file__).resolve().parents[2]


def default_workspace() -> Path:
    """A writable workspace that exists on any platform and needs no configuration.

    Deliberately *not* tied to a vendor folder name so the package avoids
    inventing paths inside a user's CAD documents tree.
    """
    return Path.home() / "NXSkillWorkspace"


@dataclass(frozen=True)
class Settings:
    """Resolved runtime settings. Immutable; use :meth:`with_overrides` to derive."""

    nx_root: Path | None = None
    nx_bin: Path | None = None
    workspace: Path = None  # type: ignore[assignment]
    live_port: int = 25121
    auto_launch: bool = True
    auto_launch_timeout: int = 240
    require_online: bool = True
    delete_generated: bool = True
    skip_global_search: bool = False
    python: Path | None = None
    log_level: str = "INFO"

    def __post_init__(self) -> None:
        # Coerce here rather than trusting callers: `with_overrides` and direct
        # construction both bypass `from_env`, and a workspace that stays a bare
        # string fails later with an opaque "'str' object has no attribute 'mkdir'".
        for name in ("workspace", "nx_root", "nx_bin", "python"):
            value = getattr(self, name)
            if isinstance(value, str):
                text = value.strip()
                object.__setattr__(self, name, Path(text).expanduser() if text else None)
        if self.workspace is None:
            object.__setattr__(self, "workspace", default_workspace())
        if self.live_port < 1 or self.live_port > 65535:
            raise ConfigError(f"live_port {self.live_port} is outside 1..65535")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        source = os.environ if env is None else env
        return cls(
            nx_root=env_path("NX_ROOT", None, source),
            nx_bin=env_path("NX_BIN", None, source),
            workspace=env_path("WORKSPACE", None, source) or default_workspace(),
            live_port=env_int("LIVE_PORT", 25121, source),
            auto_launch=env_bool("AUTO_LAUNCH", True, source),
            auto_launch_timeout=env_int("AUTO_LAUNCH_TIMEOUT", 240, source),
            require_online=env_bool("REQUIRE_ONLINE", True, source),
            delete_generated=env_bool("DELETE_GENERATED", True, source),
            skip_global_search=env_bool("SKIP_GLOBAL_SEARCH", False, source),
            python=env_path("PYTHON", None, source),
            log_level=(env_lookup("LOG_LEVEL", source) or "INFO").upper(),
        )

    def with_overrides(self, **kwargs: object) -> "Settings":
        clean = {k: v for k, v in kwargs.items() if v is not None}
        return replace(self, **clean) if clean else self

    def runtime_root(self) -> Path:
        """The NX custom-directory payload shipped with this package."""
        return package_root() / "nx_runtime"

    def generated_root(self) -> Path:
        return self.workspace / "generated"

    def config_root(self) -> Path:
        """Where generated NX configuration lives (per user, outside the install).

        Overridable with \"NX_SKILL_CONFIG_DIR\" so tests -- and anyone running several
        workspaces side by side -- never write into the real per-user location.
        """
        override = env_lookup("CONFIG_DIR")
        if override:
            return Path(override).expanduser()
        base = os.environ.get("LOCALAPPDATA")
        root = Path(base) if base else Path.home() / ".config"
        return root / "nx-skill"

    def custom_directory_file(self) -> Path:
        return self.config_root() / "custom_dirs.dat"

    def bridge_client(self) -> Path:
        return package_root() / "scripts" / "dotnet_bridge" / "bin" / "NxLiveBridgeClient.exe"

    def bridge_server_dll(self) -> Path:
        return self.runtime_root() / "startup" / "NxLiveBridgeServer.dll"

    def ensure_workspace(self) -> Path:
        self.workspace.mkdir(parents=True, exist_ok=True)
        return self.workspace
