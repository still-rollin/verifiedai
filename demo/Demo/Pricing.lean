/-! Pricing logic with formally verified properties.

    This file compiles: every proof below is accepted by the Lean kernel.
    But two of the three theorems don't say what their authors think they say —
    exactly the class of problem `verifiedai audit` exists to catch. -/

def applyDiscount (price discount : Nat) : Nat := price - discount

/-- Healthy: a discounted price never exceeds the original price. -/
theorem discount_le_price (p d : Nat) : applyDiscount p d ≤ p := by
  unfold applyDiscount
  omega

/-- VACUOUS: the hypotheses `d > p + 10` and `d < p` are contradictory,
    so this theorem is true about nothing. The kernel happily accepts it. -/
theorem big_discount_still_positive (p d : Nat) (h1 : d > p + 10) (h2 : d < p) :
    applyDiscount p d > 0 := by
  omega

/-- TRIVIAL + unused hypothesis: `t + 0 = t` holds by `rfl` alone; the
    hypothesis `h` contributes nothing. Likely a mis-formalized claim. -/
theorem tax_identity (t : Nat) (h : t > 3) : t + 0 = t := by
  simp
