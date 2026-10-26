"""Body measurements that start as a photo estimate and get sharper with every item you own.

Each closet item with a size label and a fit verdict ("perfect", "tight", "loose") is a data
point: a standard size chart says what body that size is cut for, and the fit says whether
you're at, above or below it. The estimate is a weighted average of the photo estimate and
all item evidence; the uncertainty range shrinks as evidence grows. Measurements you typed
in yourself (measurements_locked) are never overwritten.
"""

from __future__ import annotations

import math
import re

# Typical US women's body measurements (inches) per size: bust, waist, hips.
NUMERIC = {
    0: (32, 24, 34.5), 2: (33, 25, 35.5), 4: (34, 26, 36.5), 6: (35, 27, 37.5), 8: (36, 28, 38.5),
    10: (37, 29, 39.5), 12: (38.5, 30.5, 41), 14: (40, 32, 42.5), 16: (41.5, 33.5, 44), 18: (43.5, 35.5, 46),
    20: (45.5, 37.5, 48), 22: (47.5, 39.5, 50), 24: (49.5, 41.5, 52), 26: (51.5, 43.5, 54), 28: (53.5, 45.5, 56),
}
LETTER = {
    "XXS": (31, 23, 33), "XS": (32.5, 25, 35), "S": (34.5, 27, 37), "M": (36.5, 29, 39), "L": (39, 32, 42),
    "XL": (42, 35, 45), "XXL": (45, 38, 48), "1X": (45, 38, 48), "2X": (48, 41, 51), "3X": (51, 44, 54), "4X": (54, 47, 57),
}
SHOE_FOOT_IN = {6: 9.25, 6.5: 9.4, 7: 9.5, 7.5: 9.7, 8: 9.9, 8.5: 10.0, 9: 10.2, 9.5: 10.4, 10: 10.5,
                10.5: 10.7, 11: 10.9, 11.5: 11.0, 12: 11.2, 12.5: 11.4, 13: 11.6, 14: 11.9}
FIT_SHIFT = {"perfect": 0.0, "snug": 0.75, "tight": 1.75, "loose": -1.75}  # body vs. the size's chart value
PHOTO_WEIGHT, ITEM_WEIGHT = 1.0, 2.0
KEYS = ("height", "shoulders", "bust", "waist", "hips", "inseam", "foot_length")


def chart_for(size_label: str):
    """(bust, waist, hips) for a size label like '16', 'US 18', 'XL', '2X', or None."""
    lab = (size_label or "").upper().replace("US", "").strip()
    lab = lab.replace("WOMEN'S", "").replace("W", "W").strip()
    m = re.match(r"^(\d{1,2})(W|P|T)?$", lab.split("/")[0].strip())
    if m and int(m.group(1)) in NUMERIC:
        return NUMERIC[int(m.group(1))]
    for k in sorted(LETTER, key=len, reverse=True):
        if re.search(rf"(^|[^A-Z0-9]){re.escape(k)}([^A-Z0-9]|$)", lab):
            return LETTER[k]
    return None


def evidence(item: dict, size_label: str, fit: str) -> dict:
    """Measurement -> value implied by one item's size + fit."""
    shift = FIT_SHIFT.get(fit, 0.0)
    cat, out = item.get("category"), {}
    if cat == "shoes":
        m = re.search(r"(\d{1,2}(?:\.5)?)", size_label or "")
        if m and float(m.group(1)) in SHOE_FOOT_IN:
            out["foot_length"] = SHOE_FOOT_IN[float(m.group(1))] + {"tight": 0.15, "snug": 0.08, "loose": -0.15}.get(fit, 0)
        return out
    c = chart_for(size_label)
    if not c:
        return out
    bust, waist, hips = c
    if cat in ("top", "outerwear") or item.get("subtype") in ("sports_bra",):
        out["bust"] = bust + shift
    elif cat in ("bottom",) or item.get("subtype") in ("leggings", "shorts"):
        out["waist"] = waist + shift
        out["hips"] = hips + shift
    elif cat == "dress":
        out.update(bust=bust + shift, waist=waist + shift, hips=hips + shift)
    return out


def size_from(measurements: dict) -> dict:
    """Nearest numeric/letter sizes for the current measurements."""
    b, w, h = (measurements.get(k) for k in ("bust", "waist", "hips"))
    if not all(isinstance(x, (int, float)) for x in (b, w, h)):
        return {}
    def nearest(chart, parts):
        return min(chart, key=lambda s: sum((chart[s][i] - v) ** 2 for i, v in parts))
    return {"top": nearest(LETTER, [(0, b)]), "bottom": str(nearest(NUMERIC, [(1, w), (2, h)])),
            "dress": str(nearest(NUMERIC, [(0, b), (1, w), (2, h)]))}


