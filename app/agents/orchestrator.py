"""Who hands work to whom.

Plan my day:  Day Planner -> code checks -> Style Critic -> (revise, at most twice) -> you
Shop:         Shopping Scout -> code checks -> Fit Tailor -> Style Critic -> (re-scout once) -> you
Add to closet: Closet Cataloger -> you confirm -> closet
"""

from __future__ import annotations

import re

from .. import config, memory, outfit_rules, safety, store, stylists
from ..ledger import Ledger
from ..tools import weather
from . import critic, planner, scout, tailor
from .common import closet_brief, profile_brief


def run_plan_day(ledger: Ledger, dataset: str, day: str) -> dict:
    closet = planner.wearable(dataset)
    prof = store.profile(dataset)
    if not closet:
        raise ValueError("Your closet is empty. Add a few items first (Closet tab).")
    events, _source = store.day_events(dataset, day)
    wx = weather.forecast(prof.get("lat", 41.31), prof.get("lon", -72.93), day)
    bans = outfit_rules.bans(prof)
    note_bans(ledger, bans)

    plan, review, feedback, best = None, None, None, None
    for round_no in range(config.MAX_CRITIC_ROUNDS + 1):
        plan = planner.plan_day(ledger, dataset, day, feedback, plan)
        _check_alternates(ledger, dataset, day, plan, closet, bans)
        flags, grounded = [], True
        for b in plan["blocks"]:
            bad = safety.unknown_item_ids(b["item_ids"], closet)
            if bad:
                flags.append(f"Block '{b['label']}' uses item ids that are not in the closet: {bad}")
                grounded = False
        if flags:
            ledger.safety("grounding", "Day Planner", "Plan used clothes that are not in the closet; sent back.", flags)
        rules = memory.rule_flags(dataset, day, plan["blocks"])
        by_id = {i["id"]: i for i in closet}
        for b in plan["blocks"]:
            for p in outfit_rules.problems([by_id[i] for i in b["item_ids"] if i in by_id], b.get("events") or []):
                rules.append(f"Block '{b['label']}': {p}.")
            for i in b["item_ids"]:
                why = outfit_rules.ban_reason(by_id[i], bans) if i in by_id else ""
                if why:
                    rules.append(f"Block '{b['label']}' uses {by_id[i]['name']}, which they ruled out ({why}). Use another piece.")
        pf = outfit_rules.palette_flag(prof, closet, plan["blocks"])
        if pf:
            rules.append(f"Color: {pf}.")
        if rules:
            ledger.step("Orchestrator", "check", "No-repeat rules broken; sent back to the planner.", rules)
            flags += rules
        context = (
            f"CLOSET:\n{closet_brief(closet)}\n\nUSER:\n{profile_brief(prof, include_body=False)}\n\n"
            f"{stylists.point_of_view(prof, dataset)}\n\nCALENDAR {day}: {events}\n\nWEATHER: {wx}"
        )
        # medium: at low effort the critic flip-flopped between rounds (parka "excessive", then "not warm enough")
        review = critic.critique(ledger, "day plan", plan, context, flags, effort="medium")
        # a revision can come back worse: keep the round the critic scored highest (failed code checks never win,
        # and a plan with clothes she doesn't own loses to any plan without them)
        score = (grounded, review["verdict"] == "approve", not flags, sum((review.get("scores") or {}).values()))
        if best is None or score > best[0]:
            best = (score, plan, review)
        if review["verdict"] == "approve":
            break
        feedback = review["issues"]
        if round_no == config.MAX_CRITIC_ROUNDS:
            ledger.step("Orchestrator", "stop", f"Critic still wants changes after {config.MAX_CRITIC_ROUNDS} revisions; showing the highest-scored plan with the critic's notes.")
    _, plan, review = best
    # last line of defense: if every round broke a ban, the banned piece is taken out rather than shown
    by_id = {i["id"]: i for i in closet}
    for b in plan["blocks"]:
        out = [i for i in b["item_ids"] if i in by_id and outfit_rules.banned(by_id[i], bans)]
        if out:
            blocked(ledger, plan, [(by_id[i]["name"], outfit_rules.ban_reason(by_id[i], bans)) for i in out], f"taken out of '{b['label']}'")
            b["item_ids"] = [i for i in b["item_ids"] if i not in out]
    # her house rule on bags (backpack to school): every school look carries that bag, whatever the model picked
    carry = outfit_rules.carry_rules(prof, closet)
    where = {e["title"]: e.get("location") or "" for e in events}
    for b in plan["blocks"]:
        evs = [e + next((f" @ {loc}" for t, loc in where.items() if loc and t in e), "") for e in b.get("events") or []]
        for look in [b] + (b.get("alternates") or []):
            look["item_ids"], swaps = outfit_rules.apply_carry(look["item_ids"], evs, carry, by_id)
            if swaps and look is b:
                blocked(ledger, plan, [(bag, rule["why"]) for bag, _ev, rule in swaps],
                        f"replaced with your {swaps[0][2]['name']} for '{swaps[0][1]}'")
    # the critic's veto on extras: an option it wouldn't send her out in is never shown
    drop = {t.strip().lower() for t in review.get("drop_alternates") or []}
    for b in plan["blocks"]:
        gone = [a for a in b.get("alternates") or [] if a.get("title", "").strip().lower() in drop]
        if gone:
            ledger.step("Style Critic", "check", f"Vetoed for '{b['label']}': " + ", ".join(a["title"] for a in gone))
            b["alternates"] = [a for a in b["alternates"] if a not in gone]
        b["alternates"] = (b.get("alternates") or [])[:2]

    by_id = {i["id"]: i for i in closet}
    for b in plan["blocks"]:
        b["items"] = [by_id[i] for i in b["item_ids"] if i in by_id]
        for alt in b.get("alternates") or []:
            alt["items"] = [by_id[i] for i in alt["item_ids"] if i in by_id]
    result = {"plan": plan, "review": review, "weather": wx, "events": events, "blocked": plan.pop("blocked", [])}
    memory.save_plan(dataset, day, result)
    return result


