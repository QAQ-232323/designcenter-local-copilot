"""Parsing the API reference that ships inside an NX installation."""

from __future__ import annotations

import pytest

from nx_skill.contracts import DocsUnavailable
from nx_skill.discovery import NxInstall
from nx_skill.localdocs import ApiDocs


def test_stats_describe_the_bundled_reference(fake_install):
    install, _settings = fake_install
    stats = ApiDocs(install).stats()
    assert stats["xmlDocFiles"] == 1
    assert stats["release"] == "2512"
    assert stats["pythonStubFiles"] == 1


def test_search_finds_a_member_by_name(fake_install):
    install, _ = fake_install
    hits = ApiDocs(install).search("GetSession")
    assert [h.qualified for h in hits] == ["NXOpen.Session.GetSession"]


def test_summary_is_flattened_across_nested_elements(fake_install):
    """ElementTree.findtext truncates at the first nested <see>; itertext must not."""
    install, _ = fake_install
    member = ApiDocs(install).member("NXOpen.Session.GetSession")
    assert member is not None
    assert member.summary == "Gets the singleton for NXOpen.Session."


def test_release_note_is_extracted(fake_install):
    install, _ = fake_install
    docs = ApiDocs(install)
    assert docs.member("NXOpen.Session.GetSession").created_in == "3.0.0"
    assert docs.member("NXOpen.Features.ExtrudeBuilder.Distance").created_in == "2206.0.0"


def test_parameters_and_return_value_are_captured(fake_install):
    install, _ = fake_install
    member = ApiDocs(install).member("NXOpen.Session.SetUndoMark(NXOpen.Session.MarkVisibility,System.String)")
    assert member is not None
    assert member.params["name"] == "Name of the mark."
    assert member.kind == "method"


def test_kind_filtering(fake_install):
    install, _ = fake_install
    docs = ApiDocs(install)
    types = docs.search("NXOpen", kinds=["type"], limit=50)
    assert types and all(h.kind == "type" for h in types)
    methods = docs.search("Session", kinds=["method"], limit=50)
    assert methods and all(h.kind == "method" for h in methods)


def test_search_summary_matches_prose_not_just_names(fake_install):
    install, _ = fake_install
    docs = ApiDocs(install)
    assert docs.search("extrusion distance", kinds=["property"]) == []
    hits = docs.search("extrusion distance", kinds=["property"], search_summary=True)
    assert [h.qualified for h in hits] == ["NXOpen.Features.ExtrudeBuilder.Distance"]


def test_limit_is_respected(fake_install):
    install, _ = fake_install
    assert len(ApiDocs(install).search("NXOpen", limit=2)) == 2


def test_type_members_lists_the_whole_type(fake_install):
    install, _ = fake_install
    names = {m.qualified for m in ApiDocs(install).type_members("NXOpen.Session")}
    assert "NXOpen.Session" in names
    assert "NXOpen.Session.GetSession" in names


def test_member_lookup_returns_none_for_unknown(fake_install):
    install, _ = fake_install
    assert ApiDocs(install).member("NXOpen.Nope.Nothing") is None


def test_python_stub_search(fake_install):
    install, _ = fake_install
    hits = ApiDocs(install).search_stubs("GetSession")
    assert hits and hits[0]["file"] == "__init__.pyi"


def test_sample_applications_are_listed(fake_install):
    install, _ = fake_install
    assert ApiDocs(install).sample_applications("demo") == ["Python/demo.py"]


def test_docs_unavailable_is_explicit(tmp_path):
    bare = tmp_path / "bare"
    (bare / "NXBIN").mkdir(parents=True)
    (bare / "NXBIN" / "run_journal.exe").write_bytes(b"MZ")
    install = NxInstall(root=bare, release="x", source="test")
    docs = ApiDocs(install)
    assert docs.available() is False
    with pytest.raises(DocsUnavailable) as excinfo:
        docs.search("anything")
    assert "NX_SKILL_NX_ROOT" in (excinfo.value.suggestion or "")
