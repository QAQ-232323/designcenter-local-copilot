# Review mode: the human-paced workflow

## Why this mode exists

There are two ways to drive NX from an agent, and a third is needed when the work
is not something a user is willing to let run unwatched.

| Mode | Who is at the keyboard | Use for |
|---|---|---|
| **Batch** | nobody — a private headless NX process | files, exports, CI |
| **Live** | the agent drives the open session | fast, reversible, low-risk edits |
| **Review** | **the person**, one step at a time | anything they must watch, approve or undo |

Review mode is for the work where speed is not the goal. Building a part the user
will inspect, and above all **running a CAE solve**, are things a person wants to
see happen: mesh generation, solution progress and results are the deliverable,
not a side effect. A headless worker optimises exactly the wrong thing.

## What it looks like

The agent writes a plan. In NX, the user opens **NX Skill → Review Plan** and
gets a dialog listing the steps. They press *Run Next Step* and watch the model
change. If they do not like it, *Undo Last Step* puts the model back exactly.

```text
agent                                    NX (visible session)
  │                                        │
  │ nx_review_submit  ──► review/plan.json │
  │                        review/scripts/ │
  │                                        │  user opens NX Skill > Review Plan
  │                                        │  clicks Run Next Step
  │                                        │    ├─ SetUndoMark("03_Mounting_Holes")
  │                                        │    ├─ run the step
  │                                        │    ├─ export a PNG of the work view
  │                                        │    └─ append to run.json
  │ ◄── nx_review_status ── review/run.json│
  │                                        │  clicks Undo Last Step
  │                                        │    └─ UndoToMark(...)  exact revert
```

**There is no listener, no socket and no .NET.** The plan and the run log are
files. That is not a shortcut — it is the reason this mode is robust:

- nothing to install beyond the package itself;
- nothing to firewall;
- a modal dialog in NX cannot wedge it, because a person is already there;
- the user can read `plan.json` and every step script **before** approving
  anything.

## Gates: which steps may run unattended

Every step carries a `gate`:

| Gate | Meaning |
|---|---|
| `auto` | Cheap and reversible. *Run All Automatic* executes consecutive auto steps back to back. |
| `manual` | Needs a human decision. The auto-runner **stops before it**. |

`manual` is the default for a step that does not declare one, because the safe
default is "ask". Mark these manual:

- CAE solves and mesh generation
- `save` and any overwrite
- exports into a real directory
- booleans, deletes, mass feature edits
- anything that takes minutes — the user should choose when to spend them

Mark these auto: reference geometry, sketches, expressions, the base body, and
read-only checks.

## Undo is exact, not a re-run

Before each step the executor calls:

```python
mark = session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible, "03_Mounting_Holes")
```

and *Undo Last Step* calls `session.UndoToMark(mark, name)`. The model returns to
the state immediately before that step. This matters when the step took four
minutes, and it is why every step gets its own mark rather than relying on one
mark per session.

If the dialog was reopened and the in-memory mark list is empty, the executor
falls back to `UndoToLastVisibleMark()`, which is why the marks are created
*Visible* and *named*.

**A failed step is not auto-undone.** A half-built feature is evidence; the
person may want to look at it before deciding. The undo is offered, not assumed.

## Screenshots

After every step the executor exports the graphics window to
`review/screenshots/<step>_<timestamp>.png` using
`part.Views.CreateImageExportBuilder()`. This gives:

- the reviewer a visual history without having to remember what step 4 looked
  like;
- the agent something to compare against the source drawing or three-view sheet.

A failure to capture a screenshot never marks a successful step as failed — it is
recorded in the step's message instead.

## The plan format

```json
{
  "prompt": "build a flange plate from the three-view drawing",
  "partPath": "flange.prt",
  "steps": [
    {
      "id": "01",
      "name": "01_Base_Sketch",
      "operation": "journal",
      "gate": "auto",
      "params": { "path": "01_base_sketch.py" },
      "note": "profile sketch driven by expressions"
    },
    {
      "id": "02",
      "name": "02_Base_Extrude",
      "operation": "create_block",
      "gate": "auto",
      "params": { "length": 120, "width": 80, "height": 12 }
    },
    {
      "id": "03",
      "name": "03_Mounting_Holes",
      "operation": "journal",
      "gate": "manual",
      "params": { "path": "03_holes.py" },
      "note": "destructive: cuts material"
    }
  ]
}
```

