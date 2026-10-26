"""Shopping Scout: finds products that match the request, sizes, style and review comfort.

Catalog mode searches the bundled sample catalog (fictional brands and reviews) and
runs every review through the injection screen before the agent reads it.
Web mode uses OpenAI's built-in web search for real stores.
The Scout never receives body measurements: only store size labels.
"""

from __future__ import annotations

import re

from .. import memory, config, safety, store, stylists
from ..ledger import Ledger
from ..llm import Tool, obj_schema, run_agent
from .common import CATEGORIES, closet_brief, instructions, profile_brief

PICKS_SCHEMA = obj_schema({
    "picks": {"type": "array", "items": obj_schema({
        "product_id": {"type": "string", "description": "catalog id, or empty string in web mode"},
        "url": {"type": "string"},
        "name": {"type": "string"},
        "brand": {"type": "string"},
        "category": {"type": "string", "enum": CATEGORIES},
        "subtype": {"type": "string"},
        "color": {"type": "string"},
        "color_hex": {"type": "string"},
        "price_usd": {"type": "number"},
        "sizes_note": {"type": "string"},
        "store": {"type": "string", "description": "retailer name, e.g. Nordstrom"},
        "confirmed_sizes": {"type": "string", "description": "the user's size/width as confirmed on the product page, e.g. '11 Wide in stock'; empty if not confirmed"},
        "review_quotes": {"type": "array", "items": {"type": "string"}},
        "agree_count": {"type": "integer"},
        "why": {"type": "string"},
        "stylist_note": {"type": "string"},
    })},
    "stylist_take": {"type": "string"},
    "note": {"type": "string"},
})


def in_size(product: dict, sizes: dict) -> bool:
    chart = product.get("size_chart", {})
    if product["category"] == "shoes":
        row = chart.get(str(sizes.get("shoe_size", "")))
        if not row:
            return False
        need = sizes.get("shoe_width") or "medium"
        return need in ("medium", "regular") or need in row.get("widths", []) or "extra wide" in row.get("widths", [])
    wanted = [sizes.get("top_size"), sizes.get("bottom_size"), sizes.get("dress_size")]
    return any(str(w) in chart for w in wanted if w)


def catalog_tool(ledger: Ledger, sizes: dict) -> Tool:
    def search_catalog(category: str, keywords: str, max_price: float) -> dict:
        words = [w for w in re.split(r"\W+", keywords.lower()) if len(w) > 2]
        results = []
        for p in store.catalog():
            if category != "any" and p["category"] != category:
                continue
            if max_price and p["price_usd"] > max_price:
                continue
            hay = f"{p['name']} {p['subtype']} {p['colors'][0]['name']} {p.get('fabric', '')}".lower()
            score = sum(w in hay for w in words)
            screened = safety.screen_reviews(p, ledger)
            results.append((score, {
                "product_id": p["id"],
                "name": p["name"],
                "brand": p["brand"],
                "category": p["category"],
                "subtype": p["subtype"],
                "color": p["colors"][0],
                "price_usd": p["price_usd"],
                "url": p["url"],
                "formality": p.get("formality"),
                "seasons": p.get("seasons"),
                "sizes_offered": list(p["size_chart"]),
                "widths": sorted({w for r in p["size_chart"].values() for w in r.get("widths", [])}) or None,
                "in_your_size": in_size(p, sizes),
                "toe_box": p.get("toe_box"),
                "heel_in": p.get("heel_in"),
                "reviews": safety.fence(
                    f"reviews:{p['id']}",
                    "\n".join(f"[{r['stars']}★ {r['author']}, bought {r.get('size_bought')}] {r['text']}" for r in screened["reviews"]),
                ),
                "reviews_blocked_by_screen": screened["quarantined_reviews"],
            }))
        results.sort(key=lambda x: -x[0])
        return {"results": [r for _, r in results[:8]]}

    return Tool(
        "search_catalog",
        "Search the shop catalog. category is one of top, bottom, dress, outerwear, activewear, shoes, accessory, or 'any'. "
        "max_price 0 means no limit. Returns sizes offered, whether it's in the user's size, and screened reviews.",
        obj_schema({
            "category": {"type": "string", "enum": CATEGORIES + ["any"]},
            "keywords": {"type": "string"},
            "max_price": {"type": "number"},
        }),
        search_catalog,
    )


