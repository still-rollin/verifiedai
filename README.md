# verifiedai — CI for formal proofs

**The kernel checks your proofs. Nobody checks your statements — and mathlib breaks
your build every month. verifiedai does both.**

Two commands, one bot:

- **`verifiedai audit`** — flags theorems that are kernel-accepted but don't say what
  you think they say: contradictory (vacuous) hypotheses, trivially-true statements,
  unused hypotheses. The class of error that made [more than half of miniF2F's failure
  cases](https://arxiv.org/abs/2511.03108) statement bugs, unnoticed for five years.
- **`verifiedai repair`** — when a dependency bump breaks your proofs, repairs them with
  a deterministic-first ladder (`exact?` library search → tactic cascade → LLM), and
  **only accepts fixes the Lean kernel verifies**. It cannot ship a wrong fix.

## Quick start

```sh
# Audit a file's theorem statements
PYTHONPATH=cli python3 -m verifiedai audit <project-root> Demo/Pricing.lean

# Repair a broken build (add ANTHROPIC_API_KEY for the LLM tier; optional)
PYTHONPATH=cli python3 -m verifiedai repair <project-root>
```

## Try the demo (90 seconds)

```sh
cd demo && lake build          # green — but is everything as it seems?
cd .. && PYTHONPATH=cli python3 -m verifiedai audit demo Demo/Pricing.lean
#  ✗ big_discount_still_positive — VACUOUS: hypotheses are contradictory
#  ⚠ tax_identity — trivial + unused hypothesis

./demo/break.sh                # simulate a dependency-bump breakage
PYTHONPATH=cli python3 -m verifiedai repair demo --no-llm
#  ✓ fixed via exact? → exact Nat.add_comm a b   (kernel-verified)
```

## CI integration

Copy [`action/verifiedai.yml`](action/verifiedai.yml) into `.github/workflows/` of any
Lean 4 project — every PR gets its new theorem statements audited, with findings posted
as a PR comment.

## How the audit works

For each `theorem`/`lemma` in a file that already compiles:

| Check | Mechanism | Meaning when it fires |
|---|---|---|
| **vacuous** | try to prove `False` from the hypotheses alone (`omega`/`simp_all`/`decide`) | the theorem is true about nothing |
| **trivial** | try to close the statement with `rfl`/`omega`/`decide`/`simp` | likely a simplification of the intended claim |
| **unused hypothesis** | compiler's unused-variable analysis, mapped to the enclosing theorem | statement may be over-constrained or mis-formalized |

Every probe is an actual Lean compilation — no heuristics, no false certainty.

## Status

Early prototype (v0.1). Roadmap: mathlib-scale probe batching, LLM back-translation
faithfulness checks (formal → informal → compare), GitHub App packaging, Rocq/Coq
support.

Built by [Ayaan Siddiqui](mailto:f20231060@hyderabad.bits-pilani.ac.in) — BITS Pilani
Hyderabad · research intern, INRIA/CNRS Paris. This repository contains no third-party
or institutional code; it is a clean-room implementation.
