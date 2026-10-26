"""Seasonal color analysis (12 seasons) and style archetypes (7 types).

The Color Analyst agent only *describes* what it sees (undertone, lightness, clarity,
contrast). Plain code then maps those traits to a season, so the result is explainable
and the same traits always give the same season. Palettes are Closet Twin's own picks.
Archetype names follow Emma Irene Cavanagh's seven style archetypes (emmairenecavanagh.com);
descriptions here are our own summaries.
"""

from __future__ import annotations

SEASONS = {
    "Light Spring": {
        "traits": "warm-leaning, light, clear",
        "palette": [["Peach", "#F6B89A"], ["Light coral", "#F08C7E"], ["Warm aqua", "#7FD1C1"], ["Butter yellow", "#F7DF8C"], ["Periwinkle", "#9DB2E8"], ["Mint", "#B8E3C7"], ["Light camel", "#D2B48C"], ["Warm pink", "#F4A3B4"]],
        "neutrals": ["Ivory", "Light camel", "Warm light grey", "Soft navy"], "metals": "light gold, rose gold",
        "avoid": ["Black", "Burgundy", "Dark charcoal", "Icy grey"],
    },
    "True Spring": {
        "traits": "warm, medium, bright",
        "palette": [["Coral", "#FF7F61"], ["Golden yellow", "#F5C13C"], ["Kelly green", "#3BAA4A"], ["Turquoise", "#1FB5AC"], ["Poppy red", "#E8473B"], ["Warm violet", "#8E6CC4"], ["Camel", "#C19A6B"], ["Apricot", "#F7A86A"]],
        "neutrals": ["Cream", "Camel", "Warm grey", "Bright navy"], "metals": "yellow gold, brass",
        "avoid": ["Black", "Dusty mauve", "Cool grey", "Icy pastels"],
    },
    "Bright Spring": {
        "traits": "warm-leaning, bright, high contrast",
        "palette": [["Hot coral", "#FF5A4E"], ["Bright turquoise", "#00B7B0"], ["Emerald", "#0E9F6E"], ["Electric blue", "#2E6BE6"], ["Hot pink", "#F0408A"], ["Sunflower", "#FFC93C"], ["Bright violet", "#7B4BD8"], ["Clear red", "#E0303A"]],
        "neutrals": ["Soft white", "Charcoal", "Navy", "Warm taupe"], "metals": "polished gold, silver",
        "avoid": ["Dusty pastels", "Muddy olive", "Beige", "Heather grey"],
    },
    "Light Summer": {
        "traits": "cool-leaning, light, soft",
        "palette": [["Powder blue", "#AFC8E7"], ["Lavender", "#C6B6E0"], ["Rose pink", "#E7A8BF"], ["Soft aqua", "#9FD3D0"], ["Dove grey", "#BDBDC6"], ["Sea glass", "#B7D8C7"], ["Soft periwinkle", "#A6ACDA"], ["Watermelon", "#E58C9E"]],
        "neutrals": ["Soft white", "Light grey", "Grey-blue", "Soft navy"], "metals": "silver, white gold",
        "avoid": ["Black", "Orange", "Mustard", "Rust"],
    },
    "True Summer": {
        "traits": "cool, medium, soft",
        "palette": [["Dusty rose", "#C98A9C"], ["Slate blue", "#6E86B5"], ["Raspberry", "#B34A6E"], ["Soft teal", "#5E9FA3"], ["Plum", "#7E5A86"], ["Cornflower", "#7C9CE0"], ["Cool mauve", "#A9879B"], ["Spruce", "#4F7D73"]],
        "neutrals": ["Soft white", "Rose-beige", "Blue-grey", "Navy"], "metals": "silver, pewter",
        "avoid": ["Orange", "Camel", "Mustard", "Pure black"],
    },
    "Soft Summer": {
        "traits": "cool-leaning, soft, low contrast",
        "palette": [["Smoky blue", "#7D93A8"], ["Mauve", "#A98A98"], ["Sage", "#9AAA95"], ["Soft plum", "#7B6577"], ["Dusty teal", "#5F8A8B"], ["Rosewood", "#A86E7A"], ["Heather", "#9E97AB"], ["Soft denim", "#6F86A6"]],
        "neutrals": ["Oyster", "Taupe", "Charcoal blue", "Soft navy"], "metals": "brushed silver, rose gold",
        "avoid": ["Bright orange", "Neon", "Pure white", "Black"],
    },
    "Soft Autumn": {
        "traits": "warm-leaning, soft, low contrast",
        "palette": [["Sage", "#A3AE8C"], ["Terracotta", "#C47A5A"], ["Soft teal", "#5C8C86"], ["Camel", "#B8936A"], ["Dusty coral", "#D98C7A"], ["Olive", "#8A8A5A"], ["Mushroom", "#A69585"], ["Warm rose", "#C48A86"]],
        "neutrals": ["Oatmeal", "Camel", "Warm taupe", "Soft brown"], "metals": "brushed gold, bronze",
        "avoid": ["Black", "Icy pastels", "Hot pink", "Electric blue"],
    },
    "True Autumn": {
        "traits": "warm, medium, rich",
        "palette": [["Rust", "#B5532E"], ["Mustard", "#D19A2A"], ["Olive", "#6B7135"], ["Forest green", "#2F5D3A"], ["Pumpkin", "#D9772B"], ["Teal", "#1F6F6B"], ["Brick red", "#9E3B2C"], ["Camel", "#B98B5A"]],
        "neutrals": ["Cream", "Camel", "Chocolate", "Olive"], "metals": "antique gold, copper",
        "avoid": ["Black", "Icy pastels", "Fuchsia", "Cool grey"],
    },
    "Deep Autumn": {
        "traits": "warm-leaning, deep, rich",
        "palette": [["Burgundy", "#6E1F2E"], ["Deep teal", "#0F5257"], ["Chocolate", "#4A2C21"], ["Burnt orange", "#C2551F"], ["Forest", "#244A35"], ["Aubergine", "#4B2340"], ["Mustard", "#C99A2E"], ["Tomato red", "#B8322A"]],
        "neutrals": ["Cream", "Espresso", "Dark olive", "Warm charcoal"], "metals": "gold, bronze",
        "avoid": ["Pastels", "Icy grey", "Powder blue", "Pale pink"],
    },
    "Deep Winter": {
        "traits": "cool-leaning, deep, high contrast",
        "palette": [["True black", "#111111"], ["Ruby", "#9B1B30"], ["Emerald", "#0B6E4F"], ["Royal blue", "#1F3FA6"], ["Deep plum", "#4A1942"], ["Pure white", "#FAFAFA"], ["Burgundy", "#6A1B2C"], ["Pine", "#123D33"]],
        "neutrals": ["Black", "Pure white", "Charcoal", "Navy"], "metals": "silver, platinum",
        "avoid": ["Beige", "Camel", "Orange", "Dusty pastels"],
    },
    "True Winter": {
        "traits": "cool, high contrast, clear",
        "palette": [["Fuchsia", "#C2187A"], ["Cobalt", "#1B4DB3"], ["True red", "#C8102E"], ["Emerald", "#00875A"], ["Icy pink", "#F3D3E2"], ["Black", "#111111"], ["Pure white", "#FAFAFA"], ["Royal purple", "#5B2A86"]],
        "neutrals": ["Black", "Pure white", "Charcoal", "Navy"], "metals": "silver, white gold",
        "avoid": ["Camel", "Orange", "Mustard", "Muted earth tones"],
    },
    "Bright Winter": {
        "traits": "cool-leaning, bright, high contrast",
        "palette": [["Hot pink", "#E6007E"], ["Electric blue", "#0057FF"], ["Emerald", "#009B72"], ["Lemon", "#F7E83A"], ["Bright red", "#E1061B"], ["Violet", "#6A2BD9"], ["Black", "#111111"], ["Icy white", "#F7FAFC"]],
        "neutrals": ["Black", "Pure white", "Charcoal", "Navy"], "metals": "polished silver",
        "avoid": ["Dusty pastels", "Beige", "Olive", "Brown"],
    },
}


