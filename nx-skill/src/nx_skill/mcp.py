"""Convenience entry point so `python -m nx_skill.mcp` starts the server.

The MCP manifest in `.mcp.json` points here, which keeps the launcher a plain
`python -m` invocation with no shell, no PowerShell and no absolute path.
"""

from .server import main

if __name__ == "__main__":
    raise SystemExit(main())
