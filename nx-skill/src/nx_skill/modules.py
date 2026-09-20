"""Inventory of the NXOpen modules an installation can actually import.

This deliberately does **not** ask the live bridge. The original plugin only
implemented `module-list` in its scripting layer, and doing it here is strictly
better: it reads the installation on disk, so it answers with no NX running, no
licence, and no bridge -- and it answers about a *specific* installation rather
than whichever session happens to be open.

Three independent sources are combined, because an installation can have any of
them and they disagree in useful ways:

* `UGOPEN/pythonStubs/NXOpen/*` -- what the vendor intends to be usable.
* `NXBIN/python/NXOpen_*.pyd` -- what the embedded interpreter can really load.
* `NXBIN/managed/*.dll` -- the .NET assemblies (what the live bridge needs).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .discovery import NxInstall

#: Modules a modelling or CAE workflow is likely to need, reported explicitly so
#: a missing one is visible before code depends on it.
REQUIRED_MODULES: tuple[str, ...] = (
    "NXOpen.Features",
    "NXOpen.Assemblies",
    "NXOpen.Drawings",
    "NXOpen.CAM",
    "NXOpen.CAE",
    "NXOpen.UF",
)


@dataclass
class ModuleInventory:
    nx_root: Path
    release: str
    modules: tuple[str, ...] = ()
    required: dict[str, bool] = field(default_factory=dict)
    stubs_dir: Path | None = None
    pyd_dir: Path | None = None
    managed_dir: Path | None = None
    managed_assemblies: tuple[str, ...] = ()

    @property
    def missing_required(self) -> tuple[str, ...]:
        return tuple(name for name, present in self.required.items() if not present)

    def to_dict(self) -> dict[str, object]:
        return {
            "nxRoot": str(self.nx_root),
            "release": self.release,
            "moduleCount": len(self.modules),
            "modules": list(self.modules),
            "required": dict(self.required),
            "missingRequired": list(self.missing_required),
            "sources": {
                "pythonStubs": str(self.stubs_dir) if self.stubs_dir else None,
                "pythonExtensionModules": str(self.pyd_dir) if self.pyd_dir else None,
                "managedAssemblies": str(self.managed_dir) if self.managed_dir else None,
            },
            "managedAssemblies": list(self.managed_assemblies),
        }


def _safe_dirs(path: Path) -> list[Path]:
    try:
        return sorted((p for p in path.iterdir() if p.is_dir()), key=lambda p: p.name)
    except OSError:
        return []


def _safe_files(path: Path, pattern: str) -> list[Path]:
    try:
        return sorted(path.glob(pattern), key=lambda p: p.name)
    except OSError:
        return []


def inventory(install: NxInstall) -> ModuleInventory:
    """Build the module inventory for one installation."""
    root = install.root
    stubs_dir = root / "UGOPEN" / "pythonStubs" / "NXOpen"
    pyd_dir = install.nxbin / "python"
    managed_dir = install.managed

    modules: set[str] = set()

    if stubs_dir.is_dir():
        for child in _safe_dirs(stubs_dir):
            modules.add(f"NXOpen.{child.name}")
    else:
        stubs_dir = None  # type: ignore[assignment]

    if pyd_dir.is_dir():
        for file in _safe_files(pyd_dir, "NXOpen_*.pyd"):
            modules.add("NXOpen." + file.stem[len("NXOpen_") :])
    else:
        pyd_dir = None  # type: ignore[assignment]

    managed: list[str] = []
    if managed_dir.is_dir():
        managed = [
            file.name
            for file in _safe_files(managed_dir, "*.dll")
            if any(token in file.stem for token in ("Open", "NXOpen", "Snap"))
        ]
    else:
        managed_dir = None  # type: ignore[assignment]

    modules.add("NXOpen")
    ordered = tuple(sorted(modules))

    required = {
        name: (name in modules) or (name == "NXOpen.UF" and pyd_dir is not None and (pyd_dir / "NXOpen_UF.pyd").exists())
        for name in REQUIRED_MODULES
    }

    return ModuleInventory(
        nx_root=root,
        release=install.release,
        modules=ordered,
        required=required,
        stubs_dir=stubs_dir,
        pyd_dir=pyd_dir,
        managed_dir=managed_dir,
        managed_assemblies=tuple(managed),
    )
