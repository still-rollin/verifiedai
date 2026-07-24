"""Domain formalizer: Indian income-tax slab tables → verified Lean 4.

Compiles the published slab tables for THREE regimes into Lean:

  * new regime FY 2024-25 (AY 2025-26)  — §87A rebate to ₹7,00,000, marginal relief
  * new regime FY 2025-26 (AY 2026-27)  — §87A rebate to ₹12,00,000, marginal relief
  * old regime (unchanged for years)    — §87A rebate to ₹5,00,000, no marginal relief

For each regime it emits: the slab function, the tax-payable function
(rebate + marginal relief, modeled with `min` exactly as the Act computes it),
kernel-checked boundary facts at every slab edge and the rebate cliff, and
general theorems (rebate nils tax below the limit; with marginal relief, one
extra rupee of income costs at most one rupee of tax — payable ≤ income − limit).

The table is the spec, this script is a compiler, the Lean kernel checks the
output. No LLM anywhere.

Simplified, and says so: no surcharge, no 4% cess (provided as a separate
helper), no deductions/exemptions, no capital-gains rates. Informational
pilot, not tax advice.

    python3 tools/formalize_tax.py --out compliance/Compliance/IncomeTax.lean
"""

from __future__ import annotations

import argparse
from pathlib import Path

REGIMES = [
    {
        "id": "nr24",
        "doc": "New regime, FY 2024-25 (AY 2025-26)",
        "slabs": [(300_000, 0), (700_000, 5), (1_000_000, 10),
                  (1_200_000, 15), (1_500_000, 20), (None, 30)],
        "rebate_limit": 700_000,
        "marginal_relief": True,
    },
    {
        "id": "nr25",
        "doc": "New regime, FY 2025-26 (AY 2026-27)",
        "slabs": [(400_000, 0), (800_000, 5), (1_200_000, 10),
                  (1_600_000, 15), (2_000_000, 20), (2_400_000, 25),
                  (None, 30)],
        "rebate_limit": 1_200_000,
        "marginal_relief": True,
    },
    {
        "id": "old",
        "doc": "Old regime (individuals below 60)",
        "slabs": [(250_000, 0), (500_000, 5), (1_000_000, 20), (None, 30)],
        "rebate_limit": 500_000,
        "marginal_relief": False,
    },
]

CESS_PCT = 4  # health & education cess, on tax payable


def slab_tax(regime: dict, i: int) -> int:
    lower, base = 0, 0
    for upper, rate in regime["slabs"]:
        if upper is None or i <= upper:
            return base + (i - lower) * rate // 100
        base += (upper - lower) * rate // 100
        lower = upper
    raise AssertionError


def payable(regime: dict, i: int) -> int:
    L = regime["rebate_limit"]
    if i <= L:
        return 0
    t = slab_tax(regime, i)
    return min(t, i - L) if regime["marginal_relief"] else t


