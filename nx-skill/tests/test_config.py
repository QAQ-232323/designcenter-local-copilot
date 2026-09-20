"""The environment contract: canonical names, legacy fallback, validation."""

from __future__ import annotations

import pytest

from nx_skill.config import ConfigError, Settings, env_bool, env_int, env_lookup, package_root


def test_defaults_need_no_configuration(clean_env):
    settings = Settings.from_env()
    assert settings.live_port == 25121
    assert settings.auto_launch is True
    assert settings.skip_global_search is False
    assert settings.workspace.name == "NXSkillWorkspace"
    assert settings.nx_root is None


def test_canonical_names_win_over_legacy(clean_env, monkeypatch):
    monkeypatch.setenv("NX2512_LIVE_PORT", "11111")
    monkeypatch.setenv("NX_SKILL_LIVE_PORT", "22222")
    assert Settings.from_env().live_port == 22222


def test_legacy_names_are_still_honoured(clean_env, monkeypatch):
    """Existing installs from the earlier plugins must keep working."""
    monkeypatch.setenv("NX2512_ROOT", r"D:\Siemens\NX 2512")
    monkeypatch.setenv("NX2512_LIVE_PORT", "26001")
    monkeypatch.setenv("NX2512_PROJECT_ROOT", r"D:\work")
    settings = Settings.from_env()
    assert str(settings.nx_root) == r"D:\Siemens\NX 2512"
    assert settings.live_port == 26001
    assert str(settings.workspace) == r"D:\work"


def test_ugii_variables_are_accepted_as_roots(clean_env, monkeypatch):
    monkeypatch.setenv("UGII_BASE_DIR", r"D:\Program Files\Siemens\DC 2606")
    assert str(Settings.from_env().nx_root) == r"D:\Program Files\Siemens\DC 2606"


@pytest.mark.parametrize("value,expected", [("true", True), ("YES", True), ("off", False), ("0", False)])
def test_boolean_spellings(clean_env, monkeypatch, value, expected):
    monkeypatch.setenv("NX_SKILL_AUTO_LAUNCH", value)
    assert Settings.from_env().auto_launch is expected


def test_boolean_rejects_nonsense(clean_env, monkeypatch):
    monkeypatch.setenv("NX_SKILL_AUTO_LAUNCH", "maybe")
    with pytest.raises(ConfigError):
        Settings.from_env()


def test_integer_rejects_nonsense(clean_env, monkeypatch):
    monkeypatch.setenv("NX_SKILL_LIVE_PORT", "not-a-port")
    with pytest.raises(ConfigError):
        Settings.from_env()


def test_port_range_is_validated():
    with pytest.raises(ConfigError):
        Settings(live_port=70000)


def test_empty_value_falls_through_to_default(clean_env, monkeypatch):
    """An empty variable must not be treated as an intentional blank value."""
    monkeypatch.setenv("NX_SKILL_NX_ROOT", "   ")
    assert Settings.from_env().nx_root is None


def test_overrides_do_not_mutate(clean_env):
    base = Settings.from_env()
    derived = base.with_overrides(live_port=1234)
    assert derived.live_port == 1234
    assert base.live_port == 25121


def test_generated_paths_live_under_the_workspace_or_config(clean_env):
    settings = Settings.from_env()
    assert package_root().name == "nx-skill"
    assert settings.generated_root().parent == settings.workspace
    assert settings.custom_directory_file().name == "custom_dirs.dat"
    assert "nx-skill" in str(settings.custom_directory_file()).lower()
