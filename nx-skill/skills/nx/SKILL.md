---
name: nx
description: Drive Siemens NX / Designcenter through NXOpen to build, inspect and validate parts. Use when the user asks to model a part in NX, build a model from a picture or three-view drawing, run a CAE simulation, look up an NXOpen API, run an NX journal, or check what NX installation is available. Works with any local NX release.
---

# Siemens NX

NX is a CAD/CAM/CAE system whose automation surface is **NXOpen**, exposed as a
Python API (also .NET and C++). This skill drives it in three modes. Choosing the
wrong one is the most common way to waste a user's time.

| Mode | Tools | Touches the user's screen? | Use for |
|---|---|---|---|
| **Batch** | `nx_run_journal`, `nx_create_part`, `nx_open_part` | No — a private, headless NX process | File work, exports, generating parts on disk, CI |
| **Live** | `nx_live_*` | Yes — driven **by the agent** | Fast, reversible, low-risk edits in the session the user has open |
| **Review** | `nx_review_*` | Yes — driven **by the person**, one step at a time | Anything they must watch, approve or undo; **all CAE solves** |

`run_journal` **does not attach to an already-open NX window**. A batch command
can write a `.prt` file and leave the visible session completely untouched. If
the user says "in the window I have open", that is not a batch task.

## 1. Establish the environment before anything else

Call `nx_status` first. It works even on a machine with no NX installed and
reports exactly what is missing: the discovered installation, its release, the
workspace, running NX processes and whether the live bridge is answering.

Do not assume a release. This skill discovers *any* NX or Designcenter
installation rather than expecting a particular one, because the installed
release differs per machine. If the user names one, pass `nx_root` on the call
or set `NX_SKILL_NX_ROOT`.

## 2. Answer API questions from the installation, not from memory

This is the single most important habit in this skill.

`@
nx_docs_search   query="ExtrudeBuilder"            # find members
nx_docs_member   name="NXOpen.Session.GetSession"  # one member, full text
nx_docs_type     type_name="NXOpen.Features.ExtrudeBuilder"
nx_docs_samples  query="Python"                    # vendor sample applications
`@

These read the reference that **ships inside the installed NX release**:
`NXBIN/managed/*.xml` (tens of megabytes of per-member documentation) and the
`UGOPEN/pythonStubs` type stubs. This beats the public web documentation three
ways: it is exact for the release actually installed, it works offline, and each
member reports the release that introduced it (`Created in NX2206.0.0`), so you
can tell whether an API exists here.

It also catches deprecations that matter. `BlockDialog.Show` is deprecated as of
NX 2206 in favour of `Launch` — a detail you only get by reading the installed
documentation, and one that changes the code you write.

The historical public reference host
`docs.plm.automation.siemens.com/data_services/resources/nx/<release>/...` still
appears in search results but every path now redirects to an authenticated
customer centre. See [official-docs.md](docs/official-docs.md) for what is
genuinely reachable, and [similar-projects.md](docs/similar-projects.md) for other
open-source NX projects worth borrowing from.

**Never guess an NXOpen class, method or argument name.** Look it up. A wrong name
fails late inside NX with an unhelpful error.

## 3. Plan before modelling

Call `nx_prepare_session` once with the user's original wording. It resolves the
workspace, routes the request, and returns the plan schema.

`nx_route_intent` decides between modelling (`NXOpen.Features`, application
`UG_APP_MODELING`) and CAE (`NXOpen.CAE`). Read the returned `matchedKeywords`
rather than trusting the label — it tells you *why* the route won.

For an image, blueprint or three-view request, `nx_visual_spec` returns the
orthographic rules: first-angle vs third-angle, which view drives the silhouette,
what counts as design evidence (centrelines, hidden lines, section hatching), and
when a missing dimension should become an editable expression instead of an
invented number.

`nx_modeling_plan` returns the required shape of an ordered plan. Split work into
stages: reference geometry, base body, primary cuts and additions, patterns,
finishing, validation.

## 4. Choose review mode when a person must be in the loop

**If the user needs to watch it, do not run it yourself.** Reach for
`nx_review_submit` instead of the live tools when any of these is true:

- it is a **CAE solve, meshing or post-processing** — the process is the
  deliverable, and it must be visible;
- it is expensive (minutes), destructive, or overwrites/saves a real file;
- the user said they want to inspect, approve, or check the result;
- you are unsure enough that a human seeing it would change the outcome.

`nx_review_submit` writes a plan the user runs from the NX menu (**NX Skill →
Review Plan**). They press *Run Next Step* per step, *Run All Automatic* for the
safe ones, and *Undo Last Step* to revert exactly one step.

