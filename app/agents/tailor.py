"""Fit Tailor: virtual try-on. Works out size and zone-by-zone fit before the user sees a product."""

from __future__ import annotations

from .. import safety, store
from ..ledger import Ledger
from ..llm import Tool, obj_schema, run_agent
from ..tools import fit_math
from .common import STATUSES, instructions, profile_brief

FIT_SCHEMA = obj_schema({
    "fits": {"type": "array", "items": obj_schema({
        "product_ref": {"type": "string", "description": "the product_id, or the URL in web mode"},
        "size_to_buy": {"type": "string"},
        "zones": {"type": "array", "items": obj_schema({
            "zone": {"type": "string"},
            "status": {"type": "string", "enum": STATUSES},
            "note": {"type": "string"},
        })},
        "review_evidence": {"type": "array", "items": {"type": "string"}},
        "comfort_verdict": {"type": "string", "enum": ["comfortable", "ok", "uncomfortable"]},
        "skip": {"type": "boolean"},
        "summary": {"type": "string"},
    })},
})


def tailor_tools(ledger: Ledger, dataset: str) -> list[Tool]:
    prof = store.profile(dataset)
    m = prof.get("measurements_in", {})
    width = prof.get("sizes", {}).get("shoe_width", "medium")
    by_id = {p["id"]: p for p in store.catalog()}

    def fit_check(product_id: str) -> dict:
        p = by_id.get(product_id)
        if not p:
            return {"error": "Product not in catalog. Judge fit from reviews only and mark zones unknown."}
        is_shoe = p["category"] == "shoes"
        best = fit_math.best_size(p["size_chart"], m, is_shoe=is_shoe, foot_length_in=m.get("foot_length", 0), foot_width=width)
        screened = safety.screen_reviews(p, ledger, agent="Fit Tailor")
        reviews = "\n".join(f"[{r['stars']}★ bought {r.get('size_bought')}] {r['text']}" for r in screened["reviews"])
        return best | {"reviews": safety.fence(f"reviews:{product_id}", reviews)}

    return [Tool(
        "fit_check",
        "Compare the user's body measurements to this product's size chart. Returns the best size, zone-by-zone fit, and screened reviews.",
        obj_schema({"product_id": {"type": "string"}}),
        fit_check,
    )]


def try_on(ledger: Ledger, dataset: str, picks: list[dict], live_web: bool) -> dict:
    lines = []
    for p in picks:
        ref = p["product_id"] or p["url"]
        lines.append(f"- {ref}: {p['name']} ({p['category']}/{p['subtype']}). Sizes: {p['sizes_note']}. "
                     f"Review quotes the scout found: {safety.fence('scout-quotes', ' | '.join(p['review_quotes']))}")
    # The Tailor never searches the web, so it is the one agent allowed to see body measurements.
    content = (f"ABOUT ME:\n{profile_brief(store.profile(dataset), include_body=True)}\n\n"
               "Try these on for me and tell me how each will fit:\n" + "\n".join(lines))
    if live_web:
        content += "\nThese are from the web (no size chart): judge from the review quotes and the user's store sizes; mark zones without evidence as unknown."
    ledger.step("Fit Tailor", "start", f"Virtual try-on for {len(picks)} item(s)")
    out = run_agent(ledger, "Fit Tailor", instructions("tailor"), content,
                    schema=FIT_SCHEMA, schema_name="fits", tools=tailor_tools(ledger, dataset), effort="low").output
    for f in out["fits"]:
        bad = [z["zone"] for z in f["zones"] if z["status"] in ("tight", "short")]
        ledger.step("Fit Tailor", "fit", f"{f['product_ref']}: size {f['size_to_buy']}, {f['comfort_verdict']}"
                    + (f" — problem zones: {', '.join(bad)}" if bad else ""), f)
    return out
