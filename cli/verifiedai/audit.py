"""Statement auditor: finds theorems that are kernel-accepted but don't say what
their author thinks they say — vacuous hypotheses, trivially-true statements,
unused hypotheses."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .lean import LeanProject, find_matching

_DECL_RE = re.compile(r"^[ \t]*(?:private\s+|protected\s+)?(theorem|lemma)\s+([\w'.]+)", re.M)

VACUITY_TACTICS = "first | omega | simp_all | decide"
TRIVIALITY_TACTICS = "first | rfl | omega | decide | simp"


@dataclass
class Theorem:
    name: str
    line: int
    binders: str
    conclusion: str
    findings: list[dict] = field(default_factory=list)


def parse_theorems(src: str) -> list[Theorem]:
    thms: list[Theorem] = []
    for m in _DECL_RE.finditer(src):
        i = m.end()
        assign = find_matching(src, i, ":=")
        if assign is None:
            continue
        # first top-level ':' before ':=' separates binders from the statement
        colon = None
        j = i
        depth = 0
        while j < assign:
            c = src[j]
            if c in "([{⟨":
                depth += 1
            elif c in ")]}⟨⟩":
                depth -= 1 if c in ")]}⟩" else 0
            elif depth == 0 and c == ":" and not src.startswith(":=", j):
                colon = j
                break
            j += 1
        if colon is None:
            continue
        thms.append(
            Theorem(
                name=m.group(2),
                line=src[: m.start()].count("\n") + 1,
                binders=src[i:colon].strip(),
                conclusion=src[colon + 1 : assign].strip(),
            )
        )
    return thms


def _probe_source(base_src: str, decl: str) -> str:
    return (
        base_src
        + "\n\n-- verifiedai audit probe (auto-generated, never committed)\n"
        + "set_option linter.unusedVariables false\n"
        + "set_option maxHeartbeats 400000\n"
        + decl
        + "\n"
    )


class Auditor:
    def __init__(self, project: LeanProject, rel_path: str):
        self.project = project
        self.rel_path = rel_path
        self.abs_path = project.root / rel_path
        self.src = self.abs_path.read_text()
        self.probe_path = self.project.root / ".verifiedai_probe.lean"

    def _probe_compiles(self, decl: str) -> bool:
        self.probe_path.write_text(_probe_source(self.src, decl))
        try:
            ok, _, _ = self.project.check_file(self.probe_path.name)
        finally:
            self.probe_path.unlink(missing_ok=True)
        return ok

    def run(self) -> list[Theorem]:
        # Precondition: the file itself must compile.
        ok, diags, _ = self.project.check_file(self.rel_path)
        if not ok:
            errs = "\n".join(f"  {d.file}:{d.line}: {d.message}" for d in diags if d.severity == "error")
            raise RuntimeError(f"{self.rel_path} does not compile; fix it (or run repair) first:\n{errs}")

        thms = parse_theorems(self.src)

        # Unused-hypothesis warnings from the compiler, mapped to enclosing theorem.
        unused = [(d.line, d.message) for d in diags if d.severity == "warning" and "unused variable" in d.message]
        starts = [t.line for t in thms]
        for ln, msg in unused:
            owner = None
            for t, s in zip(thms, starts):
                if s <= ln:
                    owner = t
            if owner:
                var = msg.split("`")[1] if "`" in msg else "?"
                owner.findings.append(
                    {
                        "kind": "unused_hypothesis",
                        "severity": "warning",
                        "detail": f"hypothesis `{var}` is never used by the proof — "
                        "the statement may be over-constrained or mis-formalized",
                    }
                )

        for t in thms:
            binders = t.binders if t.binders else ""
            # Vacuity: can False be derived from the hypotheses alone?
            vac = f"theorem __verifiedai_vac_{t.name.replace('.', '_')} {binders} : False := by {VACUITY_TACTICS}"
            if self._probe_compiles(vac):
                t.findings.append(
                    {
                        "kind": "vacuous",
                        "severity": "error",
                        "detail": "the hypotheses are contradictory (False is derivable from them alone) — "
                        "this theorem is vacuously true and proves nothing about any real case",
                    }
                )
                continue  # a vacuous statement is trivially provable too; don't double-report

            # Triviality: does a one-step tactic close the goal?
            triv = (
                f"theorem __verifiedai_triv_{t.name.replace('.', '_')} {binders} : "
                f"{t.conclusion} := by {TRIVIALITY_TACTICS}"
            )
            if self._probe_compiles(triv):
                t.findings.append(
                    {
                        "kind": "trivial",
                        "severity": "info",
                        "detail": f"the statement is closed by `{TRIVIALITY_TACTICS}` alone — "
                        "it may be a simplification of the claim you meant to formalize",
                    }
                )
        return thms


def render_report(rel_path: str, thms: list[Theorem], as_json: bool = False) -> str:
    if as_json:
        return json.dumps(
            {
                "file": rel_path,
                "theorems": [
                    {"name": t.name, "line": t.line, "findings": t.findings} for t in thms
                ],
            },
            indent=2,
        )
    G, Y, R, B, DIM, END = "\033[32m", "\033[33m", "\033[31m", "\033[34m", "\033[2m", "\033[0m"
    lines = [f"\n{B}verifiedai audit{END} — {rel_path}\n"]
    flagged = 0
    for t in thms:
        if not t.findings:
            lines.append(f"  {G}✓{END} {t.name} {DIM}(line {t.line}){END}")
            continue
        flagged += 1
        worst = max(t.findings, key=lambda f: {"info": 0, "warning": 1, "error": 2}[f["severity"]])
        mark = {"error": f"{R}✗", "warning": f"{Y}⚠", "info": f"{Y}○"}[worst["severity"]]
        lines.append(f"  {mark}{END} {t.name} {DIM}(line {t.line}){END}")
        for f in t.findings:
            tag = {"error": R, "warning": Y, "info": Y}[f["severity"]]
            lines.append(f"      {tag}[{f['kind']}]{END} {f['detail']}")
    lines.append(
        f"\n  {len(thms)} theorems audited, "
        + (f"{R}{flagged} flagged{END}" if flagged else f"{G}all clean{END}")
        + "\n"
    )
    return "\n".join(lines)