RETAILERS = ("Nordstrom, Zappos, DSW, J.Crew, Madewell, Everlane, Abercrombie, Banana Republic, Ralph Lauren, "
             "Clarks, Vionic, Naturalizer, Sam Edelman, Amazon")


def size_query_hints(sizes: dict) -> str:
    """Store size labels turned into search phrases. These are the only body facts that reach the web."""
    width = sizes.get("shoe_width") or ""
    shoe = f"women's size {sizes.get('shoe_size')}" + (f" {width}" if width and width not in ("medium", "regular") else "")
    inseam = {"long": "long / tall inseam", "petite": "petite"}.get(sizes.get("inseam_length", ""), "")
    return (f"shoes: \"{shoe}\"; tops: size {sizes.get('top_size')}; bottoms: size {sizes.get('bottom_size')}"
            + (f" {inseam}" if inseam else "") + f"; dresses: size {sizes.get('dress_size')}")


def scout(ledger: Ledger, dataset: str, request: str, live_web: bool) -> tuple[dict, set[str], list[str]]:
    prof = store.profile(dataset)
    sizes = safety.size_labels(prof)
    closet = store.closet(dataset)
    request, flags = safety.clean_untrusted(request, 300)
    if live_web:
        how = (
            "Search real online stores now with short, natural shopper queries (one store or idea each; never stack quoted phrases). Include my size in each query using these labels: "
            f"{size_query_hints(sizes)}. Prefer retailers that show size availability and reviews ({RETAILERS}). "
            "Search results rarely show live stock, so judge size by what the store offers: keep a product when its page, "
            "listing or the retailer's size range for that style includes my size (e.g. 'sizes 00-24', 'XXS-3X', "
            "'extended sizes', 'available in Wide'); write exactly what you saw in confirmed_sizes, e.g. 'Size 18 offered "
            "(00-24)' or '11 Wide listed'. Skip it only if the page shows my size is NOT offered. Aim for 3 picks from "
            "different stores. Use the exact product page URL from your search results "
            "(the page you cite), set store to the retailer, and choose colors from my color season palette when you can. "
            "Resale (Poshmark, The RealReal, ThredUp, eBay) is welcome when it's a better buy and my size is listed. "
            "Favor pieces that fill a gap in my closet and make several new outfits with what I own."
        )
    else:
        how = "Use search_catalog (try a couple of keyword variations if needed)."
    content = (
        f"WHAT I OWN:\n{closet_brief(closet)}\n\nABOUT ME:\n{profile_brief(prof, include_body=False)}\n\n"
        f"{stylists.point_of_view(prof, dataset)}\n\n"
        + (f"MY BUDGET RULES: {'; '.join(prof['budget_rules'])}\n\n" if prof.get("budget_rules") else "")
        + (f"{memory.shopping_brief(dataset)}\n\n" if memory.shopping_brief(dataset) else "")
        + f"Find me: {request}\n{how}"
    )
    ledger.step("Shopping Scout", "start", f"Looking for: {request} ({'live web' if live_web else 'sample catalog'})")
    result = run_agent(
        ledger, "Shopping Scout", instructions("scout"), content,
        schema=PICKS_SCHEMA, schema_name="picks",
        tools=[] if live_web else [catalog_tool(ledger, sizes)],
        web_search=live_web, effort="low",
        max_tool_calls=config.MAX_WEB_SEARCHES_PER_CALL if live_web else None,
    )
    picks = result.output
    if live_web:
        # Trusted links = pages the search returned or opened, plus cited ones. Anything else is dropped later.
        allowed = {c["url"] for c in result.citations} | set(result.seen_urls)
        ledger.step("Shopping Scout", "check",
                    f"{len(allowed)} trusted link(s) the search returned or opened ({len(result.citations)} cited)",
                    sorted(allowed))
    else:
        allowed = {p["url"] for p in store.catalog()} | {p["id"] for p in store.catalog()}
    # Privacy check on what actually went to the web.
    leaks = safety.leaked_in_queries(result.searches, prof)
    if leaks:
        ledger.safety("privacy", "Shopping Scout", "A web search query contained private data.", leaks)
    ledger.step("Shopping Scout", "done", f"{len(picks['picks'])} pick(s): " + ", ".join(p["name"] for p in picks["picks"]))
    return picks, allowed, result.searches
