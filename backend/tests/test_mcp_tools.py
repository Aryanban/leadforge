"""Guards the MCP tool surface: every advertised tool must be dispatched.

Regression guard — 7 tools were once advertised in ``TOOLS_DEFINITIONS`` but
missing from ``handle_tool_call``'s dispatch chain, so any agent that called
one crashed with ``Unknown tool``. This test parses the server source and
fails if the advertised set and the handled set ever diverge again.
"""

import re
from pathlib import Path

MCP_SOURCE = Path(__file__).resolve().parents[1] / "app" / "mcp_server.py"


def _advertised_tools(src: str) -> set:
    return set(re.findall(r'"name": "(leadforge_[a-z_]+)"', src))


def _handled_tools(src: str) -> set:
    return set(re.findall(r'(?:if|elif) name == "(leadforge_[a-z_]+)"', src))


def test_every_advertised_tool_has_a_dispatch_handler():
    src = MCP_SOURCE.read_text(encoding="utf-8")
    advertised = _advertised_tools(src)
    handled = _handled_tools(src)

    assert advertised, f"no tool definitions parsed from {MCP_SOURCE}"
    assert advertised == handled, (
        "MCP tools advertised but not dispatched: "
        f"{sorted(advertised - handled) or 'none'}; "
        f"dispatched but not advertised: {sorted(handled - advertised) or 'none'}"
    )


def test_dispatch_falls_back_to_unknown_tool_error():
    src = MCP_SOURCE.read_text(encoding="utf-8")
    assert 'raise ValueError(f"Unknown tool: {name}")' in src, (
        "dispatch must reject unknown tools explicitly"
    )
