"""Wardrobe memory: what you wore, how it went, what you sent back, and the rules that follow.

Everything the stylist learns lives in memory.json per dataset:
  wear_log  one entry per outfit you gave feedback on (wore it, banger, compliments, comfy, ...)
  plans     the last plan made for each day, so Today can show it again without paying
  returns   items sent back, with the reason
  brand_fit per-brand sizing lessons ("J.Crew bottoms run small on you: size up")

Code, not the model, enforces the no-repeat rules: the planner is told what is resting, and any
block that breaks the rules is sent back to it like an ungrounded item id.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from . import body_model, safety, store
from .agents.common import section

TAGS = {
    # tag: (item score change, counts as worn)
    "wore_it": (0.5, True),
    "banger": (3.0, True),
    "compliments": (3.0, True),
    "comfy": (2.0, True),
    "not_me": (-3.0, False),
    "uncomfortable": (-3.0, True),
    "too_warm": (0.0, True),
    "too_cold": (0.0, True),
}
RETURN_REASONS = {
    "too_small": "ran small", "too_big": "ran big", "wrong_length": "was the wrong length",
    "uncomfortable": "was uncomfortable", "color": "was the wrong color", "quality": "had poor quality",
    "not_my_style": "wasn't your style",
}
OUTFIT_GAP_DAYS = 14      # the same full outfit comes back at most every 14 days
STATEMENT_REST_DAYS = 7   # statement pieces rest a week after you wear them
NEUTRALS = {"white", "ivory", "cream", "black", "navy", "grey", "gray", "charcoal", "beige", "camel", "tan",
            "brown", "khaki", "denim", "blue", "light blue", "chambray", "oatmeal", "taupe", "stone"}


def _load(dataset: str) -> dict:
    m = store._read(dataset, "memory.json", {})
    for k, v in (("wear_log", []), ("plans", {}), ("returns", []), ("brand_fit", {}), ("learned", [])):
        m.setdefault(k, v)
    return m


def _save(dataset: str, m: dict) -> None:
    m["plans"] = dict(sorted(m["plans"].items())[-30:])
    m["wear_log"] = m["wear_log"][-500:]
    m["learned"] = m["learned"][-40:]
    store._write(dataset, "memory.json", m)


def _day(d: str) -> date:
    return date.fromisoformat(d[:10])


def is_statement(item: dict) -> bool:
    """Prints, dresses and bright colors are memorable; basics, shoes and coats can repeat freely."""
    if item.get("category") in ("shoes", "outerwear", "accessory", "activewear"):
        return False
    if item.get("pattern") not in (None, "", "solid"):
        return True
    if item.get("category") == "dress":
        return True
    colors = {c.get("name", "").lower() for c in item.get("colors", [])}
    return bool(colors) and not colors <= NEUTRALS


def outfit_key(item_ids, closet_by_id: dict) -> str:
    """The 'full outfit' is the clothes, not the shoes, coat or bag that go with everything."""
    core = [i for i in item_ids if closet_by_id.get(i, {}).get("category") not in ("shoes", "outerwear", "accessory")]
    return "|".join(sorted(core or item_ids))


# ---------------------------------------------------------------- plans
def save_plan(dataset: str, day: str, result: dict) -> None:
    m = _load(dataset)
    m["plans"][day] = result
    _save(dataset, m)


def saved_plan(dataset: str, day: str):
    return _load(dataset)["plans"].get(day)


# ---------------------------------------------------------------- same inputs, same pick
# A stylist doesn't change their mind on a refresh. Each saved plan / recommendation keeps a fingerprint of what
# it was made from; asking again with the same closet, calendar, weather and feedback returns it (no model call).
INPUT_NAMES = {"closet": "your closet", "events": "your calendar", "weather": "the forecast", "feedback": "your feedback",
               "style": "your style settings", "look": "the look you asked for", "week": "your week ahead",
               "bans": "what you've ruled out"}


def _digest(v) -> str:
    import hashlib
    return hashlib.sha256(json.dumps(v, sort_keys=True, default=str).encode()).hexdigest()[:12]


def fingerprint(dataset: str, day: str, events=None, wx=None, look=None, week=None) -> dict:
    prof = store.profile(dataset)
    closet = [(i["id"], i.get("name"), i.get("category"), i.get("subtype"), [c.get("name") for c in i.get("colors") or []],
               i.get("out_of_season"), i.get("status")) for i in store.closet(dataset)]
    parts = {"closet": _digest(closet), "feedback": _digest(brief(dataset, day)),
             "style": _digest([prof.get(k) for k in ("style", "stylist", "color_season", "archetype", "comfort", "feedback", "aesthetic")]),
             # her no's as the code checks them: a new ban (or a sharper check) means a new pick
             "bans": _digest(_ban_inputs(prof))}
    if events is not None:
        parts["events"] = _digest([(e.get("start"), e.get("title")) for e in events])
    if wx is not None:  # 5 °F buckets: a forecast nudged by a degree isn't a new day
        parts["weather"] = _digest([round((wx.get(k) or 0) / 5) for k in ("high_f", "low_f")] + [wx.get("summary"), round((wx.get("rain_chance_pct") or 0) / 25)])
    if look is not None:
        parts["look"] = _digest(look.strip().lower())
    if week is not None:
        parts["week"] = _digest(week)
    return parts


def _ban_inputs(prof: dict) -> list:
    from . import outfit_rules  # outfit_rules imports this module
    # the bag house rule is checked in code too (backpack to school), so it is part of what makes picks stale
    rules = [r for r in (prof.get("stylist") or {}).get("extra_rules") or [] if outfit_rules.SCHOOL_WORD.search(r)]
    return [outfit_rules.bans(prof), outfit_rules.CONCEPTS, outfit_rules.TYPES, rules, outfit_rules.SCHOOL_EVENT.pattern]


def changed(old: dict | None, new: dict) -> list[str]:
    """What's different since last time, in her words (empty: nothing changed)."""
    if not old:
        return []
    return [INPUT_NAMES[k] for k in new if old.get(k) != new[k]]


