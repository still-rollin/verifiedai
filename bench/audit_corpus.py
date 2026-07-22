"""Statement-integrity sweep of any statement-only Lean 4 corpus.

Generalizes bench/audit_minif2f.py: point it at a lake project and a glob of
statement files (each typically `import Mathlib` + `theorem … := sorry`).
`sorry` findings are suppressed by default — statement-only benchmarks carry
them by design; what remains (vacuous / trivial / unused_hypothesis) is signal
about the STATEMENTS themselves.

    python3 bench/audit_corpus.py --repo experiments/PutnamBench/lean4 \
        --glob 'src/*.lean' --out experiments/putnambench_audit.json --jobs 6
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "cli"))

from verifiedai.audit import Auditor, report_dict  # noqa: E402
from verifiedai.lean import LeanProject  # noqa: E402


def audit_one(project: LeanProject, rel: str, ignore: set[str]) -> dict:
    try:
        thms = Auditor(project, rel).run()
    except RuntimeError as e:
        return {"file": rel, "error": str(e).splitlines()[0]}
    for t in thms:
        t.findings = [f for f in t.findings if f["kind"] not in ignore]
    return report_dict(rel, thms)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="lake project root")
    ap.add_argument("--glob", required=True, action="append",
                    help="glob(s) of statement files, relative to repo root")
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--ignore", default="sorry",
                    help="comma-separated finding kinds to suppress")
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0,
                    help="audit only the first N files (smoke test)")
    args = ap.parse_args()

    ignore = {k for k in args.ignore.split(",") if k}
    project = LeanProject(args.repo)
    files = sorted({
        str(p.relative_to(project.root))
        for g in args.glob
        for p in project.root.glob(g)
    })
    if args.limit:
        files = files[: args.limit]
    if not files:
        print(f"no files matched {args.glob} under {project.root}", file=sys.stderr)
        return 1
    print(f"auditing {len(files)} files under {project.root} "
          f"with {args.jobs} workers (ignoring: {sorted(ignore) or 'nothing'}) …")

    t0 = time.monotonic()
    reports, errors = [], []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futs = {pool.submit(audit_one, project, f, ignore): f for f in files}
        done = 0
        for fut in as_completed(futs):
            r = fut.result()
            (errors if "error" in r else reports).append(r)
            done += 1
            if done % 25 == 0:
                flagged = sum(x["flagged"] for x in reports)
                print(f"  {done}/{len(files)} files · {flagged} flagged so far "
                      f"· {time.monotonic() - t0:.0f}s", flush=True)

    elapsed = time.monotonic() - t0
    n_thms = sum(len(r["theorems"]) for r in reports)
    flagged = [
        (r["file"], t["name"], f["kind"], f["detail"])
        for r in reports
        for t in r["theorems"]
        for f in t["findings"]
    ]
    by_kind: dict[str, int] = {}
    for _, _, k, _ in flagged:
        by_kind[k] = by_kind.get(k, 0) + 1

    Path(args.out).write_text(json.dumps(
        {"repo": args.repo, "globs": args.glob,
         "reports": reports, "errors": errors,
         "summary": {"files": len(reports), "theorems": n_thms,
                     "findings": len(flagged), "by_kind": by_kind,
                     "seconds": round(elapsed, 1)}}, indent=2))

    print(f"\n=== statement audit: {args.repo} ===")
    print(f"files audited : {len(reports)} ({len(errors)} failed to compile)")
    print(f"theorems      : {n_thms}")
    print(f"wall time     : {elapsed / 60:.1f} min ({args.jobs} workers)")
    print(f"findings      : {len(flagged)}  {by_kind}")
    for f, name, kind, detail in flagged:
        print(f"  [{kind}] {f} :: {name}")
    if errors:
        print("compile failures:")
        for e in errors[:10]:
            print(f"  {e['file']}: {e['error']}")
    print(f"\nfull report → {args.out}")
    return 0


if __name__ == "__main__":
    main()