Rules the validator enforces at submit time:

- `steps` must be a non-empty array;
- step names follow `NN_Short_Action_Object` — the number is what makes the Part
  Navigator read as an ordered history;
- step ids must be unique (they key the run log);
- `operation` must be one of `journal`, `create_block`, `status`,
  `screenshot`, `noop`;
- `gate` must be `auto` or `manual`;
- a `journal` step's `params.path` must be **relative**, must stay inside
  `review/scripts/`, and **must already exist** — so a missing script is a
  message at submit time, not a surprise when the user clicks the step.

### Operations

| Operation | Does |
|---|---|
| `journal` | Runs a reviewed `.py` file from `review/scripts/` in the NX process |
| `create_block` | Creates a named block feature in the work part |
| `status` | Reports the current work part (read-only) |
| `screenshot` | Captures the work view without changing anything |
| `noop` | Does nothing; useful as an explicit checkpoint |

## Preparing a plan

From an agent (MCP):

```
nx_review_submit   plan={...}  scripts={"01_base_sketch.py": "<source>"}
nx_review_status
nx_review_clear
```

From a shell:

```bash
nx-skill review submit plan.json --script 01_base_sketch.py --script 03_holes.py
nx-skill review status
nx-skill review clear
```

Neither needs NX to be installed or running: preparing and inspecting a review is
file work.

## Files

```text
<workspace>/review/
├── plan.json               written by the agent, read by the dialog
├── run.json                written by the dialog, read by the agent
├── scripts/                the journals each step runs (reviewable before use)
└── screenshots/            one PNG per executed step
```

Writes are atomic on both sides (temp file plus replace), because the reader is a
process inside NX that may be reading the file at the moment a click happens.

## Limitations, stated plainly

- **The dialog has not been exercised inside a running NX by this package's
  authors.** The APIs it uses were each verified against the release-exact
  documentation shipped with NX — `UI.CreateDialog`, `BlockDialog.Launch`
  (note: `Show` is deprecated as of NX 2206), `Session.SetUndoMark`,
  `Session.UndoToMark`, `BasePart.Views.CreateImageExportBuilder` — and the
  `.dlx` dialog is assembled from vendor-generated block definitions rather than
  hand-written. But "the calls exist and are internally consistent" is not the
  same as "the dialog opens". Expect to iterate on first run.
- **A part must be open.** Block Styler blocks misbehave without one; the entry
  point checks and says so instead of opening a broken dialog.
- **NX must be told about this package.** See `nx-skill loader install`; without it
  the *NX Skill* menu does not exist at all, which looks like the feature is
  missing rather than unregistered.
- **The dialog blocks NX** while it is open, which is inherent to running on the
  main thread — and is exactly why a human is in the loop.
- **Review mode does not replace the live bridge.** For fast, reversible,
  unattended edits the bridge is still the right tool.

## Troubleshooting

| Symptom | Cause |
|---|---|
| Menu item missing | NX is not reading this package's custom directory. Run `nx-skill loader status`, then `nx-skill loader install` if it reports not installed. The variable must point at the generated `custom_dirs.dat`, and `nx_runtime/application/` must hold `nx_control.men` and `nx_review_executor.dlx`. |
| "No plan found" in the dialog | The dialog is looking at a different workspace. It resolves `NX_SKILL_REVIEW_DIR`, else `NX_SKILL_WORKSPACE/review`. Both processes must agree. |
| A step reports a missing journal | Should be impossible: submission validates existence. If it happens, the file was deleted afterwards. |
| Screenshot unavailable | Usually no display part. The step still counts as successful. |
| Undo reverts more than one step | Marks from an earlier session were used. Prefer undoing within the same dialog session. |