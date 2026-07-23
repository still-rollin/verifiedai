"""Statement-integrity audit of a sample of Lean Workbook (internlm/Lean-Workbook).

Lean Workbook is ~140k LLM-auto-formalized contest statements used as TRAINING
DATA by theorem-prover teams — the highest-leverage place for statement bugs:
a vacuous training statement is a reward-hacking signal.

Statements are standalone one-liners, so we PACK many per file — the auditor
costs 2 compiles per file regardless of theorem count. Pipeline:

  1. sample N entries reproducibly (--seed)
  2. pack K statements per .lean file inside a host lake project whose
     mathlib cache is already present
  3. pre-filter compile: drop statements that no longer elaborate under the
     host's mathlib (dropped ids are RECORDED — that rate is itself data)
  4. audit surviving files with the standard battery, map findings back to
     dataset ids + informal statements

    python3 bench/audit_lean_workbook.py \
        --json experiments/lean_workbook.json \
        --host experiments/PutnamBench/lean4 \
        --n 2000 --pack 20 --jobs 6 \
        --out experiments/lean_workbook_audit.json
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "cli"))

from verifiedai.audit import Auditor, parse_theorems  # noqa: E402
from verifiedai.lean import LeanProject, parse_diagnostics  # noqa: E402

IGNORE = {"sorry"}  # every proof is `sorry` by design
GEN_DIR = "lwb"     # generated files live under <host>/lwb/

_NAME_RE = re.compile(r"\b(?:theorem|lemma)\s+([A-Za-z0-9_'.]+)")


def normalize(stmt: str) -> str | None:
    """One packed-file-safe declaration per entry, or None to skip."""
    s = stmt.strip()
    if not s.startswith(("theorem", "lemma")):
        return None
    if "import" in s.split(":", 1)[0]:
        return None
    return s if s.rstrip().endswith("sorry") else None


def pack(entries: list[dict], k: int) -> list[tuple[str, list[dict]]]:
    files = []
    for i in range(0, len(entries), k):
        chunk = entries[i : i + k]
        body = "import Mathlib\n\nset_option maxHeartbeats 400000\n\n" + \
            "\n\n".join(e["stmt"] for e in chunk) + "\n"
        files.append((body, chunk))
    return files


def line_ranges(body: str, chunk: list[dict]) -> list[tuple[int, int, dict]]:
    """(start_line, end_line, entry) for each statement in the packed body."""
    lines = body.splitlines()
    out, cur = [], 0
    for e in chunk:
        first = e["stmt"].splitlines()[0]
        for j in range(cur, len(lines)):
            if lines[j] == first:
                n = len(e["stmt"].splitlines())
                out.append((j + 1, j + n, e))
                cur = j + n
                break
    return out


def prefilter(project: LeanProject, body: str, chunk: list[dict],
              rel: str) -> tuple[list[dict], list[dict]]:
    """Compile the packed file once; split chunk into (alive, dead)."""
    path = project.root / rel
    path.write_text(body)
    _ok, diags, _out = project.check_file(rel)
    bad_lines = {d.line for d in diags if d.severity == "error"}
    alive, dead = [], []
    for lo, hi, e in line_ranges(body, chunk):
        if any(lo <= ln <= hi for ln in bad_lines):
            dead.append(e)
        else:
            alive.append(e)
    # errors outside any statement span (e.g. import failure) kill the file
    stray = bad_lines - {ln for lo, hi, _ in line_ranges(body, chunk)
                         for ln in range(lo, hi + 1)}
    if stray:
        return [], chunk
    return alive, dead


def audit_pack(project: LeanProject, idx: int, chunk: list[dict]) -> dict:
    rel = f"{GEN_DIR}/LWB_{idx:04d}.lean"
    body = pack(chunk, len(chunk))[0][0]
    alive, dead = prefilter(project, body, chunk, rel)
    result = {"file": rel, "dead": [e["id"] for e in dead], "findings": []}
    if not alive:
        (project.root / rel).unlink(missing_ok=True)
        return result
    body2 = pack(alive, len(alive))[0][0]
    (project.root / rel).write_text(body2)
    by_name = {}
    for e in alive:
        m = _NAME_RE.search(e["stmt"])
        if m:
            by_name[m.group(1)] = e
    try:
        thms = Auditor(project, rel).run()
    except RuntimeError as exc:
        result["error"] = str(exc).splitlines()[0]
        (project.root / rel).unlink(missing_ok=True)
        return result
    for t in thms:
        for f in t.findings:
            if f["kind"] in IGNORE:
                continue
            e = by_name.get(t.name, {})
            result["findings"].append({
                "id": e.get("id"), "name": t.name, "kind": f["kind"],
                "detail": f["detail"], "split": e.get("split"),
                "informal": e.get("informal", "")[:400],
                "stmt": e.get("stmt", "")})
    (project.root / rel).unlink(missing_ok=True)
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(ROOT / "experiments" / "lean_workbook.json"))
    ap.add_argument("--host", default=str(ROOT / "experiments" / "PutnamBench" / "lean4"))
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--pack", type=int, default=20)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--out", default=str(ROOT / "experiments" / "lean_workbook_audit.json"))
    args = ap.parse_args()

    data = json.load(open(args.json))
    entries = []
    for i, d in enumerate(data):
        s = normalize(d.get("formal_statement", ""))
        if s is None:
            continue
        m = _NAME_RE.search(s)
        if not m or not parse_theorems(s):
            continue
        entries.append({"id": i, "stmt": s, "split": d.get("split", "?"),
                        "informal": d.get("natural_language_statement", "")})
    print(f"{len(data)} entries → {len(entries)} usable standalone statements")

    rng = random.Random(args.seed)
    sample = rng.sample(entries, min(args.n, len(entries)))
    # unique theorem names across the sample (dataset has no dup names, but be safe)
    seen: set[str] = set()
    sample = [e for e in sample
              if (n := _NAME_RE.search(e["stmt"]).group(1)) not in seen
              and not seen.add(n)]

    project = LeanProject(args.host)
    (project.root / GEN_DIR).mkdir(exist_ok=True)
    chunks = [sample[i:i + args.pack] for i in range(0, len(sample), args.pack)]
    print(f"sampled {len(sample)} (seed={args.seed}) → {len(chunks)} packed files "
          f"of ≤{args.pack} → auditing with {args.jobs} workers …")

    t0 = time.monotonic()
    results = []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futs = {pool.submit(audit_pack, project, i, c): i
                for i, c in enumerate(chunks)}
        done = 0
        for fut in as_completed(futs):
            results.append(fut.result())
            done += 1
            if done % 10 == 0:
                nf = sum(len(r["findings"]) for r in results)
                nd = sum(len(r["dead"]) for r in results)
                print(f"  {done}/{len(chunks)} packs · {nf} findings · "
                      f"{nd} non-elaborating · {time.monotonic() - t0:.0f}s",
                      flush=True)

    elapsed = time.monotonic() - t0
    findings = [f for r in results for f in r["findings"]]
    dead = [i for r in results for i in r["dead"]]
    errors = [r for r in results if "error" in r]
    by_kind: dict[str, int] = {}
    for f in findings:
        by_kind[f["kind"]] = by_kind.get(f["kind"], 0) + 1

    Path(args.out).write_text(json.dumps(
        {"dataset": "internlm/Lean-Workbook", "seed": args.seed,
         "sampled": len(sample), "non_elaborating": len(dead),
         "dead_ids": dead, "pack_errors": [r["file"] for r in errors],
         "findings": findings,
         "summary": {"audited": len(sample) - len(dead),
                     "findings": len(findings), "by_kind": by_kind,
                     "seconds": round(elapsed, 1)}}, indent=2))

    print(f"\n=== Lean Workbook statement audit (seed {args.seed}) ===")
    print(f"sampled          : {len(sample)}")
    print(f"non-elaborating  : {len(dead)} ({100 * len(dead) / len(sample):.1f}%)"
          f"  (vs mathlib of host toolchain)")
    print(f"pack errors      : {len(errors)}")
    print(f"wall time        : {elapsed / 60:.1f} min")
    print(f"findings         : {len(findings)}  {by_kind}")
    for f in findings:
        print(f"  [{f['kind']}] #{f['id']} {f['name']} ({f['split']})")
    print(f"\nfull report → {args.out}")
    return 0


if __name__ == "__main__":
    main()
