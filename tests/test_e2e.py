"""End-to-end tests against the bundled demo Lean project.

Requires a Lean toolchain (`lake` on PATH); skipped otherwise. The demo project
is the ground truth: known-vacuous, known-trivial, known-clean theorems.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "demo"

pytestmark = pytest.mark.skipif(shutil.which("lake") is None, reason="lake not on PATH")


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "verifiedai", *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env={**__import__("os").environ, "PYTHONPATH": str(ROOT / "cli")},
    )


@pytest.fixture(scope="module", autouse=True)
def built_demo():
    assert subprocess.run(["lake", "build"], cwd=DEMO, capture_output=True).returncode == 0


def _findings(report: dict, thm: str) -> set[str]:
    for t in report["theorems"]:
        if t["name"] == thm:
            return {f["kind"] for f in t["findings"]}
    raise AssertionError(f"{thm} not in report")


def test_audit_pricing_ground_truth():
    p = run_cli("audit", "demo", "Demo/Pricing.lean", "--json")
    assert p.returncode == 1  # vacuous finding => exit 1
    report = json.loads(p.stdout)["reports"][0]
    assert _findings(report, "discount_le_price") == set()
    assert _findings(report, "big_discount_still_positive") == {"vacuous"}
    assert _findings(report, "tax_identity") == {"trivial", "unused_hypothesis"}


def test_audit_namespace_context_preserved():
    p = run_cli("audit", "demo", "Demo/Geometry.lean", "--json")
    report = json.loads(p.stdout)["reports"][0]
    assert _findings(report, "dist_self") == set()
    # hypotheses mention the namespaced `Geometry.dist` — only works if probes
    # are inserted inside the namespace
    assert _findings(report, "far_and_near") == {"vacuous"}


def test_corpus_mode_counts():
    p = run_cli("audit", "demo", "--all", "--json")
    data = json.loads(p.stdout)
    total = sum(len(r["theorems"]) for r in data["reports"])
    assert total == 6
    assert data["skipped"] == []


def test_repair_fixes_broken_proof():
    refunds = DEMO / "Demo" / "Refunds.lean"
    original = refunds.read_text()
    assert "Nat.add_comm" in original
    try:
        refunds.write_text(original.replace("Nat.add_comm", "Nat.add_com"))
        p = run_cli("repair", "demo", "--no-llm")
        assert p.returncode == 0, p.stdout + p.stderr
        fixed = refunds.read_text()
        assert "Nat.add_com " not in fixed  # typo gone (kernel-verified fix applied)
        assert subprocess.run(["lake", "build"], cwd=DEMO, capture_output=True).returncode == 0
    finally:
        refunds.write_text(original)
        subprocess.run(["lake", "build"], cwd=DEMO, capture_output=True)
