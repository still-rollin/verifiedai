/-! Geometry helpers inside a namespace — exercises the auditor's
    context-preserving probe insertion (probes must compile *inside*
    `namespace Geometry`, or they'd miss `dist`). -/

namespace Geometry

def dist (a b : Nat) : Nat := (a - b) + (b - a)

/-- Healthy: distance from a point to itself is zero. -/
theorem dist_self (a : Nat) : dist a a = 0 := by
  unfold dist
  omega

/-- VACUOUS: `dist a b` cannot be both > 5 and < 2 — the hypotheses are
    contradictory, so this "theorem" constrains nothing. -/
theorem far_and_near (a b : Nat) (h1 : dist a b > 5) (h2 : dist a b < 2) :
    a = b := by
  omega

end Geometry
