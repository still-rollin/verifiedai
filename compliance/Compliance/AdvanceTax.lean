/- Advance tax (§208, §211) — simplified pilot. Informational only.

   Liability threshold: advance tax is due once estimated liability for the
   year reaches ₹10,000. Instalment schedule (cumulative % of liability):
   15 Jun: 15% · 15 Sep: 45% · 15 Dec: 75% · 15 Mar: 100%. -/

namespace Compliance

def advanceTaxThreshold : Nat := 10000

/-- Advance tax becomes payable at the liability threshold. -/
def advanceTaxDue (liability : Nat) : Prop := advanceTaxThreshold ≤ liability

/-- Cumulative instalment percentage after quarter q (1-4). -/
def instalmentPct : Nat → Nat
  | 0 => 15
  | 1 => 15
  | 2 => 45
  | 3 => 75
  | _ => 100

/-- Cumulative amount due by quarter q. -/
def instalmentDue (liability q : Nat) : Nat := liability * instalmentPct q / 100

example : instalmentPct 1 = 15  := by decide
example : instalmentPct 2 = 45  := by decide
example : instalmentPct 3 = 75  := by decide
example : instalmentPct 4 = 100 := by decide
example : instalmentDue 100000 2 = 45000 := by decide

/-- The March instalment settles the full liability. -/
theorem final_instalment_settles (liability : Nat) :
    instalmentDue liability 4 = liability := by
  show liability * 100 / 100 = liability
  omega

/-- Cumulative dues never decrease from one quarter to the next. -/
theorem instalments_monotone (liability q : Nat) :
    instalmentDue liability q ≤ instalmentDue liability (q + 1) := by
  match q with
  | 0 => show liability * 15 / 100 ≤ liability * 15 / 100; omega
  | 1 => show liability * 15 / 100 ≤ liability * 45 / 100; omega
  | 2 => show liability * 45 / 100 ≤ liability * 75 / 100; omega
  | 3 => show liability * 75 / 100 ≤ liability * 100 / 100; omega
  | _ + 4 => show liability * 100 / 100 ≤ liability * 100 / 100; omega

/-- No instalment ever exceeds the liability. -/
theorem instalment_le_liability (liability q : Nat) :
    instalmentDue liability q ≤ liability := by
  match q with
  | 0 => show liability * 15 / 100 ≤ liability; omega
  | 1 => show liability * 15 / 100 ≤ liability; omega
  | 2 => show liability * 45 / 100 ≤ liability; omega
  | 3 => show liability * 75 / 100 ≤ liability; omega
  | _ + 4 => show liability * 100 / 100 ≤ liability; omega

end Compliance
