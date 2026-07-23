# Statement audit: Lean Workbook (auto-formalized training data)

**TL;DR — we sampled 2,000 statements from [Lean Workbook](https://huggingface.co/datasets/internlm/Lean-Workbook)
(internlm, ~140k LLM-auto-formalized contest problems, used as training data by
theorem-prover teams). Of 1,752 fully audited: 23 findings (1.31%) — 1 vacuous
statement (contradictory hypotheses) and 22 one-tactic-trivial statements,
including `theorem … (n : ℕ) : n = n` twice. Separately, 9.8% of the sample no
longer elaborates against current mathlib. Every finding is a compiled Lean
probe: sound by construction.**

## Why this corpus

Benchmarks mismeasure; training data misteaches. A vacuous or trivial statement
in an eval skews a score — the same statement in a *training corpus* is a live
reward signal teaching a prover that contradiction-mining and `rfl` are what
"doing mathematics" looks like. Lean Workbook is the largest open corpus of
LLM-auto-formalized statements and appears in the training mix of multiple
published provers (InternLM2-StepProver, DeepSeek-Prover lineage, Kimina-Prover's
data ancestry). Auto-formalized + lightly-checked + widely-trained-on is the
most vulnerable dataset profile there is. That's exactly where an automated
statement auditor should be pointed.

## Setup (fully reproducible)

- Dataset: `internlm/Lean-Workbook`, `lean_workbook.json` (140,214 entries;
  139,505 usable standalone `theorem … := by sorry` statements).
- Sample: 2,000 statements, `random.Random(42)`, both splits.
- Host: statements compiled against mathlib for Lean `v4.27.0`
  (the PutnamBench toolchain; statements import only `Mathlib`).
- Statements are packed 20 per file — the auditor costs 2 compiles per *file*,
  so 2,000 statements ≈ 100 packs ≈ 93 minutes on one M2 laptop.
- Pipeline: pack → pre-filter compile (statements that no longer elaborate are
  dropped *and counted*) → probe battery (vacuity / triviality with hypotheses
  stripped / unused hypotheses), `sorry` suppressed by design.

```sh
python3 bench/audit_lean_workbook.py --n 2000 --seed 42 \
    --host experiments/PutnamBench/lean4 --out experiments/lean_workbook_audit.json
```

Raw output: [`lean_workbook_audit.json`](lean_workbook_audit.json).

## Headline numbers

| | count | rate |
|---|---|---|
| sampled | 2,000 | |
| no longer elaborate vs current mathlib | 197 | **9.8%** |
| lost to probe-harness errors (3 packs) | 51 | 2.6% |
| **fully audited** | **1,752** | |
| **findings** | **23** | **1.31%** |
| — vacuous | 1 | |
| — one-tactic-trivial | 22 | |

Extrapolated to the full ~140k corpus, 1.31% is on the order of **~1,800
defective statements** — with the usual caveat that this is a single
2,000-statement sample and the battery only lower-bounds the defect rate
(a stronger battery flags more, never fewer).

## The vacuous statement

`lean_workbook_plus_4012` formalizes a recurrence that contradicts its own
initial conditions: `h₂ 0` forces `a 2 = a 1 + a 0 + 2 ≥ 3`, but `h₁` says
`a 2 = 2`. Kernel-certified derivation of `False` from the exact hypotheses:

```lean
theorem lean_workbook_plus_4012_is_vacuous (a : ℕ → ℕ)
    (h₀ : a 1 = 1) (h₁ : a 2 = 2)
    (h₂ : ∀ n, a (n + 2) = a (n + 1) + a n + 2) : False := by
  have h := h₂ 0
  simp only [Nat.zero_add] at h
  omega
```

It's a double defect: the paired `natural_language_statement` is about an
unrelated set-partition problem, so the formalization is both self-contradictory
*and* unfaithful to its informal source.

## A taxonomy of the 22 trivial statements

**Degenerate formalizations (6).** The auto-formalizer produced a tautology
instead of the problem:

```lean
theorem lean_workbook_plus_11333 (n : ℕ) : n = n            -- "prove f(n) = n"
theorem lean_workbook_49956      (n : ℕ) : n = n            -- independent entry!
theorem lean_workbook_plus_12314 (h₀ : (36:ℝ)/4 = 9) : 36/4 = 9   -- hypothesis IS the conclusion
theorem lean_workbook_plus_82449 …  : <expr> = <same expr>   -- literal X = X
```

plus two identity-rearrangements (`x = ⌊x⌋ + (x − ⌊x⌋)`, `3 − x ≥ 0 ↔ x ≤ 3`).

**The nat-division bug class (6) — the mathd_algebra_275 signature, again.**
Exponents like `^(3/4)`, `^(1/3)`, `^(1/5)` where the literal is elaborated in
`ℕ`, so the exponent is `0` and every term collapses to `1`:

```lean
-- each summand is x^0 = 1; "1+1+1 ≥ 1", hypotheses irrelevant
theorem lean_workbook_11013 … : (x/(x+y+z))^(3/4) + (y/(x+y+z))^(3/4)
                              + (z/(x+y+z))^(3/4) ≥ 1
```

Also in this class: `(m*n)/(m+n+1) ≥ 1/3` over `ℕ` (the RHS is `0`), and
`8 ∣ (…)` stated over `ℝ` — divisibility in a field is trivially true.
The same defect signature that shipped in miniF2F recurs, independently, in a
140k-statement training corpus. This is why a check catalog compounds:
**one signature, many corpora.**

**Zero-reasoning decidables (8).** True statements a single decision procedure
closes — `3^31 + 2^31 > 8(3^29 + 2^29)`, `2^20 % 7 = 4`, `choose 8 3 = 56`,
`Odd (2n+1)`, a finite existential over `{24,27,32}`… Harmless individually;
as training data they reward tactic-guessing over reasoning, and as benchmark
items they inflate solve rates.

**Already a mathlib lemma (2).** e.g. `gcd(2^a − 1, 2^b − 1) = 2^(gcd a b) − 1`
closes by `simp` because mathlib already knows it — a real theorem, but its
presence in a training set teaches retrieval, not proof.

## The 9.8% that no longer compiles

197 of 2,000 sampled statements fail to elaborate against current mathlib
(v4.27). This conflates two causes we do not separate here: genuine defects,
and mathlib-API drift since the corpus was generated (2024). Either way it is
operationally real: anyone training on this corpus against a current toolchain
silently loses ~10% of it — or worse, retains it via a pinned old toolchain
along with the defects above. (This drift is exactly what the `verifiedai
repair` half of the product exists for.)

## What we claim — and what we don't

- Every finding is **sound by construction**: a finding is a Lean probe that
  compiled. Zero false positives are possible. False negatives are expected —
  the battery is a lower bound.
- "Trivial" ≠ wrong. It means: closed by one tactic with all hypotheses
  stripped — no mathematical content survives formalization.
- We audited a **seeded random sample**, not the full corpus; rates carry
  sampling error (23/1752 → 95% CI roughly 0.8–2.0%).
- We audit one artifact: `internlm/Lean-Workbook` as downloaded 2026-07-23,
  against mathlib v4.27. We make **no novelty claim** — the Lean Workbook
  paper itself reports imperfect autoformalization quality; our contribution
  is that a static, model-free, 2-compiles-per-file gate finds these
  *mechanically*, which is what lets them be caught in CI before training runs,
  not in postmortems after.

## Comparison across corpora (same battery)

| corpus | type | maintained? | audited | findings |
|---|---|---|---|---|
| miniF2F-lean4 | benchmark | port, unmaintained | 488 | 1 vacuous + 50 trivial (10.4%) |
| PutnamBench | benchmark | actively maintained | 130 (partial) | 0 |
| **Lean Workbook** | **training data** | **static dump** | **1,752** | **23 (1.31%)** |

The gradient is the story: actively-maintained corpora are clean, static and
auto-generated ones aren't — and nothing in the ecosystem currently re-audits
the static ones. That is a CI problem, and CI is the product.
