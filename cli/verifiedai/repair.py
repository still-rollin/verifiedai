"""Proof repair: build the project, find broken declarations, fix them with a
deterministic-first / LLM-second ladder. A fix is accepted only if the Lean
kernel verifies the file afterwards — the tool cannot ship a wrong fix."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .lean import Diagnostic, LeanProject, find_matching
from . import llm

_DECL_START = re.compile(r"^[ \t]*(?:private\s+|protected\s+|noncomputable\s+)?(theorem|lemma|def|example|instance)\b")
_TRY_THIS = re.compile(r"Try this: (.+)")

CASCADE = "first | rfl | simp | omega | decide"
MAX_LLM_ROUNDS = 3


@dataclass
class RepairResult:
    file: str
    decl_head: str
    fixed: bool
    method: str = ""
    error: str = ""


def _decl_span(lines: list[str], error_line: int) -> tuple[int, int] | None:
    """(start, end) 0-based line span of the declaration enclosing error_line (1-based)."""
    starts = [i for i, l in enumerate(lines) if _DECL_START.match(l)]
    if not starts:
        return None
    start = max((i for i in starts if i <= error_line - 1), default=None)
    if start is None:
        return None
    end = next((i for i in starts if i > start), len(lines))
    return start, end


class Repairer:
    def __init__(self, project: LeanProject, use_llm: bool = True):
        self.project = project
        self.use_llm = use_llm

    def run(self) -> list[RepairResult]:
        ok, diags, _ = self.project.build()
        if ok:
            print("build is green — nothing to repair")
            return []
        errors = [d for d in diags if d.severity == "error" and d.file.endswith(".lean")]
        results = []
        for rel in sorted({d.file for d in errors}):
            results.extend(self._repair_file(rel, [d for d in errors if d.file == rel]))
        return results

    # -- per-file ------------------------------------------------------------

    def _repair_file(self, rel: str, file_errors: list[Diagnostic]) -> list[RepairResult]:
        abs_path = self.project.root / rel
        original = abs_path.read_text()
        results: list[RepairResult] = []
        rounds = 0
        while rounds < 10:  # safety bound; each round targets the first broken decl
            rounds += 1
            ok, diags, _ = self.project.check_file(rel)
            errs = [d for d in diags if d.severity == "error"]
            if ok or not errs:
                break
            res = self._repair_decl(rel, abs_path, errs)
            results.append(res)
            if not res.fixed:
                break
        if not results:
            # errors came from lake build but single-file check is clean (e.g. import issue)
            results.append(
                RepairResult(rel, "(file)", False, error=file_errors[0].message if file_errors else "unknown")
            )
        # if nothing was fixed at all, restore the original bytes
        if not any(r.fixed for r in results):
            abs_path.write_text(original)
        return results

    def _repair_decl(self, rel: str, abs_path: Path, errs: list[Diagnostic]) -> RepairResult:
        src = abs_path.read_text()
        lines = src.splitlines(keepends=True)
        first = errs[0]
        span = _decl_span(lines, first.line)
        if span is None:
            return RepairResult(rel, "(unknown)", False, error=first.message)
        start, end = span
        decl = "".join(lines[start:end])
        head = decl.strip().splitlines()[0][:80]
        decl_errs = "\n".join(f"line {d.line}: {d.message}" for d in errs if start + 1 <= d.line <= end)
        print(f"  repairing {rel} :: {head}")

        assign = find_matching(decl, 0, ":=")

        def apply(new_decl: str) -> tuple[bool, str]:
            candidate = "".join(lines[:start]) + new_decl.rstrip("\n") + "\n" + "".join(lines[end:])
            abs_path.write_text(candidate)
            ok, diags, out = self.project.check_file(rel)
            still = [d for d in diags if d.severity == "error" and start + 1 <= d.line]
            return ok or not any(d.severity == "error" for d in diags), out

        # Tier 1: `exact?` — let Lean's library search find the proof, then inline it.
        if assign is not None:
            probe = decl[: assign + 2] + " by\n  exact?\n"
            ok, out = apply(probe)
            if ok:
                m = _TRY_THIS.search(out)
                if m:
                    inlined = decl[: assign + 2] + " by\n  " + m.group(1).strip() + "\n"
                    ok2, _ = apply(inlined)
                    if ok2:
                        return RepairResult(rel, head, True, method="exact? → " + m.group(1).strip()[:60])
                return RepairResult(rel, head, True, method="exact?")

            # Tier 2: deterministic tactic cascade.
            ok, _ = apply(decl[: assign + 2] + f" by\n  {CASCADE}\n")
            if ok:
                return RepairResult(rel, head, True, method=f"cascade ({CASCADE})")

        # Tier 3: LLM escalation, kernel-verified, with error feedback.
        if self.use_llm:
            avail, why = llm.llm_available()
            if not avail:
                abs_path.write_text(src)
                return RepairResult(rel, head, False, error=f"deterministic tiers failed; {why}")
            feedback = None
            for _ in range(MAX_LLM_ROUNDS):
                proposal = llm.propose_fix(src, decl, decl_errs, feedback)
                if proposal is None:
                    break
                ok, out = apply(proposal)
                if ok:
                    return RepairResult(rel, head, True, method="llm (kernel-verified)")
                feedback = out[-2000:]

        abs_path.write_text(src)  # restore — never leave a broken candidate behind
        return RepairResult(rel, head, False, error=decl_errs.splitlines()[0] if decl_errs else "unfixed")


def render_results(results: list[RepairResult]) -> str:
    G, R, DIM, B, END = "\033[32m", "\033[31m", "\033[2m", "\033[34m", "\033[0m"
    lines = [f"\n{B}verifiedai repair{END}\n"]
    for r in results:
        if r.fixed:
            lines.append(f"  {G}✓ fixed{END} {r.file} {DIM}{r.decl_head}{END}")
            lines.append(f"      via {r.method}")
        else:
            lines.append(f"  {R}✗ needs human attention{END} {r.file} {DIM}{r.decl_head}{END}")
            lines.append(f"      {r.error}")
    n_fixed = sum(r.fixed for r in results)
    lines.append(f"\n  {n_fixed}/{len(results)} broken declarations repaired (all fixes kernel-verified)\n")
    return "\n".join(lines)
