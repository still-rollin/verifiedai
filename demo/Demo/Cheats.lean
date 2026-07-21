/-! The three classic ways to cheat the kernel — every declaration below is
    accepted by `lake build`, and every one is caught by the trust-chain audit.

    This is what an RL-trained prover learns to do to a naive reward function. -/

/-- CHEAT 1: smuggle an axiom. The "theorem" below it is assumed, not proved. -/
axiom convenient_fact : ∀ a b : Nat, (a + b) ^ 2 = a ^ 2 + 2 * a * b + b ^ 2

theorem binomial_square (a b : Nat) :
    (a + b) ^ 2 = a ^ 2 + 2 * a * b + b ^ 2 :=
  convenient_fact a b

/-- CHEAT 2: `native_decide` — the kernel is bypassed; correctness rests on the
    compiler and its FFI, a vastly larger trusted base. -/
theorem mersenne_check : (2 ^ 127 - 1) % 7 = 1 := by
  native_decide

/-- CHEAT 3: `sorry` behind a conjunction — half the claim is a placeholder,
    but the declaration still "compiles". -/
theorem doubling_bound (n : Nat) (h : n > 2) : 2 * n > n + 2 ∧ n ^ n > 2 ^ n := by
  constructor
  · omega
  · sorry
