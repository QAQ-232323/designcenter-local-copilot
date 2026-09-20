# Comparable open-source NX projects

What already exists, how each one connects to NX, and what is worth borrowing.
Entries marked **[read]** were cloned and inspected; **[readme]** were assessed
from their documentation only.

## The short version

There are three viable ways to drive NX programmatically, and every project here
picks one or more:

1. **Batch journal** — launch `run_journal.exe` with a script. Simple, headless,
   but it starts its own NX process and never touches an open window.
2. **In-process** — run Python *inside* NX (journal, or NX's own script
   execution). Full session access; needs NX to cooperate.
3. **Sidecar bridge** — a listener inside NX plus an outside client. Gives an
   external agent live control of a real session; by far the most machinery.

## Projects

### DreamEnding/NX_MCP — **[read]** — https://github.com/DreamEnding/NX_MCP
MCP server for Siemens NX ("AI agents control the NX GUI"). Python package
(`pyproject.toml`, `src/nx_mcp/`), plus `docs/architecture.md`,
`docs/real-nx-validation.md` and `skills/nx-modeling/SKILL.md`. A fork exists at
https://github.com/xupeiwust/NX_MCP.

- **Connection:** two processes — `MCP client <--stdio--> Python sidecar
  <--authenticated loopback JSON-RPC--> NX bridge <--NXOpen--> NX`. The sidecar
  starts without NX and calls fail with `NX_BRIDGE_UNAVAILABLE` until a journal
  inside NX starts the bridge.
- **Discovery/config:** no hardcoded machine paths. Everything is environment
  driven (`NX_MCP_WORKSPACE`, `NX_MCP_ENABLE_EXPERIMENTAL`,
  `NX_MCP_ENABLE_JOURNAL`, `NX_MCP_BRIDGE_STOP_FILE`).
- **License:** not verified here.
- **What to borrow:** the *honesty* of its failure model. It distinguishes
  `not_started` from `failed` from `execution_state="unknown"`, refuses to
  auto-replay an uncertain mutation after a timeout or disconnect, and documents
  a rollback contract. Its workspace confinement (every file argument is
  relative and may not escape) is the right default for an agent tool. Its
  `SKILL.md` is the best-written NX agent skill in the ecosystem: it explicitly
  says "a tool returning successfully is not, by itself, proof of the intended
  model" and requires re-querying object IDs after any undo.
- **What to avoid:** its own README describes the release as `0.2.0.dev0` with an
  opt-in bridge pending validation of a non-blocking GUI event pump, and states
  that safety hardening still needs a full real-NX acceptance run. Treat live
  control as experimental there. It also commits to a version-specific
  validation story (tested on NX 2506).

### cfs-energy/nxlib — **[readme]** — https://github.com/cfs-energy/nxlib
"Library and toolkit for software development with the NXOpen Python API" from
Commonwealth Fusion Systems. **Apache-2.0.**

- **Connection:** in-process NXOpen Python, plus CI execution of journals on a VM.
- **What to borrow:** it solves the two problems most NX automation ignores —
  (a) *making a library importable by NX's own interpreter*, and (b) *testing
  NXOpen code automatically* (a test runner for unit and integration tests, and
  journal execution on a VM for CI). Any serious NX tooling eventually needs
  both. It also links the live public NXOpen Python reference, which is how the
  working docs.sw.siemens.com URL in
  [official-docs.md](official-docs.md) was found.
- **What to avoid:** Apache-2.0 with a corporate copyright header; check the
  terms before copying code into your own project.

### theScriptingEngineer/nxopentse — **[read]** — https://github.com/theScriptingEngineer/nxopentse
PyPI package of NXOpen helpers: `src/nxopentse/{cad,cae,tools}` covering
assemblies, faceted bodies, CAE preprocessing/solving/post-processing, Excel and
vector utilities. Sphinx docs under `docs/`.

- **Connection:** in-process NXOpen Python. Its README states you must have
  configured NX/Simcenter to work with an external Python interpreter.
- **What to borrow:** the packaging model — a normal `pip install`able package
  with typed modules and generated API docs, which is what makes NXOpen code
  reviewable. The author's blog and courses are the most practical NXOpen
  teaching material available.
