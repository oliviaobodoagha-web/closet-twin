"""Style Critic: checks every plan or shopping pick before the user sees it."""

from __future__ import annotations

import json

from ..ledger import Ledger
from ..llm import obj_schema, run_agent
from .common import instructions

REVIEW_SCHEMA = obj_schema({
    "verdict": {"type": "string", "enum": ["approve", "revise"]},
    "issues": {"type": "array", "items": {"type": "string"}},
    "scores": obj_schema({
        "weather": {"type": "integer"},
        "dress_code": {"type": "integer"},
        "comfort": {"type": "integer"},
        "style": {"type": "integer"},
        "truth": {"type": "integer"},
    }),
    "user_note": {"type": "string"},
    # day plans: titles of alternate outfits she should not be shown (empty for anything else)
    "drop_alternates": {"type": "array", "items": {"type": "string"}},
})


def critique(ledger: Ledger, what: str, proposal: dict, context: str, code_flags: list[str], effort: str = "low") -> dict:
    """`code_flags` are problems our own code already found (e.g. an item id that isn't in the closet)."""
    content = (
        f"CONTEXT:\n{context}\n\nPROPOSAL ({what}):\n{json.dumps(proposal, indent=1)}\n\n"
        "Score each area 1-5 and decide approve or revise."
    )
    if code_flags:
        content += "\n\nAUTOMATIC CHECKS FAILED (these must be fixed, verdict must be revise):\n- " + "\n- ".join(code_flags)
    ledger.step("Style Critic", "start", f"Reviewing the {what}")
    review = run_agent(ledger, "Style Critic", instructions("critic"), content,
                       schema=REVIEW_SCHEMA, schema_name="review", effort=effort).output
    if code_flags and review["verdict"] == "approve":
        # The model cannot overrule a failed code check.
        review["verdict"] = "revise"
        review["issues"] = code_flags + review["issues"]
    ledger.step("Style Critic", "verdict", f"{review['verdict'].upper()}: {review['user_note']}", review)
    return review
