"""Back-translation faithfulness check (opt-in: `verifiedai audit --faithful`).

Does the formal statement mean what the informal one says? Protocol:

  1. BLIND BACK-TRANSLATION — a model that has never seen the informal statement
     translates the Lean statement into plain English.
  2. JUDGE — a second call compares the informal statement with the blind
     back-translation and reports equivalence + concrete discrepancies.

The two-step design prevents contamination: the back-translator cannot parrot
the informal wording it never saw. This is a *soft* signal (LLM-judged, unlike
the kernel-compiled probes) — findings are warnings, never reward-gating facts.

Requires `pip install anthropic` and Anthropic credentials (ANTHROPIC_API_KEY
or an `ant auth login` profile).
"""

from __future__ import annotations

import json
import re

MODEL = "claude-opus-4-8"
SCORE_THRESHOLD = 0.75

_BT_SYSTEM = """You translate Lean 4 theorem statements into plain English for a \
mathematician who does not read Lean. State exactly what the theorem claims — the \
hypotheses and the conclusion — faithfully and completely. Do not editorialize, do \
not guess intent, do not strengthen or weaken the claim. Reply with the English \
statement only."""

_JUDGE_SYSTEM = """You compare two statements of a mathematical claim: (A) the \
original informal statement, and (B) an independent English rendering of its \
formalization. Decide whether B states the SAME claim as A — same hypotheses, same \
conclusion, same strength. Quantifier changes, dropped/added hypotheses, weakened \
conclusions, or changed constants all count as mismatches. Reply with ONLY a JSON \
object: {"score": <0.0-1.0 equivalence score>, "faithful": <true|false>, \
"discrepancies": "<one sentence; empty string if none>"}"""


def _complete(system: str, user: str) -> str | None:
    """One Messages API call; returns text or None on any failure."""
    try:
        import anthropic
    except ImportError:
        return None
    client = anthropic.Anthropic()
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1000,
            thinking={"type": "adaptive"},
            system=system,
            messages=[{"role": "user", "content": user}],
        )
    except anthropic.AuthenticationError:
        return None
    except (anthropic.APIStatusError, anthropic.APIConnectionError):
        return None
    return next((b.text for b in response.content if b.type == "text"), "").strip()


def check_faithfulness(formal_stmt: str, informal: str) -> dict | None:
    """Returns a finding dict if unfaithful, {} if faithful, None if unavailable."""
    english = _complete(_BT_SYSTEM, f"```lean\n{formal_stmt}\n```")
    if not english:
        return None
    verdict_raw = _complete(
        _JUDGE_SYSTEM,
        f"(A) informal statement:\n{informal}\n\n(B) back-translated formalization:\n{english}",
    )
    if not verdict_raw:
        return None
    m = re.search(r"\{.*\}", verdict_raw, re.S)
    if not m:
        return None
    try:
        verdict = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if verdict.get("faithful") and float(verdict.get("score", 0)) >= SCORE_THRESHOLD:
        return {}
    return {
        "kind": "unfaithful",
        "severity": "warning",
        "detail": (
            f"back-translation disagrees with the informal statement "
            f"(equivalence score {verdict.get('score', '?')}): "
            f"{verdict.get('discrepancies', '').strip() or 'see back-translation'} "
            f"[blind back-translation: {english[:200]}]"
        ),
    }


def audit_faithfulness(thms) -> tuple[int, int]:
    """Run the check on every theorem carrying a docstring. Returns
    (checked, unavailable) counts; findings are appended in place."""
    checked = unavailable = 0
    for t in thms:
        if not t.docstring:
            continue
        stmt = f"theorem {t.name} {t.binders} : {t.conclusion}"
        result = check_faithfulness(stmt, t.docstring)
        if result is None:
            unavailable += 1
            continue
        checked += 1
        if result:
            t.findings.append(result)
    return checked, unavailable
