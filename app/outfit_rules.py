"""Hard style rules checked in code after the Day Planner, so a clash can't reach her however the model words it.

The planner and critic are told these rules too; this is the backstop. A main outfit that breaks one goes back
to the planner; an alternate that breaks one is dropped.
"""

from __future__ import annotations

import re

from .memory import NEUTRALS

NEUTRAL = NEUTRALS | {"dark indigo", "dark brown", "off-white", "silver", "gold", "nude", "white denim"}
BROWNS = ("brown", "tan", "cognac", "camel", "chocolate")
BLACK_WHITE = {"black", "white", "ivory", "cream", "grey", "gray", "charcoal", "off-white"}
# events where she meets recruiters or interviews: business casual at least
POLISHED_EVENT = re.compile(r"interview|coffee chat|\bchat\b|recruit|\bcase\b|network|office hours|info session|"
                            r"mckinsey|bain|bcg|deloitte|goldman|morgan|presentation|client", re.I)
CASUAL_PIECE = re.compile(r"\b(jeans?|denim|shorts?|leggings?|sneakers?|tee|t-shirt|hoodie|sweatshirt|joggers?|bike)\b", re.I)


def _color(item: dict) -> str:
    return ((item.get("colors") or [{}])[0].get("name") or "").lower()


def problems(items: list[dict], events: list[str]) -> list[str]:
    """What a stylist would refuse in this outfit, in plain words (empty if it's fine)."""
    out = []
    # coats come off indoors and shoes/bags are leather-family checks, so only the clothes count for color
    clothes = [i for i in items if i.get("category") in ("top", "bottom", "dress")
               or (i.get("category") == "outerwear" and "blazer" in (i.get("subtype") or "").lower())]
    loud = {}
    for i in clothes:
        c = _color(i)
        if c and c not in NEUTRAL and not any(n in c for n in ("black", "white", "ivory", "cream", "navy", "denim")):
            loud.setdefault(c, i["name"])
    if len(loud) > 1:
        out.append("two statement colors together (" + " with ".join(f"{c} {n}" for c, n in loud.items())
                   + "): pair one colored piece with neutrals")
    shoes = [i for i in items if i.get("category") == "shoes"]
    colors = {_color(i) for i in clothes}
    if shoes and any(b in _color(shoes[0]) for b in BROWNS) and colors and colors <= BLACK_WHITE and "black" in colors:
        out.append(f"brown shoes ({shoes[0]['name']}) under a black-and-white outfit: use black shoes")
    if any(POLISHED_EVENT.search(e or "") for e in events):
        casual = [i["name"] for i in items if i.get("category") == "activewear"
                  or CASUAL_PIECE.search(f"{i.get('subtype') or ''} {i.get('name') or ''}")]
        if casual:
            out.append(f"too casual for recruiting events ({', '.join(casual)}): business casual pieces only")
    return out


# ---- season color: her palette's colors, not just its neutrals ------------------------------------------
PALETTE_DE = 38  # Lab distance that still reads as "that color"; photo colors come out a little darker than the swatch


HUE_GAP = 25  # degrees on the Lab color wheel


def _hue_gap(x, y) -> float:
    import math
    d = abs(math.degrees(math.atan2(x[2], x[1])) - math.degrees(math.atan2(y[2], y[1]))) % 360
    return min(d, 360 - d)


def _lab(hex_: str):
    from .color_measure import rgb_to_lab
    h = (hex_ or "").lstrip("#")
    if len(h) != 6:
        return None
    return rgb_to_lab(tuple(int(h[k:k + 2], 16) for k in (0, 2, 4)))


def season_colors(profile: dict) -> list[tuple[str, tuple]]:
    """The season's best colors that aren't neutrals, as (name, Lab)."""
    from .color_style import SEASONS
    s = SEASONS.get((profile.get("color_season") or {}).get("season"))
    if not s:
        return []
    neutral = {n.lower() for n in s["neutrals"]} | {"black", "white", "icy white", "pure white", "ivory", "cream"}
    return [(n, _lab(h)) for n, h in s["palette"] if n.lower() not in neutral and _lab(h)]


def in_palette(item: dict, palette: list) -> str | None:
    """The palette color this item reads as, if any."""
    for c in item.get("colors") or []:
        lab = _lab(c.get("hex", ""))
        if lab:
            for name, p in palette:
                # close overall AND the same hue: terracotta is near bright red in distance, but it's a warm color
                if sum((a - b) ** 2 for a, b in zip(lab, p)) ** 0.5 <= PALETTE_DE and _hue_gap(lab, p) <= HUE_GAP:
                    return name
    return None


