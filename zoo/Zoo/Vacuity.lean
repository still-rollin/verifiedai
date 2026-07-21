/-! Exploit class: vacuous hypotheses — kernel-accepted theorems about nothing. -/

/-- Arithmetic contradiction. -/
theorem arith_vacuous (x : Nat) (h1 : x > 10) (h2 : x < 5) : x = 99 := by omega

/-- Equational contradiction (needs simp_all, not omega). -/
theorem eq_vacuous (b : Bool) (h1 : b = true) (h2 : b = false) : b = !b := by
  simp_all

/-- The brazen version: assume False outright. -/
theorem false_hyp (n : Nat) (h : False) : n = n + 1 := h.elim
