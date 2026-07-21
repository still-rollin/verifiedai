"""Throughput benchmark: generate a synthetic Lean corpus, audit it, report
theorems/minute. Seeded findings verify correctness at the same time.

    python3 bench/run_bench.py [--files 20] [--theorems 25]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

LAKEFILE = 'name = "bench"\ndefaultTargets = ["Bench"]\n\n[[lean_lib]]\nname = "Bench"\n'


def gen_file(i: int, n_theorems: int) -> tuple[str, int]:
    """Returns (source, seeded_finding_count). Every 5th theorem is vacuous,
    every 7th trivial-by-construction; the rest are honest omega lemmas."""
    out = [f"/-! benchmark file {i} (auto-generated) -/", ""]
    seeded = 0
    for k in range(n_theorems):
        name = f"thm_{i}_{k}"
        if k % 5 == 0:
            out += [
                f"theorem {name} (x : Nat) (h1 : x > {k + 10}) (h2 : x < {k + 3}) :",
                f"    x = {k} := by omega",
                "",
            ]
            seeded += 1
        elif k % 7 == 0:
            out += [f"theorem {name} (a : Nat) : a + {k} = {k} + a := by omega", ""]
            seeded += 1  # trivial: omega closes it
        else:
            out += [
                f"theorem {name} (a b : Nat) (h : a ≤ b) : a + {k} ≤ b + {k} := by omega",
                "",
            ]
    return "\n".join(out), seeded


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", type=int, default=20)
    ap.add_argument("--theorems", type=int, default=25)
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="verifiedai_bench_"))
    try:
        (tmp / "lakefile.toml").write_text(LAKEFILE)
        shutil.copy(ROOT / "demo" / "lean-toolchain", tmp / "lean-toolchain")
        pkg = tmp / "Bench"
        pkg.mkdir()
        roots, total_seeded = [], 0
        for i in range(args.files):
            src, seeded = gen_file(i, args.theorems)
            (pkg / f"F{i}.lean").write_text(src)
            roots.append(f"import Bench.F{i}")
            total_seeded += seeded
        (tmp / "Bench.lean").write_text("\n".join(roots) + "\n")

        print(f"corpus: {args.files} files × {args.theorems} theorems "
              f"({args.files * args.theorems} total, {total_seeded} seeded findings)")
        t0 = time.monotonic()
        subprocess.run(["lake", "build"], cwd=tmp, check=True, capture_output=True)
        t_build = time.monotonic() - t0

        t0 = time.monotonic()
        p = subprocess.run(
            [sys.executable, "-m", "verifiedai", "audit", str(tmp), "--all", "--json"],
            capture_output=True, text=True,
            env={**__import__("os").environ, "PYTHONPATH": str(ROOT / "cli")},
        )
        t_audit = time.monotonic() - t0
        data = json.loads(p.stdout)
        n = sum(len(r["theorems"]) for r in data["reports"])
        flagged = sum(1 for r in data["reports"] for t in r["theorems"] if t["findings"])

        print(f"lake build: {t_build:.1f}s")
        print(f"audit:      {t_audit:.1f}s  →  {n / t_audit:.1f} theorems/sec "
              f"({60 * n / t_audit:.0f} theorems/min) single-process")
        print(f"findings:   {flagged} theorems flagged (seeded: {total_seeded})")
        ok = flagged == total_seeded and n == args.files * args.theorems
        print("correctness:", "✓ all seeded findings recovered, no extras" if ok else "✗ MISMATCH")
        return 0 if ok else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
