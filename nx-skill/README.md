# nx-skill

A portable, agent-agnostic skill for driving **Siemens NX / Designcenter** through
NXOpen.

It is the generalization of the earlier NX Codex plugins. Those worked, but
assumed one release ("NX 2512") and one machine layout — hardcoded paths in the
MCP manifest, the C# client and the NX payload. This package assumes neither.
Point it at any NX installation and it works; leave it pointed at nothing and it
still tells you what is missing and why.

```bash
nx-skill doctor          # what is installed, what is built, what is running
nx-skill discover        # every NX installation on this machine
nx-skill docs search ExtrudeBuilder
```

## What is actually different here

**1. Release-agnostic discovery.** No release number is baked in. An installation
is recognised structurally — a directory containing `NXBIN` with the NX
executables — and searched for through the environment, the Windows uninstall
registry, conventional vendor directories, and optionally a filesystem-wide scan.
It reports which release it found. The machine this was developed on runs
**Designcenter 2606** while the plugin it derives from hardcodes NX 2512, which is
exactly the failure mode being fixed.

**2. The API reference that ships inside your installation.** Every full NX
install contains `NXBIN/managed/*.xml` — tens of megabytes of per-member
documentation — plus `UGOPEN/pythonStubs` type stubs and vendor sample code. This
package reads them:

```bash
nx-skill docs member "NXOpen.Session.GetSession"
nx-skill docs type "NXOpen.Features.ExtrudeBuilder"
nx-skill docs search "ExtrudeBuilder" --kinds type --summary
```

That gives an answer that is **exact for the release you have**, works offline,
and tells you the release that introduced each member (`Created in NX2206.0.0`),
so you can tell whether an API exists before writing code against it. It is also
more reliable than the web: the historical public reference host now redirects
every path to a login-walled customer centre. See
[docs/official-docs.md](docs/official-docs.md).

**3. Three execution paths, honestly separated.** Batch journals run in a private
headless NX process and never touch an open window. Live commands act on the
session you are looking at, driven by the agent. **Review mode** hands the plan to
the person instead: they run each step from a dialog inside NX, watch it happen,
and can undo any step exactly. The difference is documented instead of glossed
over, because "it wrote a .prt file" and "your model changed" are different claims.

**4. Human-paced review for work that must be watched.** A CAE solve, a save, an
export, or anything the user wants to inspect should not run unattended — the
process *is* the deliverable. `nx_review_submit` writes an ordered plan with a
`gate` per step; the dialog runs the automatic ones back to back and **stops
before every manual one**. Each step gets its own visible undo mark, so
"undo last step" is an exact revert rather than a re-run, and every executed step
exports a PNG of the work view as an audit trail. There is no listener, no socket
and no .NET involved.

  See [docs/review-mode.md](docs/review-mode.md).

**5. A failure model that admits uncertainty.** `execution_state` distinguishes
`not_started` from `failed` from `unknown`. A bridge timeout may mean the
operation never ran, or that it succeeded and the answer was lost — so it is
reported as `unknown` and the caller is told not to replay it.

## Install

Requires Python 3.9+ and, for live commands, Windows with .NET Framework 4.x.
There are **no runtime dependencies** — standard library only, so the package
imports on a bare machine and inside NX's embedded interpreter, where pip is
unavailable.

