"""Shared fixtures: a synthetic NX installation and a clean environment.

The tests never need a real NX install. A synthetic tree with the same
structural fingerprint lets discovery, documentation parsing and validation be
tested on any machine, including CI with no CAD software at all.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nx_skill.config import Settings  # noqa: E402


#: A minimal but structurally valid NXOpen documentation file, including a nested
#: <see> element (which naive text extraction truncates) and a release note.
SAMPLE_XML = """<?xml version="1.0"?>
<doc>
  <assembly><name>NXOpen</name></assembly>
  <members>
    <member name="T:NXOpen.Session">
      <summary>Represents the NX session.</summary>
      <remarks><para>Created in NX3.0.0</para></remarks>
    </member>
    <member name="M:NXOpen.Session.GetSession">
      <summary>Gets the singleton for <see cref="T:NXOpen.Session"/>.</summary>
      <returns>the session</returns>
      <remarks><para>Created in NX3.0.0</para></remarks>
    </member>
    <member name="M:NXOpen.Session.SetUndoMark(NXOpen.Session.MarkVisibility,System.String)">
      <summary>Creates an undo mark.</summary>
      <param name="mark_visibility">Visibility of the mark.</param>
      <param name="name">Name of the mark.</param>
      <remarks><para>Created in NX3.0.0</para></remarks>
    </member>
    <member name="T:NXOpen.Features.ExtrudeBuilder">
      <summary>Represents a builder for an extrude feature.</summary>
      <remarks><para>Created in NX5.0.0</para></remarks>
    </member>
    <member name="P:NXOpen.Features.ExtrudeBuilder.Distance">
      <summary>Returns or sets the extrusion distance.</summary>
      <remarks><para>Created in NX2206.0.0</para></remarks>
    </member>
  </members>
</doc>
"""


def build_fake_nx(root: Path, *, release: str = "2512", managed: bool = True) -> Path:
    """Create a directory tree that looks like an NX installation."""
    nxbin = root / "NXBIN"
    nxbin.mkdir(parents=True, exist_ok=True)
    (nxbin / "run_journal.exe").write_bytes(b"MZ")
    (nxbin / "ugraf.exe").write_bytes(b"MZ")
    if managed:
        managed_dir = nxbin / "managed"
        managed_dir.mkdir(parents=True, exist_ok=True)
        (managed_dir / "NXOpen.dll").write_bytes(b"MZ")
        (managed_dir / "NXOpen.xml").write_text(SAMPLE_XML, encoding="utf-8")
    stubs = root / "UGOPEN" / "pythonStubs" / "NXOpen"
    stubs.mkdir(parents=True, exist_ok=True)
    (stubs / "__init__.pyi").write_text(
        "class Session:\n    def GetSession() -> Session: ...\n", encoding="utf-8"
    )
    for module in ("Features", "Assemblies", "Drawings", "CAM", "CAE"):
        (stubs / module).mkdir(parents=True, exist_ok=True)
    python_dir = nxbin / "python"
    python_dir.mkdir(parents=True, exist_ok=True)
    for module in ("Features", "Assemblies", "Drawings", "CAM", "CAE", "UF"):
        (python_dir / f"NXOpen_{module}.pyd").write_bytes(b"\x00")
    examples = root / "UGOPEN" / "SampleNXOpenApplications" / "Python"
    examples.mkdir(parents=True, exist_ok=True)
    (examples / "demo.py").write_text("# sample\n", encoding="utf-8")
    return root


@pytest.fixture(autouse=True)
def isolated_config_dir(tmp_path_factory):
    """Keep generated config out of the real per-user directory.

    \"custom_dirs.dat\" is written under the user profile by default, so without this
    a test run would modify the developer's own NX configuration.
    """
    import os

    config = tmp_path_factory.mktemp("nx-skill-config")
    previous = os.environ.get("NX_SKILL_CONFIG_DIR")
    os.environ["NX_SKILL_CONFIG_DIR"] = str(config)
    try:
        yield config
    finally:
        if previous is None:
            os.environ.pop("NX_SKILL_CONFIG_DIR", None)
        else:
            os.environ["NX_SKILL_CONFIG_DIR"] = previous


@pytest.fixture()
def clean_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Remove every variable this package reads, so tests are machine-independent."""
    names = [
        "NX_SKILL_NX_ROOT", "NX_SKILL_NX_BIN", "NX_SKILL_WORKSPACE",
        "NX_SKILL_LIVE_PORT", "NX_SKILL_AUTO_LAUNCH", "NX_SKILL_AUTO_LAUNCH_TIMEOUT",
        "NX_SKILL_REQUIRE_ONLINE", "NX_SKILL_DELETE_GENERATED",
        "NX_SKILL_SKIP_GLOBAL_SEARCH", "NX_SKILL_PYTHON", "NX_SKILL_LOG_LEVEL",
        "NX_SKILL_CONFIG_DIR", "NX2512_CONFIG_DIR",
        "NX2512_ROOT", "NX2512_BIN", "NX2512_LIVE_PORT", "NX2512_AUTO_LAUNCH",
        "NX2512_AUTO_LAUNCH_TIMEOUT", "NX2512_REQUIRE_ONLINE",
        "NX2512_DELETE_GENERATED_SCRIPTS", "NX2512_SKIP_GLOBAL_SEARCH",
        "NX2512_PROJECT_ROOT", "NX2512_PLUGIN_ROOT", "DC2512_ROOT", "DC2512_BIN",
        "DC2512_PROJECT_ROOT", "UGII_BASE_DIR", "UGII_ROOT_DIR", "NX_ROOT",
        "NXBIN", "SIEMENS_NX_ROOT", "CODEX_PYTHON",
    ]
    for name in names:
        monkeypatch.delenv(name, raising=False)
    return {}


@pytest.fixture()
def no_nx(clean_env, monkeypatch: pytest.MonkeyPatch):
    """Make the machine look like it has no NX installed at all.

    Clearing environment variables is not enough: discovery also consults the
    Windows uninstall registry and the vendor directories, so on a developer
    machine that genuinely has NX the 'no installation' path would never be
    exercised. Neutralising the sources is what makes that path testable.
    """
    from nx_skill import discovery

    monkeypatch.setattr(discovery, "registry_candidates", lambda: [])
    monkeypatch.setattr(discovery, "vendor_bases", lambda: [])
    monkeypatch.setattr(discovery, "fixed_drive_roots", lambda: [])
    return monkeypatch


@pytest.fixture()
def fake_install(tmp_path: Path):
    """A synthetic NX installation plus matching settings."""
    from nx_skill.discovery import NxInstall, detect_capabilities, detect_release

    root = build_fake_nx(tmp_path / "NX 2512")
    settings = Settings(workspace=tmp_path / "workspace", nx_root=root, skip_global_search=True)
    install = NxInstall(
        root=root,
        release=detect_release(root),
        source="fixture",
        capabilities=detect_capabilities(root),
    )
    return install, settings