def season_from_traits(undertone: str, value: str, chroma: str, contrast: str) -> tuple[str, str]:
    """Deterministic 12-season mapping from four traits. Returns (season, why)."""
    warm = undertone in ("warm", "neutral-warm")
    if value == "light":
        s = "Light Spring" if warm else "Light Summer"
        why = "light is your strongest trait"
    elif value == "deep":
        s = "Deep Autumn" if warm else "Deep Winter"
        why = "depth is your strongest trait"
    elif chroma == "bright":
        s = "Bright Spring" if warm else "Bright Winter"
        why = "clarity (bright) is your strongest trait"
    elif chroma == "soft":
        s = "Soft Autumn" if warm else "Soft Summer"
        why = "softness (muted) is your strongest trait"
    elif warm:
        s = "True Spring" if contrast in ("medium", "high") else "True Autumn"
        why = "warmth is your strongest trait"
    else:
        s = "True Winter" if contrast == "high" else "True Summer"
        why = "coolness is your strongest trait"
    return s, f"{undertone} undertone, {value} value, {chroma} chroma, {contrast} contrast; {why}"


ARCHETYPES = {
    "Natural": "Relaxed and easy: breathable fabrics, soft knits, denim, linen, sneakers. Effortless over polished.",
    "Classic": "Timeless and structured: blazers, trench coats, crisp shirts, loafers, investment pieces.",
    "Romantic": "Soft and feminine: fluid fabrics, flowing dresses, silk, lace, florals, soft color.",
    "Dramatic": "Bold and high-impact: sharp tailoring, statement coats, monochrome, strong contrast.",
    "Creative": "Expressive and eclectic: pattern mixing, unexpected pairings, statement accessories, bold color.",
    "Gamine": "Playful and youthful: cropped jackets, stripes, ankle pants, retro details, masculine-meets-feminine.",
    "Elegant Chic": "Polished and minimal: tailored trousers, silk blouses, clean lines, neutrals, fine jewelry.",
}

