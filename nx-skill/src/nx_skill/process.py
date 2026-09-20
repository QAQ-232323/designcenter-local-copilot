"""Cross-platform probing for running NX processes.

The original implementation shelled out to PowerShell's `Get-Process`. This
module uses `tasklist` on Windows and `ps` elsewhere so the package has no
PowerShell dependency for read-only status calls, and degrades to an empty list
rather than raising when the probe itself is unavailable.
"""

from __future__ import annotations

import csv
import io
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

#: Executable basenames that mean "an NX session is running".
GUI_PROCESS_NAMES = frozenset({"ugraf", "ugraf.exe", "nx", "nx.exe"})
JOURNAL_PROCESS_NAMES = frozenset({"run_journal", "run_journal.exe"})


@dataclass(frozen=True)
class ProcessInfo:
    name: str
    pid: int
    title: str = ""

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "pid": self.pid, "title": self.title}


def _probe_windows() -> list[ProcessInfo]:
    completed = subprocess.run(
        ["tasklist", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    if completed.returncode != 0:
        return []
    found: list[ProcessInfo] = []
    for row in csv.reader(io.StringIO(completed.stdout)):
        if len(row) < 2:
            continue
        name = row[0].strip()
        if not name:
            continue
        try:
            pid = int(row[1].strip())
        except ValueError:
            continue
        found.append(ProcessInfo(name=name, pid=pid, title=row[2].strip() if len(row) > 2 else ""))
    return found


def _probe_posix() -> list[ProcessInfo]:
    completed = subprocess.run(
        ["ps", "-eo", "pid=,comm="],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    if completed.returncode != 0:
        return []
    found: list[ProcessInfo] = []
    for line in completed.stdout.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2:
            continue
        try:
            found.append(ProcessInfo(name=Path(parts[1]).name, pid=int(parts[0])))
        except ValueError:
            continue
    return found


def list_processes() -> list[ProcessInfo]:
    try:
        return _probe_windows() if sys.platform == "win32" else _probe_posix()
    except (OSError, subprocess.SubprocessError):
        return []


def _matching(names: frozenset[str]) -> list[ProcessInfo]:
    wanted = {n.casefold() for n in names}
    return [p for p in list_processes() if p.name.casefold() in wanted]


def nx_gui_processes() -> list[ProcessInfo]:
    """Running interactive NX sessions authorised to host the live bridge."""
    return _matching(GUI_PROCESS_NAMES)


def nx_journal_processes() -> list[ProcessInfo]:
    """Running batch journal processes (used to avoid concurrent runs)."""
    return _matching(JOURNAL_PROCESS_NAMES)


def nx_running() -> bool:
    return bool(nx_gui_processes())
