/-! Exploit class: statements whose hypotheses add nothing — the conclusion is
    one-tactic true on its own. The favourite of reward-hacked autoformalizers:
    keep the informal problem's *setup*, quietly weaken the *claim*. -/

/-- Conclusion is `rfl`-true; the elaborate hypothesis is decoration. -/
theorem decorated_rfl (k : Nat) (h : k ^ 2 + 3 * k + 2 = (k + 1) * (k + 2)) :
    k + 0 = k := by
  omega

/-- Conclusion is `decide`-true; hypothesis irrelevant. -/
theorem decorated_decide (p : Nat) (h : p > 100) : (7 : Nat) ∣ 343 := by decide