- **What to avoid:** it assumes the external-interpreter setup is already done,
  which is exactly the part that breaks on a new machine. Nothing here helps an
  agent *find* or *verify* an installation.

### Foadsf/NXOpen_Python_tutorials — **[readme]** — https://github.com/Foadsf/NXOpen_Python_tutorials
Tutorial collection for automating NX CAD/CAM/CAE with NXOpen Python. **CC0-1.0.**
Companion repo: https://github.com/Foadsf/NXtips

- **What to borrow:** CC0 means copy freely; useful as grounding examples.
- **What to avoid:** it links the legacy
  `docs.plm.automation.siemens.com` reference, which is now login-walled — a good
  illustration of why documentation links rot and why reading the reference out
  of the local installation is more durable.

### kamao6757-crypto/nx-codex-plugin and codex-NX — **[read]** — the ancestors
https://github.com/kamao6757-crypto/nx-codex-plugin (v0.6.0) and
https://github.com/kamao6757-crypto/codex-NX (v0.1.4). Codex plugins driving NX
through NXOpen journals plus a .NET Remoting bridge, with an in-NX menu
(`NX2512 Control`), a PowerShell layer and an MCP stdio server.

- **Connection:** all three mechanisms — `run_journal.exe` for batch, plus a
  .NET Remoting server compiled into the NX custom directory and a console client
  that an MCP server shells out to.
- **What this project takes from them:** the working live-bridge design and the
  modelling semantics (intent routing, three-view rules, Part Navigator naming).
- **What this project fixes:** v0.6.0 hardcodes machine paths — its `.mcp.json`
  pins `E:\AIprojects\NXMCP`, its C# client defaults
  `DefaultNxRoot = @"D:\Program Files\Siemens\NX 2512"`, and its NX payload
  defaults to `E:\AIprojects\NXplugin`. It also binds everything to one release
  number ("2512") in file names, environment variables and menu identifiers.
  v0.1.4 had already moved to relative paths (`./scripts/start_mcp.ps1`), so the
  regression was a step backwards rather than an original sin.

### Others seen, not assessed
- https://github.com/AneeshSB/Python-CAD-Automation-NX-Composite-Curve-Export-Tool
  — composite curve extraction and feature-group selection for composite
  engineering workflows.
- `nxopen` on PyPI — https://pypi.org/project/nxopen/ (existence confirmed via
  search results; contents not inspected).
- https://github.com/topics/nxopen — the GitHub topic listing, useful for finding
  new projects.

## Comparison

| Project | Approach | Connection | Config style | License |
|---|---|---|---|---|
| DreamEnding/NX_MCP | MCP server for agents | sidecar + loopback JSON-RPC bridge | env vars, workspace-confined | not verified |
| cfs-energy/nxlib | library + CI toolkit | in-process NXOpen Python | library, importable by NX | Apache-2.0 |
| theScriptingEngineer/nxopentse | helper library | in-process NXOpen Python | pip package | not verified |
| Foadsf/NXOpen_Python_tutorials | teaching material | in-process NXOpen Python | n/a | CC0-1.0 |
| nx-codex-plugin / codex-NX | Codex plugin | journal + .NET Remoting bridge | **hardcoded paths** (0.6.0) | MIT |
| **nx-skill** | skill + MCP server | journal **and** live bridge | env vars + auto-discovery, zero hardcoded paths | MIT |

## Gaps this project tries to close

1. **Release-agnostic discovery.** Every project above either assumes a
   configured path or names one release. Machines in the wild run different
   releases — the machine this was developed on has Designcenter 2606 while the
   plugin it derives from hardcodes NX 2512. `nx_skill.discovery` recognises any
   installation structurally (a directory containing `NXBIN` with the NX
   executables) and reports which release it found.

2. **Documentation that is exact for the installed release.** The ecosystem
   points at web documentation that is variously login-walled or stale. The full
   reference already ships inside the installation; `nx_docs_*` reads it,
   including the release that introduced each member.

3. **Working without a GUI session.** Live bridges are the most impressive and
   the most fragile part of every project here. Batch execution should be a
   first-class, always-available path with an explicit statement about which mode
   is in use — not an afterthought.

4. **A diagnosable failure mode.** `nx-skill doctor` reports what is installed,
   what is built, what is running and what is missing, on a machine with no NX at
   all — rather than failing at the first tool call.
