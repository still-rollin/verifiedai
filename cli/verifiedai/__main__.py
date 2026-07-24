"""verifiedai CLI.

  verifiedai audit  <project-root> [file.lean ...] [--all] [--json|--md]
  verifiedai repair <project-root> [--no-llm]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .lean import LeanProject

_SKIP_DIRS = {".lake", ".git", "build", "_build", "lake-packages"}


def _discover(root: Path) -> list[str]:
    files = []
    for p in sorted(root.rglob("*.lean")):
        rel = p.relative_to(root)
        if any(part in _SKIP_DIRS for part in rel.parts):
            continue
        if rel.name.startswith(".verifiedai"):
            continue
        files.append(str(rel))
    return files


def main() -> int:
    ap = argparse.ArgumentParser(prog="verifiedai", description="CI for formal proofs")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser(
        "audit", help="audit theorem statements (vacuity, triviality, unused hypotheses)"
    )
    a.add_argument("root", help="Lean project root (contains lakefile)")
    a.add_argument("files", nargs="*", help=".lean files relative to root")
    a.add_argument("--all", action="store_true", help="audit every .lean file under root")
    a.add_argument("--json", action="store_true", help="machine-readable output")
    a.add_argument("--md", action="store_true", help="PR-comment-ready markdown output")
    a.add_argument(
        "--ignore",
        nargs="*",
        default=[],
        metavar="KIND",
        help="suppress finding kinds (e.g. --ignore sorry for statement-only benchmarks)",
    )
    a.add_argument(
        "--faithful",
        action="store_true",
        help="LLM back-translation faithfulness check on docstring'd theorems "
        "(requires anthropic + API credentials)",
    )

    r = sub.add_parser("repair", help="repair broken proofs (kernel-verified fixes only)")
    r.add_argument("root", help="Lean project root (contains lakefile)")
    r.add_argument("--no-llm", action="store_true", help="deterministic tiers only")

    s = sub.add_parser("serve", help="run the self-hosted HTTP API")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8419)

    m = sub.add_parser(
        "mutate",
        help="spec mutation testing: break each def, see if its specs notice",
    )
    m.add_argument("root", help="Lean project root (contains lakefile)")
    m.add_argument("files", nargs="+", help=".lean files relative to root")
    m.add_argument("--limit-per-op", type=int, default=4)
    m.add_argument("--json", action="store_true", help="machine-readable output")

    args = ap.parse_args()

    if args.cmd == "serve":
        from .server import serve

        serve(args.host, args.port)
        return 0

    project = LeanProject(args.root)

    if args.cmd == "mutate":
        import json as _json

        from .mutate import mutate_file

        exit_code = 0
        out = {}
        for f in args.files:
            results = mutate_file(project, f, args.limit_per_op)
            out[f] = {
                name: {"tested": r.tested, "killed": r.killed,
                       "invalid": r.invalid, "survived": r.survived}
                for name, r in results.items()
            }
            if not args.json:
                print(f"\n\033[34mverifiedai mutate\033[0m — {f}")
                for name, r in results.items():
                    if r.survived:
                        exit_code = 1
                        print(f"  \033[31m✗\033[0m {name} — "
                              f"{len(r.survived)}/{r.tested} mutants SURVIVED "
                              f"(spec too weak):")
                        for s in r.survived:
                            print(f"      · {s['mutation']}")
                    elif r.tested:
                        print(f"  \033[32m✓\033[0m {name} — "
                              f"{r.killed}/{r.tested} mutants killed")
                    else:
                        print(f"  \033[2m-\033[0m {name} — no applicable mutants")
            else:
                exit_code = exit_code or int(any(
                    r.survived for r in results.values()))
        if args.json:
            print(_json.dumps(out, indent=2))
        return exit_code

    if args.cmd == "audit":
        from .audit import Auditor, render_markdown, render_report, report_dict

        targets = _discover(project.root) if args.all else args.files
        if not targets:
            print("error: give one or more .lean files, or --all", file=sys.stderr)
            return 2

        ignore = set(args.ignore)
        reports, skipped, had_error = [], [], False
        for f in targets:
            try:
                thms = Auditor(project, f).run()
            except RuntimeError as e:
                skipped.append((f, str(e).splitlines()[0]))
                continue
            if args.faithful:
                from .faithfulness import audit_faithfulness

                src = (project.root / f).read_text()
                defs = "\n".join(
                    ln for ln in src.splitlines()
                    if ln.lstrip().startswith(("def ", "abbrev "))
                )
                _, unavailable = audit_faithfulness(thms, defs)
                if unavailable:
                    print(
                        f"  note: faithfulness unavailable for {unavailable} theorem(s) "
                        "(LLM SDK or API credentials missing)",
                        file=sys.stderr,
                    )
            if ignore:
                for t in thms:
                    t.findings = [fd for fd in t.findings if fd["kind"] not in ignore]
            reports.append((f, thms))
            if any(fd["severity"] == "error" for t in thms for fd in t.findings):
                had_error = True

        import json as _json

        if args.json:
            print(
                _json.dumps(
                    {
                        "reports": [report_dict(f, t) for f, t in reports],
                        "skipped": [{"file": f, "reason": r} for f, r in skipped],
                    },
                    indent=2,
                )
            )
        elif args.md:
            print(render_markdown([report_dict(f, t) for f, t in reports]))
        else:
            for f, thms in reports:
                print(render_report(f, thms))
            if skipped:
                print("  skipped (does not compile — run repair first):")
                for f, why in skipped:
                    print(f"    - {f}")
            if len(reports) > 1:
                total = sum(len(t) for _, t in reports)
                flagged = sum(1 for _, thms in reports for t in thms if t.findings)
                print(f"\n  corpus total: {total} theorems in {len(reports)} files, {flagged} flagged\n")
        return 1 if had_error else 0

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
