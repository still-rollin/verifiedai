"""Statement auditor: finds theorems that are kernel-accepted but don't say what
their author thinks they say — vacuous hypotheses, trivially-true statements,
unused hypotheses.

Engine design
-------------
Every check is a real Lean compilation ("probe"). For speed, all probes for a
file are batched into ONE compile: Lean 4 keeps elaborating after a declaration
fails, so we insert every probe declaration into a copy of the file and read
which probes compiled (probe fired) vs errored (statement survived) from a
single pass. Probes are inserted immediately after their theorem, inside the
same namespace/section, so context (open, variable, local defs) is preserved.

Cost: 2 compiles per file (original + probe copy) up to 20 theorems, +1 probe
compile per additional 20 (chunking keeps the error count under Lean's
maxErrors=100 abort — in a probe file, errors are the NORMAL case). Every probe
carries a `#print axioms` sentinel; a finding requires the sentinel present and
sorry-free, so an aborted compile fails safe instead of fabricating findings.
If batching can't attribute an error cleanly, we fall back to one-probe-per-
compile, which is slower but unambiguous.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .lean import Diagnostic, LeanProject, find_matching

_DECL_RE = re.compile(r"^(?:@\[[^\]]*\]\s*)?(?:private\s+|protected\s+)?(theorem|lemma)\s+([\w'.]+)", re.M)

# A line that starts a new top-level item — the safe place to insert a probe.
_BOUNDARY_RE = re.compile(
    r"^(?:@\[|/--|/-!|theorem\b|lemma\b|def\b|abbrev\b|example\b|instance\b|structure\b"
    r"|inductive\b|class\b|end\b|section\b|namespace\b|open\b|variable\b|set_option\b"
    r"|attribute\b|deriving\b|import\b|#|private\b|protected\b|noncomputable\b|mutual\b)"
)

VACUITY_TACTICS = "first | omega | simp_all | decide"
TRIVIALITY_TACTICS = "first | rfl | omega | decide | simp"

_PROBE_OPTS = (
    "set_option linter.unusedVariables false in\n"
    "set_option maxHeartbeats 400000 in\n"
)


@dataclass
class Theorem:
    name: str
    line: int
    binders: str
    conclusion: str
    insert_at: int  # 0-based line index in the source where probes go
    docstring: str = ""  # `/-- ... -/` immediately above, if any (informal statement)
    findings: list[dict] = field(default_factory=list)


@dataclass
class _ProbeSpan:
    thm: Theorem
    kind: str  # "vac" | "triv"
    start: int  # 1-based line range in the probe file
    end: int


def parse_theorems(src: str) -> list[Theorem]:
    lines = src.splitlines()
    # precompute char offset of each line start for offset->line conversion
    offsets, off = [], 0
    for l in lines:
        offsets.append(off)
        off += len(l) + 1

    def line_of(pos: int) -> int:
        lo, hi = 0, len(offsets) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if offsets[mid] <= pos:
                lo = mid
            else:
                hi = mid - 1
        return lo

    docs = [(dm.start(), dm.end(), dm.group(1).strip()) for dm in re.finditer(r"/--(.*?)-/", src, re.S)]

    def doc_for(decl_start: int) -> str:
        for ds, de, text in docs:
            if de <= decl_start and src[de:decl_start].strip() == "":
                return text
        return ""

    thms: list[Theorem] = []
    for m in _DECL_RE.finditer(src):
        i = m.end()
        assign = find_matching(src, i, ":=")
        if assign is None:
            continue
        # first top-level ':' before ':=' separates binders from the statement
        colon = None
        j, depth = i, 0
        while j < assign:
            c = src[j]
            if c in "([{⟨":
                depth += 1
            elif c in ")]}⟩":
                depth -= 1
            elif depth == 0 and c == ":" and not src.startswith(":=", j):
                colon = j
                break
            j += 1
        if colon is None:
            continue
        decl_line = line_of(m.start())
        # insertion point: first boundary line after the ':=' line
        insert_at = len(lines)
        for k in range(line_of(assign) + 1, len(lines)):
            if lines[k] and not lines[k][0].isspace() and _BOUNDARY_RE.match(lines[k]):
                insert_at = k
                break
        thms.append(
            Theorem(
                name=m.group(2),
                line=decl_line + 1,
                binders=src[i:colon].strip(),
                conclusion=src[colon + 1 : assign].strip(),
                insert_at=insert_at,
                docstring=doc_for(m.start()),
            )
        )
    return thms


def _binder_groups(binders: str) -> list[str]:
    """Split a binder string into top-level (…) / {…} / […] / ⦃…⦄ groups."""
    groups, depth, start = [], 0, None
    for i, c in enumerate(binders):
        if c in "([{⟨⦃":
            if depth == 0:
                start = i
            depth += 1
        elif c in ")]}⟩⦄":
            depth -= 1
            if depth == 0 and start is not None:
                groups.append(binders[start : i + 1])
                start = None
    return groups


def conclusion_binders(binders: str, conclusion: str) -> str:
    """Binders needed to *state* the conclusion: drop hypothesis groups whose
    bound names never appear in the conclusion. Instance binders ([...]) are
    always kept. If a dropped binder was actually needed, the probe fails to
    compile — which is the safe direction (no finding)."""
    kept = []
    for g in _binder_groups(binders):
        if g.startswith("["):
            kept.append(g)
            continue
        inner = g[1:-1]
        names = inner.split(":", 1)[0].split() if ":" in inner else inner.split()
        if any(re.search(rf"(?<![\w'']){re.escape(n)}(?![\w''])", conclusion) for n in names):
            kept.append(g)
    return " ".join(kept)


def _probe_decl(kind: str, idx: int, t: Theorem) -> str:
    safe = t.name.replace(".", "_").replace("'", "_")
    if kind == "ax":
        return f"#print axioms {t.name}\n"
    if kind == "vac":
        nm = f"__verifiedai_vac_{idx}_{safe}"
        sig = f"theorem {nm} {t.binders} : False := by {VACUITY_TACTICS}"
    else:
        # triviality = the conclusion holds WITHOUT the hypotheses
        nm = f"__verifiedai_triv_{idx}_{safe}"
        sig = (
            f"theorem {nm} {conclusion_binders(t.binders, t.conclusion)} : "
            f"{t.conclusion} := by {TRIVIALITY_TACTICS}"
        )
    # Sentinel: positive confirmation that THIS probe compiled. If elaboration
    # aborts mid-file (e.g. Lean's maxErrors cap — errors are the NORMAL case in
    # a probe file), later probes emit no error; without the sentinel that
    # absence would read as a finding. A missing sentinel fails safe instead.
    return _PROBE_OPTS + sig + f"\n#print axioms {nm}\n"


_FINDING = {
    "vac": {
        "kind": "vacuous",
        "severity": "error",
        "detail": "the hypotheses are contradictory (False is derivable from them alone) — "
        "this theorem is vacuously true and proves nothing about any real case",
    },
    "triv": {
        "kind": "trivial",
        "severity": "info",
        "detail": "the conclusion holds WITHOUT the hypotheses "
        f"(closed by `{TRIVIALITY_TACTICS}` with hypothesis binders stripped) — "
        "the assumptions add nothing; likely a simplification of the intended claim",
    },
}

# ---- trust-chain audit ------------------------------------------------------
# Lean's kernel accepts a proof relative to the axioms it uses. `#print axioms`
# reveals the actual trust chain; anything beyond the three standard axioms
# means the theorem is NOT proved in the ordinary sense.

STD_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}
_SORRY_AX = {"sorryAx"}
_NATIVE_AX = {"Lean.ofReduceBool", "Lean.ofReduceNat", "Lean.trustCompiler"}
# `#print axioms` output carries no file:line prefix — attribute by name:
#   'Geometry.far_and_near' depends on axioms: [propext, sorryAx]
_AX_LINE_RE = re.compile(r"'([^']+)' depends on axioms:\s*\[(.*?)\]", re.S)
# axiom-free declarations print a DIFFERENT message (no list):
_AX_NONE_RE = re.compile(r"'([^']+)' does not depend on any axioms")


def _parse_sentinels(out: str) -> dict[str, set[str]]:
    """`#print axioms` results for __verifiedai_* probe declarations only."""
    # probes declared inside a namespace print with the namespace prefix
    # (e.g. 'Geometry.__verifiedai_vac_0_x') — key by the bare probe name,
    # which is unique per (kind, idx) within one probe file
    def bare(name: str) -> str | None:
        i = name.find("__verifiedai_")
        return name[i:] if i >= 0 else None

    res: dict[str, set[str]] = {}
    for name, ax_list in _AX_LINE_RE.findall(out):
        if (b := bare(name)) is not None:
            res[b] = {
                a.strip() for a in ax_list.replace("\n", " ").split(",") if a.strip()
            }
    for name in _AX_NONE_RE.findall(out):
        if (b := bare(name)) is not None:
            res[b] = set()
    return res


def apply_axiom_output(out: str, thms: list[Theorem]) -> None:
    for name, ax_list in _AX_LINE_RE.findall(out):
        t = next(
            (t for t in thms if name == t.name or name.endswith("." + t.name)), None
        )
        if t is None:
            continue
        axioms = {a.strip() for a in ax_list.replace("\n", " ").split(",") if a.strip()}
        t.findings.extend(classify_axioms(axioms))


def classify_axioms(axioms: set[str]) -> list[dict]:
    findings = []
    if axioms & _SORRY_AX:
        findings.append(
            {
                "kind": "sorry",
                "severity": "error",
                "detail": "the proof depends on `sorryAx` — it is incomplete; the kernel "
                "accepted a placeholder, not a proof",
            }
        )
    if axioms & _NATIVE_AX:
        findings.append(
            {
                "kind": "native_trust",
                "severity": "error",
                "detail": "the proof bypasses the kernel via compiler trust "
                f"({', '.join(sorted(axioms & _NATIVE_AX))} — e.g. `native_decide`); "
                "correctness rests on the compiler, not the proof checker",
            }
        )
    custom = axioms - STD_AXIOMS - _SORRY_AX - _NATIVE_AX
    if custom:
        findings.append(
            {
                "kind": "nonstandard_axiom",
                "severity": "error",
                "detail": "the proof depends on non-standard axiom(s) "
                f"[{', '.join(sorted(custom))}] — the theorem is assumed, not proved",
            }
        )
    return findings


class Auditor:
    def __init__(self, project: LeanProject, rel_path: str):
        self.project = project
        self.rel_path = rel_path
        self.abs_path = project.root / rel_path
        self.src = self.abs_path.read_text()
        # unique per-auditor probe file → concurrent audits (server mode) don't collide
        self.probe_path = self.project.root / f".verifiedai_probe_{uuid.uuid4().hex[:10]}.lean"

    # ------------------------------------------------------------------ batch

    def _build_probe_file(self, thms: list[Theorem]) -> tuple[str, list[_ProbeSpan]]:
        lines = self.src.splitlines()
        by_insert: dict[int, list[tuple[str, int, Theorem]]] = {}
        for idx, t in enumerate(thms):
            by_insert.setdefault(t.insert_at, []).append(("ax", idx, t))
            by_insert.setdefault(t.insert_at, []).append(("vac", idx, t))
            by_insert.setdefault(t.insert_at, []).append(("triv", idx, t))

        out: list[str] = []
        spans: list[_ProbeSpan] = []

        def emit_probes(at: int) -> None:
            for kind, idx, t in by_insert.get(at, []):
                decl = _probe_decl(kind, idx, t)
                start = len(out) + 1
                out.extend(decl.splitlines())
                spans.append(_ProbeSpan(t, kind, start, len(out)))

        for k, line in enumerate(lines):
            emit_probes(k)
            out.append(line)
        emit_probes(len(lines))
        return "\n".join(out) + "\n", spans

    # Lean aborts at maxErrors=100 (not overridable on all toolchains), and in a
    # probe file errors are the NORMAL case: a clean theorem yields up to 4
    # (2 failed probes + their 2 orphaned sentinels). 20 theorems ≤ 80 errors.
    _CHUNK = 20

    def _run_batched(self, thms: list[Theorem]) -> bool:
        """Returns True on success (findings recorded), False → caller falls back."""
        for i in range(0, len(thms), self._CHUNK):
            if not self._run_batched_chunk(thms[i : i + self._CHUNK]):
                return False
        return True

    def _run_batched_chunk(self, thms: list[Theorem]) -> bool:
        probe_src, spans = self._build_probe_file(thms)
        self.probe_path.write_text(probe_src)
        try:
            _, diags, out = self.project.check_file(self.probe_path.name)
        finally:
            self.probe_path.unlink(missing_ok=True)

        err_lines = [d.line for d in diags if d.severity == "error"]
        failed: set[tuple[int, str]] = set()  # (id(thm), kind) probes that errored
        for ln in err_lines:
            owner = next((s for s in spans if s.start <= ln <= s.end), None)
            if owner is None:
                return False  # error in original code region — attribution unsafe
            failed.add((id(owner.thm), owner.kind))

        # Positive confirmation: a probe counts as compiled ONLY if its sentinel
        # `#print axioms` output is present (and sorry-free). If elaboration
        # aborted for any reason, missing sentinels fail safe — no finding.
        sentinels = _parse_sentinels(out)
        confirmed: set[tuple[int, str]] = set()
        for idx, t in enumerate(thms):
            safe = t.name.replace(".", "_").replace("'", "_")
            for kind in ("vac", "triv"):
                axs = sentinels.get(f"__verifiedai_{kind}_{idx}_{safe}")
                if axs is not None and not (axs & _SORRY_AX):
                    confirmed.add((id(t), kind))

        # trust-chain: `#print axioms` output is attributed by theorem name
        apply_axiom_output(out, thms)

        for s in spans:
            if (
                s.kind == "vac"
                and (id(s.thm), "vac") in confirmed
                and (id(s.thm), "vac") not in failed
            ):
                s.thm.findings.append(dict(_FINDING["vac"]))
        for s in spans:
            if (
                s.kind == "triv"
                and (id(s.thm), "triv") in confirmed
                and (id(s.thm), "triv") not in failed
                and not any(f["kind"] == "vacuous" for f in s.thm.findings)
            ):
                s.thm.findings.append(dict(_FINDING["triv"]))
        return True

    # --------------------------------------------------------------- fallback

    def _probe_compiles(self, decl: str) -> bool:
        self.probe_path.write_text(self.src + "\n\n" + decl)
        try:
            ok, _, _ = self.project.check_file(self.probe_path.name)
        finally:
            self.probe_path.unlink(missing_ok=True)
        return ok

    def _run_unbatched(self, thms: list[Theorem]) -> None:
        for idx, t in enumerate(thms):
            self._trust_chain_single(t)
            if self._probe_compiles(_probe_decl("vac", idx, t)):
                t.findings.append(dict(_FINDING["vac"]))
                continue
            if self._probe_compiles(_probe_decl("triv", idx, t)):
                t.findings.append(dict(_FINDING["triv"]))

    def _trust_chain_single(self, t: Theorem) -> None:
        lines = self.src.splitlines()
        probe = lines[: t.insert_at] + [f"#print axioms {t.name}"] + lines[t.insert_at :]
        self.probe_path.write_text("\n".join(probe) + "\n")
        try:
            _, _, out = self.project.check_file(self.probe_path.name)
        finally:
            self.probe_path.unlink(missing_ok=True)
        apply_axiom_output(out, [t])

    # ------------------------------------------------------------------- main

    def run(self) -> list[Theorem]:
        # Precondition: the file itself must compile (also yields lint warnings).
        ok, diags, _ = self.project.check_file(self.rel_path)
        if not ok:
            errs = "\n".join(
                f"  {d.file}:{d.line}: {d.message}" for d in diags if d.severity == "error"
            )
            raise RuntimeError(
                f"{self.rel_path} does not compile; fix it (or run repair) first:\n{errs}"
            )

        thms = parse_theorems(self.src)
        if not thms:
            return []

        # Unused-hypothesis warnings from the compiler, mapped to enclosing theorem.
        unused = [
            (d.line, d.message)
            for d in diags
            if d.severity == "warning" and "unused variable" in d.message
        ]
        for ln, msg in unused:
            owner = None
            for t in thms:
                if t.line <= ln:
                    owner = t
            if owner:
                var = msg.split("`")[1] if "`" in msg else "?"
                owner.findings.append(
                    {
                        "kind": "unused_hypothesis",
                        "severity": "warning",
                        "detail": f"hypothesis `{var}` is never used by the declaration — "
                        "the statement may be over-constrained or mis-formalized",
                    }
                )

        if not self._run_batched(thms):
            self._run_unbatched(thms)
        return thms


# ------------------------------------------------------------------ reporting


def render_report(rel_path: str, thms: list[Theorem], as_json: bool = False) -> str:
    if as_json:
        return json.dumps(report_dict(rel_path, thms), indent=2)
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


def report_dict(rel_path: str, thms: list[Theorem]) -> dict:
    return {
        "file": rel_path,
        "theorems": [{"name": t.name, "line": t.line, "findings": t.findings} for t in thms],
        "flagged": sum(1 for t in thms if t.findings),
    }


def render_markdown(reports: list[dict]) -> str:
    """PR-comment-ready markdown for one or many file reports."""
    out = ["### 🔍 verifiedai statement audit", ""]
    total = flagged = 0
    for r in reports:
        total += len(r["theorems"])
        flagged += r["flagged"]
    out.append(f"**{total} theorems audited across {len(reports)} file(s) — {flagged} flagged**")
    out.append("")
    for r in reports:
        bad = [t for t in r["theorems"] if t["findings"]]
        if not bad:
            continue
        out.append(f"#### `{r['file']}`")
        out.append("")
        out.append("| Theorem | Line | Finding |")
        out.append("|---|---|---|")
        for t in bad:
            for f in t["findings"]:
                icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}[f["severity"]]
                detail = f["detail"].replace("|", "\\|")
                out.append(f"| `{t['name']}` | {t['line']} | {icon} **{f['kind']}** — {detail} |")
        out.append("")
    if flagged == 0:
        out.append("✅ all statements survived the probe battery.")
    return "\n".join(out)
