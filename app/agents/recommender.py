"""Wardrobe Recommender: closet + profile + next 7 days -> the pieces worth buying next (and, optionally, shop the top one)."""

from __future__ import annotations

from datetime import date, timedelta

from .. import memory, outfit_rules, safety, store, stylists
from ..ledger import Ledger
from ..llm import obj_schema, run_agent
from ..tools import weather
from . import orchestrator
from .common import CATEGORIES, closet_brief, instructions, profile_brief

GAPS_SCHEMA = obj_schema({
    "stylist_take": {"type": "string"},
    "gaps": {"type": "array", "items": obj_schema({
        "piece": {"type": "string"},
        "category": {"type": "string", "enum": CATEGORIES},
        "why": {"type": "string"},
        "events": {"type": "array", "items": {"type": "string"}},
        "pairs_with_ids": {"type": "array", "items": {"type": "string"}},
        "colors": {"type": "array", "items": obj_schema({"name": {"type": "string"}, "hex": {"type": "string"}})},
        "search_request": {"type": "string"},
        # the outfit this piece makes with what she owns (drawn as a mock-up)
        "outfit_title": {"type": "string"},
        "outfit_ids": {"type": "array", "items": {"type": "string"}},
    })},
})


def week_ahead(dataset: str, start: date, days: int = 7) -> str:
    lines = []
    for i in range(days):
        d = (start + timedelta(days=i)).isoformat()
        events, _source = store.day_events(dataset, d)
        if events:
            lines.append(f"{d}: " + "; ".join(f"{e['start']} {e['title']}" + (f" @ {e['location']}" if e.get("location") else "") for e in events))
        if dataset == "sample":  # the sample calendar is one example day shown on any date
            break
    return "\n".join(lines) or "(no calendar events found)"


def places(dataset: str, start: date, days: int = 7) -> dict:
    """Event title -> where it is, for the week (so 'Welcome Back Cider' is known to be at the Student Commons)."""
    out = {}
    for i in range(days):
        for e in store.day_events(dataset, (start + timedelta(days=i)).isoformat())[0]:
            out.setdefault(e["title"], e.get("location") or "")
    return out


def with_place(events: list[str], where: dict) -> list[str]:
    return [e + next((f" @ {loc}" for t, loc in where.items() if loc and e.startswith(t)), "") for e in events or []]