def tag_plan(dataset: str, day: str, inputs: dict) -> None:
    m = _load(dataset)
    if day in m["plans"]:
        m["plans"][day]["inputs"] = inputs
        _save(dataset, m)


def saved_recs(dataset: str):
    """The last recommendations; a piece she has ruled out since is never shown again (a fresh run replaces it)."""
    from . import outfit_rules
    recs = _load(dataset).get("recs")
    gaps = ((recs or {}).get("result") or {}).get("recommendations", {}).get("gaps")
    if gaps:
        bans = outfit_rules.bans(store.profile(dataset))
        out = [{"piece": g["piece"], "why": outfit_rules.ban_reason(g, bans), "what": "hidden from saved picks"}
               for g in gaps if outfit_rules.banned(g, bans)]
        if out:
            recs["result"]["recommendations"]["gaps"] = [g for g in gaps if not outfit_rules.banned(g, bans)]
            recs["result"]["blocked"] = out
    return recs


def save_recs(dataset: str, recs: dict) -> None:
    m = _load(dataset)
    m["recs"] = recs
    _save(dataset, m)


def replace_block(dataset: str, day: str, index: int, block: dict) -> None:
    m = _load(dataset)
    plan = m["plans"].get(day)
    if plan and 0 <= index < len(plan["plan"]["blocks"]):
        plan["plan"]["blocks"][index] = block
        _save(dataset, m)


# ---------------------------------------------------------------- what the stylist knows
def wear_stats(dataset: str, today: str | None = None) -> dict:
    today_d = _day(today) if today else date.today()
    by_id = {i["id"]: i for i in store.closet(dataset)}
    stats = {}
    for e in _load(dataset)["wear_log"]:
        for iid in e["item_ids"]:
            s = stats.setdefault(iid, {"wears": 0, "last_worn": None, "score": 0.0, "resting_until": None})
            worn = any(TAGS.get(t, (0, False))[1] for t in e["tags"])
            s["score"] += sum(TAGS.get(t, (0, False))[0] for t in e["tags"])
            if worn:
                s["wears"] += 1
                if not s["last_worn"] or e["day"] > s["last_worn"]:
                    s["last_worn"] = e["day"]
    for iid, s in stats.items():
        s["score"] = round(s["score"], 1)
        if s["last_worn"] and is_statement(by_id.get(iid, {})):
            until = _day(s["last_worn"]) + timedelta(days=STATEMENT_REST_DAYS)
            s["resting_until"] = until.isoformat() if until > today_d else None
    return stats


