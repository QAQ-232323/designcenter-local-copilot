# Architecture

## What problem this solves

Siemens NX is normally driven by a human clicking, or by an NXOpen script that
someone wrote for one release and one machine. This package makes it drivable by
an agent that does not know which release is installed, cannot see the screen,
and must not claim success it did not verify.

## Layers

```text
agent (any host: DSH / Claude / Codex / shell)
  |
  |  MCP stdio (JSON-RPC)            nx-skill CLI
  v                                        v
src/nx_skill/server.py  <-------------->  src/nx_skill/cli.py
  |                                            |
  +------------------+-------------------------+
                     v
              modeling.py     semantics: routing, plan schema, drawing rules
              review.py       human-paced plan + run log (no transport)
              localdocs.py    the API reference shipped inside the install
              discovery.py    find and validate any NX installation
              config.py       environment contract (no hardcoded paths)
              contracts.py    result envelopes, error codes, workspace boundary
              process.py      what is running right now
                     |
        +------------+-------------+
        v                          v
   journal.py                 livebridge.py
   run_journal.exe            NxLiveBridgeClient.exe
   (private NX process)              |
                                     v  Base64 JSON over loopback
                              NxLiveBridgeServer.dll
                              (loaded inside the open NX session)
                                     |
                                     v
                                NXOpen -> NX
```

## The three execution paths

**Batch** (`journal.py`). Starts `run_journal.exe -nx <script>`. It gets its own
NX process, so it never attaches to a window the user has open. It is the
reliable path: no GUI, no event pump, no modal dialogs. Correct for creating
parts on disk, exports and CI.

The environment is built explicitly rather than inherited, because a machine can
easily have stale `UGII_BASE_DIR` / `UGII_ROOT_DIR` pointing at a different
release. Notably, batch runs do **not** set `UGII_CUSTOM_DIRECTORY_FILE`: doing so
would make a headless process load this package's interactive startup payload and
open a bridge listener, which is not what a batch run should do.

**Review** (`review.py` + `nx_runtime/application/nx_review_executor.py`). The agent
writes an ordered plan; a Block Styler dialog inside NX runs the steps when a
person clicks. This exists because some work — above all a CAE solve — must be
watched, and because the live bridge's threading model makes it fragile exactly
when a human is present. There is no transport at all: the plan and run log are
files, and the human is the synchronisation mechanism. See
[review-mode.md](review-mode.md).

**Live** (`livebridge.py`). Talks to a listener hosted inside a running NX
process, so commands act on the Work Part and the Part Navigator the user is
looking at. The transport is one request/response per call: the client sends a
Base64-encoded UTF-8 JSON payload and prints JSON on stdout. That constraint is
why every command is a discrete verb rather than an arbitrary script — the design
follows from the transport.

The bridge cannot be written in pure Python because it must be hosted inside the
NX process as a .NET assembly loaded from the NX custom directory. The C# sources
live in `scripts/dotnet_bridge/` and are compiled locally; the binaries are
deliberately **not** committed.

Worth recording *why* it is built this way: the server marshals the NXOpen
`Session` object over .NET Remoting, and the listener runs on a background
thread, so NXOpen calls happen off NX's main thread. That is unsupported but
mostly works — until a modal dialog appears. There is no NXOpen primitive for
marshalling work back to the main thread (no timer, no event pump), which is why
the pure-Python socket bridge shipped with the earlier plugins has to occupy the
main thread and freeze the UI. Review mode avoids the problem entirely by putting
a person where the event pump would have to be.

## Discovery without hardcoding

`discovery.py` never assumes a release or a directory layout. It recognises an
installation by structure — a directory containing `NXBIN` with the NX
executables — and searches in ascending cost order:

1. an explicit argument
2. environment variables (canonical `NX_SKILL_*`, then the legacy
   `NX2512_*` / `DC2512_*` / `UGII_*` names, so existing installs keep working)
3. Windows uninstall-registry entries
4. conventional vendor directories on every fixed drive
5. an optional filesystem-wide scan for `NXBIN`, opt-out via
   `NX_SKILL_SKIP_GLOBAL_SEARCH`

A path that merely exists is never accepted — each candidate is validated against
a named requirement (`run_journal`, `managed`, `ugraf`), with POSIX variants so
the same requirement works on Linux. When nothing is found, the error lists every
location that was checked, because "not found" without that list is unactionable.

The release number is derived from an explicit setting, a version marker file, or
the install directory name, and reports `"unknown"` rather than guessing.

## Documentation from the installation

`localdocs.py` streams the XML documentation that ships in `NXBIN/managed/`
(tens of megabytes) instead of loading it, and matches members on name or summary.
Each member carries the release that introduced it. This is the package's answer
to documentation rot: an offline, release-exact reference beats a web page that
may be stale, login-walled, or about a different version. See
[official-docs.md](official-docs.md).

One subtlety worth recording: `ElementTree.findtext()` returns only the text
*directly* inside a tag and silently drops the rest, truncating summaries at the
first nested `<see>` element. The module flattens sections with `itertext()`
instead, which is why full signatures survive.

## Failure model

Every operation returns the same envelope:

```json
{"ok": true,  "result": {}, "execution_state": "succeeded"}
{"ok": false, "error": {"code": "...", "message": "...", "suggestion": "...", "retryable": true},
              "execution_state": "unknown"}
```

`execution_state` is the important part. "The call failed" and "the model was not
changed" are different claims, and a bridge timeout is neither:

| State | Meaning | Correct response |
|---|---|---|
| `not_started` | The operation never reached NX | Correct the input and retry |
| `succeeded` | Done | Verify against the request |
| `failed` | It ran and failed | Read the error |
| `unknown` | Outcome genuinely undetermined (timeout, disconnect) | Inspect the model; **never** auto-replay |

`NX_BRIDGE_TIMEOUT`, `NX_BRIDGE_DISCONNECTED`, `NX_JOURNAL_TIMEOUT` and
`NX_EXECUTION_UNKNOWN` all map to `unknown`.

## Safety properties

- **Workspace confinement.** Every file argument is relative to the workspace;
  absolute paths and `..` escapes raise `WORKSPACE_VIOLATION`. An agent that can
  be argued into writing an arbitrary path is a liability.
- **A whitelisted live verb set.** `nx_live_call` only forwards commands in
  `LIVE_COMMANDS`.
- **Explicit steps reject smuggled code.** `nx_live_run_steps` refuses `code`,
  `python`, `source`, `script` and `script_path` inside a step, so a reviewable
  operation cannot quietly become an arbitrary script.
- **No runtime dependencies.** Standard library only, so the package imports on a
  bare machine and inside NX's embedded interpreter, where pip is unavailable.

## Entry points

| Entry point | Purpose |
|---|---|
| `nx-skill doctor` | Full environment report; never raises |
| `nx-skill review submit <plan.json>` | Hand a plan to the human-paced dialog in NX |
| `nx-skill mcp` / `python -m nx_skill.mcp` | MCP stdio server |
| `nx_skill.cli:main` | Console script |
| `nx_skill.server:serve` | Embeddable server loop |

The MCP reader accepts both newline-delimited JSON (current MCP) and LSP-style
`Content-Length` framing (used by the earlier plugins), and replies in whichever
framing the client established, so it works with either generation of client.