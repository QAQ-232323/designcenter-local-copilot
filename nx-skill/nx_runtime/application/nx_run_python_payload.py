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

    try:
        result_globals = runpy.run_path(full_path, run_name="__main__")
    except Exception:
        # NX 对外只会说"无法执行 python 脚本,请参见系统日志"——对调用方毫无信息量,
        # 而真正的 traceback(常见:用了 NXOpen.Features.X 却没 import NXOpen.Features)
        # 只落在系统日志里。所以这里把它落到脚本旁边的 .error.txt,同时写进信息窗口,
        # 然后**原样抛出**:执行状态仍然是失败(不能被吞成"成功"),但原因可读了。
        import traceback
        text = traceback.format_exc()
        try:
            with open(full_path + ".error.txt", "w") as handle:
                handle.write(text)
        except Exception:
            pass
        try:
            listing = NXOpen.Session.GetSession().ListingWindow
            listing.Open()
            listing.WriteLine("NX skill: python script failed, traceback follows")
            listing.WriteLine(text)
        except Exception:
            pass
        raise

    session = NXOpen.Session.GetSession()
    session.ListingWindow.Open()
    session.ListingWindow.WriteLine("NX skill executed Python script: " + full_path)

    if "NX_SKILL_RESULT" in result_globals:
        return str(result_globals["NX_SKILL_RESULT"])
    return str(result_globals.get("NX_CODEX_RESULT", "OK"))
