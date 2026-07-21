"""verifiedai as an MCP server — so AI agents can audit and repair the proofs
they write, from inside any MCP client (Claude Code, Cursor, custom agents).

Run (stdio transport):
    PYTHONPATH=cli python3 -m verifiedai.mcp_server

Register with Claude Code:
    claude mcp add verifiedai -- env PYTHONPATH=/path/to/verifiedai/cli \
        python3 -m verifiedai.mcp_server
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .lean import LeanProject

mcp = FastMCP("verifiedai")


@mcp.tool()
def audit_file(project_root: str, file: str) -> dict:
    """Audit the theorem statements in a Lean 4 file for problems the kernel cannot
    see: vacuous (contradictory) hypotheses, trivially-true statements, and unused
    hypotheses. Every check is a real Lean compilation. The file must already
    compile; `project_root` is the directory containing the lakefile and `file` is
    the .lean path relative to it."""
    from .audit import Auditor

    project = LeanProject(project_root)
    try:
        thms = Auditor(project, file).run()
    except RuntimeError as e:
        return {"ok": False, "error": str(e)}
    return {
        "ok": True,
        "file": file,
        "theorems": [
            {"name": t.name, "line": t.line, "findings": t.findings} for t in thms
        ],
        "flagged": sum(1 for t in thms if t.findings),
    }


@mcp.tool()
def repair_project(project_root: str, use_llm: bool = False) -> dict:
    """Build a Lean 4 project and automatically repair broken proofs. Fix ladder:
    `exact?` library search, then a tactic cascade, then (if use_llm) an LLM — and
    a fix is only kept if the Lean kernel verifies the file afterwards. Returns
    which declarations were fixed, by what method, and which need a human."""
    from .repair import Repairer

    project = LeanProject(project_root)
    results = Repairer(project, use_llm=use_llm).run()
    return {
        "ok": all(r.fixed for r in results),
        "repairs": [
            {
                "file": r.file,
                "declaration": r.decl_head,
                "fixed": r.fixed,
                "method": r.method,
                "error": r.error,
            }
            for r in results
        ],
    }


def main() -> None:
    mcp.run()  # stdio transport


if __name__ == "__main__":
    main()
