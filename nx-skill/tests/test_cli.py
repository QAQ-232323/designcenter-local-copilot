"""CLI behaviour: one JSON envelope per command, non-zero exit on failure."""

from __future__ import annotations

import json

import pytest

from nx_skill.cli import build_parser, main


def _run(capsys, *argv):
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, json.loads(captured.out)


def test_doctor_succeeds_and_reports_on_any_machine(capsys, tmp_path, no_nx, monkeypatch):
    monkeypatch.setenv("NX_SKILL_WORKSPACE", str(tmp_path / "ws"))
    code, payload = _run(capsys, "doctor")
    assert code == 0, "doctor is a diagnostic: producing a report is success"
    assert payload["ok"] is False, "but the envelope reports the environment as unhealthy"
    assert payload["result"]["installations"] == []
    assert payload["result"]["liveBridge"]["clientBuilt"] in (True, False)
    assert payload["result"]["settings"]["livePort"] == 25121


def test_doctor_flags_a_missing_installation(capsys, tmp_path, no_nx, monkeypatch):
    monkeypatch.setenv("NX_SKILL_WORKSPACE", str(tmp_path / "ws"))
    code, payload = _run(capsys, "doctor")
    assert any("No NX installation" in p for p in payload["result"]["problems"])
    assert code == 0  # it still produced a report


def test_doctor_with_text_output(capsys, tmp_path, no_nx, monkeypatch):
    monkeypatch.setenv("NX_SKILL_WORKSPACE", str(tmp_path / "ws"))
    code = main(["doctor", "--text"])
    out = capsys.readouterr().out
    assert code == 0
    assert "installations" in out


def test_discover_reports_a_clean_error_when_nothing_is_found(capsys, tmp_path, no_nx, monkeypatch):
    monkeypatch.setenv("NX_SKILL_WORKSPACE", str(tmp_path / "ws"))
    code, payload = _run(capsys, "discover")
    assert code == 1
    assert payload["ok"] is False
    assert payload["error"]["code"] == "NX_NOT_FOUND"
    assert payload["error"]["suggestion"]


def test_discover_finds_an_installation(capsys, fake_install, no_nx):
    install, settings = fake_install
    code, payload = _run(capsys, "--nx-root", str(install.root), "--workspace", str(settings.workspace), "discover")
    assert code == 0
    assert payload["result"]["count"] == 1
    assert payload["result"]["installations"][0]["release"] == "2512"


def test_docs_search_from_the_cli(capsys, fake_install):
    install, settings = fake_install
    code, payload = _run(
        capsys, "--nx-root", str(install.root), "--workspace", str(settings.workspace),
        "docs", "search", "ExtrudeBuilder",
    )
    assert code == 0
    assert payload["result"]["members"][0]["name"] == "NXOpen.Features.ExtrudeBuilder"


def test_docs_member_from_the_cli(capsys, fake_install):
    install, settings = fake_install
    code, payload = _run(
        capsys, "--nx-root", str(install.root), "--workspace", str(settings.workspace),
        "docs", "member", "NXOpen.Session.GetSession",
    )
    assert code == 0
    assert payload["result"]["createdIn"] == "3.0.0"


def test_docs_type_from_the_cli(capsys, fake_install):
    install, settings = fake_install
    code, payload = _run(
        capsys, "--nx-root", str(install.root), "--workspace", str(settings.workspace),
        "docs", "type", "NXOpen.Features.ExtrudeBuilder",
    )
    assert code == 0
    assert payload["result"]["memberCount"] >= 2


def test_route_and_plan_need_no_nx(capsys, tmp_path, no_nx, monkeypatch):
    monkeypatch.setenv("NX_SKILL_WORKSPACE", str(tmp_path / "ws"))
    code, payload = _run(capsys, "route", "建模一个支架")
    assert code == 0 and payload["result"]["route"] == "modeling"

    code, payload = _run(capsys, "plan", "build a bracket", "--part-name", "Bracket")
    assert code == 0
    assert payload["result"]["partName"] == "Bracket"


def test_visual_spec_command(capsys, tmp_path, no_nx, monkeypatch):
    monkeypatch.setenv("NX_SKILL_WORKSPACE", str(tmp_path / "ws"))
    code, payload = _run(capsys, "visual-spec", "三视图", "--projection", "third_angle")
    assert code == 0
    assert payload["result"]["projectionSystem"]["requested"] == "third_angle"


def test_journal_run_rejects_paths_outside_the_workspace(capsys, fake_install):
    install, settings = fake_install
    code, payload = _run(
        capsys, "--nx-root", str(install.root), "--workspace", str(settings.workspace),
        "journal", "run", r"C:\Windows\evil.py",
    )
    assert code == 1
    assert payload["error"]["code"] == "WORKSPACE_VIOLATION"


def test_parser_requires_a_command():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_live_call_rejects_an_unimplemented_verb(capsys, fake_install):
    install, settings = fake_install
    code, payload = _run(
        capsys, "--nx-root", str(install.root), "--workspace", str(settings.workspace),
        "live", "call", "run-python-inline",
    )
    assert code == 1
    assert payload["error"]["code"] == "INVALID_ARGUMENT"