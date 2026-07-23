"""Spec mutation testing: does your spec actually constrain your code?

A verified program is (implementation, spec, proof). The kernel guarantees the
proof matches the spec — it says nothing about whether the spec pins down the
implementation's behavior. A spec like `result.size = arr.size` verifies a
sort, an identity function, and a shuffle equally well.

Mechanism: mutate the implementation with a known bug (flip a comparison,
off-by-one a literal, swap && and ||), keep the spec and the ORIGINAL proof,
recompile.

  * proof breaks       → mutant KILLED — the spec constrained that behavior
  * everything compiles → mutant SURVIVED — the same proof certifies broken
                          code; the spec does not distinguish right from wrong

A survivor is a compiled artifact, not an opinion: same soundness discipline
as the statement audit. Killed ≠ strong (the proof may fail for incidental
reasons), so survivors are the only claim we make — the safe direction.

Mutations are single-site and deterministic. Sites inside comments and string
literals are skipped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Mutant:
    op: str          # operator name
    description: str # human-readable, e.g. "`<` → `≤` at offset 121"
    src: str         # full mutated text of the region
    site: int        # offset of the mutation within the region


# (name, pattern, replacement, human description)
# Order matters only for reporting. All are single-token, syntax-level flips
# chosen to be type-preserving in the common case; mutants that fail to
# typecheck are discarded as invalid, so an over-eager operator costs time,
# never soundness.
_OPERATORS: list[tuple[str, str, str, str]] = [
    ("cmp_lt_le", r"(?<![<>=!≤≥])<(?![<>=|])", "≤", "`<` → `≤`"),
    ("cmp_le_lt", r"≤", "<", "`≤` → `<`"),
    ("cmp_gt_ge", r"(?<![<>=!≤≥])>(?![<>=])", "≥", "`>` → `≥`"),
    ("cmp_ge_gt", r"≥", ">", "`≥` → `>`"),
    ("beq_bne", r"==", "!=", "`==` → `!=`"),
    ("and_or", r"&&", "||", "`&&` → `||`"),
    ("or_and", r"\|\|", "&&", "`||` → `&&`"),
    ("plus_minus", r"(?<![+.])\+(?![+.])", "-", "`+` → `-`"),
    ("minus_plus", r"(?<![-.<])-(?![->.])", "+", "`-` → `+`"),
    ("lit_offbyone", r"(?<![\w.])([1-9]\d*)(?![\w.])", None, "literal n → n+1"),
]

_COMMENT_RE = re.compile(r"--[^\n]*|/-.*?-/", re.S)
_STRING_RE = re.compile(r'"(?:[^"\\]|\\.)*"')


def _masked_spans(region: str) -> list[tuple[int, int]]:
    spans = []
    for rx in (_COMMENT_RE, _STRING_RE):
        spans += [(m.start(), m.end()) for m in rx.finditer(region)]
    return spans


def _in_masked(pos: int, spans: list[tuple[int, int]]) -> bool:
    return any(a <= pos < b for a, b in spans)


def generate_mutants(region: str, limit_per_op: int = 4) -> list[Mutant]:
    """All single-site mutants of a code region (comments/strings excluded)."""
    masked = _masked_spans(region)
    out: list[Mutant] = []
    for name, pat, repl, desc in _OPERATORS:
        rx = re.compile(pat)
        n = 0
        for m in rx.finditer(region):
            if _in_masked(m.start(), masked):
                continue
            if n >= limit_per_op:
                break
            if repl is None:  # literal off-by-one
                new = str(int(m.group(1)) + 1)
                mutated = region[: m.start(1)] + new + region[m.end(1):]
                out.append(Mutant(name, f"{desc}: {m.group(1)} → {new}",
                                  mutated, m.start(1)))
            else:
                mutated = region[: m.start()] + repl + region[m.end():]
                out.append(Mutant(name, f"{desc} at offset {m.start()}",
                                  mutated, m.start()))
            n += 1
    return out


@dataclass
class MutationResult:
    survived: list[dict] = field(default_factory=list)
    killed: int = 0
    invalid: int = 0

    @property
    def tested(self) -> int:
        return self.killed + len(self.survived)


def classify(err_lines: list[int], region_start_line: int,
             region_end_line: int) -> str:
    """One mutant's compile outcome → 'survived' | 'killed' | 'invalid'.

    An error inside the mutated region means the mutant didn't typecheck
    (invalid — tells us nothing). An error anywhere else means the proof (or a
    dependent) rejected the mutant (killed). No errors: survived.
    """
    if not err_lines:
        return "survived"
    if all(region_start_line <= ln <= region_end_line for ln in err_lines):
        return "invalid"
    return "killed"


def run_region_mutation(project, rel_path: str, src: str,
                        region_start: int, region_end: int,
                        label: str, limit_per_op: int = 4,
                        probe_name: str | None = None) -> MutationResult:
    """Mutate src[region_start:region_end], recompile per mutant, classify.

    `project` is a LeanProject. Writes a sibling probe file per mutant so the
    original is never touched.
    """
    import uuid

    region = src[region_start:region_end]
    start_line = src[:region_start].count("\n") + 1
    end_line = start_line + region.count("\n")
    probe = project.root / (
        probe_name or f".verifiedai_mut_{uuid.uuid4().hex[:10]}.lean")

    res = MutationResult()
    try:
        for mut in generate_mutants(region, limit_per_op):
            mutated_src = src[:region_start] + mut.src + src[region_end:]
            probe.write_text(mutated_src)
            _ok, diags, _out = project.check_file(probe.name)
            errs = [d.line for d in diags if d.severity == "error"]
            verdict = classify(errs, start_line, end_line)
            if verdict == "survived":
                res.survived.append({
                    "target": label, "op": mut.op, "mutation": mut.description,
                    "detail": "the original proof still certifies the mutated "
                              "implementation — either the spec does not "
                              "constrain the mutated behavior, or the mutant "
                              "is semantically equivalent (triage required)",
                })
            elif verdict == "killed":
                res.killed += 1
            else:
                res.invalid += 1
    finally:
        probe.unlink(missing_ok=True)
    return res


# ---- generic file mode (CLI) -------------------------------------------------

_DEF_RE = re.compile(
    r"^(?:@\[[^\]]*\]\s*)?(?:private\s+)?(?:noncomputable\s+)?"
    r"(?:def|abbrev)\s+([A-Za-z0-9_'.]+)", re.M)


def def_regions(src: str) -> list[tuple[str, int, int]]:
    """(name, body_start, body_end) for each top-level def/abbrev body."""
    from .audit import _BOUNDARY_RE
    from .lean import find_matching

    out = []
    lines = src.splitlines(keepends=True)
    offsets = [0]
    for ln in lines:
        offsets.append(offsets[-1] + len(ln))
    for m in _DEF_RE.finditer(src):
        if m.start() > 0 and src[m.start() - 1] not in "\n":
            continue
        assign = find_matching(src, m.end(), ":=")
        if assign is None:
            continue
        body_start = assign + 2
        # body ends at the next top-level boundary line
        line_no = src[:body_start].count("\n")
        end = len(src)
        for k in range(line_no + 1, len(lines)):
            line = lines[k]
            if line and not line[0].isspace() and _BOUNDARY_RE.match(line):
                end = offsets[k]
                break
        out.append((m.group(1), body_start, end))
    return out


def mutate_file(project, rel_path: str, limit_per_op: int = 4) -> dict:
    """Mutation-test every def in a file. Returns per-def results."""
    src = (project.root / rel_path).read_text()
    results = {}
    for name, start, end in def_regions(src):
        res = run_region_mutation(project, rel_path, src, start, end,
                                  label=name, limit_per_op=limit_per_op)
        results[name] = res
    return results
