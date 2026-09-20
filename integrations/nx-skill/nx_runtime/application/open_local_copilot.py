"""Open the local Copilot host page inside Designcenter.

This is the working replacement for the built-in UG_APP_COPILOT command:
that command is gated behind "Designcenter X" and does nothing on a classic
install, while NXOpen.UF.UFUi.DisplayUrl carries "License requirements: None".

The page is served by the local host in plchat-local/ (plchat-local\\start.cmd).
Override the address with the NX_SKILL_COPILOT_URL environment variable.
"""
import os

import NXOpen
import NXOpen.UF

DEFAULT_URL = "http://127.0.0.1:8765/"


def _url():
    value = os.environ.get("NX_SKILL_COPILOT_URL")
    if value and value.strip():
        return value.strip()
    return DEFAULT_URL


def main():
    session = NXOpen.Session.GetSession()
    listing = session.ListingWindow
    listing.Open()
    url = _url()
    uf = NXOpen.UF.UFSession.GetUFSession()

    try:
        uf.Ui.DisplayUrlAndActivate(url)
        listing.WriteLine("Copilot (local) opened: " + url)
        return
    except Exception as exc:  # noqa: BLE001 - report, then try the plain call
        listing.WriteLine("DisplayUrlAndActivate failed: %s" % exc)

    try:
        uf.Ui.DisplayUrl(url)
        listing.WriteLine("Copilot (local) opened: " + url)
    except Exception as exc:  # noqa: BLE001
        listing.WriteLine("DisplayUrl failed: %s" % exc)
        listing.WriteLine("Please open this address in a browser manually: " + url)


if __name__ == "__main__":
    main()
