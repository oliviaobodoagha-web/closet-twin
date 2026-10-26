"""One expert stylist who builds every look around the user's style archetypes and learns their point of view.

Archetypes follow the style-archetype guides (Emma Irene Cavanagh's seven, with the overlaps from
Capitol Hill Clothiers and Flourish Styling noted): most people are a blend of two or three. The
primary is the long-term foundation; the secondary is the current season of life; a third is an accent.

What the stylist knows about the user grows from four things, all in the profile:
  profile["archetype"]   their blend (from the quiz/Style Analyst or picked by hand)
  profile["stylist"]     their house rules and the stylist's written read on them ("read")
  profile["feedback"]    every Love it / Not for me, with notes
  profile["style"]       their own style words, colors they love and things they avoid
"""

from __future__ import annotations

from datetime import date

from . import outfit_rules, store

NAME = "Margaux-Sloan"
PERSONALITY = ("Half Margaux: calm, exacting quiet luxury, fewer and better things, fit and fabric first. "
               "Half Sloane: uptown prep with a dash of glam, confident, a little iconic, one fun detail that makes it yours. "
               "Together: decisive and warm, never sloppy, never trying too hard.")
PUSH_EVERY_DAYS = 14       # about every two weeks she offers one bolder "Push" option
MAX_ANSWERS_IN_PROMPT = 15

# Asked in the app before any model call: the basics a stylist would ask in a first session.
STARTER_QUESTIONS = [
    {"id": "life", "q": "Besides recruiting, which parts of your life should I dress you for?", "multi": True,
     "options": ["Class & campus", "Weekends & brunch", "Going out & dates", "Travel", "Workouts & errands", "Office / internship"]},
    {"id": "bold", "q": "How bold should I go?", "multi": False,
     "options": ["Mostly staples", "Staples plus one statement", "Push me now and then", "Push me often"]},
    {"id": "accessories", "q": "How much should I accessorize you?", "multi": False,
     "options": ["Minimal: just the right bag", "Finished: 2-3 pieces", "Statement accessories carry the look"]},
    {"id": "color", "q": "Which color approach feels most like you?", "multi": True,
     "options": ["Neutrals plus one pop", "Coordinated color stories", "Tonal, one color family", "Depends: read the occasion"]},
    {"id": "never", "q": "What should I never put you in?", "multi": True,
     "options": ["Anything that reads masculine", "Shapeless or boxy", "Very short or low-cut", "Itchy or stiff fabrics", "Hard-to-walk-in shoes"]},
    {"id": "feel", "q": "How do you want people to feel when you walk in?", "multi": True,
     "options": ["She has it together", "Approachable and warm", "Glamorous", "Effortlessly cool", "Memorable"]},
]
STARTER_IDS = {q["id"] for q in STARTER_QUESTIONS}
MAX_FEEDBACK = 40          # stored
MAX_FEEDBACK_IN_PROMPT = 12  # most recent notes sent to agents (keeps prompts small)
REFLECT_EVERY = 3          # the stylist rewrites its read on you after this many new notes

