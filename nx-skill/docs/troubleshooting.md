# Troubleshooting

Start here: `nx-skill doctor` prints the whole environment — discovered
installations, releases, workspace, running NX processes, whether the bridge is
built — and on a machine with no NX it still succeeds, listing what is missing.

```bash
nx-skill doctor            # JSON
nx-skill doctor --text     # human-readable
```

## "No Siemens NX installation was found"

The error lists every location that was checked. Fix it one of three ways:

```bash
# 1. point at the folder that CONTAINS NXBIN (not NXBIN itself)
export NX_SKILL_NX_ROOT="D:\\Program Files\\Siemens\\NX 2512"     # bash
$env:NX_SKILL_NX_ROOT = "D:\Program Files\Siemens\NX 2512"          # PowerShell

# 2. or pass it per call
nx-skill --nx-root "D:\Program Files\Siemens\DC 2606" discover

# 3. or let it search everywhere (slow; off by default)
export NX_SKILL_SKIP_GLOBAL_SEARCH=false
```

Common causes: pointing at `NXBIN` instead of its parent (this actually works —
both are accepted); an installation on a drive that is not fixed (removable or
network drives are not scanned by the default search); a partial install with no
`run_journal.exe`.

## "The live bridge client is not built"

The live bridge is C# and must be compiled once (~seconds):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_dotnet_bridge.ps1
```

It needs .NET Framework 4.x (`csc.exe`). If it is missing, **batch journals still
work** — `nx_run_journal`, `nx_create_part` and `nx_open_part` do not need the
bridge. Say which mode you are using rather than implying the live path worked.

## "No live bridge answered on port 25121"

In order of likelihood:

1. **NX is open but the listener is not running.** Start it from the NX menu:
   **NX Skill → Start Live Bridge**. A session started without this package's
   custom directory will not have the listener.
2. **A modal dialog is open in NX.** Modal dialogs block the NX thread; nothing
   will answer until the dialog is dismissed.
3. **NX was launched without the custom directory.** Relaunch with the package's
   environment so `UGII_CUSTOM_DIRECTORY_FILE` points at the generated
   `custom_dirs.dat`. `nx-skill doctor` reports whether the server DLL exists.
4. **Port conflict.** Change both sides:
   `export NX_SKILL_LIVE_PORT=25123` (the in-NX listener reads the same variable).
5. **Firewall** blocking loopback — unusual, but possible with aggressive
   endpoint security.
6. **A TUN-mode proxy (Clash and friends) is hijacking the hostname.** The server
   publishes its Remoting channel under the local machine name, and TUN mode
   resolves that name to a fake address (Clash uses `198.18.0.0/15`), so the
   client dials something that does not exist: it times out after 60 s, reports
   `无法连接到远程服务器 198.18.0.1:25121` and exits with code 143. The fix is to
   pin **both** ends to loopback — `props["machineName"] = "127.0.0.1"` in
   `NxLiveBridgeServer.cs` and `http://127.0.0.1:<port>/...` in
   `NxLiveBridgeClient.cs`. Both are already applied in this tree. Rebuild both
   after touching either one: rebuilding a single side changes nothing, because
   the server decides the URI the client must dial.

## "run_journal exited with code N"

Read the captured output in the error details. Frequent causes:

- The journal imports a module this installation does not provide. Check what
  exists: `nx-skill docs search "<Module>" --kinds type`, or compare
  `NXBIN/python/NXOpen_*.pyd`.
- **A licence is not available.** NX batch runs still need a licence; this is a
  licensing problem, not a code problem.
- The journal path is outside the workspace. Paths are workspace-relative by
  design; pass a relative path or move the file.
- Stale `UGII_*` variables in the parent shell. This package overrides them for
  the child process, but a wrapper script may not.

Remember that `run_journal` starts a **separate** NX process: a successful batch
run that writes a `.prt` changes nothing in an open window. If the user expected
to see it, that was a live task.

## The model looks wrong, or a step silently did nothing

- Re-query instead of assuming: `nx_live_status`, list bodies/features, check the
  Part Navigator names.
- If a step reported `execution_state: "unknown"` (timeout, disconnect), the
  operation may well have succeeded. Inspect the model and reconcile it against
  the request. **Do not re-run it** — that is how you get duplicate features.
- If a command was committed but appears unnamed, the journal forgot `SetName`.
  Naming is what makes the history usable.