def gen_regime(r: dict) -> str:
    rid, L = r["id"], r["rebate_limit"]
    # slab function body
    branches, lower, base = [], 0, 0
    for upper, rate in r["slabs"]:
        expr = f"{base} + (i - {lower}) * {rate} / 100" if rate else "0"
        if upper is None:
            branches.append(f"    {expr}")
        else:
            branches.append(f"    if i ≤ {upper} then {expr}\n    else")
            base += (upper - lower) * rate // 100
            lower = upper
    body = "\n".join(branches)
    slab_doc = " · ".join(
        f"{'∞' if u is None else f'≤{u}'}:{rt}%" for u, rt in r["slabs"])

    if r["marginal_relief"]:
        pay_body = f"if i ≤ {L} then 0 else min ({rid}_slabTax i) (i - {L})"
    else:
        pay_body = f"if i ≤ {L} then 0 else {rid}_slabTax i"

    # boundary examples: every slab edge and edge+1, for slab and payable
    ex = []
    for upper, _ in r["slabs"]:
        if upper is None:
            continue
        for j in (upper, upper + 1):
            ex.append(f"example : {rid}_slabTax {j} = {slab_tax(r, j)} := by decide")
    for j in (L, L + 1, L + 5000):
        ex.append(f"example : {rid}_payable {j} = {payable(r, j)} := by decide")

    thms = [f"""
/-- §87A ({r["doc"]}): taxable income up to ₹{L} ⇒ zero tax payable. -/
theorem {rid}_rebate_nils_tax (i : Nat) (h : i ≤ {L}) :
    {rid}_payable i = 0 := by
  simp [{rid}_payable, h]"""]
    if r["marginal_relief"]:
        thms.append(f"""
/-- Marginal relief: one extra rupee of income above ₹{L} costs at most one
    extra rupee of tax — payable never exceeds income − {L}. -/
theorem {rid}_marginal_relief (i : Nat) (h : {L} < i) :
    {rid}_payable i ≤ i - {L} := by
  unfold {rid}_payable
  rw [if_neg (Nat.not_le.mpr h)]
  exact Nat.min_le_right _ _

/-- Above the rebate limit you never pay more than the slab schedule. -/
theorem {rid}_payable_le_slab (i : Nat) (h : {L} < i) :
    {rid}_payable i ≤ {rid}_slabTax i := by
  unfold {rid}_payable
  rw [if_neg (Nat.not_le.mpr h)]
  exact Nat.min_le_left _ _""")
    else:
        thms.append(f"""
/-- Old regime: above the rebate limit, payable is exactly the slab schedule. -/
theorem {rid}_payable_eq_slab (i : Nat) (h : {L} < i) :
    {rid}_payable i = {rid}_slabTax i := by
  unfold {rid}_payable
  rw [if_neg (Nat.not_le.mpr h)]""")

    nl = "\n"
    return f"""
/-! ### {r["doc"]}
    Slabs: {slab_doc} · §87A rebate to ₹{L}{" · marginal relief" if r["marginal_relief"] else ""} -/

/-- Slab tax (₹) before rebate, {r["doc"]}. -/
def {rid}_slabTax (i : Nat) : Nat :=
{body}

/-- Tax payable after §87A{" with marginal relief" if r["marginal_relief"] else ""}. -/
def {rid}_payable (i : Nat) : Nat :=
  {pay_body}

{nl.join(ex)}
{nl.join(thms)}
"""


def gen() -> str:
    parts = [f"""/- GENERATED by tools/formalize_tax.py — do not edit by hand.
   Indian income tax, three regimes, compiled from the published slab tables.
   Simplified pilot: no surcharge, deductions, or capital-gains rates; the 4%
   health-and-education cess is provided as a helper. Informational only —
   not tax advice. -/

namespace Compliance
"""]
    for r in REGIMES:
        parts.append(gen_regime(r))
    parts.append(f"""
/-- Health & education cess ({CESS_PCT}%), applied to tax payable. -/
def withCess (tax : Nat) : Nat := tax + tax * {CESS_PCT} / 100

example : withCess 0 = 0 := by decide
example : withCess 60000 = 62400 := by decide

/-- Cess never decreases tax. -/
theorem withCess_ge (t : Nat) : t ≤ withCess t := by
  unfold withCess; omega

end Compliance
""")
    return "".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    src = gen()
    Path(args.out).write_text(src)
    n_ex = src.count("example :")
    n_thm = src.count("theorem ")
    print(f"wrote {args.out}: {len(REGIMES)} regimes, "
          f"{n_thm} theorems, {n_ex} kernel-checked facts")
    for r in REGIMES:
        probe = {700_000: None, 705_000: None, 1_200_001: None}
        print(f"  {r['id']}: payable @ rebate+5000 = "
              f"{payable(r, r['rebate_limit'] + 5000)}")
    return 0


if __name__ == "__main__":
    main()