def recent_outfits(dataset: str, day: str) -> list[str]:
    """Outfit keys worn in the last OUTFIT_GAP_DAYS days (not counting the day itself)."""
    by_id = {i["id"]: i for i in store.closet(dataset)}
    start = _day(day) - timedelta(days=OUTFIT_GAP_DAYS)
    keys = []
    for e in _load(dataset)["wear_log"]:
        worn = any(TAGS.get(t, (0, False))[1] for t in e["tags"])
        if worn and start <= _day(e["day"]) < _day(day):
            keys.append(outfit_key(e["item_ids"], by_id))
    return keys


def brief(dataset: str, day: str) -> str:
    """Text the Day Planner gets: resting pieces, outfits not to repeat, formulas you loved, what to avoid."""
    m = _load(dataset)
    by_id = {i["id"]: i for i in store.closet(dataset)}
    name = lambda iid: by_id.get(iid, {}).get("name", iid)
    stats = wear_stats(dataset, day)
    resting = [f"{iid} ({name(iid)}, until {s['resting_until']})" for iid, s in stats.items() if s["resting_until"]]
    repeats = sorted(set(recent_outfits(dataset, day)))
    loved, avoid, comfort, temp = [], [], [], []
    for e in m["wear_log"][-60:]:
        items = " + ".join(name(i) for i in e["item_ids"])
        tags = set(e["tags"])
        if tags & {"banger", "compliments"}:
            loved.append(f"{items}" + (" (got compliments)" if "compliments" in tags else "") + (f": {e['note']}" if e.get("note") else ""))
        if "not_me" in tags:
            avoid.append(f"{items}" + (f": {e['note']}" if e.get("note") else ""))
        if "comfy" in tags:
            comfort.append(f"comfy: {items}")
        if "uncomfortable" in tags:
            comfort.append(f"UNCOMFORTABLE (avoid for long days): {items}" + (f": {e['note']}" if e.get("note") else ""))
        if tags & {"too_warm", "too_cold"}:
            temp.append(f"{items} was {'too warm' if 'too_warm' in tags else 'too cold'} on {e['day']}" + (f" ({e['weather']})" if e.get("weather") else ""))
    lines = ["WHAT I'VE LEARNED ABOUT YOU (from your feedback; follow it):"]
    if resting:
        lines.append("Resting, do not use today: " + "; ".join(resting))
    if repeats:
        lines.append(f"Worn in the last {OUTFIT_GAP_DAYS} days, do not repeat these exact outfits (clothes only; shoes and coats may repeat): " + "; ".join(repeats))
    if loved:
        lines.append("Bangers to echo (reuse the formula, colors or silhouette with other pieces; repeat the outfit itself once 14 days have passed): " + "; ".join(loved[-8:]))
    if avoid:
        lines.append("Not her, never suggest again: " + "; ".join(avoid[-8:]))
    if comfort:
        lines.append("Comfort: " + "; ".join(comfort[-8:]))
    if temp:
        lines.append("Temperature lessons: " + "; ".join(temp[-6:]))
    top = sorted(((s["score"], iid) for iid, s in stats.items() if s["score"] >= 3), reverse=True)[:6]
    if top:
        lines.append("Favorite pieces: " + ", ".join(name(i) for _, i in top))
    rarely = [i for i in by_id if i not in stats and by_id[i].get("status") != "returned"][:8]
    if rarely and len(stats) >= 5:
        lines.append("Never worn yet, give them a chance when they fit the day: " + ", ".join(name(i) for i in rarely))
    if m["brand_fit"]:
        lines.append("Brand sizing: " + "; ".join(f"{b}: {v['note']}" for b, v in m["brand_fit"].items()))
    return "\n".join(lines) if len(lines) > 1 else ""


