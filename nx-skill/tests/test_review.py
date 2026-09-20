"""The human-paced review contract between the agent and the NX dialog."""

from __future__ import annotations

import json

import pytest

from nx_skill.config import Settings
from nx_skill.review import (
    GATE_AUTO,
    GATE_MANUAL,
    PlanError,
    ReviewPlan,
    ReviewStore,
    RunLog,
    Step,
    StepRecord,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_UNDONE,
)


@pytest.fixture()
def store(tmp_path) -> ReviewStore:
    return ReviewStore(Settings(workspace=tmp_path / "ws", skip_global_search=True))


def _plan(steps):
    return {"prompt": "test", "steps": steps}


BASE_STEPS = [
    {"id": "01", "name": "01_Base_Sketch", "operation": "journal", "gate": "auto", "params": {"path": "a.py"}},
    {"id": "02", "name": "02_Base_Extrude", "operation": "create_block", "gate": "auto"},
    {"id": "03", "name": "03_Solve", "operation": "journal", "gate": "manual", "params": {"path": "b.py"}},
    {"id": "04", "name": "04_Export", "operation": "status", "gate": "auto"},
]


# -- plan validation --------------------------------------------------------


def test_a_valid_plan_round_trips():
    plan = ReviewPlan.from_dict(_plan(BASE_STEPS))
    assert [s.name for s in plan.steps][:2] == ["01_Base_Sketch", "02_Base_Extrude"]
    assert ReviewPlan.from_dict(plan.to_dict()).to_dict() == plan.to_dict()


def test_steps_default_to_the_manual_gate():
    """The safe default: an unlabelled step is one a human must approve."""
    plan = ReviewPlan.from_dict(_plan([{"name": "01_Thing", "operation": "noop"}]))
    assert plan.steps[0].gate == GATE_MANUAL


def test_an_empty_plan_is_rejected():
    with pytest.raises(PlanError):
        ReviewPlan.from_dict({"steps": []})


def test_unknown_operation_is_rejected_with_the_known_ones():
    with pytest.raises(PlanError) as excinfo:
        ReviewPlan.from_dict(_plan([{"name": "01_X", "operation": "rm_rf"}]))
    assert "Known operations" in (excinfo.value.suggestion or "")


def test_step_names_must_be_numbered():
    """The number is what makes the Part Navigator read as an ordered history."""
    with pytest.raises(PlanError) as excinfo:
        ReviewPlan.from_dict(_plan([{"name": "Base_Extrude", "operation": "noop"}]))
    assert "numbered convention" in excinfo.value.message


def test_duplicate_step_ids_are_rejected():
    duplicate = [
        {"id": "01", "name": "01_A", "operation": "noop"},
        {"id": "01", "name": "02_B", "operation": "noop"},
    ]
    with pytest.raises(PlanError) as excinfo:
        ReviewPlan.from_dict(_plan(duplicate))
    assert "Duplicate step id" in excinfo.value.message


def test_unknown_gate_is_rejected():
    with pytest.raises(PlanError):
        ReviewPlan.from_dict(_plan([{"name": "01_A", "operation": "noop", "gate": "whenever"}]))


def test_a_missing_name_is_generated_from_the_position():
    plan = ReviewPlan.from_dict(_plan([{"operation": "noop"}, {"operation": "noop"}]))
    assert plan.steps[0].name == "01_Step"
    assert plan.steps[1].name == "02_Step"


# -- gate semantics ---------------------------------------------------------


def _log_with(done_ids):
    log = RunLog()
    for step_id in done_ids:
        log.upsert(StepRecord(id=step_id, name=step_id, status=STATUS_DONE))
    return log


def test_the_auto_range_stops_before_the_first_manual_gate():
    """This is the whole point of gates: a solve must not run unattended."""
    plan = ReviewPlan.from_dict(_plan(BASE_STEPS))
    assert plan.auto_run_range(RunLog()) == [0, 1]


def test_the_auto_range_skips_completed_steps():
    plan = ReviewPlan.from_dict(_plan(BASE_STEPS))
    assert plan.auto_run_range(_log_with(["01"])) == [1]


def test_the_auto_range_is_empty_when_the_next_step_is_manual():
    plan = ReviewPlan.from_dict(_plan(BASE_STEPS))
    assert plan.auto_run_range(_log_with(["01", "02"])) == []


def test_the_auto_range_resumes_after_a_manual_step_completes():
    plan = ReviewPlan.from_dict(_plan(BASE_STEPS))
    assert plan.auto_run_range(_log_with(["01", "02", "03"])) == [3]


def test_next_pending_returns_none_when_everything_is_done():
    plan = ReviewPlan.from_dict(_plan(BASE_STEPS))
    assert plan.next_pending(_log_with(["01", "02", "03", "04"])) is None


@pytest.mark.parametrize("status", [STATUS_FAILED, STATUS_UNDONE])
def test_failed_and_undone_steps_are_pending_again(status):
    plan = ReviewPlan.from_dict(_plan(BASE_STEPS))
    log = _log_with(["01"])
    log.upsert(StepRecord(id="02", name="02_Base_Extrude", status=status))
    assert plan.next_pending(log) == 1


# -- journal confinement ----------------------------------------------------


def test_journal_paths_must_be_relative(store: ReviewStore):
    plan = ReviewPlan.from_dict(_plan([{"name": "01_A", "operation": "journal", "params": {"path": r"C:\evil.py"}}]))
    with pytest.raises(PlanError):
        plan.validate_scripts(store)


