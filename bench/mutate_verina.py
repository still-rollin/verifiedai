"""Spec-strength mutation sweep of VERINA (Berkeley verifiable-codegen benchmark).

VERINA tasks are (implementation, precond, postcond, proof) with machine-
readable markers. We take every task whose ground-truth proof is COMPLETE
(no sorry), mutate only the implementation between `@start code`/`@end code`,
keep the spec and the original proof, and recompile.

A SURVIVOR means: the ground-truth proof still certifies an implementation we
deliberately broke — the task's postcondition does not constrain the mutated
behavior. That is a property of the BENCHMARK's spec, demonstrated by a
compiled artifact.

    python3 bench/mutate_verina.py [--repo experiments/verina] [--jobs 6]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "cli"))

from verifiedai.lean import LeanProject  # noqa: E402
from verifiedai.mutate import run_region_mutation  # noqa: E402

CODE_RE = re.compile(
    r"-- !benchmark @start code\n(.*?)\n\s*-- !benchmark @end code", re.S)


def sweep_task(project: LeanProject, task_dir: Path, limit_per_op: int) -> dict:
    rel = task_dir / "task.lean"
    src = rel.read_text()
    name = task_dir.name
    m = CODE_RE.search(src)
    if not m:
        return {"task": name, "skip": "no code markers"}
    if "sorry" in src:
        return {"task": name, "skip": "ground-truth proof incomplete (sorry)"}

    # baseline: the unmutated task must compile, or every mutant verdict is noise
    base = project.root / f".verifiedai_base_{name}.lean"
    try:
        base.write_text(src)
        ok, diags, _ = project.check_file(base.name)
        if any(d.severity == "error" for d in diags):
            return {"task": name, "skip": "baseline does not compile"}
    finally:
        base.unlink(missing_ok=True)

    res = run_region_mutation(
        project, str(rel.relative_to(project.root)), src,
        m.start(1), m.end(1), label=name, limit_per_op=limit_per_op,
        probe_name=f".verifiedai_mut_{name}.lean")
    return {"task": name, "tested": res.tested, "killed": res.killed,
            "invalid": res.invalid, "survived": res.survived}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=str(ROOT / "experiments" / "verina"))
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--limit-per-op", type=int, default=3)
    ap.add_argument("--out", default=str(ROOT / "experiments" / "verina_mutation.json"))
    ap.add_argument("--only", default="", help="comma-separated task names")
    args = ap.parse_args()

    project = LeanProject(args.repo)
    tasks = sorted((project.root / "datasets" / "verina").glob("verina_*"))
    if args.only:
        keep = set(args.only.split(","))
        tasks = [t for t in tasks if t.name in keep]
    print(f"{len(tasks)} tasks · mutating ground-truth implementations "
          f"(≤{args.limit_per_op} sites/operator) · {args.jobs} workers")

    t0 = time.monotonic()
    results = []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futs = {pool.submit(sweep_task, project, t, args.limit_per_op): t
                for t in tasks}
        done = 0
        for fut in as_completed(futs):
            r = fut.result()
            results.append(r)
            done += 1
            if done % 10 == 0:
                surv = sum(len(x.get("survived", [])) for x in results)
                weak = sum(1 for x in results if x.get("survived"))
                print(f"  {done}/{len(tasks)} · {weak} tasks with survivors "
                      f"({surv} survivors) · {time.monotonic()-t0:.0f}s", flush=True)

    swept = [r for r in results if "skip" not in r]
    weak = [r for r in swept if r["survived"]]
    n_mut = sum(r["tested"] for r in swept)
    n_surv = sum(len(r["survived"]) for r in swept)
    elapsed = time.monotonic() - t0

    Path(args.out).write_text(json.dumps(
        {"results": sorted(results, key=lambda r: r["task"]),
         "summary": {"tasks_swept": len(swept),
                     "tasks_skipped": len(results) - len(swept),
                     "mutants_tested": n_mut, "survivors": n_surv,
                     "tasks_with_weak_spec": len(weak),
                     "seconds": round(elapsed, 1)}}, indent=2))

    print(f"\n=== VERINA spec-mutation sweep ===")
    print(f"tasks with complete ground-truth proofs swept : {len(swept)}")
    print(f"mutants tested   : {n_mut}")
    print(f"survivors        : {n_surv}")
    print(f"tasks whose spec accepted broken code : {len(weak)}/{len(swept)}")
    for r in sorted(weak, key=lambda r: -len(r["survived"])):
        print(f"  {r['task']}: {len(r['survived'])}/{r['tested']} mutants survived")
        for s in r["survived"][:3]:
            print(f"      · {s['mutation']}")
    print(f"\nfull report → {args.out}")
    return 0


if __name__ == "__main__":
    main()