def rule_flags(dataset: str, day: str, blocks: list[dict]) -> list[str]:
    """Code check after the planner: resting pieces, repeated outfits and returned items go back to it."""
    by_id = {i["id"]: i for i in store.closet(dataset)}
    stats = wear_stats(dataset, day)
    repeats = set(recent_outfits(dataset, day))
    flags = []
    for b in blocks:
        for iid in b.get("item_ids", []):
            if stats.get(iid, {}).get("resting_until"):
                flags.append(f"Block '{b['label']}' uses {by_id.get(iid, {}).get('name', iid)}, which is resting until {stats[iid]['resting_until']} (worn recently).")
            if by_id.get(iid, {}).get("status") == "returned":
                flags.append(f"Block '{b['label']}' uses {by_id[iid]['name']}, which was returned.")
        if outfit_key(b.get("item_ids", []), by_id) in repeats:
            flags.append(f"Block '{b['label']}' repeats an outfit worn in the last {OUTFIT_GAP_DAYS} days; change at least one main piece.")
    return flags


# ---------------------------------------------------------------- feedback
def record_feedback(dataset: str, day: str, block_label: str, item_ids: list[str], tags: list[str], note: str = "", weather: str = "") -> list[str]:
    tags = [t for t in tags if t in TAGS]
    if not tags:
        raise ValueError("Pick at least one: wore it, banger, compliments, comfy, not me, uncomfortable, too warm, too cold.")
    by_id = {i["id"]: i for i in store.closet(dataset)}
    item_ids = [str(i)[:80] for i in item_ids[:10] if str(i) in by_id]
    note, _ = safety.clean_untrusted(note or "", 200)
    label, _ = safety.clean_untrusted(block_label or "", 80)
    m = _load(dataset)
    # one entry per day + block: tapping again updates it instead of double counting
    m["wear_log"] = [e for e in m["wear_log"] if not (e["day"] == day and e["block_label"] == label)]
    m["wear_log"].append({"day": day, "block_label": label, "item_ids": item_ids, "tags": tags, "note": note,
                          "weather": weather[:80], "at": datetime.now(timezone.utc).isoformat()})
    core = [i for i in item_ids if by_id[i].get("category") not in ("shoes", "outerwear", "accessory")] or item_ids
    names = " + ".join(by_id[i]["name"] for i in core) or "that outfit"
    learned = []
    if "compliments" in tags:
        learned.append(f"Compliments noted: {names} is a keeper. I'll bring it back after {OUTFIT_GAP_DAYS} days and build more looks on that formula.")
    elif "banger" in tags:
        learned.append(f"Banger noted: I'll echo {names}'s colors and silhouette in new looks.")
    if "comfy" in tags:
        learned.append(f"Comfort win: I'll lean on these pieces for long days.")
    if "not_me" in tags:
        learned.append(f"Got it, {names} isn't you. I won't suggest that combination again.")
    if "uncomfortable" in tags:
        learned.append("Noted as uncomfortable: I'll keep those pieces off long, walking-heavy days" + (f" ({note})" if note else "") + ".")
    if "too_warm" in tags or "too_cold" in tags:
        learned.append(f"I'll dress you {'lighter' if 'too_warm' in tags else 'warmer'} in similar weather.")
    if tags == ["wore_it"]:
        learned.append(f"Logged. {names} will rest so you don't repeat it too soon.")
    rest = [by_id[i]["name"] for i in item_ids if is_statement(by_id[i]) and any(TAGS[t][1] for t in tags)]
    if rest:
        learned.append(f"Resting for a week: {', '.join(rest)}.")
    m["learned"] += learned
    _save(dataset, m)
    return learned


def pending_checkin(dataset: str, today: str | None = None):
    """The most recent planned outfit from the last 3 days that you haven't told me about yet."""
    today_d = _day(today) if today else date.today()
    m = _load(dataset)
    told = {(e["day"], e["block_label"]) for e in m["wear_log"]}
    for back in (1, 2, 3):
        d = (today_d - timedelta(days=back)).isoformat()
        plan = m["plans"].get(d)
        if not plan:
            continue
        for b in plan["plan"]["blocks"]:
            if b.get("scene") != "gym" and (d, b["label"]) not in told:
                return {"day": d, "block_label": b["label"], "item_ids": b.get("item_ids", [])}
    return None


