"""Human-paced review executor: a Block Styler dialog that lives inside NX.

This is the other half of :mod:`nx_skill.review`. It is loaded from this
package's NX custom directory (see `nx_runtime/custom_dirs.dat.template`) and
opened from the NX menu, so it runs **on NX's main thread inside the visible
session**. That is the point: the user watches every step happen, and nothing is
executed behind their back.

Design notes that are not obvious:

* **No listener, no .NET, no background thread.** An in-NX socket server would
  have to call NXOpen from a non-main thread, which is what makes the .NET
  Remoting bridge fragile: it works until a modal dialog appears and then hangs.
  Here the human is the synchronisation mechanism, so none of that is needed.

* **One visible undo mark per step.** `SetUndoMark` is called *before* a step
  runs, so `UndoToMark` reverts exactly that step. "Undo last step" is therefore
  an exact operation rather than a re-run, which matters when a step took minutes.

* **A failure does not auto-undo.** A part-built feature is evidence, and the
  person may want to look at it before deciding. The dialog offers the undo
  explicitly instead of guessing.

* **A manual gate is not a restriction on the human.** Clicking "run next step"
  is itself the approval; the gate exists so that "run all automatic" *stops*
  before a solve, a save or an export.

Written without f-strings and without type annotations because NX releases embed
different Python versions; older installs embed Python 2.7.
"""

import datetime
import json
import os
import runpy
import time
import traceback

import NXOpen
import NXOpen.BlockStyler
import NXOpen.Gateway


DLX_NAME = "nx_review_executor.dlx"

#: How each run status is rendered in the step list.
STATUS_MARK = {
    "pending": "[    ]",
    "running": "[ .. ]",
    "done": "[ ok ]",
    "failed": "[FAIL]",
    "undone": "[undo]",
    "skipped": "[skip]",
}

DIALOG_TITLE = "NX Skill Review"


def _env(name, *fallbacks):
    """Read NX_SKILL_<name>, then the legacy names used by the earlier plugins."""
    for candidate in ("NX_SKILL_" + name,) + fallbacks:
        value = os.environ.get(candidate)
        if value and value.strip():
            return value.strip()
    return None


def _default_workspace():
    return os.path.join(os.path.expanduser("~"), "NXSkillWorkspace")


def _workspace():
    return _env("WORKSPACE", "NX2512_PROJECT_ROOT", "DC2512_PROJECT_ROOT") or _default_workspace()


def _review_dir():
    explicit = _env("REVIEW_DIR", "NX2512_REVIEW_DIR")
    if explicit:
        return explicit
    return os.path.join(_workspace(), "review")


def _safe_name(text):
    return "".join(c if (c.isalnum() or c in "._-") else "_" for c in str(text))


def _read_json(path):
    if not os.path.isfile(path):
        return None
    try:
        stream = open(path, "r")
        try:
            return json.load(stream)
        finally:
            stream.close()
    except Exception:
        return None


def _write_json(path, payload):
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    temporary = path + ".tmp"
    stream = open(temporary, "w")
    try:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
    finally:
        stream.close()
    try:
        os.replace(temporary, path)
    except AttributeError:
        if os.path.exists(path):
            os.remove(path)
        os.rename(temporary, path)


