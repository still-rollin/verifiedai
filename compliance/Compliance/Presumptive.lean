/- Presumptive taxation — §44AD (business) and §44ADA (professions).
   Simplified pilot, FY 2024-25 limits. Informational only.

   §44AD:  turnover ≤ ₹2 crore (₹3 crore when ≥95% receipts are digital)
   §44ADA: gross receipts ≤ ₹50 lakh (₹75 lakh when ≥95% digital) -/

namespace Compliance

def limit44AD         : Nat := 20000000
def limit44AD_digital : Nat := 30000000
def limit44ADA         : Nat := 5000000
def limit44ADA_digital : Nat := 7500000

def eligible44AD (turnover : Nat) : Prop := turnover ≤ limit44AD
def eligible44AD_digital (turnover : Nat) : Prop := turnover ≤ limit44AD_digital
def eligible44ADA (receipts : Nat) : Prop := receipts ≤ limit44ADA
def eligible44ADA_digital (receipts : Nat) : Prop := receipts ≤ limit44ADA_digital

example : limit44ADA < limit44ADA_digital := by decide
example : limit44ADA_digital < limit44AD  := by decide
example : limit44AD < limit44AD_digital   := by decide

/-- The digital-receipts route only widens §44AD eligibility. -/
theorem digital_widens_44AD (t : Nat) (h : eligible44AD t) :
    eligible44AD_digital t := by
  unfold eligible44AD limit44AD at h
  unfold eligible44AD_digital limit44AD_digital
  omega

/-- The digital-receipts route only widens §44ADA eligibility. -/
theorem digital_widens_44ADA (r : Nat) (h : eligible44ADA r) :
    eligible44ADA_digital r := by
  unfold eligible44ADA limit44ADA at h
  unfold eligible44ADA_digital limit44ADA_digital
  omega

/-- A §44ADA-eligible professional is inside the §44AD business limit too. -/
theorem ada_within_ad (r : Nat) (h : eligible44ADA_digital r) :
    eligible44AD r := by
  unfold eligible44ADA_digital limit44ADA_digital at h
  unfold eligible44AD limit44AD
  omega

end Compliance
