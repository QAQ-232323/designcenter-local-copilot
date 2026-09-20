"""Registering this package as an NX custom directory."""

from __future__ import annotations

import sys

import pytest

from nx_skill import loader
from nx_skill.config import Settings

#: Captured before any fixture runs, so the guard test below can prove the module
#: was actually patched. Without the fixture these tests write to -- and delete
#: from -- the real HKCU\Environment, which silently breaks every other NX
#: customisation on the machine.
_REAL_READ = loader._read_user_env
_REAL_WRITE = loader._write_user_env


@pytest.fixture(autouse=True)
def fake_user_environment(monkeypatch):
    """Keep every user-environment read and write inside this test process."""
    state: dict[str, str] = {}

    monkeypatch.setattr(loader, "_read_user_env", lambda name: state.get(name))

    def fake_write(name: str, value: str | None) -> bool:
        if value is None:
            state.pop(name, None)
        else:
            state[name] = value
        return True

    monkeypatch.setattr(loader, "_write_user_env", fake_write)
    monkeypatch.setattr(loader, "_broadcast_environment_change", lambda: None)
    return state


def test_the_suite_is_isolated_from_the_real_user_environment():
    """Guard: if this fails, the other tests here are mutating the machine."""
    assert loader._write_user_env is not _REAL_WRITE
    assert loader._read_user_env is not _REAL_READ


def test_install_and_uninstall_leave_the_real_editor_untouched(settings: Settings):
    """End-to-end proof: a full cycle changes nothing outside the fake state."""
    before = _REAL_READ(loader.ENV_NAME)
    loader.install(settings)
    loader.uninstall(settings)
    assert _REAL_READ(loader.ENV_NAME) == before


@pytest.fixture()
def settings(tmp_path) -> Settings:
    return Settings(workspace=tmp_path / "ws", skip_global_search=True)


def test_status_is_not_installed_on_a_clean_machine(settings: Settings):
    report = loader.status(settings)
    assert report["installed"] is False
    assert report["customDirectoryFileExists"] is False
    assert report["packageRuntimeRoot"].endswith("nx_runtime")


def test_install_writes_a_file_pointing_at_this_package(settings: Settings):
    report = loader.install(settings)
    target = settings.custom_directory_file()
    assert target.is_file()
    content = target.read_text(encoding="utf-8")
    assert str(settings.runtime_root()) in content
    assert content.startswith("#")
    assert report["customDirectoryFileWritten"] is True


def test_install_is_idempotent(settings: Settings):
    loader.install(settings)
    first = settings.custom_directory_file().read_text(encoding="utf-8")
    loader.install(settings)
    assert settings.custom_directory_file().read_text(encoding="utf-8") == first


def test_status_detects_a_file_that_points_somewhere_else(settings: Settings):
    """A stale file from another project must not be reported as installed."""
    target = settings.custom_directory_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# someone else's\nD:\\OtherProject\\nx_runtime\n", encoding="utf-8")
    report = loader.status(settings)
    assert report["customDirectoryFileExists"] is True
    assert report["customDirectoryPointsHere"] is False
    assert report["pointedAt"] == "D:\\OtherProject\\nx_runtime"
    assert report["installed"] is False


def test_the_generated_file_has_exactly_one_path_line(settings: Settings):
    """NX parses this file; a stray non-comment line silently adds a search root."""
    loader.write_custom_directory_file(settings)
    lines = [
        line
        for line in settings.custom_directory_file().read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert lines == [str(settings.runtime_root())]


@pytest.mark.skipif(sys.platform != "win32", reason="user environment writes are Windows-only")
def test_install_reports_the_environment_variable_it_set(settings: Settings):
    report = loader.install(settings)
    assert report["envVariable"] == loader.ENV_NAME
    assert report["expectedEnvValue"] == str(settings.custom_directory_file())


# -- coexistence with other NX customisations ---------------------------------


@pytest.fixture()
def other_project(tmp_path, fake_user_environment):
    """Simulate another NX customisation already owning the environment variable."""
    other_root = tmp_path / "OtherProject" / "nx_runtime"
    other_root.mkdir(parents=True)
    other_file = tmp_path / "OtherProject" / "custom_dirs.dat"
    other_file.write_text(
        "# someone else's registration\n" + str(other_root) + "\n",
        encoding="utf-8",
    )
    fake_user_environment[loader.ENV_NAME] = str(other_file)
    return other_root, other_file


def test_install_preserves_the_previous_registration(settings: Settings, other_project):
    """Installing must not silently disable every other NX customisation."""
    other_root, _ = other_project
    loader.install(settings)
    roots = loader.status(settings)["preservedRoots"]
    assert str(settings.runtime_root()) in roots
    assert str(other_root) in roots


def test_install_reports_what_it_replaced(settings: Settings, other_project):
    _, other_file = other_project
    report = loader.install(settings)
    assert report["replacedRegistration"] == str(other_file)
    assert report["installed"] is True
    assert "carried over" in report["note"]


def test_preserved_roots_is_empty_without_a_previous_registration(settings: Settings, fake_user_environment):
    assert loader.preserved_roots(settings) == []


def test_preserved_roots_is_empty_when_the_pointer_is_already_ours(
    settings: Settings, fake_user_environment
):
    loader.write_custom_directory_file(settings, extra_roots=())
    fake_user_environment[loader.ENV_NAME] = str(settings.custom_directory_file())
    assert loader.preserved_roots(settings) == []


def test_preserved_roots_excludes_our_own_runtime(tmp_path, settings: Settings, fake_user_environment):
    """A file that already lists us plus someone else keeps only the someone else."""
    other = tmp_path / "elsewhere"
    other.mkdir()
    shared = tmp_path / "shared.dat"
    shared.write_text(
        str(settings.runtime_root()) + "\n" + str(other) + "\n",
        encoding="utf-8",
    )
    fake_user_environment[loader.ENV_NAME] = str(shared)
    assert loader.preserved_roots(settings) == [str(other)]


def test_preserved_roots_deduplicates(settings: Settings, tmp_path, fake_user_environment):
    other = tmp_path / "elsewhere"
    other.mkdir()
    shared = tmp_path / "shared.dat"
    shared.write_text(str(other) + "\n" + str(other) + "\n", encoding="utf-8")
    fake_user_environment[loader.ENV_NAME] = str(shared)
    assert loader.preserved_roots(settings) == [str(other)]


def test_content_has_no_preserved_section_when_there_is_nothing_to_preserve(settings: Settings):
    content = loader.custom_directory_content(settings, [])
    assert "Carried over" not in content
    assert str(settings.runtime_root()) in content


def test_uninstall_does_not_delete_the_generated_file(settings: Settings):
    """Removing the registration should not destroy a file another tool may read."""
    loader.install(settings)
    loader.uninstall(settings)
    assert settings.custom_directory_file().is_file()
    assert loader.status(settings)["customDirectoryFileExists"] is True