#!/bin/sh
# Re-introduce the demo breakage (a typo'd lemma name, as a dependency bump would),
# so `verifiedai repair` has something to fix during a live demo.
cd "$(dirname "$0")" || exit 1
sed -i '' 's/Nat\.add_comm a b/Nat.add_com a b/' Demo/Refunds.lean
echo "Demo/Refunds.lean is now broken — run:  PYTHONPATH=../cli python3 -m verifiedai repair ."
