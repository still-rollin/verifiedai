# Spec-strength mutation test: VERINA

**TL;DR — we mutation-tested every fully-proved task in
[VERINA](https://github.com/sunblaze-ucb/verina), the Berkeley benchmark for
verifiable code generation. 46 of 189 tasks ship complete ground-truth proofs;
across them we tested 71 single-site implementation mutants while keeping the
original spec and proof. 68 were killed. The 3 survivors are all semantically
equivalent mutants (redundant branches), not weak specs — on this subset,
VERINA's ground-truth postconditions are tight. The larger finding is the
denominator: 143 of 189 tasks (76%) have `sorry` in their ground-truth proofs,
so their spec strength cannot be tested this way at all.**

## What spec mutation measures

A verified program is (implementation, spec, proof). The kernel checks the
proof against the spec; nothing checks whether the spec pins down behavior.
`result.size = arr.size` verifies a sort, an identity function, and a shuffle
equally well. In AI-generated verified code this is the dominant failure mode:
a weak spec silently certifies a wrong program.

The test: break the implementation with one small, realistic bug — flip a
comparison, off-by-one a literal, swap `&&` and `||` — keep the spec and the
*original* proof, recompile.

* proof breaks → mutant **killed**: the spec constrained that behavior;
* everything compiles → mutant **survived**: the same proof certifies the
  mutated code. Either the spec is weak, or the mutant is semantically
  equivalent — survivors are compiled artifacts, and they get human triage.

Only survivors are claimed. A killed mutant is weak evidence (the proof may
break for incidental reasons); we never report "spec is strong" as a finding.

## Numbers

| | |
|---|---|
| tasks in benchmark | 189 |
| ground-truth proofs incomplete (`sorry`) — untestable | **143 (76%)** |
| tasks swept (complete proofs, baseline compiles) | 46 |
| mutants tested (≤3 sites per operator per task) | 71 |
| killed | 68 |
| survivors | 3 |
| survivors that are genuine weak specs | **0** (all 3 semantically equivalent) |
| tasks with no applicable mutation site | 20 |

Raw report: [`verina_mutation.json`](verina_mutation.json). Reproduce:

```sh
cd experiments && git clone https://github.com/sunblaze-ucb/verina
cd verina && lake exe cache get && cd ../..
python3 bench/mutate_verina.py
```

## The three survivors, triaged

* `verina_basic_19` (isSorted): `a.size ≤ 1` → `a.size < 1`. The general
  branch already returns `true` for singleton arrays, so the short-circuit is
  redundant — behavior unchanged. Equivalent mutant.
* `verina_basic_99` (Triple), two survivors: `x < 18` → `x ≤ 18` and
  `18 → 19`. Both branches of the conditional compute `3 * x` — the split is
  vestigial, so moving its boundary changes nothing. The postcondition
  (`result / 3 = x ∧ result / 3 * 3 = result`) pins the result completely.
  Equivalent mutants — though they do expose dead structure in the reference
  implementation.

We looked for weak specs and found none in the provable subset. That is the
honest result, and it is worth stating plainly: **on the 24% of VERINA that
can be checked, the specs hold up.** The auditor's value is that it can tell
you this mechanically — and that it says *clean* when things are clean, the
same way our PutnamBench audit did.

## What we claim — and what we don't

* Survivors are sound by construction (a compiled artifact); the *weak-spec*
  claim additionally requires semantic triage, which we did by hand for all 3.
* Killed ≠ strong. 20 tasks had no applicable mutation site under the current
  10-operator battery; broader operators (branch swaps, constant zeroing,
  call-argument permutation) would widen coverage. The battery is a lower
  bound, as always.
* We tested the benchmark's ground-truth (implementation, spec, proof)
  triples, not any model's submissions. Model-generated proofs over these
  specs inherit whatever strength the spec has — which is why the 76%
  untestable fraction matters: **for three quarters of VERINA, spec strength
  is an open question the benchmark itself cannot currently answer.**

## Why this matters

The money in formal verification is moving to AI-generated verified code,
where the certificate is only as good as the spec. Mutation testing is the
mechanical way to price that risk, and this sweep is — to our knowledge — the
first one run against a verifiable-codegen benchmark's ground truth. Same
engine, same discipline as our statement audits: the kernel judges, artifacts
are published, and the claim never exceeds the evidence.
