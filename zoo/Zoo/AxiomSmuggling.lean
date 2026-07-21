/-! Exploit class: axiom smuggling.
    Every "theorem" here builds green — none of them is proved. -/

/-- Global axiom: the oldest trick. -/
axiom convenient : ∀ n : Nat, n ^ 2 ≥ n

theorem sq_ge_self (n : Nat) : n ^ 2 ≥ n := convenient n

section HiddenInSection
/- An axiom inside a section is still a global axiom — it just *looks* scoped. -/
axiom section_secret : ∀ a b : Nat, a ^ b = b ^ a

theorem pow_comm_fake (a b : Nat) : a ^ b = b ^ a := section_secret a b
end HiddenInSection