# ---------------------------------------------------------------- returns
def record_return(dataset: str, item_id: str, reason: str, note: str = "") -> tuple[dict, list[str]]:
    if reason not in RETURN_REASONS:
        raise ValueError(f"reason must be one of {sorted(RETURN_REASONS)}")
    items = store.closet(dataset)
    item = next((i for i in items if i["id"] == item_id), None)
    if not item:
        raise ValueError("That item isn't in the closet.")
    note, _ = safety.clean_untrusted(note or "", 200)
    item.update(status="returned", returned_at=date.today().isoformat(), return_reason=reason, return_note=note)
    store.save_closet(dataset, items)
    m = _load(dataset)
    m["returns"].append({"item_id": item_id, "name": item["name"], "brand": item.get("brand"), "reason": reason,
                         "note": note, "size_label": item.get("size_label"), "at": date.today().isoformat()})
    learned = [f"Returned: {item['name']} {RETURN_REASONS[reason]}."]
    brand = (item.get("brand") or "").strip()
    if brand and reason in ("too_small", "too_big"):
        bf = m["brand_fit"].setdefault(brand, {"shift": 0, "note": ""})
        bf["shift"] += 1 if reason == "too_small" else -1
        bf["note"] = ("runs small on you: size up" if bf["shift"] > 0 else "runs big on you: size down" if bf["shift"] < 0 else "true to size")
        learned.append(f"{brand} {bf['note']}. The shopper will use that.")
    prof = store.profile(dataset)
    if item.get("size_label") and reason in ("too_small", "too_big"):
        # a return for size is fit evidence too: it sharpens your measurement estimate
        implied = body_model.evidence(item, item["size_label"], "tight" if reason == "too_small" else "loose")
        if implied:
            prof.setdefault("fit_evidence", []).append({"item_id": item_id, "size_label": item["size_label"],
                                                        "fit": "tight" if reason == "too_small" else "loose", "implied": implied})
            body_model.refine(prof)
            learned.append("Your measurement estimate was updated from this return.")
    if reason in ("color", "quality", "not_my_style", "uncomfortable"):
        fb = prof.setdefault("feedback", [])
        fb.append({"kind": "product", "rating": "no", "item_ids": [item_id], "label": item["name"],
                   "note": f"returned: {RETURN_REASONS[reason]}" + (f" ({note})" if note else ""), "at": date.today().isoformat()})
        learned.append("I'll steer away from things like it.")
    store.save_profile(dataset, prof)
    m["learned"] += learned
    _save(dataset, m)
    return item, learned


def shopping_brief(dataset: str) -> str:
    """For the Shopping Scout: brand sizing lessons and what came back."""
    m = _load(dataset)
    lines = []
    if m["brand_fit"]:
        lines.append("Brand sizing lessons: " + "; ".join(f"{b} {v['note']}" for b, v in m["brand_fit"].items()))
    if m["returns"]:
        lines.append("Returned before (avoid the same problem): " + "; ".join(f"{r['name']} ({RETURN_REASONS[r['reason']]})" for r in m["returns"][-8:]))
    return "\n".join(lines)


def summary(dataset: str, today: str | None = None) -> dict:
    m = _load(dataset)
    return {"wear": wear_stats(dataset, today), "pending_checkin": pending_checkin(dataset, today),
            "learned": m["learned"][-12:], "brand_fit": {b: v["note"] for b, v in m["brand_fit"].items()},
            "returns": m["returns"][-20:]}


def with_size_guesses(dataset: str, items: list[dict]) -> list[dict]:
    """Add size_guess (not saved) to each item: your likely size from measurements + brand lessons."""
    prof, m = store.profile(dataset), _load(dataset)
    for it in items:
        shift = m["brand_fit"].get((it.get("brand") or "").strip(), {}).get("shift", 0)
        it["size_guess"] = body_model.guess_size(prof, it, shift)
        it["section"] = section(it)
        # version stamp for image URLs: a turned or re-cut photo gets a new URL, so no browser shows a stale copy
        path = store.image_path(dataset, it.get("shot") or it.get("cutout") or it.get("image") or "")
        if path:
            it["v"] = int(path.stat().st_mtime)
    return items