def palette_flag(profile: dict, closet: list[dict], blocks: list[dict]) -> str | None:
    """Every outfit of the day in neutrals only while her closet has pieces in her season's colors: send it back."""
    pal = season_colors(profile)
    if not pal:
        return None
    by_id = {i["id"]: i for i in closet}
    dressed = [b for b in blocks if not all(by_id.get(i, {}).get("category") == "activewear" for i in b["item_ids"])]
    if not dressed or any(in_palette(by_id[i], pal) for b in dressed for i in b["item_ids"] if i in by_id):
        return None
    have = [f"{i['name']} ({in_palette(i, pal)})" for i in closet if in_palette(i, pal)][:5]
    if not have:
        return None
    return ("every outfit today is neutrals only (black/white). Bring one of their season colors into at least one look, "
            "as a piece or an accessory, e.g. " + "; ".join(have))


# ---- taste bans: what she ruled out, as hard checks (the prompt tells the stylist too; this is the backstop) ------
# A ban keeps the nuance of what she said. "Loafers look like men's shoes" rules out loafers that read masculine,
# not every loafer: a slim, soft or pointed feminine loafer still passes. A "Not for me" with no reason rules out
# that one piece only. A reason on its own (a check-in "never" answer, a "Too masculine" tag) applies to every piece.
FEMININE = (r"ballet|slim|pointed|pointy|almond|kitten|heeled|slingback|mary ?jane|bow|feminine|delicate|"
            r"dainty|scalloped|ruched|satin|velvet|metallic|embellished")
CONCEPTS = {
    # key: label, what she might say (reason), hard markers (always out), types that lean that way unless softened
    "masculine": {"label": "anything that reads masculine",
                  "said": r"\bmen'?s\b|\bmens\b|\bman'?s\b|masculine|menswear|manly|like a (?:man|guy|dad)|\bguy'?s\b",
                  "hard": r"\bmen'?s\b|menswear|masculine|unisex|chunky|lug[- ]?sole|brogue|wingtip|monk[- ]strap",
                  "leaning": r"loafers?|oxford shoes?|derby shoes?|boat shoes?",
                  "unless": FEMININE, "fine": "slim, pointed, ballet-style or kitten-heel feminine versions"},
    "business": {"label": "too business / corporate",
                 "said": r"business|corporate|stuffy|boardroom",
                 "hard": r"pinstripe|power suit|briefcase|boardroom|corporate",
                 "unless": FEMININE + r"|suede|patent|colou?rful|playful", "fine": "softer, playful or feminine versions"},
    "boxy": {"label": "shapeless or boxy", "said": r"boxy|shapeless|baggy|frumpy|sack",
             "hard": r"boxy|shapeless|sack|tent|baggy|slouchy|oversized", "unless": r"tailored|fitted|cropped|belted|waisted",
             "fine": "tailored, fitted or belted versions"},
    "short": {"label": "very short or low-cut", "said": r"too short|low[- ]cut|revealing",
              "hard": r"micro|mini ?(?:skirt|dress|shorts?)|low[- ]cut|plunging|deep[- ]v", "unless": "", "fine": ""},
    "itchy": {"label": "itchy or stiff fabrics", "said": r"itchy|scratchy|stiff",
              "hard": r"itchy|scratchy|stiff|rigid|mohair|coarse", "unless": r"soft|brushed|lined", "fine": "soft or lined versions"},
    "walk": {"label": "hard-to-walk-in shoes", "said": r"hard to walk|can'?t walk|painful|hurts?|blisters?",
             "hard": r"stiletto|sky[- ]high|towering|platform heels?|very high heels?|\b[4-6](?:\.\d)?[- ]?(?:inch|in\b|\")",
             "unless": r"cushion|block heel|low heel|flat|comfort", "fine": "low, cushioned or block-heel versions"},
}
ADJ = {"masculine": "men's-style", "business": "too-corporate", "boxy": "boxy", "short": "too-short",
       "itchy": "stiff", "walk": "hard-to-walk-in"}  # a scoped ban in words: "men's-style, too-corporate loafers"
TELL_TAGS = {"Too masculine": "masculine", "Too business": "business"}  # tags that rule something out
NEVER_OPTIONS = {"Anything that reads masculine": "masculine", "Shapeless or boxy": "boxy", "Very short or low-cut": "short",
                 "Itchy or stiff fabrics": "itchy", "Hard-to-walk-in shoes": "walk"}