`@json
{
  "prompt": "build a flange plate from the three-view drawing",
  "steps": [
    {"id": "01", "name": "01_Base_Sketch", "operation": "journal", "gate": "auto",
     "params": {"path": "01_base_sketch.py"}},
    {"id": "02", "name": "02_Base_Extrude", "operation": "create_block", "gate": "auto",
     "params": {"length": 120, "width": 80, "height": 12}},
    {"id": "03", "name": "03_Mounting_Holes", "operation": "journal", "gate": "manual",
     "params": {"path": "03_holes.py"}, "note": "destructive: cuts material"}
  ]
}
`@

Rules that matter:

- **`gate` is the contract.** `auto` may run back to back; `manual` makes the
  auto-runner *stop*. Omitted gates default to `manual` — the safe default.
  Mark solves, saves, exports, booleans and deletes `manual` **always**.
- Step names follow `NN_Short_Action_Object`; the number is what makes the Part
  Navigator read as an ordered history.
- Journal steps must point at a **relative** path inside `review/scripts/`, and
  the file **must exist at submit time** — pass its source in the same `scripts`
  argument. A missing script is rejected then, not when the user clicks the step.
- Every step gets its own visible undo mark, so a rejected step is reverted
  exactly rather than re-run.
- Each executed step exports a PNG of the work view to `review/screenshots/`,
  which is also your chance to verify the result visually.

After submitting, **do not assume the user ran anything**. Call
`nx_review_status` and read it: it reports the next step, whether that step is
waiting on a human gate (`awaitingHuman`), what is runnable automatically right
now, and whether the plan is finished. You may also see `undone` — the user
rolled a step back, which means they disagreed with it. Treat that as a signal to
change the approach, not to re-submit the same step.

Full details: [review-mode.md](docs/review-mode.md).

## 5. Build so the Part Navigator reads like a human made it

Name every committed object with the convention `NN_Short_Action_Object`:

`@text
01_Base_Profile_Sketch
02_Base_Extrude
03_Main_Bore
04_Mounting_Holes
05_Hole_Pattern
06_Chamfers
07_Edge_Fillets
`@

Rules that matter:

- Drive dimensions with **NXOpen expressions**, so a correction is cheap.
- Prefer **sketches + feature builders** over constructing a final body directly.
- Wrap each human-sized operation in `session.SetUndoMark(...)`.
- Use `SetName(...)` on every sketch, datum and feature.
- Do not delete construction geometry unless the user asked for a clean tree.

## 6. Prefer explicit steps over free-form code

`nx_live_run_steps` takes ordered, named operations and reports each step's
outcome. It rejects `code`, `python`, `source` and `script_path` inside a
step **by design** — an explicit step is reviewable and individually reportable,
while a code blob is neither. The same principle runs through review mode.

Use `nx_live_run_python_inline` only for a genuine one-off, and say so.

## 7. Verify, and do not overclaim

A tool returning successfully is **not** proof of the intended model.

- After important geometry changes, query the model again (`nx_live_status`).
- Compare the result against the request: dimensions, feature count, body count.
- For a three-view job, re-check the silhouette against each view — or read the
  screenshots review mode already produced.
- Report the part path, what you actually verified, and what remains uncertain.

## 8. Failure handling

Tools return an `execution_state`. Treat it as load-bearing:

- `not_started` — the operation did not reach NX. Safe to correct and retry.
- `succeeded` — done.
- `failed` — it ran and failed. Read the error before retrying.
- `unknown` — **the outcome is genuinely unknown** (timeout, disconnect). Do not
  replay the command. Reconnect, inspect the part, and reconcile what you see
  with what was asked. A timeout does not mean "it did not happen".

Other things worth knowing:

- If NX is open but the live bridge is silent, the listener can be started from
  the NX menu: **NX Skill → Start Live Bridge**. A modal dialog in NX will block
  it — which is a reason to prefer review mode when a person is available.
- If the live bridge cannot be built or started, batch journals still work, and
  so does review mode. Say which mode you fell back to instead of implying the
  live path succeeded.
- Never loop on a failing command. Two identical failures mean the approach is
  wrong, not that the third attempt will work.

## 9. Boundaries

- Every file path is **relative to the workspace**; absolute paths and `..`
  escapes are rejected. Parts land in the workspace, never next to the user's
  documents by accident.
- Confirm before overwriting an existing part, deleting features, or exporting
  into a production directory.
- The package works on a machine with no NX at all for planning, documentation
  and review preparation; do not treat a missing installation as a bug to work
  around.

## Reference

- [docs/review-mode.md](docs/review-mode.md) — human-paced execution in detail
- [docs/official-docs.md](docs/official-docs.md) — Siemens documentation: what is
  reachable, what is a dead end, and how to search it
- [docs/similar-projects.md](docs/similar-projects.md) — comparable open-source
  NX projects and what to borrow
- [docs/architecture.md](docs/architecture.md) — how discovery, batch, live and
  review execution fit together
- [docs/troubleshooting.md](docs/troubleshooting.md) — symptom-driven fixes
- `nx-skill doctor` — one command that reports the whole environment