# How to dress each archetype. Our own wording, built from the three guides.
GUIDE = {
    "Classic": {
        "also": "Traditional, preppy",
        "pieces": "navy blazer, trench, crisp button-down, straight trousers, cashmere crew, pencil or A-line skirt, slim feminine loafers or ballet flats, structured bag",
        "fabrics": "wool, cotton poplin, cashmere, smooth leather",
        "lines": "tailored, symmetrical, clean, nothing extreme",
        "colors": "navy, camel, cream, white, burgundy, black",
        "details": "pearls or small gold, a good belt, a watch",
        "avoid": "distressed pieces, loud logos, trend-of-the-week shapes",
    },
    "Elegant Chic": {
        "also": "Minimalist, cosmopolitan, quiet luxury",
        "pieces": "tailored wide-leg trousers, silk blouse, fine knit, long coat, slip skirt, sleek flats or slingbacks",
        "fabrics": "silk, fine merino, crepe, buttery leather",
        "lines": "long, clean, tonal, nothing fussy",
        "colors": "ivory, oatmeal, camel, grey, black; one deliberate color at most",
        "details": "delicate fine jewelry, no visible logos",
        "avoid": "busy prints, many colors at once, cheap shine",
    },
    "Natural": {
        "also": "Earthy, relaxed",
        "pieces": "linen shirt, relaxed jeans, soft knit, chore jacket, easy dress, clean sneakers, flat sandals",
        "fabrics": "linen, cotton, denim, soft wool, suede",
        "lines": "relaxed, unstructured, easy to move in",
        "colors": "earth tones, olive, rust, sand, denim blue, cream",
        "details": "woven bag, simple leather, minimal jewelry",
        "avoid": "stiff tailoring, high shine, anything you fidget with all day",
    },
    "Romantic": {
        "also": "Feminine, soft glam, ingenue",
        "pieces": "flowing midi dress, silk or satin blouse, soft cardigan, lace, wrap shapes, ballet flats, kitten heels",
        "fabrics": "silk, satin, chiffon, lace, velvet, cashmere",
        "lines": "soft, curved, fluid, waist-defined",
        "colors": "blush, rose, soft pastels, cream, florals; jewel tones for evening",
        "details": "bows, ruffles, pearls, delicate gold",
        "avoid": "boxy, harsh, very severe or utilitarian pieces",
    },
    "Dramatic": {
        "also": "Edgy, bold",
        "pieces": "statement coat, sharp blazer, monochrome look, leather jacket, strong boots, sculptural bag",
        "fabrics": "leather, structured wool, crisp cotton, patent",
        "lines": "angular, strong shoulders, long and sharp",
        "colors": "black, white, high contrast, one bold color like red",
        "details": "one big statement accessory, bold metal",
        "avoid": "small fussy details, washed-out pastels, timid half-measures",
    },
    "Creative": {
        "also": "Avant-garde, eclectic",
        "pieces": "printed skirt, unexpected pairings, vintage find, statement knit, interesting shoes, artful jewelry",
        "fabrics": "anything with texture or story: jacquard, vintage, mixed",
        "lines": "unusual silhouettes, mixing proportions on purpose",
        "colors": "bold and unexpected pairings, done with intent",
        "details": "pattern mixing, one-of-a-kind accessories",
        "avoid": "head-to-toe basics with no point of view",
    },
    "Gamine": {
        "also": "Playful, retro",
        "pieces": "mod mini shift dress, cropped boxy jacket, Peter Pan collar, cigarette ankle pants, Mary Janes or ballet flats, beret",
        "fabrics": "cotton, tweed, knit, denim",
        "lines": "cropped, compact, crisp, masculine-meets-feminine",
        "colors": "black and white, red, navy, clear brights",
        "details": "retro touches, a beret or headband, a fun bag",
        "avoid": "long shapeless layers, overly sweet head-to-toe looks",
    },
}
ARCHETYPES = list(GUIDE)


def blend(profile: dict) -> list[str]:
    """[primary, secondary, third] that are set, in order."""
    a = profile.get("archetype") or {}
    out = []
    for k in ("primary", "secondary", "third"):
        v = a.get(k)
        if v in GUIDE and v not in out:
            out.append(v)
    return out


def _guide_lines(name: str) -> list[str]:
    g = GUIDE[name]
    return [f"  pieces: {g['pieces']}", f"  fabrics: {g['fabrics']} · lines: {g['lines']}",
            f"  colors: {g['colors']} · details: {g['details']}", f"  avoid: {g['avoid']}"]


def learned(dataset: str, profile: dict) -> dict:
    """What the stylist has picked up from feedback, counted in code (no model call)."""
    fb = profile.get("feedback") or []
    names = {i["id"]: i.get("name", i["id"]) for i in store.closet(dataset)}
    score: dict[str, int] = {}
    for f in fb:
        for i in f.get("item_ids", []):
            if i in names:
                score[i] = score.get(i, 0) + (1 if f.get("rating") == "love" else -1)
    loved = [names[i] for i, s in sorted(score.items(), key=lambda kv: -kv[1]) if s > 0][:5]
    skipped = [names[i] for i, s in sorted(score.items(), key=lambda kv: kv[1]) if s < 0][:5]
    n = len(fb)
    stage = ("Getting to know you" if n < 5 else "Learning your eye" if n < 15 else "Knows your taste")
    n += len((profile.get("stylist") or {}).get("answers") or [])  # answering her questions teaches her too
    stage = ("Getting to know you" if n < 5 else "Learning your eye" if n < 15 else "Knows your taste")
    return {"notes": n, "loves": sum(f.get("rating") == "love" for f in fb), "nos": sum(f.get("rating") == "no" for f in fb),
            "loved_items": loved, "skipped_items": skipped, "stage": stage, "level": min(100, round(n / 15 * 100))}


