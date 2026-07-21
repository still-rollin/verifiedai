# verifiedai — CI for formal proofs

![ci](https://github.com/still-rollin/verifiedai/actions/workflows/ci.yml/badge.svg)

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
git clone https://github.com/still-rollin/verifiedai && cd verifiedai
pip install ./cli          # installs the `verifiedai` command

verifiedai audit  <project-root> Demo/Pricing.lean   # audit one file
verifiedai audit  <project-root> --all               # sweep the whole project
verifiedai audit  <project-root> --all --md          # PR-comment-ready markdown
verifiedai repair <project-root>                     # fix broken proofs (LLM tier
                                                     # optional: ANTHROPIC_API_KEY)
```

(Without installing: `PYTHONPATH=cli python3 -m verifiedai …`)

```sh
verifiedai serve --port 8419    # self-hosted HTTP API (stdlib-only, zero deps):
                                # GET /v1/health · POST /v1/audit · POST /v1/repair
verifiedai audit <root> --all --faithful   # + LLM back-translation faithfulness
                                           # on docstring'd theorems (BYO key)
python3 bench/run_bench.py      # throughput benchmark with seeded ground truth
```

**Measured throughput:** 1,278 theorems/min single-process (500-theorem synthetic
corpus, Apple Silicon), recovering **160/160 seeded findings with zero false
positives** — the benchmark doubles as a precision/recall harness.

## The adversarial zoo

[`zoo/`](zoo/) is a growing corpus of kernel-accepted declarations that mislead —
smuggled axioms (including section-laundered), sorry variants (tactic, term-level,
**macro-laundered** so the token `sorry` never appears at the use site),
`native_decide`, vacuity patterns, and decorated-trivial statements. A
[manifest](zoo/manifest.json) records what the auditor must catch **forever**;
[`tests/test_zoo.py`](tests/test_zoo.py) enforces the contract in CI, and known
gaps (currently: definition drift) are documented as first-class entries that must
be promoted the day their check ships. The catalog compounds like an antivirus
signature database — that's the moat.

**Fast by design:** all probes for a file are batched into a single Lean compile
(Lean keeps elaborating past a failed declaration), so auditing costs **2 compiles
per file regardless of theorem count** — the bundled demo corpus (4 files) audits in
under a second. Probes are inserted inside each theorem's own namespace/section, so
real-world files using `namespace` / `open` / `variable` context work.

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

## Use it from an AI agent (MCP)

verifiedai ships as an [MCP](https://modelcontextprotocol.io) server, so agents that *write*
proofs can also *audit* them. Two tools: `audit_file(project_root, file)` and
`repair_project(project_root, use_llm)`, both returning structured JSON.

```sh
# stdio server
PYTHONPATH=cli python3 -m verifiedai.mcp_server

# register with Claude Code
claude mcp add verifiedai -- env PYTHONPATH=/path/to/verifiedai/cli python3 -m verifiedai.mcp_server
```

Requires `pip install mcp`.

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
| **sorry** | trust-chain audit (`#print axioms`) | the proof depends on `sorryAx` — a placeholder, not a proof |
| **native_trust** | trust-chain audit | kernel bypassed via compiler trust (`native_decide`) |
| **nonstandard_axiom** | trust-chain audit | the proof assumes a custom axiom — the theorem is asserted, not proved |

The trust-chain checks are what make verifiedai suitable as a **reward-integrity gate**
for RL-trained provers: a model optimizing against "the kernel accepted it" will learn
to smuggle axioms, `sorry` fragments, and `native_decide` — see
[`demo/Demo/Cheats.lean`](demo/Demo/Cheats.lean) for all three, each caught.

Every probe is an actual Lean compilation — no heuristics, no false certainty.

## Status

Early prototype (v0.1). Roadmap: mathlib-scale probe batching, LLM back-translation
faithfulness checks (formal → informal → compare), GitHub App packaging, Rocq/Coq
support.

Sister project: [Rocqet](https://rocqet.vercel.app) — semantic search for Rocq/Coq
libraries (natural language → theorems), deployed and public.

Built by [Ayaan Siddiqui](mailto:f20231060@hyderabad.bits-pilani.ac.in) — BITS Pilani
Hyderabad · research intern, INRIA/CNRS Paris. This repository contains no third-party
or institutional code; it is a clean-room implementation.