This package lives in the `nx-skill/` subdirectory of
[`designcenter-local-copilot`](https://github.com/kamao6757-crypto/designcenter-local-copilot),
where it is the modelling half of a larger integration. It has no dependency on
its parent and works standalone — copy the directory anywhere.

```bash
git clone --depth 1 https://github.com/kamao6757-crypto/designcenter-local-copilot
cd designcenter-local-copilot/nx-skill
pip install -e .
nx-skill doctor
```

Nothing to install at all is also fine:

```bash
PYTHONPATH=src python -m nx_skill doctor
```

### Make NX show the menu (once)

Review mode and the live bridge are reached from a menu **inside** NX, which NX
only knows about if it is told to read this package's custom directory:

```bash
nx-skill loader install     # writes the config and sets the user environment
nx-skill loader status      # will NX see the menu? (detects a stale pointer too)
nx-skill loader uninstall   # remove the user environment variable
```

This writes one user-scope environment variable (`UGII_CUSTOM_DIRECTORY_FILE`) and
one file under your own config directory. It does not touch the NX installation,
the machine-wide environment, or any other project's registration — and
`loader status` reports if some *other* tool has claimed that variable, which
is exactly the kind of thing that silently breaks a menu. Skipping this step is
fine if you always let this package launch NX; the variable is then set for that
process only.

### Build the live bridge (optional, once)

Batch journals need nothing extra. Live commands need the small .NET bridge:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_dotnet_bridge.ps1
```

Binaries are **not** committed — they are built locally, because they must be
compiled against the NXOpen assemblies of the release you actually have.

## Use it from an agent

### MCP

`.mcp.json` is ready to use:

```json
{
  "mcpServers": {
    "nx": { "command": "python", "args": ["-m", "nx_skill.mcp"] }
  }
}
```

Or run it directly: `python -m nx_skill.mcp`. The reader accepts both
newline-delimited JSON (current MCP) and `Content-Length` framing (the earlier
plugins), and replies in whichever framing the client used.

### Skill

[SKILL.md](SKILL.md) is host-agnostic and mirrored at
[skills/nx/SKILL.md](skills/nx/SKILL.md) for hosts that expect a skill directory.
It is not a tool list — it is the discipline: check the environment first, look
API names up rather than guessing, plan before modelling, keep the Part Navigator
readable, and never claim a verification you did not perform.

### Command line

Every MCP tool has a CLI equivalent and prints the same envelope, so a human can
debug exactly what the agent did.

```bash
nx-skill doctor                                    # environment report
nx-skill journal create-part demo.prt              # batch: new part
nx-skill journal run my_journal.py                 # batch: run a journal
nx-skill live ping                                 # is the bridge up?
nx-skill live block --length 80 --width 50 --height 25 --name 01_Base_Block
nx-skill live python --stage 02_Rib < rib.py       # inline NXOpen from a file
nx-skill review submit plan.json --script 03_holes.py   # human-paced, in NX
nx-skill loader status                             # will NX show the menu?
nx-skill route "根据这张三视图建模一个法兰盘"
nx-skill plan "build a bracket" --part-name Bracket
```

## Tools

24 MCP tools, all returning the same envelope.

| Group | Tools |
|---|---|
| Environment | `nx_status` |
| Documentation | `nx_docs_search`, `nx_docs_member`, `nx_docs_type`, `nx_docs_samples` |
| Planning | `nx_route_intent`, `nx_modeling_plan`, `nx_visual_spec`, `nx_prepare_session` |
| Batch | `nx_create_part`, `nx_open_part`, `nx_run_journal` |
| Live | `nx_live_ping`, `nx_live_status`, `nx_live_module_list`, `nx_live_create_modeling_part`, `nx_live_create_block`, `nx_live_run_python_inline`, `nx_live_run_steps`, `nx_live_call` |
| **Review** | `nx_review_submit`, `nx_review_status`, `nx_review_clear` |

`nx_status`, the documentation tools and everything under "Planning" work on a
machine with **no NX installed at all** — which is what makes the package
diagnosable rather than merely broken.

## Configuration

Everything is environment-driven; nothing is hardcoded.

| Variable | Default | Meaning |
|---|---|---|
| `NX_SKILL_NX_ROOT` | auto-discovery | Directory containing `NXBIN` |
| `NX_SKILL_WORKSPACE` | `~/NXSkillWorkspace` | Where parts and journals live |
| `NX_SKILL_LIVE_PORT` | `25121` | Live bridge TCP port |
| `NX_SKILL_AUTO_LAUNCH` | `true` | Launch NX when a live command needs it |
| `NX_SKILL_SKIP_GLOBAL_SEARCH` | `false` | Skip the filesystem-wide `NXBIN` scan |

Legacy names from the earlier plugins (`NX2512_*`, `DC2512_*`, `UGII_*`) are
still read, so existing installs keep working. The canonical `NX_SKILL_*` name
always wins. Full list in [docs/troubleshooting.md](docs/troubleshooting.md).

## Safety

- **Workspace confinement** — every file argument is relative to the workspace;
  absolute paths and `..` escapes are rejected with `WORKSPACE_VIOLATION`.
- **Whitelisted live verbs** — only commands the compiled bridge implements can
  be sent.
- **No smuggled code in explicit steps** — `nx_live_run_steps` rejects `code`,
  `python`, `source`, `script` and `script_path` inside a step, so a reviewable
  operation cannot quietly become an arbitrary script.
- **Validation before side effects** — a malformed request is rejected *before*
  NX is launched, not after a window has appeared on someone's desktop.

## Testing

```bash
pip install -e ".[dev]"
python -m pytest
```

188 tests, no NX required. A synthetic installation fixture exercises discovery,
documentation parsing and validation on any machine; the suite also asserts
packaging invariants — no non-stdlib imports, no hardcoded paths in code (checked
via the AST so documentation examples are not false positives), no release-bound
identifiers, and no drift between the two copies of `SKILL.md`.

The Block Styler dialog definition (`.dlx`) is validated too: it is assembled by
`scripts/generate_review_dialog.py` out of vendor-generated block definitions
rather than authored by hand, and a test asserts the result is well-formed, has
exactly the blocks the executor looks up, and leaked no ids from the vendor sample
it was cloned from.

## Documentation

- [SKILL.md](SKILL.md) — the agent-facing skill
- [docs/official-docs.md](docs/official-docs.md) — Siemens documentation, verified: what is reachable and what is a dead end
- [docs/similar-projects.md](docs/similar-projects.md) — comparable open-source NX projects and what to borrow
- [docs/review-mode.md](docs/review-mode.md) — human-paced execution: gates, exact undo, screenshots, the plan format
- [docs/architecture.md](docs/architecture.md) — layers, discovery, the execution paths, the failure model
- [docs/troubleshooting.md](docs/troubleshooting.md) — symptom-driven fixes

## The live bridge, and why review mode exists

The live bridge works by marshalling the NXOpen `Session` object over .NET
Remoting; the listener runs on a background thread, so NXOpen is being called
**off NX's main thread**. That is not a supported pattern — it is one that happens
to work until a modal dialog appears. There is also no NXOpen primitive for
marshalling work back onto the main thread (no timer, no event pump), which is why
a pure-Python socket bridge ends up blocking the UI instead.

Review mode sidesteps the whole problem rather than solving it: when a person is
already in the loop, they are the synchronisation mechanism. That is also why it
is the right mode for simulation — you want to watch the solve, not be told about
it afterwards.

## Relationship to prior work

Derived from [nx-codex-plugin](https://github.com/kamao6757-crypto/nx-codex-plugin)
(v0.6.0) and [codex-NX](https://github.com/kamao6757-crypto/codex-NX) (v0.1.4).
The live-bridge design and the modelling semantics (intent routing, three-view
rules, Part Navigator naming) come from those. What changed is the assumption
that NX is one release on one machine.

## License

MIT.
