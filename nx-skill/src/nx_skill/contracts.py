"""Uniform result envelopes, error codes, and the workspace boundary.

Every operation in this package returns the same shape so that an agent never
has to guess how to read a result:

    {"ok": true,  "result": {...}, "execution_state": "succeeded"}
    {"ok": false, "error": {"code": ..., "message": ..., "suggestion": ...}}

`execution_state` exists because "the tool returned an error" and "the model was
not changed" are different claims. A bridge timeout may mean the operation never
started, or that it succeeded and the answer was lost. Reporting `unknown` and
refusing to auto-retry is the only honest option, and it is what
:data:`UNKNOWN_STATE_CODES` drives.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from typing import Any, Mapping

# -- execution states -------------------------------------------------------

NOT_STARTED = "not_started"
SUCCEEDED = "succeeded"
FAILED = "failed"
UNKNOWN = "unknown"

#: Error codes whose outcome cannot be determined from the failure alone. A
#: caller must inspect the model before deciding whether to retry.
UNKNOWN_STATE_CODES = frozenset(
    {
        "NX_BRIDGE_TIMEOUT",
        "NX_BRIDGE_DISCONNECTED",
        "NX_JOURNAL_TIMEOUT",
        "NX_EXECUTION_UNKNOWN",
    }
)

#: Error codes that are safe to retry unchanged once the cause is addressed.
RETRYABLE_CODES = frozenset(
    {
        "NX_BRIDGE_OFFLINE",
        "NX_LAUNCH_TIMEOUT",
        "NX_JOURNAL_BUSY",
    }
)


class SkillError(Exception):
    """Base class for every failure this package reports.

    Carrying `code`, `suggestion` and `retryable` on the exception means the
    MCP layer can render an actionable error without a second lookup table.
    """

    code = "NX_SKILL_ERROR"
    retryable = False

    def __init__(
        self,
        message: str,
        *,
        suggestion: str | None = None,
        details: Mapping[str, Any] | None = None,
        code: str | None = None,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.suggestion = suggestion
        self.details: dict[str, Any] = dict(details or {})
        if code is not None:
            self.code = code
        if retryable is not None:
            self.retryable = retryable

    @property
    def execution_state(self) -> str:
        return UNKNOWN if self.code in UNKNOWN_STATE_CODES else NOT_STARTED

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "execution_state": self.execution_state,
        }
        if self.suggestion:
            payload["suggestion"] = self.suggestion
        if self.details:
            payload["details"] = self.details
        return payload


class NxNotFound(SkillError):
    code = "NX_NOT_FOUND"


class WorkspaceViolation(SkillError):
    code = "WORKSPACE_VIOLATION"


class InvalidArgument(SkillError):
    code = "INVALID_ARGUMENT"


class BridgeOffline(SkillError):
    code = "NX_BRIDGE_OFFLINE"
    retryable = True


class BridgeTimeout(SkillError):
    code = "NX_BRIDGE_TIMEOUT"


class JournalFailed(SkillError):
    code = "NX_JOURNAL_FAILED"


class DocsUnavailable(SkillError):
    code = "NX_DOCS_UNAVAILABLE"


def ok(result: Any = None, **extra: Any) -> dict[str, Any]:
    """Build a success envelope."""
    payload: dict[str, Any] = {"ok": True, "execution_state": SUCCEEDED}
    if result is not None:
        payload["result"] = result
    payload.update(extra)
    return payload


def fail(exc: BaseException) -> dict[str, Any]:
    """Build a failure envelope from any exception."""
    if isinstance(exc, SkillError):
        return {"ok": False, "error": exc.to_dict(), "execution_state": exc.execution_state}
    return {
        "ok": False,
        "error": {
            "code": "INTERNAL_ERROR",
            "message": str(exc) or exc.__class__.__name__,
            "retryable": False,
            "execution_state": NOT_STARTED,
        },
        "execution_state": NOT_STARTED,
    }


def dumps(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Workspace boundary
# ---------------------------------------------------------------------------


class Workspace:
    """Confines every file operation to a single configured directory.

    An agent that can be talked into writing an arbitrary absolute path is a
    liability, so every path argument in this package is *relative* to the
    workspace and is rejected if it escapes it.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve(self, relative_path: str | Path, *, must_exist: bool = False) -> Path:
        text = str(relative_path)
        if not text.strip():
            raise WorkspaceViolation("A relative path inside the workspace is required.")

        candidate = Path(text)
        if candidate.is_absolute() or PureWindowsPath(text).anchor:
            raise WorkspaceViolation(
                f"Absolute paths are not accepted: {text!r}.",
                suggestion="Pass a path relative to the configured NX_SKILL_WORKSPACE.",
            )

        resolved = (self.root / candidate).resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise WorkspaceViolation(
                f"Path escapes the workspace: {text!r}.",
                suggestion=f"Keep the path inside {self.root}.",
            )
        if must_exist and not resolved.exists():
            raise WorkspaceViolation(f"No such file in the workspace: {text!r}")
        return resolved

    def ensure_inside(self, path: str | Path) -> Path:
        resolved = Path(path).expanduser().resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise WorkspaceViolation(f"Path escapes the workspace: {path}")
        return resolved

    def relative(self, path: str | Path) -> str:
        return str(self.ensure_inside(path).relative_to(self.root)).replace("\\", "/")
