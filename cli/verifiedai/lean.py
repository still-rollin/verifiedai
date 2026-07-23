"""Interaction with a Lean 4 / lake project: builds, single-file checks, diagnostics."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

# lake build:      error: ././././Demo/Refunds.lean:6:8: unknown constant 'X'
# lake env lean:   Demo/Refunds.lean:6:8: error: unknown constant 'X'
_LAKE_RE = re.compile(r"^(error|warning|info): (?:\./)*(.+?\.lean):(\d+):(\d+): (.*)$")
_LEAN_RE = re.compile(r"^(?:\./)*(.+?\.lean):(\d+):(\d+): (error|warning|info): (.*)$")

OPEN, CLOSE = "([{⟨", ")]}⟩"


@dataclass
class Diagnostic:
    file: str
    line: int
    col: int
    severity: str  # error | warning | info
    message: str


def parse_diagnostics(output: str) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    for raw in output.splitlines():
        m = _LAKE_RE.match(raw)
        if m:
            sev, f, ln, col, msg = m.groups()
            diags.append(Diagnostic(f, int(ln), int(col), sev, msg))
            continue
        m = _LEAN_RE.match(raw)
        if m:
            f, ln, col, sev, msg = m.groups()
            diags.append(Diagnostic(f, int(ln), int(col), sev, msg))
            continue
        # continuation line of a multi-line message
        if diags and raw.startswith(("  ", "\t")):
            diags[-1].message += "\n" + raw.strip()
    return diags


class LeanProject:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        if not (self.root / "lakefile.toml").exists() and not (self.root / "lakefile.lean").exists():
            raise FileNotFoundError(f"no lakefile found in {self.root}")

    def _run(self, args: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
        return subprocess.run(
            args, cwd=self.root, capture_output=True, text=True, timeout=timeout
        )

    def build(self) -> tuple[bool, list[Diagnostic], str]:
        p = self._run(["lake", "build"])
        out = p.stdout + p.stderr
        return p.returncode == 0, parse_diagnostics(out), out

    def check_file(
        self, rel_path: str | Path, extra_args: tuple[str, ...] = ()
    ) -> tuple[bool, list[Diagnostic], str]:
        """Compile a single .lean file against the project env (deps must be built)."""
        p = self._run(["lake", "env", "lean", *extra_args, str(rel_path)])
        out = p.stdout + p.stderr
        return p.returncode == 0, parse_diagnostics(out), out


def find_matching(src: str, start: int, needle: str = ":=") -> int | None:
    """Index of first top-level (bracket-depth-0) occurrence of `needle` at/after start."""
    depth = 0
    i = start
    while i < len(src):
        c = src[i]
        if c in OPEN:
            depth += 1
        elif c in CLOSE:
            depth -= 1
        elif depth == 0 and src.startswith(needle, i):
            return i
        i += 1
    return None
