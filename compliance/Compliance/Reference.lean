/- Faithfulness cross-check: independently published worked examples,
   encoded as kernel-checked test vectors.

   "Does the formal rule match the law?" cannot be proved by a machine — the
   law is an informal artifact. It CAN be cross-checked: the Finance Ministry,
   Budget 2025 coverage, and standard CA references publish worked examples of
   the slab computations. Each fact below states that our GENERATED rules
   reproduce one of those independently published numbers, and the kernel
   checks it. An error in our rule table would have to coincide with an error
   in the government's own arithmetic to survive this file.

   Sources: Budget 2025 marginal-relief illustrations (new regime FY 2025-26),
   FY 2024-25 new-regime worked examples, standard old-regime references. -/

import Compliance.IncomeTax

namespace Compliance

/-! ### New regime FY 2025-26 (Budget 2025 published illustrations) -/

-- ₹12,00,000: fully rebated under §87A — zero tax.
example : nr25_payable 1200000 = 0 := by decide
-- ₹12,10,000: slab tax would be ₹61,500; marginal relief caps it at ₹10,000.
example : nr25_slabTax 1210000 = 61500 := by decide
example : nr25_payable 1210000 = 10000 := by decide
-- ₹13,00,000: slab tax ₹75,000; marginal relief no longer binds.
example : nr25_payable 1300000 = 75000 := by decide
-- ₹25,00,000: the widely-quoted ₹3,30,000.
example : nr25_payable 2500000 = 330000 := by decide

/-! ### New regime FY 2024-25 -/

-- ₹7,00,000: fully rebated — zero tax.
example : nr24_payable 700000 = 0 := by decide
-- ₹7,05,000: marginal relief caps tax at ₹5,000 (slab would be ₹20,500).
example : nr24_slabTax 705000 = 20500 := by decide
example : nr24_payable 705000 = 5000 := by decide
-- ₹16,00,000: the standard worked example, ₹1,70,000.
example : nr24_payable 1600000 = 170000 := by decide

/-! ### Old regime -/

-- ₹5,00,000: §87A rebate nils the ₹12,500 slab tax.
example : old_slabTax 500000 = 12500 := by decide
example : old_payable 500000 = 0 := by decide
-- ₹6,00,000: rebate gone; ₹12,500 + 20% of ₹1,00,000 = ₹32,500.
example : old_payable 600000 = 32500 := by decide
-- ₹12,00,000: ₹12,500 + ₹1,00,000 + 30% of ₹2,00,000 = ₹1,72,500.
example : old_payable 1200000 = 172500 := by decide

end Compliance
