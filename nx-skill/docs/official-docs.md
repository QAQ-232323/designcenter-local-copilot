# Siemens documentation: what to actually use

Finding NXOpen documentation is harder than it should be, because the URLs that
search engines return most often are dead ends. This page records what was
**actually fetched and verified**, and the order of preference an agent should
use.

Verified on **2026-09-19**.

## Decision table — look here, in this order

| Priority | Source | Reachable? | Why |
|---|---|---|---|
| 1 | **The installed NX release** (`NXBIN/managed/*.xml`, `UGOPEN/pythonStubs/`) | Always, offline | Exact for the release installed, includes the introducing release per member |
| 2 | **NX Open Python Reference Guide** on docs.sw.siemens.com | Public, no login | Official, browsable, current |
| 3 | **Siemens Support knowledge base** | Public, no login | Task-level answers (batch execution, licensing, configuration) |
| 4 | **Siemens Community forums** | Public, no login | Real-world problems, staff answers |
| — | ❌ `docs.plm.automation.siemens.com` legacy reference | **Login-walled** | Every path now redirects to an authenticated customer centre |

## 1. The installed release is the best reference (and it is already local)

Every full NX installation ships a complete API reference. This is the highest-
value and least-known source, and it is free to query:

```bash
nx-skill docs stats
nx-skill docs search "ExtrudeBuilder" --kinds type
nx-skill docs member "NXOpen.Session.GetSession"
nx-skill docs type "NXOpen.Features.ExtrudeBuilder"
nx-skill docs samples Python
```

What is on disk, and why each part matters:

| Path | Content | Value |
|---|---|---|
| `NXBIN/managed/*.xml` | .NET XML documentation for every managed assembly (43 files, ~71 MB on the machine used for verification; `NXOpen.xml` alone is ~59 MB) | Full member signatures, summaries, parameters, **and the release that introduced each member** |
| `UGOPEN/pythonStubs/NXOpen/**` | Python type stubs (136 `.pyi` files; `__init__.pyi` alone is ~86 000 lines) | The Python-side spelling of every call, ideal for autocomplete and for checking argument names |
| `UGOPEN/SampleNXOpenApplications/` | Vendor samples for **Python, C++, .NET, Java** | Working, correct-by-construction examples |
| `UGOPEN/exphdrs` | C/C++ headers | The underlying API surface |
| `NXBIN/python/NXOpen_*.pyd` | Compiled Python extension modules (~112 on the verified install) | Proof of which modules this exact installation can import |

The release annotation is the killer feature. A member's documentation says, for
example, `Created in NX2206.0.0`, so you can tell whether the API exists in the
release the user actually has instead of shipping code that fails at import.

**Prefer this over the web.** It cannot be out of date relative to the install,
it needs no account, and it answers in well under a second.

## 2. Public official documentation

### NX Open Python Reference Guide — verified working, no login

```text
https://docs.sw.siemens.com/en-US/doc/209349590/PL20231101866122454.custom_api.nxopen_python_ref
```

Verified: HTTP 200, title *"NX Open Python Reference Guide"*. Localised variants
resolve to the same document, e.g.
`https://docs.sw.siemens.com/zh-CN/doc/209349590/PL20231101866122454.custom_api.nxopen_python_ref`.

Note the URL shape — it is **not** a version number, it is
`<collection id>/<document id>.<slug>`. Guessing sibling slugs does **not**
work: `…custom_api.nxopen_net_ref`, `…nxopen_cpp_ref`, `…nxopen_java_ref` and
`…nxopen_ref` all return a generic *"Documentation Center"* soft-404 page rather
than a document. Only the Python reference slug was confirmed.

### Documentation Centre

`https://docs.sw.siemens.com/` is the portal. Its root URL returns 404 to a
direct request — it is a single-page app, so the useful entry point is a specific
document URL (as above) or the site's own search.

### Support knowledge base — verified working

```text
https://support.sw.siemens.com/en-US/okba/KB000181221_EN_US/index.html
```

Verified: HTTP 200. This article covers **executing an external NXOpen Python
batch script without `run_journal.exe`** — directly relevant when
`run_journal` is unavailable or when you need the journal to run inside an
already-running NX process. The URL pattern is
`https://support.sw.siemens.com/<locale>/okba/<KBID>_<locale>/index.html`, so
other article IDs can be constructed once you know the ID.

### Community forums — verified working

`https://community.sw.siemens.com/` returns HTTP 200 and hosts the NX and
NXOpen discussion boards. Question URLs look like
`https://community.sw.siemens.com/s/question/<id>/<slug>`.

Do **not** guess topic URLs: the plausible-looking
`/s/topic/0TO4O000000MnhkWAC/nx-open` returns 404. Search the site instead.