def note_bans(ledger: Ledger, bans: list[dict]) -> None:
    """Show in the trace which of her no's every look is checked against."""
    if bans:
        ledger.step("Orchestrator", "check", f"Taste bans checked in code ({len(bans)}): " + "; ".join(b["label"] for b in bans[:6]),
                    [f"{b['label']}: {b['why']}" for b in bans])


def blocked(ledger: Ledger, result: dict, hits: list[tuple[str, str]], what: str) -> None:
    """Log a piece a ban stopped, and keep it on the result so the stylist can say she listened."""
    for name, why in hits:
        ledger.step("Orchestrator", "blocked", f"Blocked {name}: {what}", why)
        result.setdefault("blocked", []).append({"piece": name, "why": why, "what": what})


def _check_alternates(ledger: Ledger, dataset: str, day: str, plan: dict, closet: list[dict], bans=()) -> None:
    """Alternates are extras: one with an unknown piece, a resting or repeated outfit, or the same clothes as the
    main pick is dropped quietly (logged) rather than sending the whole plan back."""
    by_id = {i["id"]: i for i in closet}
    for b in plan["blocks"]:
        keep = []
        for alt in b.get("alternates") or []:
            alt["item_ids"] = [i for i in alt.get("item_ids", []) if i in by_id]
            same = set(alt["item_ids"]) == set(b["item_ids"]) or any(set(alt["item_ids"]) == set(k["item_ids"]) for k in keep)
            broken = memory.rule_flags(dataset, day, [{"label": b["label"], "item_ids": alt["item_ids"]}])
            broken += outfit_rules.problems([by_id[i] for i in alt["item_ids"]], b.get("events") or [])
            broken += [f"{by_id[i]['name']} is ruled out ({outfit_rules.ban_reason(by_id[i], bans)})"
                       for i in alt["item_ids"] if outfit_rules.banned(by_id[i], bans)]
            if len(alt["item_ids"]) < 2 or same or broken:
                ledger.step("Orchestrator", "check", f"Dropped alternate '{alt.get('title')}' for '{b['label']}'",
                            broken or ["incomplete or same as another option"])
                continue
            keep.append(alt)
        b["alternates"] = keep  # trimmed to 2 after the critic's veto


