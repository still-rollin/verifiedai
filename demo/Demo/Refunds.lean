/-! Refund logic. The proof below is broken (a typo'd lemma name, the kind of
    breakage a dependency bump produces constantly) — `verifiedai repair`
    fixes it automatically and only accepts kernel-verified fixes. -/

theorem refund_comm (a b : Nat) : a + b = b + a := by
  exact Nat.add_comm a b
