"""Measured seasonal color analysis: pixel colors -> Lab traits -> ranked 12 seasons.

The browser finds face landmarks (MediaPipe Face Landmarker) and samples median colors
from skin (cheeks, forehead, chin), eyebrows, irises and lips. This module turns those
measurements into undertone, depth, chroma and contrast, then scores all 12 seasons.

Adapted from tkamali2020/Seasonal-Color-Analysis (Apache License 2.0,
https://github.com/tkamali2020/Seasonal-Color-Analysis): undertone, depth, chroma and
contrast thresholds and the season scoring rules are ported from its src/*.py files,
rewritten without OpenCV. Changes: Dark Autumn/Winter are named Deep Autumn/Winter, and the
result is a ranked list that the Color Analyst agent and the user choose from (draping),
because fixed skin-lightness thresholds can over-call "Deep" for deeper skin tones.
"""

from __future__ import annotations

import math

# Season features (ported from season_data.py; Dark -> Deep).
FEATURES = {
    "Light Spring": ("Warm", "Light", "Low", ["blue", "green"]),
    "True Spring": ("Warm", "Medium", "Medium", ["green", "hazel"]),
    "Bright Spring": ("Warm", "Light", "High", ["blue", "green"]),
    "Light Summer": ("Cool", "Light", "Low", ["blue", "gray"]),
    "True Summer": ("Cool", "Medium", "Low", ["blue", "gray", "green"]),
    "Soft Summer": ("Cool", "Medium", "Medium", ["gray", "green", "hazel"]),
    "Soft Autumn": ("Warm", "Medium", "Low", ["hazel", "green"]),
    "True Autumn": ("Warm", "Deep", "Medium", ["brown", "hazel"]),
    "Deep Autumn": ("Warm", "Deep", "High", ["brown", "dark brown"]),
    "Bright Winter": ("Cool", "Medium", "High", ["blue"]),
    "True Winter": ("Cool", "Deep", "High", ["blue", "gray", "dark brown"]),
    "Deep Winter": ("Cool", "Deep", "High", ["dark brown", "brown"]),
}


def rgb_to_lab(rgb) -> tuple[float, float, float]:
    """sRGB (0-255) -> CIE L*a*b* (D65)."""
    def lin(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(float(v)) for v in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 1.0
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def undertone(skin_rgb) -> dict:
    L, a, b = rgb_to_lab(skin_rgb)
    hue = math.degrees(math.atan2(b, a)) % 360
    ba = b / (a + 1e-6)
    if hue < 55.0 or ba < 1.15:
        tone = "Neutral" if (b > 17.0 and hue > 52.0) else "Cool"
    elif hue > 64.0 or ba > 1.48:
        tone = "Neutral" if (a > 20.0 and hue < 66.0) else "Warm"
    else:
        tone = "Cool" if b < 12.5 else "Warm" if b > 17.5 else "Neutral"
    return {"undertone": tone, "hue_angle": round(hue, 1), "L": round(L, 1), "a": round(a, 1), "b": round(b, 1)}


def depth(skin_rgb) -> str:
    L = rgb_to_lab(skin_rgb)[0]
    return "Light" if L >= 63.0 else "Medium" if L >= 53.0 else "Deep"


def chroma(skin_rgb) -> float:
    _, a, b = rgb_to_lab(skin_rgb)
    return math.hypot(a, b)


def contrast(skin_rgb, brow_rgb, eye_rgb) -> dict:
    s, br, e = (rgb_to_lab(c) for c in (skin_rgb, brow_rgb, eye_rgb))
    dl_brow, dl_eye = abs(s[0] - br[0]), abs(s[0] - e[0])
    de_brow, de_eye = math.dist(s, br), math.dist(s, e)
    score = (dl_brow * 0.65 + dl_eye * 0.35) * 0.85 + (de_brow * 0.65 + de_eye * 0.35) * 0.15
    return {"contrast": "Low" if score < 22 else "Medium" if score <= 36 else "High", "score": round(score, 1)}


def eye_color(h: float, s: float, v: float) -> str:
    """Classify iris color from HSV (h 0-360, s/v 0-255), ported from eyes.py."""
    if 150 <= h <= 260 and v > 30:
        return "blue"
    if 70 <= h < 150:
        return "green" if s > 20 else "blue"
    if h < 45 or h > 330:
        if s < 25 and v > 120:
            return "hazel"
        if h >= 25 and s >= 25:
            return "hazel"
        return "dark brown" if v < 60 else "brown"
    if 45 <= h < 70:
        return "green" if s > 40 else "hazel"
    return "brown"


def _score(season, tone, dep, con, con_score, value, chroma_score, eye) -> int:
    f_tone, f_depth, f_con, f_eyes = FEATURES[season]
    pts = 8 if f_tone == tone else 3 if tone == "Neutral" else -10
    pts += 5 if dep == f_depth else -2
    pts += 4 if con == f_con else -1
    if con_score >= 36:
        pts += 3 if ("Winter" in season or "Bright" in season) else -2 if "Soft" in season else 0
    elif con_score <= 22:
        pts += 3 if ("Summer" in season or "Soft" in season) else -2 if ("Bright" in season or "Winter" in season) else 0
    pts += 3 if eye in f_eyes else -1
    if value == "Light":
        pts += 5 if "Light" in season else 2 if ("Spring" in season or "Summer" in season) else -4 if "Deep" in season else 0
    elif value == "Deep":
        pts += 5 if "Deep" in season else 2 if ("Autumn" in season or "Winter" in season) else -4 if "Light" in season else 0
    if chroma_score >= 27:
        pts += 5 if ("Bright" in season or "Winter" in season or "Spring" in season) else -4 if "Soft" in season else 0
    elif chroma_score <= 18:
        pts += 5 if ("Soft" in season or "Summer" in season or "Autumn" in season) else -4 if "Bright" in season else 0
    elif "True" in season:
        pts += 3
    return pts


def analyze(m: dict) -> dict:
    """m = {skin_rgb, brow_rgb, eye_rgb, eye_hsv:[h,s,v], lip_rgb} -> traits + ranked seasons."""
    skin, brow, eye_rgb = m["skin_rgb"], m["brow_rgb"], m["eye_rgb"]
    ut = undertone(skin)
    dep = depth(skin)
    ch = chroma(skin)
    con = contrast(skin, brow, eye_rgb)
    eye = eye_color(*m.get("eye_hsv", [20, 60, 50]))
    scores = {s: _score(s, ut["undertone"], dep, con["contrast"], con["score"], dep, ch, eye) for s in FEATURES}
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    return {
        "undertone": ut, "depth": dep, "chroma": round(ch, 1),
        "chroma_level": "Soft" if ch < 18 else "Medium" if ch <= 27 else "Bright",
        "contrast": con, "eye_color": eye,
        "ranked": [{"season": s, "score": v} for s, v in ranked],
        "top3": [s for s, _ in ranked[:3]],
    }
