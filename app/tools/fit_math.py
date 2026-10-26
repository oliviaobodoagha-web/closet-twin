"""Deterministic fit math: compares body measurements (inches) to a brand's size chart.

The Fit Tailor agent calls these tools instead of guessing numbers, then adds what
reviews say ("runs small", "roomy toe box"). Zone results drive the heatmap on the
3D avatar: good = green, snug = amber, tight/short/long = red, loose = blue.
"""

from __future__ import annotations

ZONES = ("shoulders", "bust", "waist", "hips", "inseam", "length")
WIDTH_ORDER = {"narrow": 0, "medium": 1, "regular": 1, "wide": 2, "extra wide": 3}


def zone_fit(measure: float | None, rng) -> dict | None:
    if measure is None or rng is None:
        return None
    lo, hi = (rng, rng) if isinstance(rng, (int, float)) else rng
    if measure > hi + 1.0:
        return {"status": "tight", "off_by_in": round(measure - hi, 1)}
    if measure > hi:
        return {"status": "snug", "off_by_in": round(measure - hi, 1)}
    if measure < lo - 2.0:
        return {"status": "loose", "off_by_in": round(lo - measure, 1)}
    return {"status": "good", "off_by_in": 0.0}


def length_fit(measure: float | None, garment_len: float | None) -> dict | None:
    if measure is None or garment_len is None:
        return None
    diff = garment_len - measure
    if diff < -1.0:
        return {"status": "short", "off_by_in": round(-diff, 1)}
    if diff > 1.5:
        return {"status": "long", "off_by_in": round(diff, 1)}
    return {"status": "good", "off_by_in": round(diff, 1)}


def fit_garment(size_chart: dict, size: str, measurements: dict) -> dict:
    row = size_chart.get(size)
    if row is None:
        return {"size": size, "error": f"size {size} not in chart", "available": list(size_chart)}
    zones = {}
    for z in ("shoulders", "bust", "waist", "hips"):
        r = zone_fit(measurements.get(z), row.get(z))
        if r:
            zones[z] = r
    r = length_fit(measurements.get("inseam"), row.get("inseam"))
    if r:
        zones["inseam"] = r
    return {"size": size, "zones": zones, "score": _score(zones)}


def fit_shoe(size_chart: dict, size: str, foot_length_in: float, foot_width: str) -> dict:
    row = size_chart.get(size)
    if row is None:
        return {"size": size, "error": f"size {size} not sold", "available": list(size_chart)}
    zones = {}
    length = row.get("foot_length_in")
    if length is not None:
        diff = length - foot_length_in
        zones["toe_length"] = (
            {"status": "tight", "off_by_in": round(-diff, 2)} if diff < -0.05
            else {"status": "loose", "off_by_in": round(diff, 2)} if diff > 0.4
            else {"status": "good", "off_by_in": round(diff, 2)}
        )
    widths = row.get("widths", ["medium"])
    need = WIDTH_ORDER.get(foot_width, 1)
    best = max(WIDTH_ORDER.get(w, 1) for w in widths)
    zones["width"] = (
        {"status": "good", "note": f"offered in {', '.join(widths)}"} if best >= need
        else {"status": "tight", "note": f"only {', '.join(widths)}; you need {foot_width}"}
    )
    return {"size": size, "zones": zones, "score": _score(zones)}


def best_size(size_chart: dict, measurements: dict, is_shoe: bool = False,
              foot_length_in: float = 0, foot_width: str = "medium") -> dict:
    results = [
        fit_shoe(size_chart, s, foot_length_in, foot_width) if is_shoe else fit_garment(size_chart, s, measurements)
        for s in size_chart
    ]
    results = [r for r in results if "error" not in r]
    if not results:
        return {"error": "no sizes in chart"}
    top = max(results, key=lambda r: r["score"])
    return {"best": top, "all_sizes": [{"size": r["size"], "score": r["score"]} for r in results]}


def _score(zones: dict) -> int:
    pts = {"good": 100, "snug": 70, "loose": 70, "long": 60, "short": 40, "tight": 20}
    if not zones:
        return 0
    return round(sum(pts.get(z["status"], 50) for z in zones.values()) / len(zones))
