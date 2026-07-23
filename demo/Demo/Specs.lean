/- Spec-strength demo for `verifiedai mutate`.

   A verified program is (implementation, spec, proof). The kernel checks the
   proof against the spec — nobody checks whether the spec pins down the
   implementation. Mutation testing does: break the implementation, keep the
   original proof, recompile. If the proof still goes through, the spec never
   constrained the behavior you broke. -/

namespace Specs

/-- Doubling. -/
def double (n : Nat) : Nat := n + n

/-- WEAK spec: only parity. The mutant `n - n` (which returns 0) is also even,
    and the same proof certifies it — the mutant SURVIVES. -/
theorem double_is_even (n : Nat) : double n % 2 = 0 := by
  unfold double; omega

/-- Add three. -/
def addThree (n : Nat) : Nat := n + 3

/-- STRONG spec: pins the value exactly. Every mutant of `addThree`
    (`+` → `-`, `3` → `4`) breaks this proof — all mutants are KILLED. -/
theorem addThree_exact (n : Nat) : addThree n = n + 3 := by
  unfold addThree; omega

end Specs