def refine(profile: dict) -> dict:
    """Recompute measurements_in, ranges, sizes and confidence from photo estimate + item evidence."""
    photo = profile.get("body_photo_estimate") or {}
    ev = profile.get("fit_evidence") or []
    locked = set(profile.get("measurements_locked") or [])
    current = dict(profile.get("measurements_in") or {})
    ranges, counts = {}, {}
    for k in KEYS:
        if k in locked:
            ranges[k] = [current.get(k), current.get(k)]
            counts[k] = "exact"
            continue
        vals, weights = [], []
        if k in photo:
            vals.append(photo[k][0]); weights.append(PHOTO_WEIGHT)
        item_vals = [e["implied"][k] for e in ev if k in e.get("implied", {})]
        vals += item_vals; weights += [ITEM_WEIGHT] * len(item_vals)
        if not vals:
            continue
        best = sum(v * w for v, w in zip(vals, weights)) / sum(weights)
        half = ((photo[k][2] - photo[k][1]) / 2) if k in photo else 2.0
        half = max(0.4, half / math.sqrt(1 + 2 * len(item_vals)))
        current[k] = round(best, 1)
        ranges[k] = [round(best - half, 1), round(best + half, 1)]
        counts[k] = len(item_vals)
    profile["measurements_in"] = current
    profile["measurements_range"] = ranges
    profile["measurement_evidence"] = counts
    sizes = profile.setdefault("sizes", {})
    for k, v in size_from(current).items():
        if not (profile.get("sizes_locked") and k in profile["sizes_locked"]):
            sizes[k] = v
    n = len(ev)
    profile["measurements_source"] = (
        f"photo estimate + {n} fitted item{'s' if n != 1 else ''}" if photo else f"{n} fitted items"
    ) + (f"; exact: {', '.join(sorted(locked))}" if locked else "")
    return profile


LETTER_ORDER = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "3X", "4X"]
NUMERIC_ORDER = sorted(NUMERIC)


def _step(size, shift: int):
    """Move a size up or down the chart (a brand that runs small on you: size up)."""
    order = NUMERIC_ORDER if isinstance(size, int) else LETTER_ORDER
    i = order.index(size) + shift
    return order[max(0, min(len(order) - 1, i))]


NO_SIZE = re.compile(r"\b(bags?|backpacks?|totes?|purses?|clutch(es)?|handbags?|crossbody|hats?|baseball caps?|beanies?|berets?|"
                     r"fedoras?|jewel(le)?ry|necklaces?|earrings?|bracelets?|rings?|anklets?|brooch(es)?|watch(es)?|"
                     r"sunglasses|scarf|scarves|hair)\b", re.I)


def guess_size(profile: dict, item: dict, brand_shift: int = 0) -> dict | None:
    """Your likely size for an item: from your measurements (photo estimate + fitted items), nudged by
    what returns taught about the brand. A guess only; it becomes evidence once you say how it fits."""
    cat = item.get("category")
    m = profile.get("measurements_in") or {}
    sizes = profile.get("sizes") or {}
    note = " (brand runs small on you)" if brand_shift > 0 else " (brand runs big on you)" if brand_shift < 0 else ""
    if cat == "shoes":
        shoe = sizes.get("shoe")
        if not shoe:
            return None
        width = " wide" if sizes.get("shoe_width") == "wide" else ""
        try:
            shoe = float(shoe) + 0.5 * brand_shift
            shoe = f"{shoe:g}"
        except ValueError:
            pass
        return {"size": f"{shoe}{width}", "why": f"your shoe size{note}"}
    if cat == "accessory" or NO_SIZE.search(f"{item.get('subtype') or ''} {item.get('name') or ''}"):
        return None  # bags, hats, jewelry: no size
    nearest = size_from(m)
    if not nearest:
        return None
    if cat in ("top", "outerwear"):
        size, why = nearest["top"], "your bust"
    elif cat == "bottom":
        size, why = int(nearest["bottom"]), "your waist and hips"
    elif cat == "dress":
        size, why = int(nearest["dress"]), "your bust, waist and hips"
    else:
        return None
    size = _step(size, brand_shift)
    n = len(profile.get("fit_evidence") or [])
    sure = "high" if n >= 4 else "medium" if n else "low"
    return {"size": str(size), "why": f"{why}{note}", "confidence": sure}
