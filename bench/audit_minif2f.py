"""Statement-integrity sweep of miniF2F-lean4 (the field's flagship benchmark).

miniF2F files are statement-only (`:= by sorry`), so `sorry` findings are
suppressed; what remains — vacuous, trivial, unused_hypothesis — is signal
about the STATEMENTS themselves.

    python3 bench/audit_minif2f.py [--repo experiments/miniF2F-lean4] [--jobs 6]
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

IGNORE = {"sorry"}  # statement-only benchmark: every proof is `sorry` by design


def audit_one(project: LeanProject, rel: str) -> dict:
    try:
        thms = Auditor(project, rel).run()
    except RuntimeError as e:
        return {"file": rel, "error": str(e).splitlines()[0]}
    for t in thms:
        t.findings = [f for f in t.findings if f["kind"] not in IGNORE]
    return report_dict(rel, thms)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=str(ROOT / "experiments" / "miniF2F-lean4"))
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--out", default=str(ROOT / "experiments" / "minif2f_audit.json"))
    args = ap.parse_args()

    project = LeanProject(args.repo)
    files = sorted(
        str(p.relative_to(project.root))
        for split in ("Test", "Valid")
        for p in (project.root / "MiniF2F" / split).glob("*.lean")
    )
    print(f"auditing {len(files)} miniF2F statement files with {args.jobs} workers …")

    t0 = time.monotonic()
    reports, errors = [], []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futs = {pool.submit(audit_one, project, f): f for f in files}
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
        {"reports": reports, "errors": errors,
         "summary": {"files": len(reports), "theorems": n_thms,
                     "findings": len(flagged), "by_kind": by_kind,
                     "seconds": round(elapsed, 1)}}, indent=2))

    print(f"\n=== miniF2F statement audit ===")
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
