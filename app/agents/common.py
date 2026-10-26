"""Helpers every agent shares: instructions, compact closet text, enums."""

from __future__ import annotations

from .. import color_style
from ..config import load_prompt

CATEGORIES = ["top", "bottom", "dress", "outerwear", "activewear", "shoes", "accessory"]
SEASONS = ["spring", "summer", "fall", "winter"]
# Closet sections: finer than category, so the closet reads like a store (skirts apart from pants, camis apart
# from blouses). Category stays the engine's type for outfit rules, sizing and try-on.
SECTIONS = ["tops", "layers", "pants", "skirts", "dresses", "blazers", "jackets", "activewear", "swim", "shoes", "accessories"]
BASE_LAYER_WORDS = ("tank", "cami", "undershirt", "bralette", "bodysuit", "slip", "bandeau", "tube")


def section(item: dict) -> str:
    cat, sub = item.get("category"), (item.get("subtype") or "").lower()
    if any(w in sub or w in (item.get("name") or "").lower() for w in ("bikini", "swim", "one-piece")):
        return "swim"
    if cat == "top":
        if item.get("edited") and item.get("layer") in ("main", "base"):  # her own choice in Edit wins over the words
            return "layers" if item["layer"] == "base" else "tops"
        return "layers" if item.get("layer") == "base" or any(w in sub for w in BASE_LAYER_WORDS) else "tops"
    if cat == "bottom":
        return "skirts" if "skirt" in sub or "skort" in sub else "pants"
    if cat == "outerwear":
        return "blazers" if "blazer" in sub or "sport coat" in sub else "jackets"
    return {"dress": "dresses", "accessory": "accessories"}.get(cat, cat)


def from_section(sec: str) -> dict:
    """Fields to set when someone moves an item to a section in Edit."""
    return {"tops": {"category": "top", "layer": "main"}, "layers": {"category": "top", "layer": "base"},
            "pants": {"category": "bottom"}, "skirts": {"category": "bottom"}, "dresses": {"category": "dress"},
            "swim": {"category": "activewear", "subtype": "swim"}, "blazers": {"category": "outerwear"}, "jackets": {"category": "outerwear"},
            "accessories": {"category": "accessory"}}.get(sec, {"category": sec})


STATUSES = ["good", "snug", "tight", "loose", "short", "long", "unknown"]


STYLING_AGENTS = {"planner", "critic", "recommender", "scout", "inspo", "stylist_read", "aesthetic"}  # get the fashion fundamentals too


def instructions(agent_prompt: str) -> str:
    """Agent prompt first, shared rules after: both are identical on every call, so they cache."""
    extra = "\n\n" + load_prompt("fashion_fundamentals") if agent_prompt in STYLING_AGENTS else ""
    return load_prompt(agent_prompt) + extra + "\n\n" + load_prompt("_shared_rules")


def closet_brief(items: list[dict]) -> str:
    """One line per item. About 3x fewer tokens than sending the closet as JSON."""
    lines = ["id | name | type | color | formality/5 | warmth/5 | seasons | fit | comfort/5 | shoe info"]
    for i in items:
        color = "/".join(c["name"] for c in i.get("colors", []))
        shoe = ""
        if i.get("category") == "shoes":
            shoe = f"toe {i.get('toe_box', '?')}, heel {i.get('heel_in', '?')}in, {'walkable' if i.get('walkable') else 'not for long walks'}"
        note = f" ({i['notes']})" if i.get("notes") else ""
        lines.append(
            f"{i['id']} | {i['name']}{note} | {i.get('category')}/{i.get('subtype')}{' (base layer)' if section(i) == 'layers' else ''} | {color} | "
            f"{i.get('formality')} | {i.get('warmth')} | {','.join(i.get('seasons', []))} | "
            f"{i.get('fit', '')} | {i.get('comfort', '')} | {shoe}"
        )
    return "\n".join(lines)


def profile_brief(profile: dict, include_body: bool) -> str:
    style = profile.get("style", {})
    parts = [
        f"Style words: {', '.join(style.get('words', []))}",
        f"Loves: {', '.join(style.get('love_colors', []))}. Avoids: {', '.join(style.get('avoid', []))}",
        f"Comfort rules: {'; '.join(profile.get('comfort', []))}",
        f"Budget per item: ${profile.get('budget_per_item_usd', 'n/a')}",
    ]
    s = profile.get("sizes", {})
    parts.append(
        f"Store sizes: top {s.get('top')}, bottom {s.get('bottom')}, dress {s.get('dress')}, "
        f"shoe {s.get('shoe')} ({s.get('shoe_width')} width), inseam {s.get('inseam_label')}"
    )
    if profile.get("body_shape", {}).get("shape"):
        parts.append(f"Body shape: {profile['body_shape']['shape']} ({profile['body_shape'].get('flattering', '')})")
    inspo = [w for x in (profile.get("inspo") or [])[-6:] for w in x.get("vibe_words", [])]
    if inspo:
        parts.append(f"Inspiration I saved lately (lean toward it): {', '.join(dict.fromkeys(inspo))}")
    colors = color_style.color_brief(profile)
    if colors:
        parts.append(colors)
    if include_body:
        m = profile.get("measurements_in", {})
        parts.append("Body (inches): " + ", ".join(f"{k} {v}" for k, v in m.items()))
    return "\n".join(parts)
