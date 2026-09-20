import os

import NXOpen


APPLICATION_DIR = os.path.dirname(os.path.abspath(__file__))
RUNTIME_ROOT = os.path.dirname(APPLICATION_DIR)
PACKAGE_ROOT = os.path.dirname(RUNTIME_ROOT)


def _env(name, *fallback_names):
    """Read NX_SKILL_<name>, then the legacy names used by the earlier plugins."""
    for candidate in ("NX_SKILL_" + name,) + fallback_names:
        value = os.environ.get(candidate)
        if value and value.strip():
            return value.strip()
    return None


def _default_project_root():
    """A writable workspace that exists on any machine and needs no configuration."""
    return os.path.join(os.path.expanduser("~"), "NXSkillWorkspace")


SERVER_DLL = _env("LIVE_BRIDGE_DLL", "NX2512_LIVE_BRIDGE_DLL") or os.path.join(
    RUNTIME_ROOT, "startup", "NxLiveBridgeServer.dll"
)
SERVER_CLASS = "NxLiveBridgeServer"


def main():
    session = NXOpen.Session.GetSession()
    session.ListingWindow.Open()

    if not os.path.isfile(SERVER_DLL):
        session.ListingWindow.WriteLine("NX skill live bridge DLL is missing: " + SERVER_DLL)
        session.ListingWindow.WriteLine(
            "Run: powershell -NoProfile -ExecutionPolicy Bypass -File "
            + os.path.join(PACKAGE_ROOT, "scripts", "build_dotnet_bridge.ps1")
        )
        return

    session.Execute(SERVER_DLL, SERVER_CLASS, "Start", [])
    session.ListingWindow.WriteLine("NX skill live bridge requested.")


if __name__ == "__main__":
    main()
