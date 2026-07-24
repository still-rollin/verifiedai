/- GST thresholds — registration, composition, e-invoicing (simplified pilot).
   Aggregate-annual-turnover thresholds in ₹:

     registration:  goods, normal states 40 lakh · goods, special-category 20 lakh
                    services, normal 20 lakh · services, special-category 10 lakh
     composition:   goods 1.5 crore · goods, special-category 75 lakh · services 50 lakh
     e-invoicing:   5 crore

   Informational only — not tax advice. The two theorems at the bottom are
   deliberately MIS-formalized (see the audit section of the writeup):
   `verifiedai audit` catches both. -/

namespace Compliance

def regGoodsNormal    : Nat := 4000000
def regGoodsSpecial   : Nat := 2000000
def regServicesNormal : Nat := 2000000
def regServicesSpecial : Nat := 1000000
def compGoods         : Nat := 15000000
def compGoodsSpecial  : Nat := 7500000
def compServices      : Nat := 5000000
def eInvoiceLimit     : Nat := 50000000

/-- Registration mandatory: goods supplier, normal-category state. -/
def requiresRegistration (turnover : Nat) : Prop := regGoodsNormal < turnover

/-- Registration mandatory: services, special-category state (strictest). -/
def requiresRegistrationStrictest (turnover : Nat) : Prop :=
  regServicesSpecial < turnover

/-- Composition-scheme eligibility, goods, normal states (turnover criterion). -/
def compositionEligible (turnover : Nat) : Prop := turnover ≤ compGoods

/-- Mandatory e-invoicing. -/
def mustEInvoice (turnover : Nat) : Prop := eInvoiceLimit ≤ turnover

-- Threshold ordering facts, kernel-checked.
example : regServicesSpecial < regGoodsSpecial  := by decide
example : regGoodsSpecial ≤ regServicesNormal   := by decide
example : regGoodsNormal < compServices         := by decide
example : compServices < compGoodsSpecial       := by decide
example : compGoodsSpecial < compGoods          := by decide
example : compGoods < eInvoiceLimit             := by decide

/-- Whoever must e-invoice is registration-liable under EVERY category. -/
theorem einvoice_implies_registration (t : Nat) (h : mustEInvoice t) :
    requiresRegistration t := by
  unfold mustEInvoice eInvoiceLimit at h
  unfold requiresRegistration regGoodsNormal
  omega

/-- Registration under the goods/normal threshold implies registration under
    the strictest (services, special-category) threshold. -/
theorem registration_monotone (t : Nat) (h : requiresRegistration t) :
    requiresRegistrationStrictest t := by
  unfold requiresRegistration regGoodsNormal at h
  unfold requiresRegistrationStrictest regServicesSpecial
  omega

/-- A composition-scheme business is never inside the e-invoicing mandate. -/
theorem composition_excludes_einvoice (t : Nat) (h : compositionEligible t) :
    ¬ mustEInvoice t := by
  unfold compositionEligible compGoods at h
  unfold mustEInvoice eInvoiceLimit
  omega

/-- Composition eligibility for services implies it for goods. -/
theorem composition_services_within_goods (t : Nat) (h : t ≤ compServices) :
    compositionEligible t := by
  unfold compServices at h
  unfold compositionEligible compGoods
  omega

/-- MIS-FORMALIZED (vacuous): the author mixed the ₹20 lakh services threshold
    with the ₹40 lakh goods threshold — the hypotheses are contradictory, so
    this "exemption rule" is true about nothing. Kept as an audit demo. -/
theorem small_service_provider_exempt (t : Nat)
    (h₁ : t ≤ 2000000) (h₂ : 4000000 < t) :
    ¬ requiresRegistration t := by
  omega

/-- MIS-FORMALIZED (trivial): meant "an e-invoicing business is above the
    composition limit", but as written it compares two CONSTANTS — it holds
    with the hypothesis stripped and says nothing about any business. -/
theorem einvoice_above_composition (t : Nat) (h : mustEInvoice t) :
    compGoods < eInvoiceLimit := by
  decide

end Compliance