# piece words she can rule out; generic words (shoes, clothes) never become a ban on their own
TYPES = (r"loafer|flat|heel|pump|boot|bootie|sneaker|sandal|mule|slingback|oxford|brogue|clog|blazer|jacket|coat|trench|"
         r"parka|puffer|trouser|pant|jean|legging|short|skirt|dress|top|blouse|shirt|tee|sweater|cardigan|turtleneck|knit|"
         r"vest|suit|tie|bag|tote|backpack|clutch|belt|scarf|hat|beret|headband|necklace|earring|bracelet|watch|tight")
TYPE_RE = re.compile(rf"\b({TYPES})(?:e?s)?\b")
NEGATIVE = re.compile(r"\b(never|no|not|avoid|hate|don'?t|stop|ban|ruled out|dislike|can'?t stand)\b")
SHOES = {"loafer", "flat", "heel", "pump", "boot", "bootie", "sneaker", "sandal", "mule", "slingback", "oxford", "brogue", "clog"}


def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "").lower().replace("’", "'")).strip()


def _head(name: str) -> str:
    """The piece itself, without its details: 'black square-toe penny loafers, cushioned' -> 'black square-toe penny loafers'."""
    return re.split(r",|\(| with | in | for | that ", _norm(name))[0].strip()


def _reasons(text: str) -> list[str]:
    return [k for k, c in CONCEPTS.items() if re.search(c["said"], text)]


def _from_text(text: str, source: str, why: str, never: bool = False, rejected: bool = False) -> list[dict]:
    """Bans read from one thing she said. never: it answers "never put me in...", so pieces named are out;
    rejected: it was a "Not for me", so a reason counts without a "never" word (the piece itself is handled by the caller)."""
    out = []
    for clause in re.split(r"[.;!?\n]+", _norm(text)):
        reasons = _reasons(clause)
        types = list(dict.fromkeys(TYPE_RE.findall(clause)))
        if types and reasons:
            out += [{"kind": "scoped", "type": t, "reasons": reasons, "source": source, "why": why} for t in types]
        elif types and (never or NEGATIVE.search(clause)):
            out += [{"kind": "type", "type": t, "reasons": [], "source": source, "why": why} for t in types]
        elif reasons and (never or rejected or NEGATIVE.search(clause)):
            out += [{"kind": "concept", "reasons": [r], "source": source, "why": why} for r in reasons]
    return out


def bans(profile: dict) -> list[dict]:
    """Everything she has rejected or ruled out, as checkable bans, built from the profile (no model call)."""
    out: list[dict] = []
    for f in profile.get("feedback") or []:
        note, label = f.get("note") or "", f.get("label") or ""
        if f.get("rating") == "no":
            why = f"Not for me: {label[:60]}" + (f" (\"{note[:100]}\")" if note else "")
            piece = _head(label)
            found = _from_text(note, "feedback", why, rejected=True)
            # the reason in the note belongs to the piece she rejected ("men's shoes" about the loafers)
            types = TYPE_RE.findall(piece)
            reasons = _reasons(_norm(note))
            if types and reasons:
                found = [b for b in found if b["kind"] != "concept"]
                found += [{"kind": "scoped", "type": types[-1], "reasons": reasons, "source": "feedback", "why": why}]
            if not any(b["kind"] in ("scoped", "type") for b in found) and piece:
                found.append({"kind": "piece", "name": piece, "source": "feedback", "why": why})
            for i in f.get("item_ids") or []:
                if f.get("kind") in ("item", "product"):
                    found.append({"kind": "item", "id": i, "name": label, "source": "feedback", "why": why})
            out += found
        tags = [t.strip() for t in label.split(":", 1)[-1].split(",")] if ":" in label else []
        for t in tags:
            if t in TELL_TAGS:
                out.append({"kind": "concept", "reasons": [TELL_TAGS[t]], "source": "tell",
                            "why": f"You told me: {t}" + (f" (\"{note[:100]}\")" if note else "")})
        if f.get("rating") == "note" and note:
            out += _from_text(note, "tell", f"You told me: \"{note[:100]}\"")
    st = profile.get("stylist") or {}
    for a in st.get("answers") or []:
        if a.get("id") == "never":
            for opt in [x.strip() for x in (a.get("a") or "").split(";")]:
                if opt in NEVER_OPTIONS:
                    out.append({"kind": "concept", "reasons": [NEVER_OPTIONS[opt]], "source": "check-in", "why": f"Check-in: never {opt.lower()}"})
                elif opt:
                    out += _from_text(opt, "check-in", f"Check-in: never \"{opt[:80]}\"", never=True)
    for r in st.get("extra_rules") or []:
        out += _from_text(r, "house rule", f"House rule: \"{r[:100]}\"")
    for a in (profile.get("style") or {}).get("avoid") or []:
        if _norm(a):
            out.append({"kind": "phrase", "name": _norm(a), "source": "style", "why": f"On your avoid list: {a}"})
    # same ban said twice: keep one, with every reason
    seen, uniq = {}, []
    for b in out:
        key = (b["kind"], b.get("type"), tuple(b.get("reasons") or []), b.get("name"), b.get("id"))
        if key in seen:
            if b["why"] not in seen[key]["why"]:
                seen[key]["why"] += f"; {b['why']}"
            continue
        seen[key] = b
        uniq.append(b)
    for b in uniq:
        b["label"] = ban_label(b)
    return uniq


