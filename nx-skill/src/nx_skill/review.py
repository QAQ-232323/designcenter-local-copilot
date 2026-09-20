"""Human-paced review execution.

Some work should not run unattended. Building a part that a person will inspect,
and especially running a CAE solve, are things the user wants to **watch**, stop,
and undo. A headless worker is the wrong shape for that: it optimises throughput
for a workflow whose bottleneck is human judgement.

This module is the agent's half of a review loop. It writes a plan, and reads
back what happened. The other half -- :mod:`nx_runtime.application.nx_review_executor`
-- is a Block Styler dialog running inside the visible NX session, where a person
presses "run next step" and watches the model change.

The division of responsibility matters:

* the **agent** decides *what* the steps are and in what order;
* the **human** decides *when* each step runs, and can undo it;
* **NX** executes, one named undo mark per step, so a rejected step is reverted
  exactly rather than by re-running something.

No network listener is involved. The plan and the run log are files in the
workspace, which means the loop works on a machine where nothing may listen on a
port, and the human can read the plan before approving anything.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .config import Settings
from .contracts import InvalidArgument, SkillError, Workspace, WorkspaceViolation

#: Human-paced steps are not timed out: the person may take a coffee break.
DEFAULT_PLAN_NAME = "plan.json"
DEFAULT_LOG_NAME = "run.json"

#: Steps the in-NX executor knows how to perform.
OPERATIONS = (
    "journal",  # run a reviewed .py file from the plan's scripts/ directory
    "create_block",
    "status",
    "screenshot",
    "noop",
)

#: `auto` steps may be run back-to-back by the executor; `manual` steps are the
#: ones that need a human decision (a solve, a save, an export, a destructive edit).
GATE_AUTO = "auto"
GATE_MANUAL = "manual"
GATES = (GATE_AUTO, GATE_MANUAL)

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_UNDONE = "undone"
STATUS_SKIPPED = "skipped"

_NAME_RE = re.compile(r"^(\d{1,3})_[A-Za-z0-9_]+$")


class PlanError(InvalidArgument):
    code = "REVIEW_PLAN_INVALID"


@dataclass
class Step:
    """One reviewable unit of work."""

    id: str
    name: str
    operation: str
    params: dict[str, Any] = field(default_factory=dict)
    gate: str = GATE_MANUAL
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "operation": self.operation,
            "gate": self.gate,
        }
        if self.params:
            payload["params"] = self.params
        if self.note:
            payload["note"] = self.note
        return payload

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any], index: int) -> "Step":
        if not isinstance(raw, Mapping):
            raise PlanError(f"Step {index} must be an object.")
        operation = str(raw.get("operation") or "").strip()
        if operation not in OPERATIONS:
            raise PlanError(
                f"Step {index} uses unknown operation {operation!r}.",
                suggestion=f"Known operations: {list(OPERATIONS)}",
            )
        name = str(raw.get("name") or "").strip()
        if not name:
            name = f"{index:02d}_Step"
        if not _NAME_RE.match(name):
            raise PlanError(
                f"Step {index} name {name!r} does not follow the numbered convention.",
                suggestion="Use NN_Short_Action_Object, e.g. 03_Base_Extrude. The number is what "
                "makes the Part Navigator read as an ordered history.",
            )
        gate = str(raw.get("gate") or GATE_MANUAL).strip()
        if gate not in GATES:
            raise PlanError(f"Step {index} has unknown gate {gate!r}.", suggestion=f"Use {list(GATES)}.")
        return cls(
            id=str(raw.get("id") or f"{index:02d}"),
            name=name,
            operation=operation,
            params=dict(raw.get("params") or {}),
            gate=gate,
            note=str(raw.get("note") or ""),
        )


@dataclass
class ReviewPlan:
    """An ordered, human-approved modelling plan."""

    steps: list[Step]
    prompt: str = ""
    part_path: str = ""
    plan_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created: float = field(default_factory=time.time)
    workspace: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "planId": self.plan_id,
            "created": self.created,
            "prompt": self.prompt,
            "partPath": self.part_path,
            "workspace": self.workspace,
            "stepCount": len(self.steps),
            "steps": [s.to_dict() for s in self.steps],
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ReviewPlan":
        raw_steps = raw.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            raise PlanError("A plan needs a non-empty 'steps' array.")
        steps = [Step.from_dict(item, index) for index, item in enumerate(raw_steps, start=1)]

        seen: set[str] = set()
        for step in steps:
            if step.id in seen:
                raise PlanError(
                    f"Duplicate step id {step.id!r}.",
                    suggestion="Ids identify steps in the run log; they must be unique.",
                )
            seen.add(step.id)

        return cls(
            steps=steps,
            prompt=str(raw.get("prompt") or ""),
            part_path=str(raw.get("partPath") or raw.get("part_path") or ""),
            plan_id=str(raw.get("planId") or uuid.uuid4().hex[:12]),
            created=float(raw.get("created") or time.time()),
            workspace=str(raw.get("workspace") or ""),
        )

    def validate_scripts(self, store: "ReviewStore") -> None:
        """Check every journal step resolves to a file that is actually there.

        Existence is checked here rather than left to the executor on purpose: the
        person running the review would otherwise discover a missing script only
        by clicking the step inside NX, with the dialog already open and the plan
        half executed. Failing at submit time keeps that a message instead of a
        surprise.
        """
        for step in self.steps:
            if step.operation != "journal":
                continue
            raw = str(step.params.get("path") or "").strip()
            if not raw:
                raise PlanError(
                    f"Step {step.name!r} is a journal step with no params.path.",
                    suggestion="Point it at a .py file under the review scripts directory.",
                )
            resolved = store.resolve_script(raw)
            if not resolved.is_file():
                raise PlanError(
                    f"Step {step.name!r} references {raw!r}, which does not exist in the review scripts directory.",
                    suggestion=(
                        "Pass the script source in the same submit call, or place the file at "
                        f"{resolved}."
                    ),
                    details={"step": step.name, "expected": str(resolved)},
                )

    def next_pending(self, log: "RunLog") -> int | None:
        """Index of the first step that has not completed, or `None` when done."""
        for index, step in enumerate(self.steps):
            record = log.record_for(step.id)
            if record is None or record.status in (STATUS_PENDING, STATUS_FAILED, STATUS_UNDONE):
                return index
        return None

    def auto_run_range(self, log: "RunLog") -> list[int]:
        """Consecutive `auto` steps starting at the first pending one.

        Stops at the first `manual` gate, which is the whole point: a person must
        approve the solve, the save and the export.
        """
        start = self.next_pending(log)
        if start is None:
            return []
        chosen: list[int] = []
        for index in range(start, len(self.steps)):
            step = self.steps[index]
            record = log.record_for(step.id)
            if record is not None and record.status == STATUS_DONE:
                continue
            if step.gate != GATE_AUTO:
                break
            chosen.append(index)
        return chosen


@dataclass
class StepRecord:
    id: str
    name: str
    status: str = STATUS_PENDING
    undo_mark: str = ""
    screenshot: str = ""
    message: str = ""
    execution_state: str = ""
    started: float = 0.0
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "undoMark": self.undo_mark,
            "screenshot": self.screenshot,
            "message": self.message,
            "executionState": self.execution_state,
            "durationSeconds": round(self.duration_seconds, 3),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "StepRecord":
        return cls(
            id=str(raw.get("id") or ""),
            name=str(raw.get("name") or ""),
            status=str(raw.get("status") or STATUS_PENDING),
            undo_mark=str(raw.get("undoMark") or ""),
            screenshot=str(raw.get("screenshot") or ""),
            message=str(raw.get("message") or ""),
            execution_state=str(raw.get("executionState") or ""),
            started=float(raw.get("started") or 0.0),
            duration_seconds=float(raw.get("durationSeconds") or 0.0),
        )


@dataclass
class RunLog:
    """What actually happened, as both the human and the agent see it."""

    plan_id: str = ""
    started: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)
    records: list[StepRecord] = field(default_factory=list)

    def record_for(self, step_id: str) -> StepRecord | None:
        for record in self.records:
            if record.id == step_id:
                return record
        return None

    def upsert(self, record: StepRecord) -> None:
        for index, existing in enumerate(self.records):
            if existing.id == record.id:
                self.records[index] = record
                break
        else:
            self.records.append(record)
        self.updated = time.time()

    def counts(self) -> dict[str, int]:
        tally: dict[str, int] = {}
        for record in self.records:
            tally[record.status] = tally.get(record.status, 0) + 1
        return tally

    def to_dict(self) -> dict[str, Any]:
        return {
            "planId": self.plan_id,
            "started": self.started,
            "updated": self.updated,
            "counts": self.counts(),
            "steps": [r.to_dict() for r in self.records],
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "RunLog":
        return cls(
            plan_id=str(raw.get("planId") or ""),
            started=float(raw.get("started") or time.time()),
            updated=float(raw.get("updated") or time.time()),
            records=[StepRecord.from_dict(item) for item in raw.get("steps") or []],
        )

def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Write JSON so a reader never sees a half-written file.

    The reader here is a process inside NX, potentially mid-click; a truncated
    plan file would surface as a JSON error in a dialog the user cannot debug.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


class ReviewStore:
    """Owns the on-disk contract between the agent and the in-NX dialog."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.workspace = Workspace(settings.ensure_workspace())

    # -- locations --------------------------------------------------------
    @property
    def root(self) -> Path:
        return self.workspace.root / "review"

    @property
    def plan_path(self) -> Path:
        return self.root / DEFAULT_PLAN_NAME

    @property
    def log_path(self) -> Path:
        return self.root / DEFAULT_LOG_NAME

    @property
    def scripts_dir(self) -> Path:
        path = self.root / "scripts"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def screenshots_dir(self) -> Path:
        path = self.root / "screenshots"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def resolve_script(self, relative: str | Path) -> Path:
        """A journal step may only run a file from the review scripts directory."""
        text = str(relative)
        candidate = Path(text)
        if candidate.is_absolute():
            raise PlanError(
                f"Journal path must be relative to the review scripts directory: {text!r}.",
                suggestion="Use a plain file name; the executor resolves it under review/scripts/.",
            )
        resolved = (self.scripts_dir / candidate).resolve()
        if self.scripts_dir.resolve() not in resolved.parents and resolved != self.scripts_dir.resolve():
            raise PlanError(
                f"Journal path escapes the review scripts directory: {text!r}.",
                suggestion="Keep step scripts inside review/scripts/ so they can be reviewed before running.",
            )
        return resolved

    # -- plan -------------------------------------------------------------
    def save_plan(self, plan: ReviewPlan) -> Path:
        _atomic_write_json(self.plan_path, plan.to_dict())
        return self.plan_path

    def load_plan(self) -> ReviewPlan | None:
        if not self.plan_path.is_file():
            return None
        try:
            raw = json.loads(self.plan_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SkillError(
                f"The review plan at {self.plan_path} is not readable JSON: {exc}",
                code="REVIEW_PLAN_UNREADABLE",
                suggestion="Re-submit the plan; the file may have been written by an interrupted run.",
            ) from exc
        return ReviewPlan.from_dict(raw)

    def submit(self, raw_plan: Mapping[str, Any], scripts: Mapping[str, str] | None = None) -> dict[str, Any]:
        """Validate a plan, write its journals, and reset the run log.

        Resetting the log on submit is deliberate: a new plan is a new run, and
        stale "done" marks from a previous plan would make the progress display lie.
        """
        plan = ReviewPlan.from_dict(raw_plan)
        plan.workspace = str(self.workspace.root)

        written: list[str] = []
        for name, source in (scripts or {}).items():
            target = self.resolve_script(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(source), encoding="utf-8")
            written.append(str(target))

        plan.validate_scripts(self)

        previous = self.load_plan()
        self.save_plan(plan)
        log = RunLog(plan_id=plan.plan_id)
        self.save_log(log)

        return {
            "planPath": str(self.plan_path),
            "planId": plan.plan_id,
            "stepCount": len(plan.steps),
            "steps": [s.to_dict() for s in plan.steps],
            "scriptsWritten": written,
            "replacedPlanId": previous.plan_id if previous and previous.plan_id != plan.plan_id else None,
            "nextAction": (
                "In NX open the menu NX Skill > Review Plan, then use Run Next Step. "
                "The dialog reads this plan file; no bridge is required."
            ),
        }

    # -- run log ----------------------------------------------------------
    def save_log(self, log: RunLog) -> Path:
        _atomic_write_json(self.log_path, log.to_dict())
        return self.log_path

    def load_log(self) -> RunLog:
        if not self.log_path.is_file():
            return RunLog()
        try:
            raw = json.loads(self.log_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return RunLog()
        return RunLog.from_dict(raw)

    def reset(self) -> dict[str, Any]:
        removed: list[str] = []
        for path in (self.plan_path, self.log_path):
            try:
                if path.is_file():
                    path.unlink()
                    removed.append(str(path))
            except OSError:
                continue
        return {"removed": removed}

    # -- status -----------------------------------------------------------
    def status(self) -> dict[str, Any]:
        """Everything the agent needs to decide what to do next."""
        plan = self.load_plan()
        log = self.load_log()
        if plan is None:
            return {
                "hasPlan": False,
                "planPath": str(self.plan_path),
                "nextAction": "Submit a plan with nx_review_submit, then run it from the NX menu.",
            }

        next_index = plan.next_pending(log)
        auto_range = plan.auto_run_range(log)
        payload: dict[str, Any] = {
            "hasPlan": True,
            "planPath": str(self.plan_path),
            "logPath": str(self.log_path),
            "plan": plan.to_dict(),
            "counts": log.counts(),
            "nextStep": plan.steps[next_index].to_dict() if next_index is not None else None,
            "autoRunnableNow": [plan.steps[i].name for i in auto_range],
            "awaitingHuman": next_index is not None and plan.steps[next_index].gate == GATE_MANUAL,
            "finished": next_index is None,
        }
        if next_index is not None:
            step = plan.steps[next_index]
            payload["nextAction"] = (
                f"Run {step.name!r} in NX (menu NX Skill > Review Plan). "
                + ("It is a manual gate: a person must approve it." if step.gate == GATE_MANUAL else "It is an automatic step.")
            )
        else:
            payload["nextAction"] = "All steps are complete; review the screenshots and the run log."
        return payload
