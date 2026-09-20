import json
import os
import runpy

import NXOpen


def main(script_path, params_json="{}"):
    full_path = os.path.abspath(script_path)
    if not os.path.isfile(full_path):
        raise RuntimeError("Python script does not exist: " + full_path)

    # Parameters are published to the journal through the environment. The legacy
    # names are kept in step so journals written for the earlier plugin keep working.
    os.environ["NX_SKILL_PARAMS_JSON"] = params_json or "{}"
    os.environ["NX_SKILL_SCRIPT_PATH"] = full_path
    os.environ["NX_CODEX_PARAMS_JSON"] = os.environ["NX_SKILL_PARAMS_JSON"]
    os.environ["NX_CODEX_SCRIPT_PATH"] = full_path

    try:
        json.loads(os.environ["NX_SKILL_PARAMS_JSON"])
    except Exception:
        os.environ["NX_SKILL_PARAMS_JSON"] = "{}"
        os.environ["NX_CODEX_PARAMS_JSON"] = "{}"

    result_globals = runpy.run_path(full_path, run_name="__main__")

    session = NXOpen.Session.GetSession()
    session.ListingWindow.Open()
    session.ListingWindow.WriteLine("NX skill executed Python script: " + full_path)

    if "NX_SKILL_RESULT" in result_globals:
        return str(result_globals["NX_SKILL_RESULT"])
    return str(result_globals.get("NX_CODEX_RESULT", "OK"))
