"""Unit tests for the theorem parser and diagnostic parser (no Lean needed)."""

from verifiedai.audit import parse_theorems
from verifiedai.lean import parse_diagnostics


def test_simple_theorem():
    src = "theorem foo (a b : Nat) : a + b = b + a := by omega\n"
    [t] = parse_theorems(src)
    assert t.name == "foo"
    assert t.binders == "(a b : Nat)"
    assert t.conclusion == "a + b = b + a"
    assert t.line == 1


def test_lemma_keyword_and_multiline():
    src = (
        "lemma bar\n"
        "    (h1 : x > 5)\n"
        "    (h2 : x < 3) :\n"
        "    x = 100 := by\n"
        "  omega\n"
    )
    [t] = parse_theorems(src)
    assert t.name == "bar"
    assert "h1 : x > 5" in t.binders and "h2 : x < 3" in t.binders
    assert t.conclusion == "x = 100"


def test_colon_inside_binders_not_confused():
    src = "theorem baz (f : Nat → Nat) (h : ∀ n : Nat, f n = n) : f 3 = 3 := by simp [h]\n"
    [t] = parse_theorems(src)
    assert t.conclusion == "f 3 = 3"


def test_namespace_insertion_point_before_end():
    src = (
        "namespace Geo\n"
        "def d (a b : Nat) : Nat := a - b\n"
        "theorem t1 (a : Nat) : d a a = 0 := by\n"
        "  unfold d\n"
        "  omega\n"
        "end Geo\n"
    )
    [t] = parse_theorems(src)
    # probes must be inserted BEFORE `end Geo` (line index 5) to keep context
    assert t.insert_at == 5


def test_anonymous_constructor_brackets():
    src = "theorem qux (p : Nat × Nat) (h : p = ⟨1, 2⟩) : p.1 = 1 := by simp [h]\n"
    [t] = parse_theorems(src)
    assert t.conclusion == "p.1 = 1"


def test_skips_defs_and_examples():
    src = (
        "def helper (n : Nat) : Nat := n + 1\n"
        "example : 1 + 1 = 2 := rfl\n"
        "theorem real_one : True := trivial\n"
    )
    thms = parse_theorems(src)
    assert [t.name for t in thms] == ["real_one"]


def test_diag_lake_format():
    out = "error: ././././Demo/Refunds.lean:6:8: unknown constant 'Nat.add_com'"
    [d] = parse_diagnostics(out)
    assert (d.file, d.line, d.col, d.severity) == ("Demo/Refunds.lean", 6, 8, "error")


def test_diag_lean_format_with_continuation():
    out = (
        "Demo/Pricing.lean:22:25: warning: unused variable `h`\n"
        "  note: this linter can be disabled\n"
    )
    [d] = parse_diagnostics(out)
    assert d.severity == "warning"
    assert "unused variable" in d.message
    assert "linter can be disabled" in d.message
