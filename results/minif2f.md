# Statement-integrity audit of miniF2F (Lean 4)

**verifiedai swept all 488 statements of [miniF2F-lean4](https://github.com/yangky11/miniF2F-lean4)
(commit `5746b7d`, 2026-03-25) — the field's flagship theorem-proving benchmark — and found
1 vacuous statement and 50 trivially-true statements. Every finding is a compiled Lean probe,
not an opinion.**

## Method

`bench/audit_minif2f.py` — the standard verifiedai probe battery over both splits
(`Test` + `Valid`, 244 files each), with `sorry` findings suppressed (miniF2F is
statement-only by design: every proof is `:= by sorry`). All 488 files compiled;
0 audit failures; wall time 2.7 h at 6 workers (each file pays a
full `import Mathlib`). Reproduce with:

```sh
cd experiments && git clone https://github.com/yangky11/miniF2F-lean4
cd miniF2F-lean4 && lake exe cache get
cd ../.. && python3 bench/audit_minif2f.py
```

Raw machine-readable report: [`minif2f_audit.json`](minif2f_audit.json).

## Finding 1 — a vacuous statement in the Test split

[`mathd_algebra_275`](https://github.com/yangky11/miniF2F-lean4/blob/main/MiniF2F/Test/mathd_algebra_275.lean):

```lean
theorem mathd_algebra_275
  (x : ℝ)
  (h : ((11:ℝ)^(1 / 4))^(3 * x - 3) = 1 / 5) :
  ((11:ℝ)^(1 / 4))^(6 * x + 2) = 121 / 25
```

The exponent `1 / 4` is **natural-number division**, i.e. `0` — so `(11:ℝ)^(1/4) = 11^0 = 1`.
The hypothesis reads `1 = 1/5`: **false**. The auditor's vacuity probe derives `False` from
the hypotheses alone, mechanically. Consequences:

- The theorem is **vacuously true** — it says nothing about the intended problem
  (which is about `11^(1/4)`, the fourth root).
- The conclusion as formalized (`1 = 121/25`) is itself **false** — the only way any
  prover can "solve" this benchmark item is by *exploiting the contradictory
  hypothesis*. A benchmark item that can only be solved by ex-falso is a reward-hacking
  training signal, shipped inside the field's standard eval.

**Prior art & the real story.** This bug is not unknown: the
[Kimina-Prover team](https://arxiv.org/abs/2504.11354) surfaced broken miniF2F items in
2025 by noticing problems that stayed unsolved at pass@8192 and then manually auditing
them (their paper corrects eight items; `mathd_algebra_275`'s fix is credited in the
AI-MO dataset card). That method costs a frontier-scale sampling budget plus expert
review. The verifiedai probe found the same defect **statically, in 2 compiles, with no
model and no human in the loop** — and, crucially, found it **still live in the
most-widely-used Lean 4 port (the LeanDojo source) fifteen months after it was first
documented**. Manual findings don't propagate across forks; automated CI auditing does.
That is the product argument in one sentence.

Of Kimina's nine documented items, our current symbolic battery also flags
`amc12a_2021_p9` and `mathd_numbertheory_343` — though as *trivial* (their statements in
this port are true and close under `decide` alone), so we make no claim these match the
defects Kimina saw; the port may carry corrected versions. The remaining six carry no
finding — consistent with wrong-constant / unfaithful-formalization errors that symbolic
probes cannot see without provability search, which is precisely what the
back-translation faithfulness check (in beta) targets.

## Finding 2 — 50 statements (10.2%) are one-tactic trivial

For 50 of 488 statements, the **conclusion holds with the hypothesis binders stripped**,
closed by a single tactic from `rfl / omega / decide / simp`. Example
(`mathd_numbertheory_961`, Valid split) in its entirety:

```lean
theorem mathd_numbertheory_961 : 2003 % 11 = 1
```

These are kernel-checkable facts requiring zero mathematical reasoning. They are not
*errors* — but they mean up to **10.2 percentage points of any published miniF2F solve
rate is attainable by a single decision procedure**, which matters when frontier
provers are compared within a few points of each other.

### The 50, by name

| theorem | split |
|---|---|
| `amc12a_2021_p9` | Test |
| `mathd_algebra_296` | Test |
| `mathd_algebra_304` | Test |
| `mathd_algebra_314` | Test |
| `mathd_numbertheory_12` | Test |
| `mathd_numbertheory_127` | Test |
| `mathd_numbertheory_207` | Test |
| `mathd_numbertheory_212` | Test |
| `mathd_numbertheory_229` | Test |
| `mathd_numbertheory_235` | Test |
| `mathd_numbertheory_237` | Test |
| `mathd_numbertheory_239` | Test |
| `mathd_numbertheory_254` | Test |
| `mathd_numbertheory_299` | Test |
| `mathd_numbertheory_3` | Test |
| `mathd_numbertheory_342` | Test |
| `mathd_numbertheory_343` | Test |
| `mathd_numbertheory_345` | Test |
| `mathd_numbertheory_447` | Test |
| `mathd_numbertheory_517` | Test |
| `mathd_numbertheory_551` | Test |
| `mathd_numbertheory_66` | Test |
| `mathd_numbertheory_728` | Test |
| `mathd_numbertheory_769` | Test |
| `mathd_numbertheory_85` | Test |
| `mathd_numbertheory_101` | Valid |
| `mathd_numbertheory_102` | Valid |
| `mathd_numbertheory_132` | Valid |
| `mathd_numbertheory_149` | Valid |
| `mathd_numbertheory_155` | Valid |
| `mathd_numbertheory_169` | Valid |
| `mathd_numbertheory_188` | Valid |
| `mathd_numbertheory_200` | Valid |
| `mathd_numbertheory_202` | Valid |
| `mathd_numbertheory_211` | Valid |
| `mathd_numbertheory_24` | Valid |
| `mathd_numbertheory_252` | Valid |
| `mathd_numbertheory_269` | Valid |
| `mathd_numbertheory_30` | Valid |
| `mathd_numbertheory_301` | Valid |
| `mathd_numbertheory_37` | Valid |
| `mathd_numbertheory_403` | Valid |
| `mathd_numbertheory_45` | Valid |
| `mathd_numbertheory_466` | Valid |
| `mathd_numbertheory_629` | Valid |
| `mathd_numbertheory_64` | Valid |
| `mathd_numbertheory_640` | Valid |
| `mathd_numbertheory_739` | Valid |
| `mathd_numbertheory_81` | Valid |
| `mathd_numbertheory_961` | Valid |

## Caveats

- Triviality is relative to the probe battery (`rfl/omega/decide/simp`); a stronger
  battery (e.g. `norm_num`) would flag more, not fewer. All checks are sound:
  a finding = a Lean program that compiled. No false positives by construction.
- `sorry` findings (488/488, by design) are suppressed as intended for a
  statement-only benchmark.
- We audit the widely-used community Lean 4 port (the LeanDojo benchmark source),
  at the commit above.