def point_of_view(profile: dict, dataset: str | None = None) -> str:
    """The one stylist's brief: archetype blend, its read on the user, house rules, feedback. Sent to every styling agent."""
    lines = [
        f"YOUR STYLIST POINT OF VIEW: you are {NAME}, the user's one personal stylist, an expert in style archetypes "
        f"({', '.join(ARCHETYPES)}). You build every look around the user's archetype blend and you keep learning "
        f"their point of view from what they love, reject and tell you. Your personality: {PERSONALITY}",
    ]
    mix = blend(profile)
    if mix:
        roles = ["FOUNDATION (most of every look)", "CURRENT SEASON (one or two elements per look)", "ACCENT (a single touch, when it fits)"]
        lines.append("Their archetype blend:")
        for role, name in zip(roles, mix):
            lines.append(f"- {name} = {role}")
            lines += _guide_lines(name)
        lines.append("Build each look so a stylist could name its archetypes: the foundation sets the silhouette and "
                     "fabrics, the current-season archetype adds a piece or detail, the accent only a finishing touch. "
                     "Respect each archetype's 'avoid' line unless the user's own feedback says otherwise.")
    else:
        lines.append("Their archetype blend is not set yet. Infer the closest one or two archetypes from their style "
                     "words, closet and feedback, style from those, and name them in your notes.")
    pal = [n for n, _ in outfit_rules.season_colors(profile)]
    if pal:
        lines.append(f"Color: their season's signature colors are {', '.join(pal)}. Use them, not just the season's neutrals: "
                     "most looks carry one of these as a piece or an accessory (the 10% accent at least), and among the "
                     "options for a block at least one is built on one of these colors. An all black-and-white look is a "
                     "deliberate choice for the occasion, not the default. Every look must still follow the color theory rules.")
    from . import aesthetic  # aesthetic imports this module for the archetype list
    lines += aesthetic.brief(profile)
    read = (profile.get("stylist") or {}).get("read") or {}
    if read.get("signature") or read.get("bullets"):
        lines.append(f"Your read on them so far (from {read.get('n_feedback', 0)} notes): {read.get('signature', '')}")
        lines += [f"- {b}" for b in read.get("bullets", [])[:6]]
    if dataset:
        k = learned(dataset, profile)
        if k["loved_items"]:
            lines.append("Pieces they keep loving: " + "; ".join(k["loved_items"]))
        if k["skipped_items"]:
            lines.append("Pieces they keep turning down: " + "; ".join(k["skipped_items"]))
    answers = (profile.get("stylist") or {}).get("answers") or []
    if answers:
        lines.append("What the user told you when you asked them (most recent last; follow it):")
        lines += [f"- Q: {a['q'][:120]} A: {a['a'][:200]}" for a in answers[-MAX_ANSWERS_IN_PROMPT:]]
    lines += outfit_rules.ban_lines(outfit_rules.bans(profile))
    lines.append(push_line(profile))
    extra = [r for r in (profile.get("stylist") or {}).get("extra_rules", []) if r.strip()]
    if extra:
        lines.append("The user's own house rules (these win over yours):")
        lines += [f"- {r[:160]}" for r in extra[:10]]
    fb = (profile.get("feedback") or [])[-MAX_FEEDBACK_IN_PROMPT:]
    if fb:
        lines.append("What the user has told you about past suggestions (most recent last). Respect it:")
        for f in fb:
            verdict = {"love": "LOVED", "no": "DID NOT LIKE"}.get(f.get("rating"), "SAID ABOUT")
            items = f" [{', '.join(f.get('item_ids', [])[:6])}]" if f.get("item_ids") else ""
            note = f": \"{f['note'][:140]}\"" if f.get("note") else ""
            lines.append(f"- {verdict} {f.get('kind', 'look')} '{f.get('label', '')[:80]}'{items}{note}")
    lines.append("Speak as one consistent expert: warm, specific, opinionated, never generic. Say WHY in fashion terms, "
                 "naming the archetype a piece or choice comes from when it helps.")
    return "\n".join(lines)


def push_due(profile: dict) -> bool:
    last = (profile.get("stylist") or {}).get("last_push")
    try:
        return not last or (date.today() - date.fromisoformat(last)).days >= PUSH_EVERY_DAYS
    except ValueError:
        return True


def push_line(profile: dict) -> str:
    if push_due(profile):
        return ("Boldness: it's time to stretch them a little. Keep the main pick in their comfort zone, and make exactly "
                "ONE option a bolder step toward a less-used archetype or a statement piece. Title that option starting "
                "with 'Push:' and say in its why what you're testing.")
    return ("Boldness: mostly staples plus one statement piece. You stretched them recently, so no 'Push:' option this "
            "time unless they ask for one.")


def pending_questions(profile: dict) -> list[dict]:
    """Questions waiting for the user: the stylist's own follow-ups first, then starter questions not answered yet."""
    st = profile.get("stylist") or {}
    answered = {a.get("id") for a in st.get("answers") or []}
    own = [q for q in st.get("pending_qs") or [] if q.get("id") not in answered]
    starters = [q for q in STARTER_QUESTIONS if q["id"] not in answered]
    return (own + starters)[:4]


def meta() -> dict:
    return {"name": NAME, "personality": PERSONALITY, "archetypes": {k: {"also": v["also"], "pieces": v["pieces"], "colors": v["colors"]} for k, v in GUIDE.items()},
            "reflect_every": REFLECT_EVERY}