## 3. What does not work any more

`docs.plm.automation.siemens.com` was the classic NXOpen reference host, and it
is still what older tutorials and search results link to. It is no longer usable:

- Every path under
  `https://docs.plm.automation.siemens.com/data_services/resources/nx/<release>/nx_api/custom/en_US/nxopen_python_ref/…`
  returns HTTP 200 with the **same ~36 KB page** regardless of release or file,
  and that page follows **5 redirects** to `https://customer.sw.siemens.com/en-US`
  — an authenticated customer centre.
- The host's TLS certificate chain contains an **expired certificate**
  (`SEC_E_CERT_EXPIRED`), so a default `curl` fails outright with a TLS error
  before it even reaches the redirect.

Practical consequences:

- Never construct a version-specific URL there and give it to a user; it will
  either error or bounce them to a login page.
- Search-engine snippets from that host may still *look* valid. They are stale.
- Projects that still link to it (for example older tutorial repositories) are
  pointing at a dead end; the equivalent live link is the docs.sw.siemens.com
  Python reference above.

## 4. Search recipes

General web search for NXOpen material works better with these patterns:

```text
site:docs.sw.siemens.com nxopen python
site:support.sw.siemens.com KB NXOpen python batch
site:community.sw.siemens.com nxopen <ClassName>
"NXOpen.<Namespace>" <method name> python
NXOpen python <feature> builder example
github nxopen python <task>
```

Inside the local reference, prefer the qualified name over prose:

```bash
nx-skill docs search "Session.GetSession"
nx-skill docs search "Builder" --kinds type --limit 50
nx-skill docs search "Created in NX" --summary      # search prose, not just names
```

## 5. Conventions worth knowing before writing NXOpen

These are the rules that trip people up most often; see
[../SKILL.md](../SKILL.md) for the workflow that applies them.

- **NX's embedded Python is not a normal Python.** You cannot `pip install`
  into it. A script that runs in NX uses the interpreter NX ships, with the
  `NXOpen` extension modules that installation provides. Batch execution goes
  through `run_journal`; anything else needs the procedure in KB000181221.
- **Two NXOpen flavours, one API.** *Internal* programs run inside the NX
  process and can touch the session; *external* programs run in their own
  process and are limited. `run_journal` is the external/batch path and does not
  attach to a live session.
- **`NXOpen.Session.GetSession()` is the entry point** for everything
  session-scoped: parts, the listing window, undo marks, UI.
- **Everything is a builder.** Features are created by a `*Builder` object
  (`ExtrudeBuilder`, `HoleBuilder`, …) that you configure, `Commit()`, then
  `Destroy()`. Forgetting to destroy leaks; forgetting to commit produces
  nothing.
- **Expressions drive dimensions.** Hard-coding numbers produces a model nobody
  can edit. `session.SetUndoMark(...)` before each human-sized operation makes
  the result undoable step by step.
- **Release availability differs.** Check `Created in NX…` before using an API in
  code that must run on an older release.

## Verified URL table

| Purpose | URL | Verified | Result |
|---|---|---|---|
| NX Open Python Reference Guide | `https://docs.sw.siemens.com/en-US/doc/209349590/PL20231101866122454.custom_api.nxopen_python_ref` | yes | 200, title *NX Open Python Reference Guide* |
| Same, Chinese locale | `https://docs.sw.siemens.com/zh-CN/doc/209349590/PL20231101866122454.custom_api.nxopen_python_ref` | yes | 200 |
| KB: external NXOpen Python batch script without `run_journal.exe` | `https://support.sw.siemens.com/en-US/okba/KB000181221_EN_US/index.html` | yes | 200 |
| Siemens community home | `https://community.sw.siemens.com/` | yes | 200 |
| GitHub topic for NXOpen projects | `https://github.com/topics/nxopen` | yes | 200 |
| Legacy NXOpen reference host | `https://docs.plm.automation.siemens.com/data_services/resources/nx/1899/nx_api/custom/en_US/nxopen_python_ref/a24384.html` | yes | **login wall** — 5 redirects to `customer.sw.siemens.com`; TLS chain expired |
| Documentation Centre root | `https://docs.sw.siemens.com/` | yes | 404 (single-page app; use a document URL) |
| Guessed community topic | `https://community.sw.siemens.com/s/topic/0TO4O000000MnhkWAC/nx-open` | yes | **404 — do not use** |
| Guessed sibling reference slugs | `…PL20231101866122454.custom_api.nxopen_net_ref` etc. | yes | soft-404 |

Unverified: the C++/.NET/Java reference documents on docs.sw.siemens.com (the
sibling slugs tested do not resolve; a real URL would have to come from the
site's own search).
