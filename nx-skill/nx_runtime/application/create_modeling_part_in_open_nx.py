import datetime
import os

import NXOpen
import NXOpen.Features


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


PROJECT_ROOT = _env("PROJECT_ROOT", "NX2512_PROJECT_ROOT") or _default_project_root()


def main():
    session = NXOpen.Session.GetSession()

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    if not os.path.isdir(PROJECT_ROOT):
        os.makedirs(PROJECT_ROOT)
    part_path = os.path.join(PROJECT_ROOT, "nx_in_open_window_modeling_%s.prt" % timestamp)

    part = session.Parts.NewDisplay(part_path, NXOpen.Part.Units.Millimeters)
    session.Parts.SetWork(part)
    session.Parts.SetDisplay(part, False, False)
    session.ApplicationSwitchImmediate("UG_APP_MODELING")

    block_builder = part.Features.CreateBlockFeatureBuilder(None)
    block_builder.SetOriginAndLengths(NXOpen.Point3d(0.0, 0.0, 0.0), "80", "50", "25")
    block_builder.CommitFeature()
    block_builder.Destroy()

    part.ModelingViews.WorkView.Fit()
    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)

    session.ListingWindow.Open()
    session.ListingWindow.WriteLine("Created in already open NX window: " + part_path)


if __name__ == "__main__":
    main()
