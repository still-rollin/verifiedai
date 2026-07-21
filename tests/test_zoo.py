"""The adversarial zoo contract: every kernel cheat in zoo/ marked `caught` in
the manifest MUST be flagged with the expected finding kinds — forever. A
`known_gap` entry documents an attack the current battery misses; when the
corresponding check ships, this test forces the manifest to be promoted.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ZOO = ROOT / "zoo"
MANIFEST = json.loads((ZOO / "manifest.json").read_text())["entries"]

pytestmark = pytest.mark.skipif(shutil.which("lake") is None, reason="lake not on PATH")


@pytest.fixture(scope="module")
def zoo_report() -> dict:
    assert subprocess.run(["lake", "build"], cwd=ZOO, capture_output=True).returncode == 0
    p = subprocess.run(
        [sys.executable, "-m", "verifiedai", "audit", str(ZOO), "--all", "--json"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env={**__import__("os").environ, "PYTHONPATH": str(ROOT / "cli")},
    )
    data = json.loads(p.stdout)
    assert data["skipped"] == [], f"zoo files failed to compile: {data['skipped']}"
    return {r["file"]: {t["name"]: {f["kind"] for f in t["findings"]} for t in r["theorems"]}
            for r in data["reports"]}


def _cases(status):
    return [
        (f, thm, set(spec["expected"]))
        for f, thms in MANIFEST.items()
        for thm, spec in thms.items()
        if spec["status"] == status
    ]


@pytest.mark.parametrize("file,thm,expected", _cases("caught"))
def test_zoo_exploit_is_caught(zoo_report, file, thm, expected):
    got = zoo_report[file][thm]
    assert expected <= got, f"{file}::{thm}: expected {expected}, auditor found {got}"


@pytest.mark.parametrize("file,thm,expected", _cases("known_gap"))
def test_known_gap_still_open(zoo_report, file, thm, expected):
    """If this fails, congratulations — a gap closed. Promote it to `caught`."""
    got = zoo_report[file][thm]
    assert not (expected & got), (
        f"{file}::{thm} is now caught ({expected & got}) — "
        "promote its manifest entry from known_gap to caught"
    )
