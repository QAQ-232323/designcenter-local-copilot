"""Result envelopes, execution states and the workspace boundary."""

from __future__ import annotations

from pathlib import Path

import pytest

from nx_skill.contracts import (
    BridgeTimeout,
    InvalidArgument,
    SkillError,
    UNKNOWN_STATE_CODES,
    Workspace,
    WorkspaceViolation,
    dumps,
    fail,
    ok,
)


def test_success_envelope_shape():
    payload = ok({"a": 1})
    assert payload["ok"] is True
    assert payload["execution_state"] == "succeeded"
    assert payload["result"] == {"a": 1}


def test_success_envelope_accepts_extra_fields():
    payload = ok({"steps": []}, execution_state="unknown")
    assert payload["execution_state"] == "unknown"


def test_skill_error_carries_actionable_fields():
    error = SkillError("boom", suggestion="try that", details={"x": 1})
    payload = error.to_dict()
    assert payload["message"] == "boom"
    assert payload["suggestion"] == "try that"
    assert payload["details"] == {"x": 1}
    assert payload["retryable"] is False


def test_a_timeout_is_reported_as_unknown_not_as_a_clean_failure():
    """The whole point of execution_state: a timeout may still have changed the model."""
    payload = fail(BridgeTimeout("no answer"))
    assert payload["ok"] is False
    assert payload["execution_state"] == "unknown"
    assert payload["error"]["code"] == "NX_BRIDGE_TIMEOUT"


def test_an_invalid_argument_is_reported_as_not_started():
    payload = fail(InvalidArgument("bad input"))
    assert payload["execution_state"] == "not_started"


def test_every_unknown_state_code_maps_to_unknown():
    for code in UNKNOWN_STATE_CODES:
        assert fail(SkillError("x", code=code))["execution_state"] == "unknown"


def test_unexpected_exception_is_still_an_envelope():
    payload = fail(RuntimeError("kaboom"))
    assert payload["ok"] is False
    assert payload["error"]["code"] == "INTERNAL_ERROR"
    assert payload["execution_state"] == "not_started"


def test_dumps_is_valid_json_with_unicode():
    assert "建" in dumps(ok({"prompt": "建模"}))


# -- workspace boundary -----------------------------------------------------


@pytest.fixture()
def workspace(tmp_path: Path) -> Workspace:
    return Workspace(tmp_path / "ws")


def test_relative_paths_resolve_inside(workspace: Workspace):
    assert workspace.resolve("part.prt") == workspace.root / "part.prt"
    assert workspace.resolve("sub/dir/part.prt").name == "part.prt"


def test_absolute_paths_are_rejected(workspace: Workspace):
    with pytest.raises(WorkspaceViolation):
        workspace.resolve(r"C:\Windows\System32\drivers\etc\hosts")


def test_windows_style_absolute_path_is_rejected_on_any_platform(workspace: Workspace):
    """A Windows path must not slip through just because the host is POSIX."""
    with pytest.raises(WorkspaceViolation):
        workspace.resolve(r"D:\secrets\part.prt")


@pytest.mark.parametrize("attempt", ["../escape.prt", "sub/../../escape.prt", "..\\escape.prt"])
def test_traversal_is_rejected(workspace: Workspace, attempt: str):
    with pytest.raises(WorkspaceViolation):
        workspace.resolve(attempt)


def test_empty_path_is_rejected(workspace: Workspace):
    with pytest.raises(WorkspaceViolation):
        workspace.resolve("   ")


def test_must_exist_reports_a_missing_file(workspace: Workspace):
    with pytest.raises(WorkspaceViolation):
        workspace.resolve("nope.prt", must_exist=True)


def test_ensure_inside_accepts_an_absolute_path_that_is_already_confined(workspace: Workspace):
    inside = workspace.root / "a.prt"
    assert workspace.ensure_inside(inside) == inside
    assert workspace.relative(inside) == "a.prt"


def test_workspace_is_created_on_demand(tmp_path: Path):
    target = tmp_path / "deep" / "nested"
    Workspace(target)
    assert target.is_dir()