def recommend(ledger: Ledger, dataset: str, shop: bool = False, look: str = "") -> dict:
    prof = store.profile(dataset)
    closet = [i for i in store.closet(dataset) if i.get("status") != "returned" and not i.get("out_of_season")]
    today = date.today()
    wx = weather.forecast(prof.get("lat", 41.31), prof.get("lon", -72.93), today.isoformat())
    content = (
        f"MY CLOSET ({len(closet)} items):\n{closet_brief(closet) if closet else '(empty: I have not added clothes yet)'}\n\n"
        f"ABOUT ME:\n{profile_brief(prof, include_body=False)}\n\n{stylists.point_of_view(prof, dataset)}\n\n"
        f"{memory.brief(dataset, today.isoformat())}\n{memory.shopping_brief(dataset)}\n"
        + (f"INSPIRATION I SAVED: {'; '.join(x['summary'] for x in prof.get('inspo', [])[-5:])}\n" if prof.get("inspo") else "")
        + (f"MY BUDGET RULES: {'; '.join(prof['budget_rules'])}\n" if prof.get("budget_rules") else "")
        + f"\nMY NEXT 7 DAYS:\n{week_ahead(dataset, today)}\n\n"
        f"WEATHER TODAY: {wx.get('summary')}, high {wx.get('high_f')}°F / low {wx.get('low_f')}°F; season {weather.season_for(today.isoformat(), prof.get('lat', 41.31))}\n\n"
        + (f"THE LOOK I'M GOING FOR: {safety.fence('user request', look)}\n\n" if look else "")
        + "What are the next 3 pieces I should buy? List 2 backup pieces after them, in case one breaks my rules."
    )
    ledger.step("Wardrobe Recommender", "start", f"Reading {len(closet)} closet item(s), your profile and your week")
    out = run_agent(ledger, "Wardrobe Recommender", instructions("recommender"), content,
                    schema=GAPS_SCHEMA, schema_name="gaps", effort="low").output
    known = {i["id"] for i in closet}
    by_id = {i["id"]: i for i in closet}
    # her no's are hard rules: a banned piece is replaced by the next backup, never shown
    bans = outfit_rules.bans(prof)
    orchestrator.note_bans(ledger, bans)
    carry = outfit_rules.carry_rules(prof, closet)
    where = places(dataset, today) if carry else {}
    ok = []
    for gap in out["gaps"]:
        why = outfit_rules.ban_reason(gap, bans)
        if why:
            orchestrator.blocked(ledger, out, [(gap["piece"], why)], "recommendation replaced by a backup")
        else:
            ok.append(gap)
    out["gaps"] = ok
    dropped = [g for gap in out["gaps"] for g in gap["pairs_with_ids"] if g not in known]
    if dropped:
        ledger.safety("grounding", "Wardrobe Recommender", f"Removed {len(dropped)} closet id(s) that don't exist.", dropped)
    for gap in out["gaps"]:
        gap["pairs_with"] = [{"id": g, "name": by_id[g]["name"], "hex": (by_id[g].get("colors") or [{}])[0].get("hex", "#ccc")}
                             for g in gap["pairs_with_ids"] if g in known]
        gap["pairs_with_ids"] = [g for g in gap["pairs_with_ids"] if g in known]
        gap["outfit_ids"] = [g for g in gap.get("outfit_ids") or [] if g in known]
        gone = [g for g in gap["outfit_ids"] if outfit_rules.banned(by_id[g], bans)]
        if gone:
            orchestrator.blocked(ledger, out, [(by_id[g]["name"], outfit_rules.ban_reason(by_id[g], bans)) for g in gone],
                                 f"taken out of the outfit for '{gap['piece']}'")
            gap["outfit_ids"] = [g for g in gap["outfit_ids"] if g not in gone]
        # same backstop as the day plan: a jeans outfit for a "polished recruiting" look loses the casual pieces
        bad = outfit_rules.problems([by_id[g] for g in gap["outfit_ids"]], [look])
        if any(p.startswith("too casual") for p in bad):
            casual = {g for g in gap["outfit_ids"] if outfit_rules.CASUAL_PIECE.search(f"{by_id[g].get('subtype') or ''} {by_id[g]['name']}")
                      or by_id[g].get("category") == "activewear"}
            ledger.step("Orchestrator", "check", f"Took casual pieces out of '{gap.get('outfit_title')}' for the look '{look}'",
                        [by_id[g]["name"] for g in casual])
            gap["outfit_ids"] = [g for g in gap["outfit_ids"] if g not in casual]
        # her house rule on bags (backpack to school): a school look gets that bag, in code
        gap["outfit_ids"], swaps = outfit_rules.apply_carry(gap["outfit_ids"], with_place(gap.get("events"), where), carry, by_id)
        if swaps:
            orchestrator.blocked(ledger, out, [(bag, rule["why"]) for bag, _ev, rule in swaps],
                                 f"replaced with your {swaps[0][2]['name']} for '{swaps[0][1]}'")
        gap["outfit"] = [{"id": g, "name": by_id[g]["name"]} for g in gap["outfit_ids"]]
    out["gaps"] = out["gaps"][:3]
    result_look = look
    ledger.step("Wardrobe Recommender", "done", f"{len(out['gaps'])} gap(s): " + "; ".join(g["piece"] for g in out["gaps"]))
    result = {"recommendations": out, "closet_size": len(closet), "shop": None, "look": result_look,
              "blocked": out.pop("blocked", [])}
    if shop and out["gaps"]:
        live = dataset == "user"
        # Shop the top gap; if nothing verifiable turns up, try the next one (at most two, to stay in budget).
        for i, gap in enumerate(out["gaps"][:2]):
            ledger.step("Orchestrator", "handoff", f"Shopping gap #{i + 1}: {gap['search_request']} ({'live web' if live else 'sample catalog'})")
            found = orchestrator.run_shop(ledger, dataset, gap["search_request"], live)
            result["shop"] = found | {"for_gap": i, "live_web": live}
            if (found.get("picks") or {}).get("picks"):
                break
    return result