## Review mode (NX Skill > Review Plan)

| Symptom | Cause and fix |
|---|---|
| The menu entry is missing | NX is not loading this package's custom directory. Run `nx-skill loader status`; if it reports not installed, `nx-skill loader install`. Confirm `nx_runtime/application/` contains `nx_control.men`, `definitions_nx_control.btn` and `nx_review_executor.dlx`. |
| The toolbar or the Copilot button never appears | NX parses `.tbr` keywords in a fixed order: `TITLE`, then `VERSION`, then `DOCK`. Write them in any other order and NX discards the entire toolbar, logging `发现意外的关键字 VERSION。期望 TITLE`. The button then silently vanishes with no other symptom. |
| "No plan found" inside the dialog | The dialog and the agent disagree about the workspace. The dialog resolves `NX_SKILL_REVIEW_DIR`, else `NX_SKILL_WORKSPACE/review`. Set `NX_SKILL_WORKSPACE` for the NX process too. |
| The dialog warns that a part must be open | Block Styler blocks misbehave without one. Open or create a part first. |
| A step reports a missing journal | Should be impossible — submission validates that every journal exists. If it happens, the file was deleted after submission. |
| No screenshot in `review/screenshots/` | Usually no display part. The step is still counted as successful; the reason is recorded in its message. |
| Undo reverted more than one step | Marks from an earlier dialog session were used. Prefer undoing within the same session. |
| A step you expected to auto-run did not | It is gated `manual`. That is the safe default: an unlabelled step waits for a person. |
| "Run All Automatic" stops immediately | The next step is a manual gate. That is the design, not a failure. |

## Agent-specific problems

- **MCP server starts but every NX tool fails**: that is expected on a machine
  without NX. `nx_status`, `nx_docs_*`, `nx_route_intent`,
  `nx_modeling_plan`, `nx_visual_spec` and `nx_prepare_session` all work
  without NX.
- **`WORKSPACE_VIOLATION`**: the path was absolute or escaped the workspace. Pass
  a relative path; the workspace is reported by `nx_status`.
- **`INVALID_ARGUMENT` about `code`/`python`/`source` in a step**:
  `nx_live_run_steps` rejects free-form code by design. Use
  `nx_live_run_python_inline` if you genuinely intend to run code, and say so.
- **Server exits immediately**: it reads stdin until EOF. If there is no client
  holding the pipe open, use `nx-skill <command>` instead.

## Environment reference

| Variable | Default | Meaning |
|---|---|---|
| `NX_SKILL_NX_ROOT` | auto-discovery | Directory containing `NXBIN` |
| `NX_SKILL_WORKSPACE` | `~/NXSkillWorkspace` | Where parts and journals live |
| `NX_SKILL_LIVE_PORT` | `25121` | Live bridge TCP port |
| `NX_SKILL_AUTO_LAUNCH` | `true` | Launch NX when a live command needs it |
| `NX_SKILL_AUTO_LAUNCH_TIMEOUT` | `240` | Seconds to wait after launching |
| `NX_SKILL_REQUIRE_ONLINE` | `true` | Fail fast when the bridge is unreachable |
| `NX_SKILL_DELETE_GENERATED` | `true` | Delete generated journals after running |
| `NX_SKILL_SKIP_GLOBAL_SEARCH` | `false` | Skip the filesystem-wide `NXBIN` scan |
| `NX_SKILL_LOG_LEVEL` | `INFO` | Log level (logs go to stderr) |
| `NX_SKILL_CONFIG_DIR` | `%LOCALAPPDATA%/nx-skill` | Where the generated `custom_dirs.dat` lives |
| `NX_SKILL_PROJECT_ROOT` | *(unset)* | Directory under which the live bridge permits generated parts and scripts. Leave it unset and the client falls back to the legacy `NX2512_PROJECT_ROOT` and rejects every script outside that tree with "Python script path must be under ...". Set it to the same directory as `NX_SKILL_WORKSPACE` when driving a review queue. |

Legacy names are still read so existing installs keep working: `NX2512_*`,
`DC2512_*`, `UGII_BASE_DIR`, `UGII_ROOT_DIR`, `NX_ROOT`, `NXBIN`,
`SIEMENS_NX_ROOT`. The canonical `NX_SKILL_*` name always wins.