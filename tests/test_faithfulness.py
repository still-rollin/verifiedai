"""Faithfulness check unit tests — LLM calls mocked; protocol logic is real."""

import json

from verifiedai import faithfulness
from verifiedai.audit import parse_theorems


def _mock_complete(responses):
    """Returns a _complete stub that replays canned responses in order."""
    it = iter(responses)

    def fake(system, user):
        return next(it)

    return fake


def test_docstring_extraction():
    src = (
        "/-- The sum of the first n odd numbers is n squared. -/\n"
        "theorem sum_odds (n : Nat) : n * n = n ^ 2 := by ring\n"
        "\n"
        "theorem no_doc (a : Nat) : a = a := rfl\n"
    )
    thms = parse_theorems(src)
    assert thms[0].docstring == "The sum of the first n odd numbers is n squared."
    assert thms[1].docstring == ""


def test_unfaithful_flagged(monkeypatch):
    monkeypatch.setattr(
        faithfulness,
        "_complete",
        _mock_complete(
            [
                "For every natural number n, n times n equals n squared.",
                json.dumps(
                    {
                        "score": 0.2,
                        "faithful": False,
                        "discrepancies": "informal claims a sum of odd numbers; formal states a plain identity",
                    }
                ),
            ]
        ),
    )
    result = faithfulness.check_faithfulness(
        "theorem sum_odds (n : Nat) : n * n = n ^ 2",
        "The sum of the first n odd numbers is n squared.",
    )
    assert result and result["kind"] == "unfaithful"
    assert "sum of odd numbers" in result["detail"]


def test_faithful_passes(monkeypatch):
    monkeypatch.setattr(
        faithfulness,
        "_complete",
        _mock_complete(
            [
                "For all natural numbers a and b, a plus b equals b plus a.",
                json.dumps({"score": 0.97, "faithful": True, "discrepancies": ""}),
            ]
        ),
    )
    result = faithfulness.check_faithfulness(
        "theorem add_comm (a b : Nat) : a + b = b + a",
        "Addition of natural numbers is commutative.",
    )
    assert result == {}


def test_unavailable_returns_none(monkeypatch):
    monkeypatch.setattr(faithfulness, "_complete", lambda s, u: None)
    assert (
        faithfulness.check_faithfulness("theorem t : True", "Trivially true.") is None
    )


def test_judge_garbage_output_is_safe(monkeypatch):
    monkeypatch.setattr(
        faithfulness,
        "_complete",
        _mock_complete(["Some English.", "not json at all"]),
    )
    assert (
        faithfulness.check_faithfulness("theorem t : True", "Trivially true.") is None
    )
