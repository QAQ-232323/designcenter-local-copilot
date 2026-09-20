#!/usr/bin/env python3
"""Mirror the canonical SKILL.md into skills/nx/SKILL.md.

Hosts disagree about where a skill lives: some read a top-level SKILL.md, others
expect a skill directory. Rather than pick one, the file is written twice and a
test fails if the copies drift. Run this after editing either copy.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "SKILL.md"
MIRROR = ROOT / "skills" / "nx" / "SKILL.md"


def main() -> int:
    if not CANONICAL.is_file():
        print(f"missing canonical skill file: {CANONICAL}", file=sys.stderr)
        return 1
    text = CANONICAL.read_text(encoding="utf-8")
    MIRROR.parent.mkdir(parents=True, exist_ok=True)
    if MIRROR.is_file() and MIRROR.read_text(encoding="utf-8") == text:
        print("already in sync")
        return 0
    MIRROR.write_text(text, encoding="utf-8")
    print(f"wrote {MIRROR.relative_to(ROOT)} ({len(text.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
