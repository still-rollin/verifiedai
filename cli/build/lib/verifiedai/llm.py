"""LLM escalation tier for proof repair. Uses the Anthropic SDK; credentials are
resolved from the environment (ANTHROPIC_API_KEY or an `ant auth login` profile).

Every candidate the model proposes is compiled by the Lean kernel before it is
accepted — the LLM proposes, the kernel disposes."""

from __future__ import annotations

MODEL = "claude-opus-4-8"

SYSTEM = """You repair broken Lean 4 proofs. You are given a Lean file, one broken \
declaration from it, and the compiler errors. Return ONLY the corrected declaration \
(from the `theorem`/`lemma`/`def` keyword through the end of its proof), with no \
markdown fences and no commentary. Change the proof, not the statement, unless the \
statement itself is malformed. Prefer minimal edits (e.g. a typo'd lemma name)."""


def llm_available() -> tuple[bool, str]:
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False, "python package `anthropic` not installed (pip install anthropic)"
    return True, ""


def propose_fix(file_source: str, decl: str, errors: str, feedback: str | None = None) -> str | None:
    """Ask Claude for a corrected declaration. Returns None on any API failure."""
    import anthropic

    client = anthropic.Anthropic()
    user = (
        f"Full file for context:\n```lean\n{file_source}\n```\n\n"
        f"Broken declaration:\n```lean\n{decl}\n```\n\n"
        f"Compiler errors:\n{errors}\n"
    )
    if feedback:
        user += f"\nYour previous attempt failed to compile with:\n{feedback}\n"

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            thinking={"type": "adaptive"},
            system=SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
    except anthropic.AuthenticationError:
        print("    llm: no valid Anthropic credentials (set ANTHROPIC_API_KEY or `ant auth login`)")
        return None
    except anthropic.RateLimitError:
        print("    llm: rate limited, skipping")
        return None
    except anthropic.APIStatusError as e:
        print(f"    llm: API error {e.status_code}: {e.message}")
        return None
    except anthropic.APIConnectionError:
        print("    llm: network error, skipping")
        return None

    text = next((b.text for b in response.content if b.type == "text"), "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("lean"):
            text = text[4:]
        text = text.strip()
    return text or None
