/- GST registration & e-invoicing rules (simplified pilot).
   Thresholds in ₹ of aggregate annual turnover:
     · registration (goods, normal-category states):  > 40 lakh
     · composition scheme eligibility:                ≤ 1.5 crore
     · mandatory e-invoicing:                         ≥ 5 crore

   Two of the theorems below are deliberately MIS-formalized the way a
   careless (or automated) formalization would be — `verifiedai audit`
   catches both. A compliance "proof" over a wrong statement is a false
   sense of certainty, which is exactly what the auditor exists to prevent. -/

namespace Compliance

def registrationThreshold : Nat := 4000000
def compositionLimit      : Nat := 15000000
def eInvoiceThreshold     : Nat := 50000000

/-- Registration is mandatory once turnover exceeds the threshold. -/
def requiresRegistration (turnover : Nat) : Prop :=
  registrationThreshold < turnover

/-- E-invoicing is mandatory from the e-invoice threshold. -/
def mustEInvoice (turnover : Nat) : Prop :=
  eInvoiceThreshold ≤ turnover

/-- Composition-scheme eligibility (turnover criterion only). -/
def compositionEligible (turnover : Nat) : Prop :=
  turnover ≤ compositionLimit

/-- Anyone who must e-invoice is necessarily registration-liable. -/
theorem einvoice_implies_registration (t : Nat) (h : mustEInvoice t) :
    requiresRegistration t := by
  unfold mustEInvoice eInvoiceThreshold at h
  unfold requiresRegistration registrationThreshold
  omega

/-- A composition-scheme business is never within the e-invoicing mandate. -/
theorem composition_excludes_einvoice (t : Nat) (h : compositionEligible t) :
    ¬ mustEInvoice t := by
  unfold compositionEligible compositionLimit at h
  unfold mustEInvoice eInvoiceThreshold
  omega

/-- MIS-FORMALIZED (vacuous): the author mixed the services threshold
    (₹20 lakh) with the goods threshold (₹40 lakh) — the two hypotheses
    are contradictory, so this "exemption rule" is true about nothing. -/
theorem small_service_provider_exempt (t : Nat)
    (h₁ : t ≤ 2000000) (h₂ : 4000000 < t) :
    ¬ requiresRegistration t := by
  omega

/-- MIS-FORMALIZED (trivial): meant to say "an e-invoicing business is above
    the composition limit" — but as written the conclusion compares two
    CONSTANTS, so it holds with the hypothesis stripped and says nothing
    about any business. -/
theorem einvoice_above_composition (t : Nat) (h : mustEInvoice t) :
    compositionLimit < eInvoiceThreshold := by
  decide

end Compliance
