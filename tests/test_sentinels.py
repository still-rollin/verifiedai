"""Regression tests for the probe-sentinel mechanism.

Context: Lean aborts elaboration at `maxErrors` (default 100). In a probe file
errors are the NORMAL case — every clean theorem fails its vac and triv probes —
so a large file used to stop reporting errors mid-way, and every later probe's
silence was misread as "probe compiled" → mass false vacuous/trivial findings
(observed: 55 false vacuous on ProofNet's Dummit-Foote/Munkres/Rudin files).

The fix is positive confirmation: each probe carries a `#print axioms <probe>`
sentinel, and a finding requires the sentinel's output to be PRESENT.
"""

from verifiedai.audit import Theorem, _parse_sentinels, _probe_decl


def _thm(**kw) -> Theorem:
    defaults = dict(
        name="foo", binders="(n : ℕ) (h : n > 0)", conclusion="n = n",
        line=1, insert_at=1, docstring=None, findings=[],
    )
    defaults.update(kw)
    return Theorem(**defaults)


def test_probe_decl_carries_sentinel():
    t = _thm()
    for kind, nm in (("vac", "__verifiedai_vac_3_foo"),
                     ("triv", "__verifiedai_triv_3_foo")):
        decl = _probe_decl(kind, 3, t)
        assert f"theorem {nm} " in decl
        assert f"#print axioms {nm}" in decl


def test_parse_sentinels_extracts_probe_names_only():
    out = (
        "'__verifiedai_vac_0_foo' depends on axioms: [propext,\n Classical.choice]\n"
        "'foo' depends on axioms: [sorryAx]\n"
        "'__verifiedai_triv_1_bar' depends on axioms: []\n"
        # axiom-free probes (rfl/decide-closed) print a DIFFERENT message:
        "'__verifiedai_triv_2_baz' does not depend on any axioms\n"
        "'baz' does not depend on any axioms\n"
    )
    s = _parse_sentinels(out)
    assert s == {
        "__verifiedai_vac_0_foo": {"propext", "Classical.choice"},
        "__verifiedai_triv_1_bar": set(),
        "__verifiedai_triv_2_baz": set(),
    }
    # real theorems' own axiom lines are NOT sentinels
    assert "foo" not in s and "baz" not in s


def test_missing_sentinel_means_no_confirmation():
    # elaboration aborted before this probe: no error in its span AND no
    # sentinel output — the old logic called that a finding; now it must not be
    out_aborted = "'__verifiedai_vac_0_a' depends on axioms: []\n"  # only probe 0 ran
    s = _parse_sentinels(out_aborted)
    assert "__verifiedai_vac_1_b" not in s  # probe 1's silence confirms nothing