def run_shop(ledger: Ledger, dataset: str, request: str, live_web: bool) -> dict:
    prof = store.profile(dataset)
    closet = store.closet(dataset)
    picks = fits = review = None
    best = None  # last round that produced reviewed picks, kept if a retry comes back empty
    request_now = request
    searched: list[str] = []
    pool, pool_fits = [], []  # live web: picks from both rounds add up (real stores rarely give 3 at once)
    bans = outfit_rules.bans(prof)
    note_bans(ledger, bans)
    stopped: dict = {}
    hit = outfit_rules.banned(request, bans)
    if hit:
        # the request itself breaks one of her no's: every find would be thrown out, so don't pay to search
        blocked(ledger, stopped, [(request, outfit_rules.ban_reason(request, bans))], "search skipped")
        take = (f"You told me never {hit[0]['label']}, so I didn't search for that (no charge). Ask me for a version "
                "that fits your rules, or change the rule in the Me tab.")
        return {"picks": {"picks": [], "stylist_take": take, "note": ""}, "fits": None, "review": None, "searches": [],
                "blocked": stopped["blocked"]}
    link_drops = 0
    for round_no in range(2):
        picks, allowed, searches = scout.scout(ledger, dataset, request_now, live_web)
        searched += [q for q in searches if q]
        flags = []
        # Every product must come from the search results; drop anything the model made up.
        kept = []
        for p in picks["picks"]:
            ref = p["product_id"] if not live_web else p["url"]
            if live_web:
                # No citations means nothing can be verified, so every link is dropped.
                bad = safety.ungrounded_links([p["url"]], allowed) if allowed else [p["url"]]
            else:
                bad = [] if p["product_id"] in allowed else [p["product_id"]]
            if bad:
                flags.append(f"Dropped '{p['name']}': its link/id ({ref}) was not in the search results.")
                link_drops += 1
                continue
            if outfit_rules.banned(p, bans):
                blocked(ledger, stopped, [(f"{p.get('store', '')} {p['name']}".strip(), outfit_rules.ban_reason(p, bans))], "shop pick dropped")
                continue
            if live_web and UNSURE_SIZE.search(p.get("confirmed_sizes") or ""):
                # "18 not confirmed" is not a confirmation: show it as a plain size note, not a green ✓
                p["sizes_note"] = f"Size not confirmed: {p['confirmed_sizes']}" + (f" · {p['sizes_note']}" if p.get("sizes_note") else "")
                p["confirmed_sizes"] = ""
            kept.append(p)
        if flags:
            ledger.safety("grounding", "Shopping Scout", "Removed picks that did not come from search results.", flags)
        picks["picks"] = kept
        if not kept and round_no == 0:
            # an empty first search usually means the query was too narrow: try once more, broader
            ledger.step("Orchestrator", "retry", "No usable picks; searching again more broadly.")
            request_now = (f"{request}. The first search found nothing usable. Broaden it: try other retailers (department "
                           "stores, brands with extended sizes, resale), similar styles and close colors from my palette, "
                           "but keep my size.")
            continue
        if not kept:
            if best:
                ledger.step("Orchestrator", "fallback", "Retry found nothing better; showing the first picks with the critic's notes.")
                picks, fits, review = best
            else:
                review = {"verdict": "revise", "issues": flags or ["No products matched."], "scores": {},
                          "user_note": "I couldn't find anything good enough that I could verify."}
            break

        fits = tailor.try_on(ledger, dataset, kept, live_web)
        if live_web:
            seen = {safety_norm(p["url"]) for p in pool}
            new = [p for p in kept if safety_norm(p["url"]) not in seen]
            pool = new + pool  # newest round first: a retry answers the critic, so its picks lead
            pool_fits += [f for f in fits["fits"] if f.get("product_ref") in {p["url"] for p in new}]
        context = (
            f"USER:\n{profile_brief(prof, include_body=False)}\n\nCLOSET (for pairing):\n{closet_brief(closet)}\n\n"
            f"{stylists.point_of_view(prof, dataset)}\n\nREQUEST: {request}"
        )
        review = critic.critique(ledger, "shopping picks", {"picks": kept, "fits": fits["fits"]}, context, [])
        best = (picks, fits, review)
        # a "revise" gets one more search even with 3 picks in hand (~$0.04 more), so the critic's notes are acted on
        if review["verdict"] == "approve" or round_no == 1:
            break
        have = f" I already have: {'; '.join(p['store'] + ' ' + p['name'] for p in pool)}. Find different products that fix those problems (other stores welcome)." if live_web and pool else ""
        request_now = f"{request}. Avoid these problems from last time: {'; '.join(review['issues'])}.{have}"

    if live_web and len(pool) > len((picks or {}).get("picks") or []):
        ledger.step("Orchestrator", "merge", f"Showing {min(len(pool), 3)} pick(s) from both searches, newest first, each with the critic's notes.")
        picks = {**(picks or {}), "picks": pool[:3]}
        fits = {"fits": pool_fits}

    if picks and not live_web:
        by_id = {p["id"]: p for p in store.catalog()}
        for p in picks["picks"]:
            src = by_id.get(p["product_id"], {})
            p["toe_box"] = src.get("toe_box")
            p["heel_in"] = src.get("heel_in")
            p["fit"] = src.get("fit")
            p["length"] = src.get("length")
    if picks and not picks.get("picks"):
        # her note was written before the checks; never let it praise a pick that isn't shown
        if link_drops:
            picks["stylist_take"] = ("I couldn't verify a link I'd stand behind, so I'm not showing what I found. "
                                     "Try Search more broadly and I'll look again.")
            picks["note"] = "The product links I found weren't among the pages the search actually returned, so I left them out."
        else:
            picks["stylist_take"] = "Nothing I found was good enough to show you yet. Try Search more broadly and I'll look again."
    return {"picks": picks, "fits": fits, "review": review, "searches": searched[:10], "blocked": stopped.get("blocked", [])}


UNSURE_SIZE = re.compile(r"\bnot\b.{0,30}\bconfirm|\bunconfirmed\b|\bunknown\b|\bunclear\b|\bcan(?:no|')t (?:confirm|verify)", re.I)


def safety_norm(url: str) -> str:
    """Same normalization the grounding check uses (no query string, no trailing slash, lower case)."""
    import re
    return re.sub(r"[?#].*$", "", (url or "").strip().rstrip("/")).lower()
