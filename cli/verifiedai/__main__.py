"""verifiedai CLI.

  verifiedai audit  <project-root> <file.lean> [--json]
  verifiedai repair <project-root> [--no-llm]
"""

from __future__ import annotations

import argparse
import sys

from .lean import LeanProject


def main() -> int:
    ap = argparse.ArgumentParser(prog="verifiedai", description="CI for formal proofs")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("audit", help="audit theorem statements (vacuity, triviality, unused hypotheses)")
    a.add_argument("root", help="Lean project root (contains lakefile)")
    a.add_argument("file", help="path to a .lean file, relative to root")
    a.add_argument("--json", action="store_true")

    r = sub.add_parser("repair", help="repair broken proofs (kernel-verified fixes only)")
    r.add_argument("root", help="Lean project root (contains lakefile)")
    r.add_argument("--no-llm", action="store_true", help="deterministic tiers only")

    args = ap.parse_args()
    project = LeanProject(args.root)

    if args.cmd == "audit":
        from .audit import Auditor, render_report

        try:
            thms = Auditor(project, args.file).run()
        except RuntimeError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        print(render_report(args.file, thms, as_json=args.json))
        return 1 if any(f["severity"] == "error" for t in thms for f in t.findings) else 0

    if args.cmd == "repair":
        from .repair import Repairer, render_results

        results = Repairer(project, use_llm=not args.no_llm).run()
        if not results:
            return 0
        print(render_results(results))
        return 0 if all(r.fixed for r in results) else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
