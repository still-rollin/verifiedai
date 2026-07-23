# Statement audit: ProofNet (Lean 4 port)

**TL;DR — we audited all 374 statements of the ProofNet Lean 4 port
([faabian/Proofnet](https://github.com/faabian/Proofnet), LeanDojo-traceable,
toolchain v4.26.0-rc1): 6 one-tactic-trivial statements (1.6%), 0 vacuous.
Every finding is a compiled Lean probe. This run also caught a soundness bug
in our own engine — see below; we're publishing that too.**

ProofNet formalizes undergraduate textbook exercises (Rudin, Artin, Axler,
Munkres, Dummit–Foote, …) as statement-only theorems. It's the "textbook
mathematics" complement to miniF2F's competition problems, and its Lean 4
ports are low-maintenance — the profile where statement defects linger.

## Findings

All 6 findings are the same phenomenon: **the exercise is already a mathlib
lemma**, so the statement closes by `simp` with all hypotheses stripped:

| theorem | statement (abridged) | the mathlib fact |
|---|---|---|
| Axler `exercise_1_3` | `-(-v) = v` | `neg_neg` |
| Axler `exercise_1_4` | `a • v = 0 ↔ a = 0 ∨ v = 0` | `smul_eq_zero` |
| Dummit–Foote `exercise_1_1_20` | `orderOf x = orderOf x⁻¹` | `orderOf_inv` |
| Rudin `exercise_1_1a` | `Irrational x → Irrational (x + ↑y)` | rat-add irrationality lemma |
| Pugh `exercise_2_32a` | `IsClopen (A : Set ℕ)` | discrete-topology instance |
| Artin `exercise_11_2_13` | Gaussian-integer divisibility descent | `Zsqrtd` divisibility lemma |

These statements are *correct*. The observation is benchmark-difficulty, not
error: a prover scoring on these items demonstrates library retrieval, not
mathematical reasoning — which matters when ProofNet subsets appear in
training and evaluation mixes.

Raw report: [`proofnet_audit.json`](proofnet_audit.json). Reproduce:

```sh
cd experiments && git clone https://github.com/faabian/Proofnet
cd Proofnet && lake exe cache get && cd ../..
python3 bench/audit_corpus.py --repo experiments/Proofnet \
    --glob 'Proofnet/*.lean' --out experiments/proofnet_audit.json
```

## The bug this run caught — in our own engine

Our first ProofNet sweep reported **61 findings, 55 of them "vacuous", in
suspicious whole-file clusters**. They were false, and the mechanism is worth
publishing: Lean aborts elaboration after `maxErrors = 100`, and in a probe
file *errors are the normal case* (every clean theorem fails its probes). On
files with 35+ theorems — ProofNet's textbook files have up to 87 — the error
stream stopped mid-file, and the engine's "no error in this probe's span ⇒
probe compiled" logic turned every later probe into a false finding.

The fix, shipped in [`audit.py`](../cli/verifiedai/audit.py) with regression
tests:

1. **Chunked batching** — at most 20 theorems' probes per compile (≤80 errors
   worst-case; the cap is unreachable on any toolchain).
2. **Positive-confirmation sentinels** — every probe carries
   `#print axioms <probe>`; a finding now requires the sentinel's output to be
   *present and sorry-free*, so any abort mode fails safe (no finding) instead
   of fabricating findings. Attribution-by-silence is gone.

Auditing cost is now 2 compiles per file up to 20 theorems, +1 per additional
20 (ProofNet: 374 theorems, 11 files, 13 min on a laptop).

We're a tool whose entire value is "sound by construction," so the bar must
be: when our engine has a bug, we say so, we regression-test it, and the false
findings never ship. That is also precisely the argument for running audits in
CI rather than trusting any one-off sweep — including ours.
