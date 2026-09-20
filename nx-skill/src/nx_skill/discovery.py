"""Locate a Siemens NX / Designcenter installation without assuming a release.

The original plugins hardcoded one release ("NX 2512") and one machine layout.
This module instead recognises *any* NX installation by its structural
fingerprint -- a directory containing `NXBIN` with the NX executables -- so it
works across releases (NX 9 ... NX 2512, Designcenter, Simcenter) and across
platforms (Windows and Linux), including releases that did not exist when this
package was written.

Discovery order, cheapest first:

1. an explicit `nx_root` argument
2. environment variables (canonical, then legacy)
3. Windows uninstall-registry entries
4. well-known vendor directories on every fixed drive
5. an optional filesystem-wide scan for `NXBIN` directories

Every candidate is validated structurally; a path that merely exists is never
accepted. If nothing is found the caller gets a :class:`NxNotFound` carrying the
full list of places that were checked, so the failure is actionable rather than
a bare "not found".
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Sequence

from .config import Settings, env_lookup
from .contracts import SkillError

#: Directories whose presence marks a valid NX root, in ascending strictness.
REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "any": ("NXBIN",),
    "run_journal": ("NXBIN/run_journal.exe",),
    "run_journal_posix": ("NXBIN/run_journal",),
    "managed": ("NXBIN/managed/NXOpen.dll",),
    "ugraf": ("NXBIN/ugraf.exe",),
    "ugraf_posix": ("NXBIN/ugraf",),
}

#: Directory names that look like an NX product folder (used when scanning).
_PRODUCT_NAME = re.compile(
    r"^(?:siemens[ _-]?)?(?:nx|dc|designcenter|simcenter|ug)[ _-]?\d{0,4}",
    re.IGNORECASE,
)

#: A trailing release token such as "2512" in "NX 2512" or "DC 2606".
_RELEASE_TOKEN = re.compile(r"(?<![0-9])(\d{4})(?![0-9])")

#: Structural fingerprint of the built-in Designcenter Copilot feature, strongest
#: first. Recognised by what is on disk, never by release number, so any release
#: that ships the feature (2606, 2506, 2406, 2306, ...) is identified the same way.
#: Names inside an install can differ between releases; these are the markers that
#: hold across them, and the page is the one the local host mirrors.
COPILOT_MARKERS: tuple[tuple[str, str], ...] = (
    ("page", "UGII/copilot/plchat/PLChat.html"),
    ("plchat_dir", "UGII/copilot/plchat"),
    ("copilot_dir", "UGII/copilot"),
)

#: The Copilot engine libraries live in NXBIN next to the other NX libraries.
#: Globbed rather than enumerated: 2606 ships libcopilot / libcopilotui /
#: libcopilotinit / libcopilotuiinit, other releases may name them differently.
COPILOT_LIB_DIR = "NXBIN"
COPILOT_LIB_GLOB = "libcopilot*"

_SKIP_DIR_NAMES = {
    "$recycle.bin",
    "system volume information",
    "windows",
    "winsxs",
    "node_modules",
    ".git",
    "temp",
    "tmp",
}


class NxNotFound(SkillError):
    """Raised when no usable NX installation can be found.

    A `SkillError` rather than a bare `RuntimeError` on purpose: callers rely on
    the error code and suggestion to produce an actionable message, and a plain
    runtime error would be reported as an internal failure -- which is exactly the
    wrong signal for "this machine has no NX".
    """

    code = "NX_NOT_FOUND"

    def __init__(self, require: str, checked: Sequence[str]) -> None:
        self.require = require
        self.checked = list(checked)
        listed = "\n  ".join(self.checked[:40]) or "(no candidates were generated)"
        super().__init__(
            f"No Siemens NX installation satisfying requirement {require!r} was found "
            f"on this machine.\n\n"
            f"Set NX_SKILL_NX_ROOT to the directory that contains NXBIN "
            f"(the release folder under the Siemens install directory), or pass nx_root explicitly.\n\n"
            f"Checked:\n  {listed}",
            suggestion=(
                "Set NX_SKILL_NX_ROOT to the folder that contains NXBIN, or pass nx_root. "
                "Documentation and planning tools work without NX; only journal and live "
                "commands need an installation."
            ),
            details={"require": require, "checked": self.checked[:40]},
        )


@dataclass(frozen=True)
class CopilotProbe:
    """What the built-in Copilot feature looks like inside one installation.

    ``available`` is a claim about the installation, not about a release: it means
    the markers below were found on disk. ``page_available`` narrows it to the
    case the local host can actually work with -- the page scripts that
    ``plchat-local/fetch-frontend.sh`` mirrors. An install can have the engine
    libraries without the page (then it has the AI, but there is nothing to host).
    """

    available: bool = False
    markers: tuple[str, ...] = ()
    page: Path | None = None
    scripts_dir: Path | None = None
    libraries: tuple[Path, ...] = ()

    @property
    def page_available(self) -> bool:
        return self.page is not None

    def to_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "pageAvailable": self.page_available,
            "markers": list(self.markers),
            "page": str(self.page) if self.page else None,
            "scriptsDir": str(self.scripts_dir) if self.scripts_dir else None,
            "libraries": [str(p) for p in self.libraries],
        }


@dataclass(frozen=True)
class NxInstall:
    """A validated NX installation and the paths derived from it."""

    root: Path
    release: str = "unknown"
    source: str = "unknown"
    capabilities: frozenset[str] = field(default_factory=frozenset)

    # -- core paths -------------------------------------------------------
    @property
    def nxbin(self) -> Path:
        return self.root / "NXBIN"

    @property
    def managed(self) -> Path:
        return self.nxbin / "managed"

    @property
    def run_journal(self) -> Path:
        exe = self.nxbin / "run_journal.exe"
        return exe if exe.exists() else self.nxbin / "run_journal"

    @property
    def ugraf(self) -> Path:
        exe = self.nxbin / "ugraf.exe"
        return exe if exe.exists() else self.nxbin / "ugraf"

    @property
    def nxopen_assembly(self) -> Path:
        """The managed NXOpen assembly consumed by .NET and by the live bridge."""
        return self.managed / "NXOpen.dll"

    # -- offline documentation -------------------------------------------
    @property
    def api_xml_docs(self) -> tuple[Path, ...]:
        """Per-assembly .NET XML documentation shipped inside the install.

        These files are the authoritative, release-exact API reference: they
        carry every member signature plus the release that introduced it.
        """
        if not self.managed.is_dir():
            return ()
        return tuple(sorted(self.managed.glob("*.xml")))

    @property
    def python_stubs(self) -> Path | None:
        """`NXOpen` type stubs, when the install ships them."""
        candidates = (
            self.root / "UGOPEN" / "pythonStubs" / "NXOpen",
            self.nxbin / "pythonStubs" / "NXOpen",
        )
        for path in candidates:
            if path.is_dir():
                return path
        return None

    @property
    def python_modules(self) -> Path | None:
        path = self.nxbin / "python"
        return path if path.is_dir() else None

    @property
    def examples(self) -> Path | None:
        path = self.root / "UGOPEN" / "SampleNXOpenApplications"
        return path if path.is_dir() else None

    @property
    def headers(self) -> Path | None:
        path = self.root / "UGOPEN"
        return path if path.is_dir() else None

    def has(self, requirement: str) -> bool:
        rels = REQUIREMENTS.get(requirement)
        if rels is None:
            raise KeyError(f"unknown requirement {requirement!r}")
        return all((self.root / rel).exists() for rel in rels)

    @property
    def copilot(self) -> CopilotProbe:
        """The built-in Designcenter Copilot feature, when this install ships it."""
        return detect_copilot(self.root)

    def to_dict(self) -> dict[str, object]:
        stubs = self.python_stubs
        return {
            "root": str(self.root),
            "release": self.release,
            "source": self.source,
            "nxbin": str(self.nxbin),
            "runJournal": str(self.run_journal),
            "ugraf": str(self.ugraf),
            "nxopenAssembly": str(self.nxopen_assembly) if self.nxopen_assembly.exists() else None,
            "pythonStubs": str(stubs) if stubs else None,
            "pythonModules": str(self.python_modules) if self.python_modules else None,
            "examples": str(self.examples) if self.examples else None,
            "apiXmlDocCount": len(self.api_xml_docs),
            "capabilities": sorted(self.capabilities),
            "copilot": self.copilot.to_dict(),
        }

# ---------------------------------------------------------------------------
# Validation and normalisation
# ---------------------------------------------------------------------------


def normalize_root(candidate: object) -> Path | None:
    """Turn *candidate* into an NX root, or return `None` if it cannot be one.

    Accepts the root itself, its `NXBIN` directory, or a file inside it
    (`run_journal.exe`, `ugraf`, `managed/NXOpen.dll`) because users point at
    all three in practice.
    """
    if candidate is None:
        return None
    text = str(candidate).strip().strip('"')
    if not text:
        return None

    path = Path(text).expanduser()
    try:
        if not path.exists():
            return None
        resolved = path.resolve()
    except OSError:
        return None

    if resolved.is_file():
        parent = resolved.parent
        if parent.name.casefold() == "managed":
            parent = parent.parent
        if parent.name.casefold() != "nxbin":
            return None
        return parent.parent

    if resolved.name.casefold() == "nxbin":
        return resolved.parent

    return resolved


def satisfies(root: Path, require: str = "run_journal") -> bool:
    """Structurally validate *root* against a named requirement.

    `run_journal` and `ugraf` are satisfied by either the Windows executable or
    its POSIX counterpart, so the same requirement works on both platforms.
    """
    if require in {"run_journal", "run_journal_posix"}:
        return (root / "NXBIN" / "run_journal.exe").exists() or (root / "NXBIN" / "run_journal").exists()
    if require in {"ugraf", "ugraf_posix"}:
        return (root / "NXBIN" / "ugraf.exe").exists() or (root / "NXBIN" / "ugraf").exists()
    rels = REQUIREMENTS.get(require)
    if rels is None:
        raise KeyError(f"unknown requirement {require!r}; expected one of {sorted(REQUIREMENTS)}")
    return all((root / rel).exists() for rel in rels)


def detect_capabilities(root: Path) -> frozenset[str]:
    """Report which NX sub-systems this install can actually reach."""
    caps: set[str] = set()
    if satisfies(root, "run_journal"):
        caps.add("journal")
    if satisfies(root, "managed"):
        caps.add("dotnet")
    if satisfies(root, "ugraf"):
        caps.add("gui")
    if (root / "UGOPEN" / "pythonStubs" / "NXOpen").is_dir():
        caps.add("python_stubs")
    if (root / "NXBIN" / "python").is_dir():
        caps.add("python_modules")
    if (root / "NXBIN" / "managed" / "NXOpen.xml").exists():
        caps.add("api_docs")
    # 内置 Copilot:按结构特征判断,与 release 无关 —— 2606 / 2506 / 2406 / 2306 ...
    # 只要装了这一版并且带这套文件,能力就是 copilot。
    if detect_copilot(root).available:
        caps.add("copilot")
    return frozenset(caps)


def detect_copilot(root: Path) -> CopilotProbe:
    """Report whether *root* ships the built-in Designcenter Copilot feature.

    Structural, never release-based: the files decide, not the version number, so
    a release that carries the feature is recognised whether or not this package
    has heard of it. An install without the feature yields an empty probe
    (``available`` false, no markers), which is also what a non-NX directory gets.
    """
    markers: list[str] = []
    page: Path | None = None
    scripts_dir: Path | None = None
    for name, rel in COPILOT_MARKERS:
        path = root.joinpath(*rel.split("/"))
        hit = path.is_file() if name == "page" else path.is_dir()
        if not hit:
            continue
        markers.append(name)
        if name == "page":
            page = path
        elif name == "plchat_dir":
            scripts_dir = path
    libraries: list[Path] = []
    lib_dir = root / COPILOT_LIB_DIR
    if lib_dir.is_dir():
        try:
            libraries = sorted(p for p in lib_dir.glob(COPILOT_LIB_GLOB) if p.is_file())
        except OSError:
            libraries = []
    if libraries:
        markers.append("ai_libs")
    return CopilotProbe(
        available=bool(markers),
        markers=tuple(markers),
        page=page,
        scripts_dir=scripts_dir,
        libraries=tuple(libraries),
    )


def detect_release(root: Path, explicit: str | None = None) -> str:
    """Best-effort release identifier such as `"2512"`.

    Tries, in order: an explicit value, a release marker file inside the install,
    then the trailing release token of the install directory name. Returns
    `"unknown"` rather than guessing -- callers must not depend on this.
    """
    if explicit:
        return explicit.strip()

    for marker in ("NXBIN/nxversion", "NXBIN/nx_version", "nxversion", "NXBIN/nxrelease.dat"):
        path = root / marker
        try:
            if path.is_file():
                text = path.read_text(errors="replace").strip()
                match = _RELEASE_TOKEN.search(text)
                if match:
                    return match.group(1)
                if text:
                    return text.splitlines()[0][:32]
        except OSError:
            continue

    for part in reversed(root.parts[-3:]):
        match = _RELEASE_TOKEN.search(part)
        if match:
            return match.group(1)
    return "unknown"


# ---------------------------------------------------------------------------
# Candidate sources
# ---------------------------------------------------------------------------


def fixed_drive_roots() -> list[Path]:
    """Mount points to scan. Cheap on Windows, coarse on POSIX."""
    if sys.platform != "win32":
        return [Path("/")]

    roots: list[Path] = []
    try:
        import ctypes

        mask = ctypes.windll.kernel32.GetLogicalDrives()  # type: ignore[attr-defined]
        for index in range(26):
            if mask & (1 << index):
                root = Path(f"{chr(65 + index)}:\\")
                if root.exists():
                    roots.append(root)
    except Exception:
        roots = [Path(f"{letter}:\\") for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ" if Path(f"{letter}:\\").exists()]
    return roots


def registry_candidates() -> list[str]:
    """Windows uninstall-registry entries that look like an NX installation."""
    if sys.platform != "win32":
        return []

    try:
        import winreg
    except Exception:
        return []

    hives = (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    )
    found: list[str] = []
    for hive, key_path in hives:
        try:
            with winreg.OpenKey(hive, key_path) as key:
                for index in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        with winreg.OpenKey(key, winreg.EnumKey(key, index)) as sub:
                            values: dict[str, str] = {}
                            for value_name in ("DisplayName", "InstallLocation", "DisplayIcon"):
                                try:
                                    values[value_name] = str(winreg.QueryValueEx(sub, value_name)[0])
                                except OSError:
                                    pass
                            display = values.get("DisplayName", "").upper()
                            install = values.get("InstallLocation", "")
                            if "NX" in display or "DESIGNCENTER" in display or "\\SIEMENS\\" in install.upper():
                                if install:
                                    found.append(install)
                                icon = values.get("DisplayIcon")
                                if icon:
                                    found.append(str(Path(icon.strip('"')).parent))
                    except OSError:
                        continue
        except OSError:
            continue
    return found


def vendor_bases() -> list[Path]:
    """Conventional vendor directories on every drive, both platforms."""
    bases: list[Path] = []
    if sys.platform == "win32":
        for name in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
            value = os.environ.get(name)
            if value:
                bases.append(Path(value) / "Siemens")
        for drive in fixed_drive_roots():
            bases.extend(
                (
                    drive / "Program Files" / "Siemens",
                    drive / "Program Files (x86)" / "Siemens",
                    drive / "Siemens",
                )
            )
    else:
        bases.extend((Path("/usr/local/Siemens"), Path("/opt/Siemens"), Path("/opt/siemens")))
        home = Path.home()
        bases.extend((home / "Siemens", home / "siemens"))
    return bases


def product_children(base: Path) -> Iterator[Path]:
    """Yield immediate sub-directories that look like NX product folders."""
    try:
        children = sorted(base.iterdir())
    except OSError:
        return
    for child in children:
        try:
            if child.is_dir() and _PRODUCT_NAME.match(child.name):
                yield child
        except OSError:
            continue


def iter_candidates(settings: Settings, requested: object = None) -> Iterator[tuple[Path, str]]:
    """Yield `(root, how-it-was-found)` candidates, cheapest source first."""
    seen: set[str] = set()

    def emit(value: object, source: str) -> Iterator[tuple[Path, str]]:
        root = normalize_root(value)
        if root is None:
            return
        key = str(root).casefold()
        if key in seen:
            return
        seen.add(key)
        yield root, source

    if requested:
        yield from emit(requested, "argument")
    if settings.nx_root:
        yield from emit(settings.nx_root, "environment")
    if settings.nx_bin:
        yield from emit(settings.nx_bin, "environment")

    for name in ("NX_ROOT", "NX_BIN"):
        value = env_lookup(name)
        if value:
            yield from emit(value, "environment")

    for entry in registry_candidates():
        yield from emit(entry, "registry")

    for base in vendor_bases():
        yield from emit(base, "vendor-directory")
        for child in product_children(base):
            yield from emit(child, "vendor-directory")
            yield from emit(child / "NXBIN", "vendor-directory")


def global_search(settings: Settings, require: str, max_hits: int = 10, max_dirs: int = 400_000) -> Iterator[tuple[Path, str]]:
    """Scan every fixed drive for `NXBIN` directories. Opt-out with
    `NX_SKILL_SKIP_GLOBAL_SEARCH` because it can be slow on large volumes."""
    if settings.skip_global_search:
        return

    visited = 0
    for drive in fixed_drive_roots():
        for current, dirs, _files in os.walk(drive, topdown=True):
            visited += 1
            if visited > max_dirs:
                return
            dirs[:] = [d for d in dirs if d.casefold() not in _SKIP_DIR_NAMES]
            for name in list(dirs):
                if name.casefold() != "nxbin":
                    continue
                root = normalize_root(Path(current) / name)
                if root is not None and satisfies(root, require):
                    dirs.remove(name)
                    yield root, "global-search"
                    max_hits -= 1
                    if max_hits <= 0:
                        return

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def find_all(settings: Settings | None = None, require: str = "run_journal") -> list[NxInstall]:
    """Return every validated NX installation, best (highest release) first."""
    settings = settings or Settings.from_env()
    installs: dict[str, NxInstall] = {}

    for root, source in iter_candidates(settings):
        if not satisfies(root, require):
            continue
        key = str(root).casefold()
        installs.setdefault(
            key,
            NxInstall(
                root=root,
                release=detect_release(root),
                source=source,
                capabilities=detect_capabilities(root),
            ),
        )

    if not installs:
        for root, source in global_search(settings, require):
            key = str(root).casefold()
            installs.setdefault(
                key,
                NxInstall(
                    root=root,
                    release=detect_release(root),
                    source=source,
                    capabilities=detect_capabilities(root),
                ),
            )

    def sort_key(install: NxInstall) -> tuple[int, str]:
        numeric = int(install.release) if install.release.isdigit() else -1
        return (numeric, str(install.root).casefold())

    return sorted(installs.values(), key=sort_key, reverse=True)


def discover(
    requested: object = None,
    require: str = "run_journal",
    settings: Settings | None = None,
) -> NxInstall:
    """Resolve a single NX installation or raise :class:`NxNotFound`.

    An explicit *requested* root is honoured first and, when it fails
    validation, the error names the requirement it failed rather than silently
    falling back to a different installation.
    """
    settings = settings or Settings.from_env()

    if requested:
        root = normalize_root(requested)
        if root is not None and satisfies(root, require):
            return NxInstall(
                root=root,
                release=detect_release(root),
                source="argument",
                capabilities=detect_capabilities(root),
            )
        # An explicit request is a statement of intent. Falling back to a
        # different installation would silently operate on the wrong release, so
        # fail here and say precisely why the requested path was rejected.
        raise NxNotFound(
            require,
            [
                f"{requested}  [argument -- rejected: does not satisfy {require!r}]",
                "Discovery did not continue: an explicitly requested installation is never "
                "silently replaced by another one.",
            ],
        )

    checked: list[str] = []
    for root, source in iter_candidates(settings):
        checked.append(f"{root}  [{source}]")
        if satisfies(root, require):
            return NxInstall(
                root=root,
                release=detect_release(root),
                source=source,
                capabilities=detect_capabilities(root),
            )

    for root, source in global_search(settings, require):
        checked.append(f"{root}  [{source}]")
        return NxInstall(
            root=root,
            release=detect_release(root),
            source=source,
            capabilities=detect_capabilities(root),
        )

    raise NxNotFound(require, checked)
