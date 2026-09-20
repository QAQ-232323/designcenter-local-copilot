"""Release-agnostic discovery must work for any layout, not one hardcoded release."""

from __future__ import annotations

from pathlib import Path

import pytest

from nx_skill.config import Settings
from nx_skill.discovery import (
    NxNotFound,
    detect_capabilities,
    detect_release,
    discover,
    find_all,
    normalize_root,
    satisfies,
)
from tests.conftest import build_fake_nx


@pytest.mark.parametrize("release_dir", ["NX 2512", "DC 2606", "NX 12.0", "Siemens NX 1980", "nx2406"])
def test_discovers_any_release_directory_name(tmp_path, release_dir):
    root = build_fake_nx(tmp_path / release_dir)
    settings = Settings(nx_root=None, workspace=tmp_path / "ws", skip_global_search=True)
    found = discover(requested=root, settings=settings)
    assert found.root == root.resolve()
    assert found.has("run_journal")
    assert found.has("managed")


def test_normalize_accepts_root_nxbin_and_files(tmp_path):
    root = build_fake_nx(tmp_path / "NX 2512")
    assert normalize_root(root) == root.resolve()
    assert normalize_root(root / "NXBIN") == root.resolve()
    assert normalize_root(root / "NXBIN" / "run_journal.exe") == root.resolve()
    assert normalize_root(root / "NXBIN" / "managed" / "NXOpen.dll") == root.resolve()


def test_normalize_rejects_nonexistent_and_unrelated(tmp_path):
    assert normalize_root(None) is None
    assert normalize_root(tmp_path / "nope") is None
    other = tmp_path / "unrelated"
    other.mkdir()
    assert normalize_root(other / "somefile.txt") is None


def test_a_directory_that_merely_exists_is_not_an_installation(tmp_path):
    empty = tmp_path / "Siemens"
    empty.mkdir()
    assert normalize_root(empty) == empty.resolve()  # normalisation is permissive
    assert not satisfies(empty, "run_journal")  # validation is not


def test_require_run_journal_needs_the_executable(tmp_path):
    root = tmp_path / "NX"
    (root / "NXBIN").mkdir(parents=True)
    assert not satisfies(root, "run_journal")
    (root / "NXBIN" / "run_journal.exe").write_bytes(b"MZ")
    assert satisfies(root, "run_journal")
    assert not satisfies(root, "managed")


def test_posix_layout_satisfies_the_same_requirement(tmp_path):
    """NX on Linux has no .exe suffix; the requirement must still hold."""
    root = tmp_path / "nx2512"
    (root / "NXBIN").mkdir(parents=True)
    (root / "NXBIN" / "run_journal").write_bytes(b"#!/bin/sh\n")
    assert satisfies(root, "run_journal")


@pytest.mark.parametrize(
    "dirname,expected",
    [("NX 2512", "2512"), ("DC 2606", "2606"), ("Siemens NX 1980", "1980"), ("unknown-product", "unknown")],
)
def test_release_is_read_from_the_directory_name(tmp_path, dirname, expected):
    root = build_fake_nx(tmp_path / dirname)
    assert detect_release(root) == expected


def test_release_can_be_overridden_explicitly(tmp_path):
    root = build_fake_nx(tmp_path / "NX 2512")
    assert detect_release(root, explicit="custom") == "custom"


def test_release_marker_file_is_preferred_over_the_directory_name(tmp_path):
    root = build_fake_nx(tmp_path / "Siemens")
    (root / "NXBIN" / "nxversion").write_text("NX 2312\n", encoding="utf-8")
    assert detect_release(root) == "2312"


def test_capabilities_are_reported_from_structure(tmp_path):
    root = build_fake_nx(tmp_path / "NX 2512")
    caps = detect_capabilities(root)
    assert {"journal", "dotnet", "gui", "python_stubs", "api_docs"} <= caps


def test_environment_variable_is_used_when_no_argument_is_given(tmp_path, clean_env, monkeypatch):
    root = build_fake_nx(tmp_path / "DC 2606")
    monkeypatch.setenv("NX_SKILL_NX_ROOT", str(root))
    settings = Settings.from_env().with_overrides(skip_global_search=True)
    assert discover(settings=settings).root == root.resolve()


def test_legacy_root_variable_is_used(tmp_path, clean_env, monkeypatch):
    root = build_fake_nx(tmp_path / "NX 2512")
    monkeypatch.setenv("NX2512_ROOT", str(root))
    settings = Settings.from_env().with_overrides(skip_global_search=True)
    assert discover(settings=settings).root == root.resolve()


def test_an_invalid_explicit_root_does_not_silently_fall_back(tmp_path, no_nx):
    """Explicit intent must not be quietly replaced by a different installation."""
    good = build_fake_nx(tmp_path / "NX 2512")
    bad = tmp_path / "not-nx"
    bad.mkdir()
    settings = Settings(workspace=tmp_path / "ws", skip_global_search=True, nx_root=good)
    with pytest.raises(NxNotFound) as excinfo:
        discover(requested=bad, require="managed", settings=settings)
    assert any("rejected" in entry for entry in excinfo.value.checked)
    assert any("never" in entry for entry in excinfo.value.checked)


def test_not_found_lists_what_was_checked(tmp_path, no_nx):
    settings = Settings(workspace=tmp_path / "ws", skip_global_search=True)
    with pytest.raises(NxNotFound) as excinfo:
        discover(settings=settings)
    message = str(excinfo.value)
    assert "NX_SKILL_NX_ROOT" in message
    assert "Checked:" in message


def test_find_all_orders_by_release_descending(tmp_path, clean_env, monkeypatch):
    from nx_skill import discovery as _d

    monkeypatch.setattr(_d, "registry_candidates", lambda: [])
    monkeypatch.setattr(_d, "fixed_drive_roots", lambda: [])
    monkeypatch.setattr(_d, "vendor_bases", lambda: [tmp_path])
    older = build_fake_nx(tmp_path / "NX 1980")
    newer = build_fake_nx(tmp_path / "DC 2606")
    settings = Settings(workspace=tmp_path / "ws", skip_global_search=True)
    installs = find_all(settings)
    assert [i.root for i in installs][:2] == [newer.resolve(), older.resolve()]


def test_install_reports_derived_paths(tmp_path):
    root = build_fake_nx(tmp_path / "NX 2512")
    settings = Settings(workspace=tmp_path / "ws", skip_global_search=True)
    install = discover(requested=root, settings=settings)
    payload = install.to_dict()
    assert payload["release"] == "2512"
    assert payload["apiXmlDocCount"] == 1
    assert Path(payload["pythonStubs"]).is_dir()
    assert Path(payload["examples"]).is_dir()