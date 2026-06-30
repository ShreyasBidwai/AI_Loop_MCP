"""Optional LLM drafting for the classifier and the criteria proposer.

Gated on the `anthropic` SDK being installed AND `ANTHROPIC_API_KEY` being set.
When either is absent — or any call fails — the helpers return None and the
callers fall back to their deterministic stubs. So the whole pipeline runs with
zero external deps, and the test suite stays hermetic (no network, no key).

This module NEVER raises to the caller. A missing dep, missing key, network
error, or malformed model output all collapse to None.
"""
from __future__ import annotations
import os, json
from typing import Optional

# Default to the latest, most capable Claude model; override via env.
DEFAULT_MODEL = os.getenv("LOOPING_MODEL", "claude-opus-4-8")


def available() -> bool:
    """True only if we can actually make a call right now."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def draft_json(system: str, user: str, max_tokens: int = 1024) -> Optional[dict]:
    """Ask the model for a single JSON object. Returns the parsed dict, or None
    on any failure so the caller can fall back to its stub."""
    if not available():
        return None
    try:
        import anthropic
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(getattr(b, "text", "") for b in resp.content
                       if getattr(b, "type", "") == "text")
        return _extract_json(text)
    except Exception:
        return None


def _extract_json(text: str) -> Optional[dict]:
    """Pull the first JSON object out of a model response, tolerating ``` fences
    and surrounding prose."""
    text = text.strip()
    if text.startswith("```"):
        # strip the opening fence (``` or ```json) and anything after the close
        text = text[3:]
        if text[:4].lower() == "json":
            text = text[4:]
        text = text.split("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        obj = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None