def test_journal_paths_may_not_escape_the_scripts_directory(store: ReviewStore):
    plan = ReviewPlan.from_dict(
        _plan([{"name": "01_A", "operation": "journal", "params": {"path": "../../escape.py"}}])
    )
    with pytest.raises(PlanError):
        plan.validate_scripts(store)


def test_a_journal_step_needs_a_path(store: ReviewStore):
    plan = ReviewPlan.from_dict(_plan([{"name": "01_A", "operation": "journal"}]))
    with pytest.raises(PlanError):
        plan.validate_scripts(store)


def test_a_relative_journal_resolves_under_the_scripts_directory(store: ReviewStore):
    assert store.resolve_script("01_a.py") == store.scripts_dir / "01_a.py"


# -- store ------------------------------------------------------------------


def test_submit_writes_the_plan_the_log_and_the_scripts(store: ReviewStore):
    result = store.submit(_plan(BASE_STEPS), scripts={"a.py": "print('a')", "b.py": "print('b')"})
    assert store.plan_path.is_file()
    assert store.log_path.is_file()
    assert len(result["scriptsWritten"]) == 2
    assert (store.scripts_dir / "a.py").read_text(encoding="utf-8") == "print('a')"


def test_submit_resets_a_previous_run_log(store: ReviewStore):
    """Keeping stale 'done' marks would make the progress display lie."""
    store.submit(_plan(BASE_STEPS), scripts={"a.py": "", "b.py": ""})
    log = store.load_log()
    log.upsert(StepRecord(id="01", name="01_Base_Sketch", status=STATUS_DONE))
    store.save_log(log)

    store.submit(_plan(BASE_STEPS), scripts={"a.py": "", "b.py": ""})
    assert store.load_log().records == []


def test_submit_rejects_a_plan_whose_script_was_not_provided(store: ReviewStore):
    with pytest.raises(PlanError):
        store.submit(_plan(BASE_STEPS))  # a.py and b.py were never written


def test_status_without_a_plan_is_actionable(store: ReviewStore):
    status = store.status()
    assert status["hasPlan"] is False
    assert "nx_review_submit" in status["nextAction"]


def test_status_reports_the_next_step_and_its_gate(store: ReviewStore):
    store.submit(_plan(BASE_STEPS), scripts={"a.py": "", "b.py": ""})
    status = store.status()
    assert status["nextStep"]["name"] == "01_Base_Sketch"
    assert status["awaitingHuman"] is False
    assert status["finished"] is False


def test_status_flags_a_waiting_manual_gate(store: ReviewStore):
    store.submit(_plan(BASE_STEPS), scripts={"a.py": "", "b.py": ""})
    log = store.load_log()
    log.upsert(StepRecord(id="01", name="01_Base_Sketch", status=STATUS_DONE))
    log.upsert(StepRecord(id="02", name="02_Base_Extrude", status=STATUS_DONE))
    store.save_log(log)

    status = store.status()
    assert status["awaitingHuman"] is True
    assert status["nextStep"]["name"] == "03_Solve"
    assert "manual gate" in status["nextAction"]


def test_status_reports_completion(store: ReviewStore):
    store.submit(_plan(BASE_STEPS), scripts={"a.py": "", "b.py": ""})
    log = store.load_log()
    for step in BASE_STEPS:
        log.upsert(StepRecord(id=step["id"], name=step["name"], status=STATUS_DONE))
    store.save_log(log)

    status = store.status()
    assert status["finished"] is True
    assert status["nextStep"] is None
    assert status["counts"]["done"] == 4


def test_status_surfaces_a_rollback(store: ReviewStore):
    """After the reviewer undoes a step, the agent must see it is pending again."""
    store.submit(_plan(BASE_STEPS), scripts={"a.py": "", "b.py": ""})
    log = store.load_log()
    log.upsert(StepRecord(id="01", name="01_Base_Sketch", status=STATUS_UNDONE))
    store.save_log(log)

    status = store.status()
    assert status["nextStep"]["name"] == "01_Base_Sketch"
    assert status["counts"]["undone"] == 1


def test_a_corrupt_run_log_does_not_break_status(store: ReviewStore):
    store.submit(_plan(BASE_STEPS), scripts={"a.py": "", "b.py": ""})
    store.log_path.write_text("{ not json", encoding="utf-8")
    assert store.status()["hasPlan"] is True
    assert store.load_log().records == []


def test_a_corrupt_plan_is_reported_rather_than_ignored(store: ReviewStore):
    store.plan_path.parent.mkdir(parents=True, exist_ok=True)
    store.plan_path.write_text("{ not json", encoding="utf-8")
    with pytest.raises(Exception) as excinfo:
        store.load_plan()
    assert "REVIEW_PLAN_UNREADABLE" in str(getattr(excinfo.value, "code", ""))


def test_clear_removes_the_plan_and_log(store: ReviewStore):
    store.submit(_plan(BASE_STEPS), scripts={"a.py": "", "b.py": ""})
    result = store.reset()
    assert len(result["removed"]) == 2
    assert store.status()["hasPlan"] is False


def test_writes_are_atomic_and_leave_no_temporary_files(store: ReviewStore):
    store.submit(_plan(BASE_STEPS), scripts={"a.py": "", "b.py": ""})
    leftovers = list(store.root.glob("*.tmp"))
    assert leftovers == []


def test_the_plan_file_is_readable_json_with_unicode(store: ReviewStore):
    plan = _plan(BASE_STEPS)
    plan["prompt"] = "根据三视图建模"
    store.submit(plan, scripts={"a.py": "", "b.py": ""})
    raw = json.loads(store.plan_path.read_text(encoding="utf-8"))
    assert raw["prompt"] == "根据三视图建模"