class ReviewExecutor(object):
    """The review dialog and the state it drives."""

    def __init__(self):
        self.session = NXOpen.Session.GetSession()
        self.ui = NXOpen.UI.GetUI()

        self.review_dir = _review_dir()
        self.plan_path = os.path.join(self.review_dir, "plan.json")
        self.log_path = os.path.join(self.review_dir, "run.json")
        self.scripts_dir = os.path.join(self.review_dir, "scripts")
        self.screenshots_dir = os.path.join(self.review_dir, "screenshots")

        self.plan = None
        self.log = {"planId": "", "started": 0, "updated": 0, "steps": []}
        #: (step_id, undo mark id, mark name) for marks created in this session.
        self.marks = []

        self.dialog, self.dialog_spec = self._create_dialog()
        self.dialog.AddInitializeHandler(self.initialize_cb)
        self.dialog.AddDialogShownHandler(self.dialog_shown_cb)
        self.dialog.AddUpdateHandler(self.update_cb)
        self.dialog.AddOkHandler(self.ok_cb)
        self.dialog.AddApplyHandler(self.apply_cb)
        self.dialog.AddCancelHandler(self.cancel_cb)

        self.status_label = None
        self.step_list = None
        self.run_next_button = None
        self.undo_last_button = None
        self.run_auto_button = None
        self.refresh_button = None

    def _create_dialog(self):
        """Create the dialog, trying the likely locations for the .dlx file.

        NX looks for a dialog by name along its custom-directory search path, which
        is how every vendor sample does it -- but that path depends on
        "UGII_CUSTOM_DIRECTORY_FILE" being set for *this* process, which is exactly
        the thing that is easy to get wrong on a new machine. Falling back to the
        absolute path next to this script removes that dependency, and the chosen
        spec is logged so the first run says which one worked.
        """
        here = os.path.dirname(os.path.abspath(__file__))
        candidates = [DLX_NAME, os.path.join(here, DLX_NAME)]
        failure = None
        for spec in candidates:
            try:
                dialog = self.ui.CreateDialog(spec)
            except Exception as exc:
                failure = exc
                continue
            if dialog is not None:
                return dialog, spec
        raise RuntimeError(
            "Could not create the review dialog. Tried %s. Last error: %s"
            % (candidates, failure)
        )

    # ------------------------------------------------------------------
    # Block Styler callbacks
    # ------------------------------------------------------------------

    def initialize_cb(self):
        top = self.dialog.TopBlock
        self.status_label = top.FindBlock("status_label")
        self.step_list = top.FindBlock("step_list")
        self.run_next_button = top.FindBlock("run_next")
        self.undo_last_button = top.FindBlock("undo_last")
        self.run_auto_button = top.FindBlock("run_auto")
        self.refresh_button = top.FindBlock("refresh")
        self._set_status("Loading plan...")

    def dialog_shown_cb(self):
        self.reload()

    def update_cb(self, block):
        try:
            if block == self.run_next_button:
                self.run_next()
            elif block == self.run_auto_button:
                self.run_auto()
            elif block == self.undo_last_button:
                self.undo_last()
            elif block == self.refresh_button:
                self.reload()
        except Exception as exc:
            self._report("Review step failed", exc)
        self._refresh()
        return 0

    def ok_cb(self):
        return 0

    def apply_cb(self):
        return 0

    def cancel_cb(self):
        return 0

    # ------------------------------------------------------------------
    # Plan state
    # ------------------------------------------------------------------

    def reload(self):
        self._write_listing(
            "dialog '%s' | review dir %s" % (self.dialog_spec, self.review_dir)
        )
        if not os.path.isfile(self.plan_path):
            self._write_listing(
                "no plan at %s -- is NX_SKILL_WORKSPACE the same for NX and the agent?" % self.plan_path
            )
        self.plan = _read_json(self.plan_path)
        loaded = _read_json(self.log_path)
        if isinstance(loaded, dict):
            self.log = loaded
        if not isinstance(self.log.get("steps"), list):
            self.log["steps"] = []
        if self.plan is None:
            self._set_status(
                "No plan found.\nExpected: %s\n\nAsk the agent to submit a review plan." % self.plan_path
            )
        else:
            if self.log.get("planId") != self.plan.get("planId"):
                # A different plan is in place, so earlier records describe a
                # different model and must not be shown as this plan's progress.
                self.log = {
                    "planId": self.plan.get("planId", ""),
                    "started": time.time(),
                    "updated": time.time(),
                    "steps": [],
                }
            self._set_status("Loaded plan %s with %d step(s)." % (self.plan.get("planId", "?"), len(self.plan.get("steps") or [])))

    def _records(self):
        return dict((r.get("id"), r) for r in self.log.get("steps") or [])

    def _step_index(self, step_id):
        for index, step in enumerate(self.plan.get("steps") or []):
            if step.get("id") == step_id:
                return index
        return None

    def _next_pending_index(self):
        if not isinstance(self.plan, dict):
            return None
        records = self._records()
        for index, step in enumerate(self.plan.get("steps") or []):
            record = records.get(step.get("id"))
            if record is None or record.get("status") in ("pending", "failed", "undone"):
                return index
        return None

    def _auto_range(self):
        start = self._next_pending_index()
        if start is None:
            return []
        records = self._records()
        chosen = []
        for index in range(start, len(self.plan.get("steps") or [])):
            step = self.plan["steps"][index]
            record = records.get(step.get("id"))
            if record is not None and record.get("status") == "done":
                continue
            if str(step.get("gate") or "manual") != "auto":
                break
            chosen.append(index)
        return chosen

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def run_next(self):
        index = self._next_pending_index()
        if index is None:
            self._set_status("Every step is complete. Review the screenshots and the run log.")
            return
        self._execute(index)

    def run_auto(self):
        pending = self._auto_range()
        if not pending:
            following = self._next_pending_index()
            if following is None:
                self._set_status("Every step is complete.")
            else:
                name = self.plan["steps"][following].get("name")
                self._set_status(
                    "Stopped at the manual gate %s.\n\nThis step needs a person to approve it: "
                    "use Run Next Step when you are ready." % name
                )
            return
        for index in pending:
            if not self._execute(index):
                break

    def undo_last(self):
        """Revert the most recent step exactly, using its undo mark."""
        try:
            if self.marks:
                step_id, mark_id, mark_name = self.marks.pop()
                self.session.UndoToMark(mark_id, mark_name)
            else:
                # Reopened dialog, or a mark from an earlier session: the visible
                # marks are still named, so the last one is the right target.
                self.session.UndoToLastVisibleMark()
                step_id = None
                mark_name = ""

            record = None
            if step_id is not None:
                record = self._records().get(step_id)
            if record is None:
                for candidate in reversed(self.log.get("steps") or []):
                    if candidate.get("status") == "done":
                        record = candidate
                        break
            if record is not None:
                record["status"] = "undone"
                record["message"] = "Reverted by the reviewer."
                self._save_log()
                self._set_status("Reverted %s. The model is back to the state before that step." % record.get("name"))
            else:
                self._set_status("Undid the last visible operation in NX.")
        except Exception as exc:
            self._report("Undo failed", exc)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def _execute(self, index):
        steps = self.plan.get("steps") or []
        if index >= len(steps):
            return False
        step = steps[index]
        name = str(step.get("name") or step.get("id"))

        # The mark is created BEFORE the step, so undoing to it removes exactly
        # this step's changes and nothing earlier.
        mark_id = self.session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible, name)
        self.marks.append((step.get("id"), mark_id, name))

        record = {
            "id": step.get("id"),
            "name": name,
            "status": "running",
            "undoMark": name,
            "screenshot": "",
            "message": "",
            "executionState": "not_started",
            "started": time.time(),
            "durationSeconds": 0.0,
        }
        self._upsert(record)
        self._save_log()
        self._refresh()

        started = time.time()
        try:
            message = self._run_operation(step)
            record["status"] = "done"
            record["executionState"] = "succeeded"
            record["message"] = message or ""
        except Exception as exc:
            record["status"] = "failed"
            record["executionState"] = "failed"
            record["message"] = str(exc)
            record["traceback"] = traceback.format_exc()
            self._report("Step %s failed" % name, exc)

        record["durationSeconds"] = time.time() - started
        try:
            shot = self._screenshot(name)
            if shot:
                record["screenshot"] = shot
        except Exception as exc:
            # A missing screenshot must never mark a successful step as failed.
            record["message"] = (record.get("message") or "") + " [screenshot unavailable: %s]" % exc

        self._upsert(record)
        self._save_log()
        return record["status"] == "done"

    def _run_operation(self, step):
        operation = str(step.get("operation") or "")
        params = step.get("params") or {}

        if operation == "noop":
            return "no-op"

        if operation == "status":
            part = self.session.Parts.Work
            if part is None:
                return "no work part"
            return "work part: " + str(part.Name)

        if operation == "screenshot":
            return "screenshot only"

        if operation == "journal":
            relative = str(params.get("path") or "")
            if not relative:
                raise RuntimeError("journal step has no params.path")
            target = os.path.join(self.scripts_dir, relative)
            if not os.path.isfile(target):
                raise RuntimeError("journal not found: " + target)
            runpy.run_path(target, run_name="__main__")
            return "ran " + relative

        if operation == "create_block":
            part = self.session.Parts.Work
            if part is None:
                raise RuntimeError("No work part is open in the current NX window.")
            self.session.ApplicationSwitchImmediate("UG_APP_MODELING")
            builder = part.Features.CreateBlockFeatureBuilder(None)
            try:
                builder.SetOriginAndLengths(
                    NXOpen.Point3d(0.0, 0.0, 0.0),
                    str(params.get("length", 80)),
                    str(params.get("width", 50)),
                    str(params.get("height", 25)),
                )
                feature = builder.CommitFeature()
            finally:
                builder.Destroy()
            feature_name = params.get("feature_name") or step.get("name")
            if feature_name:
                try:
                    feature.SetName(str(feature_name))
                except Exception:
                    pass
            part.ModelingViews.WorkView.Fit()
            return "created block %s" % feature_name

        raise RuntimeError("unknown operation: " + operation)

    def _screenshot(self, stage_name):
        """Capture the graphics window so the reviewer has a visual record.

        RegionMode defaults to capturing the whole graphics window, which is what
        an audit trail wants; the rectangular-region path is deliberately unused.
        """
        part = None
        try:
            part = self.session.Parts.Display
        except Exception:
            part = None
        if part is None:
            part = self.session.Parts.Work
        if part is None:
            return None

        if not os.path.isdir(self.screenshots_dir):
            os.makedirs(self.screenshots_dir)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        target = os.path.join(self.screenshots_dir, "%s_%s.png" % (_safe_name(stage_name), stamp))

        builder = part.Views.CreateImageExportBuilder()
        try:
            builder.FileName = target
            builder.FileFormat = NXOpen.Gateway.ImageExportBuilder.FileFormats.Png
            builder.Commit()
        finally:
            builder.Destroy()
        return target if os.path.isfile(target) else None

    # ------------------------------------------------------------------
    # Log + UI plumbing
    # ------------------------------------------------------------------

    def _upsert(self, record):
        steps = self.log.setdefault("steps", [])
        for index, existing in enumerate(steps):
            if existing.get("id") == record.get("id"):
                steps[index] = record
                break
        else:
            steps.append(record)
        self.log["updated"] = time.time()
        if not self.log.get("planId") and isinstance(self.plan, dict):
            self.log["planId"] = self.plan.get("planId", "")

    def _save_log(self):
        try:
            _write_json(self.log_path, self.log)
        except Exception as exc:
            self.ui.NXMessageBox.Show(
                DIALOG_TITLE, NXOpen.NXMessageBox.DialogType.Warning,
                "The run log could not be written to %s\n%s" % (self.log_path, exc),
            )

    def _refresh(self):
        if self.step_list is None:
            return
        records = self._records()
        lines = []
        for index, step in enumerate(self.plan.get("steps") or [] if isinstance(self.plan, dict) else []):
            record = records.get(step.get("id"))
            status = (record or {}).get("status", "pending")
            mark = STATUS_MARK.get(status, "[    ]")
            gate = "A" if str(step.get("gate") or "manual") == "auto" else "M"
            note = (record or {}).get("message") or step.get("note") or ""
            lines.append("%s %s %s  %s" % (mark, gate, step.get("name"), note))
        self.step_list.SetListItems(lines)

        pending = self._next_pending_index()
        if isinstance(self.plan, dict) and pending is not None:
            try:
                self.step_list.SelectedItemIndex = pending
            except Exception:
                pass

    def _set_status(self, text):
        if self.status_label is not None:
            try:
                self.status_label.Label = text
            except Exception:
                pass
        self._write_listing(text)

    def _write_listing(self, text):
        try:
            window = self.session.ListingWindow
            window.Open()
            window.WriteLine("[nx-skill review] " + str(text).replace("\n", " "))
        except Exception:
            pass

    def _report(self, title, exc):
        message = "%s\n\n%s\n\n%s" % (title, exc, traceback.format_exc())
        try:
            self.ui.NXMessageBox.Show(DIALOG_TITLE, NXOpen.NXMessageBox.DialogType.Error, message)
        except Exception:
            pass
        self._write_listing(message)

    # ------------------------------------------------------------------

    def launch(self):
        return self.dialog.Launch()

    def dispose(self):
        if self.dialog is not None:
            self.dialog.Dispose()
            self.dialog = None


def main():
    session = NXOpen.Session.GetSession()
    if session.Parts.Work is None and session.Parts.Display is None:
        # Block Styler blocks behave badly without a part loaded, so say so
        # plainly rather than letting the dialog open in a broken state.
        NXOpen.UI.GetUI().NXMessageBox.Show(
            DIALOG_TITLE,
            NXOpen.NXMessageBox.DialogType.Warning,
            "Open or create a part first. The review blocks need a part loaded in NX.",
        )
        return

    executor = ReviewExecutor()
    try:
        executor.launch()
    finally:
        executor.dispose()


if __name__ == "__main__":
    main()