def ban_label(b: dict) -> str:
    if b["kind"] == "scoped":
        how = ", ".join(ADJ[r] for r in b["reasons"])
        fine = CONCEPTS[b["reasons"][0]]["fine"]
        return f"{how} {b['type']}s" + (f" ({fine} are fine)" if fine else "")
    if b["kind"] == "type":
        return f"{b['type']}s"
    if b["kind"] == "concept":
        c = CONCEPTS[b["reasons"][0]]
        return c["label"] + (f" ({c['fine']} are fine)" if c["fine"] else "")
    return b.get("name") or b.get("id", "")


NEGATED = re.compile(r"\b(?:non|anti)-[\w'-]+|\b(?:not|no|never|without|zero|nothing) (?:too |very |a |any |at all )?[\w'-]+")


def _text(piece) -> str:
    """What the piece says it is, minus what it says it isn't ('smooth, non-itchy wool' is not itchy)."""
    if isinstance(piece, str):
        text = piece
    else:
        colors = " ".join(c.get("name", "") for c in piece.get("colors") or [] if isinstance(c, dict))
        text = " ".join(str(piece.get(k) or "") for k in ("name", "piece", "subtype", "color", "search_request")) + " " + colors
    return NEGATED.sub(" ", _norm(text))


def _hits(b: dict, text: str, piece) -> bool:
    if b["kind"] == "item":
        return isinstance(piece, dict) and piece.get("id") == b["id"]
    if b["kind"] == "piece":
        return _head(piece if isinstance(piece, str) else piece.get("name") or piece.get("piece") or "") == b["name"]
    if b["kind"] == "phrase":
        return re.search(rf"\b{re.escape(b['name'])}\b", text) is not None
    if b["kind"] == "type":
        return re.search(rf"\b{b['type']}(?:e?s)?\b", text) is not None
    cs = [CONCEPTS[r] for r in b["reasons"]]
    hard = any(re.search(rf"\b(?:{c['hard']})", text) for c in cs)
    unless = "|".join(c["unless"] for c in cs if c["unless"])
    softened = bool(unless) and re.search(rf"\b(?:{unless})", text) is not None
    if b["kind"] == "scoped":
        return re.search(rf"\b{b['type']}(?:e?s)?\b", text) is not None and (hard or not softened)
    leaning = any(c.get("leaning") and re.search(rf"\b(?:{c['leaning']})\b", text) for c in cs)
    return hard or (leaning and not softened)


def banned(piece, ban_list: list[dict]) -> list[dict]:
    """The bans this piece (a closet item, a recommended gap, a shop pick, or plain text) breaks."""
    text = _text(piece)
    return [b for b in ban_list if _hits(b, text, piece)]


def ban_reason(piece, ban_list: list[dict]) -> str:
    hit = banned(piece, ban_list)
    return "; ".join(f"{b['label']}: {b['why']}" for b in hit)


def ban_lines(ban_list: list[dict]) -> list[str]:
    """For the stylist's point of view: what she ruled out, and what is still fine."""
    if not ban_list:
        return []
    return (["HARD NOs from the user (checked in code: a look or pick that uses one is sent back or thrown out). Keep "
             "the nuance: a ban covers the piece for the reason they gave, not the whole category:"]
            + [f"- never {b['label']} ({b['why']})" for b in ban_list[:20]])


