"""nx-skill: a portable, agent-agnostic skill for driving Siemens NX.

The package discovers an NX installation on the current machine, exposes the
offline API reference that ships inside it, executes NXOpen journals in batch,
and talks to an optional live bridge running inside an open NX session.
"""

from __future__ import annotations

__version__ = "1.0.0"

__all__ = ["__version__"]
