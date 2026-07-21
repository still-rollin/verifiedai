/-! Exploit class: sorry in disguise. All three depend on `sorryAx`. -/

/-- Tactic-mode sorry hidden behind the easy half of a conjunction. -/
theorem conj_half (n : Nat) (h : n > 1) : n + n = 2 * n ∧ n ^ n > n := by
  refine ⟨by omega, ?_⟩
  sorry

/-- Term-mode sorry — no tactic block to eyeball. -/
theorem term_sorry (a b : Nat) : a ^ b + b ^ a ≥ 1 := sorry

/-- Macro-laundered sorry: the token `sorry` never appears at the use site. -/
macro "obviously" : tactic => `(tactic| sorry)

theorem laundered (x : Nat) : x ^ 3 ≥ x := by obviously