def draw_guard(text: str, ban_list: list[dict]) -> str:
    """An image prompt that can't draw a banned piece: banned shoes become ballet flats, other banned clauses go,
    plain 'flats' always means ballet flats, and a never-draw line is added."""
    parts = []
    for clause in re.split(r"(?<=,)|(?<=;)|(?<= and )", text or ""):
        hit = banned(clause, [b for b in ban_list if b["kind"] in ("scoped", "type", "concept", "phrase")])
        if hit:
            t = TYPE_RE.search(_norm(clause))
            if t and t.group(1) in SHOES:
                clause = re.sub(rf"(?:[\w'-]+ ){{0,4}}{t.group(1)}(?:e?s)?\b", "feminine ballet flats", clause, count=1, flags=re.I)
            else:
                continue
        parts.append(clause)
    out = "".join(parts).strip().rstrip(",;")
    out = re.sub(r"(?<!ballet )(?<!ballet-style )\bflats\b", "ballet flats", out, flags=re.I)
    return (out + " " + never_line(ban_list)).strip()


def never_line(ban_list: list[dict]) -> str:
    """The sentence every image prompt ends with."""
    never = "; ".join(b["label"] for b in ban_list if b["kind"] != "item")[:600]
    return f"Never draw: {never}. Flats are feminine ballet flats, never loafers or men's shoes." if never else ""


# ---- house rules about which bag goes where ("I wear my backpack to school; purses are for other occasions") ----
BAG = re.compile(r"\b(bag|tote|purse|handbag|clutch|crossbody|backpack|satchel|pouch)\b", re.I)
SCHOOL_WORD = re.compile(r"\b(school|class(es)?|campus|lectures?)\b", re.I)
CARRY_VERB = re.compile(r"\b(wear|carry|bring|use|take)s?\b", re.I)
# a calendar event at school: class, campus spaces, career office, club welcome events (title or place)
SCHOOL_EVENT = re.compile(r"\b(school|class(es)?|lecture|seminar|section|recitation|office hours|campus|student commons|"
                          r"commons|cdo|som|evans hall|library|study group|exam|orientation|welcome back)\b", re.I)


def is_bag(item: dict) -> bool:
    return item.get("category") == "accessory" and bool(BAG.search(f"{item.get('subtype') or ''} {item.get('name') or ''}"))


def carry_rules(profile: dict, closet: list[dict]) -> list[dict]:
    """House rules that name a bag she owns for school, as checkable rules: {item id, name, why}."""
    out = []
    for r in (profile.get("stylist") or {}).get("extra_rules") or []:
        if not (SCHOOL_WORD.search(r) and CARRY_VERB.search(r)):
            continue
        named = BAG.search(r.split(".")[0])  # the bag she says she takes ("my backpack"), not the ones she rules out
        noun = named.group(0).lower() if named else ""
        bag = next((i for i in closet if noun and is_bag(i) and noun in f"{i.get('subtype') or ''} {i['name']}".lower()), None)
        if bag:
            out.append({"id": bag["id"], "name": bag["name"], "why": f"House rule: \"{r.strip()[:120]}\"",
                        "label": f"{bag['name']} for school, other bags only off campus"})
    return out


def at_school(events: list[str]) -> list[str]:
    return [e for e in events or [] if SCHOOL_EVENT.search(e or "")]


def apply_carry(item_ids: list[str], events: list[str], rules: list[dict], by_id: dict) -> tuple[list[str], list[tuple[str, str, dict]]]:
    """For a look worn to school, any other bag is swapped for the bag her house rule names.
    Returns (new item ids, [(removed bag name, school event, rule)])."""
    school = at_school(events)
    if not rules or not school:
        return item_ids, []
    rule = rules[0]
    swaps = [(by_id[i]["name"], school[0], rule) for i in item_ids if i in by_id and is_bag(by_id[i]) and i != rule["id"]]
    has_bag = any(i in by_id and is_bag(by_id[i]) for i in item_ids)
    if not swaps and (not has_bag or rule["id"] in item_ids):
        return item_ids, []
    kept = [i for i in item_ids if not (i in by_id and is_bag(by_id[i]) and i != rule["id"])]
    if rule["id"] not in kept:
        kept.append(rule["id"])
    return kept, swaps


def explain(profile: dict, closet: list[dict]) -> dict:
    """What each note and house rule became, for the Me tab (no model call): a code-checked rule, or guidance every
    styling agent reads."""
    def labels(p):
        seen = set()
        return [b["label"] for b in bans(p) if not (b["label"].lower() in seen or seen.add(b["label"].lower()))]
    notes = []
    for n, f in enumerate(profile.get("feedback") or []):
        notes.append({"i": n, "became": labels({"feedback": [f]})})
    rules = []
    for r in (profile.get("stylist") or {}).get("extra_rules") or []:
        one = {"stylist": {"extra_rules": [r]}}
        rules.append({"rule": r, "became": labels(one) + [c["label"] for c in carry_rules(one, closet)]})
    return {"notes": notes, "rules": rules}