# Our own quiz wording: three questions, each answer points to an archetype.
QUIZ = [
    {"q": "How do you most want to come across?", "options": {
        "Natural": "Easygoing and approachable", "Classic": "Put-together and trustworthy", "Romantic": "Soft and graceful",
        "Dramatic": "Bold and unforgettable", "Creative": "Original, one of a kind", "Gamine": "Fun and spirited",
        "Elegant Chic": "Refined and effortless"}},
    {"q": "Pick the outfit you'd wear tomorrow:", "options": {
        "Natural": "Linen shirt, relaxed jeans, white sneakers", "Classic": "Navy blazer, crisp shirt, trousers, loafers",
        "Romantic": "Floral midi dress and soft cardigan", "Dramatic": "All-black tailoring with a statement coat",
        "Creative": "Printed skirt, clashing knit, chunky jewelry", "Gamine": "Striped tee, cropped jacket, ankle pants",
        "Elegant Chic": "Silk blouse, tailored trousers, delicate gold"}},
    {"q": "Friends would describe your style as:", "options": {
        "Natural": "Comfortable", "Classic": "Polished", "Romantic": "Pretty", "Dramatic": "Striking",
        "Creative": "Artsy", "Gamine": "Cute and quirky", "Elegant Chic": "Chic"}},
]


def color_brief(profile: dict) -> str:
    """Season + archetype lines for the agents' prompts (empty if not analyzed yet)."""
    lines = []
    cs = profile.get("color_season") or {}
    if cs.get("season") in SEASONS:
        s = SEASONS[cs["season"]]
        lines.append(f"Color season: {cs['season']} ({s['traits']}). Best colors: "
                     + ", ".join(n for n, _ in s["palette"]) + f". Best neutrals: {', '.join(s['neutrals'])}. "
                     f"Metals: {s['metals']}. Avoid near the face: {', '.join(s['avoid'])}.")
    arch = profile.get("archetype") or {}
    if arch.get("primary") in ARCHETYPES:
        lines.append(f"Style archetype: {arch['primary']}" + (f" with {arch['secondary']}" if arch.get("secondary") in ARCHETYPES else "")
                     + (f" and a touch of {arch['third']}" if arch.get("third") in ARCHETYPES else "")
                     + f" ({ARCHETYPES[arch['primary']]})")
    return "\n".join(lines)
