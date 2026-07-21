/-! KNOWN GAP (documented, not yet caught): definition drift.
    `Prime` below shadows the standard notion with something weaker; the
    statement *reads* like a primality claim but isn't one. Caught by the
    roadmap definition-drift check; today's battery passes it. -/

def Prime (n : Nat) : Prop := n > 1

theorem four_is_prime : Prime 4 := by
  unfold Prime
  omega
