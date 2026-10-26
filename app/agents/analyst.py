"""Color Analyst (photo -> coloring traits -> 12-season, mapped in code) and Style Analyst (-> archetype)."""

from __future__ import annotations

import base64

from .. import color_measure, color_style, safety, store, stylists
from ..ledger import Ledger
from ..llm import obj_schema, run_agent
from .common import closet_brief, instructions, profile_brief

SWATCH = obj_schema({"name": {"type": "string"}, "hex": {"type": "string"}})
COLOR_SCHEMA = obj_schema({
    "skin": SWATCH, "hair": SWATCH, "eyes": SWATCH, "lips": SWATCH,
    "undertone": {"type": "string", "enum": ["warm", "neutral-warm", "neutral-cool", "cool"]},
    "value": {"type": "string", "enum": ["light", "medium", "deep"]},
    "chroma": {"type": "string", "enum": ["bright", "medium", "soft"]},
    "contrast": {"type": "string", "enum": ["low", "medium", "high"]},
    "lighting_quality": {"type": "string", "enum": ["good", "ok", "poor"]},
    "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    "notes": {"type": "string"},
})

STYLE_SCHEMA = obj_schema({
    "primary": {"type": "string", "enum": list(color_style.ARCHETYPES)},
    "secondary": {"type": "string", "enum": list(color_style.ARCHETYPES) + ["none"]},
    "third": {"type": "string", "enum": list(color_style.ARCHETYPES) + ["none"]},
    "evidence": {"type": "array", "items": {"type": "string"}},
    "pieces_that_fit": {"type": "array", "items": {"type": "string"}},
    "pieces_to_add": {"type": "array", "items": {"type": "string"}},
    "user_note": {"type": "string"},
})


PICK_SCHEMA = obj_schema({
    "season": {"type": "string", "enum": list(color_style.SEASONS)},
    "skin": SWATCH, "hair": SWATCH, "eyes": SWATCH,
    "lighting_quality": {"type": "string", "enum": ["good", "ok", "poor"]},
    "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    "why": {"type": "string"},
    "notes": {"type": "string"},
})


def analyze_color(ledger: Ledger, dataset: str, face_path, measured: dict) -> dict:
    """measured = pixel measurements from the browser. Code ranks the 12 seasons; the agent picks from the top 3."""
    m = color_measure.analyze(measured)
    ledger.step("Color Analyst", "tool", f"measured: {m['undertone']['undertone']} undertone (hue {m['undertone']['hue_angle']}°), "
                f"{m['depth']} depth, chroma {m['chroma']} ({m['chroma_level']}), {m['contrast']['contrast']} contrast "
                f"({m['contrast']['score']}), {m['eye_color']} eyes → top 3: {', '.join(m['top3'])}", m)
    url = "data:image/jpeg;base64," + base64.b64encode(safety.prepare_photo(face_path.read_bytes())).decode()
    text = (
        "Image 1 is a close-up of my face. Measured from the photo's pixels (skin = cheeks, forehead, chin):\n"
        f"- skin RGB {measured['skin_rgb']}, Lab L {m['undertone']['L']} a {m['undertone']['a']} b {m['undertone']['b']}, "
        f"hue angle {m['undertone']['hue_angle']}° → {m['undertone']['undertone']} undertone, {m['depth']} depth, chroma {m['chroma']} ({m['chroma_level']})\n"
        f"- brows RGB {measured['brow_rgb']}, eyes RGB {measured['eye_rgb']} ({m['eye_color']}), lips RGB {measured.get('lip_rgb')}\n"
        f"- facial contrast {m['contrast']['score']} ({m['contrast']['contrast']}); face fills {int(100 * measured.get('face_fraction', 0))}% of the frame\n"
        f"Rule-based ranking (top 3): {', '.join(m['top3'])}.\n"
        "Pick the best season, normally from the top 3. If the lighting clearly distorted the measurement (warm lamp, "
        "colored light, heavy filter), say so and choose what the photo really shows."
    )
    ledger.step("Color Analyst", "start", "Checking the measurements against the photo")
    pick = run_agent(
        ledger, "Color Analyst", instructions("color_analyst"),
        [{"role": "user", "content": [{"type": "input_text", "text": text},
                                      {"type": "input_image", "image_url": url, "detail": "high"}]}],
        schema=PICK_SCHEMA, schema_name="season_pick", effort="low",
    ).output
    if pick["season"] not in m["top3"]:
        ledger.step("Color Analyst", "note", f"Agent chose {pick['season']}, outside the measured top 3 ({pick['why'][:120]})")
    ranked = [s for s in [pick["season"], *m["top3"]] if s in color_style.SEASONS]
    top = list(dict.fromkeys(ranked))[:3]
    ledger.step("Color Analyst", "done", f"{pick['season']}; confidence {pick['confidence']}, lighting {pick['lighting_quality']}", pick)
    return {"season": pick["season"], "why": pick["why"], "top3": top, "measured": m, "pick": pick,
            "details": color_style.SEASONS[pick["season"]]}


def analyze_style(ledger: Ledger, dataset: str, quiz_answers: list[str]) -> dict:
    prof = store.profile(dataset)
    closet = store.closet(dataset)
    picks = [a for a in quiz_answers if a in color_style.ARCHETYPES]
    quiz_lines = [f"Q{i + 1} ({q['q']}): {q['options'].get(a, 'skipped')} → {a}"
                  for i, (q, a) in enumerate(zip(color_style.QUIZ, picks))] or ["(quiz skipped)"]
    content = (
        f"MY CLOSET:\n{closet_brief(closet)}\n\nABOUT ME:\n{profile_brief(prof, include_body=False)}\n"
        f"{color_style.color_brief(prof)}\n\n{stylists.point_of_view(prof, dataset)}\n\n"
        "ARCHETYPES:\n" + "\n".join(f"- {k}: {v}" for k, v in color_style.ARCHETYPES.items())
        + "\n\nMY QUIZ ANSWERS:\n" + "\n".join(quiz_lines) + "\n\nWhat is my style archetype?"
    )
    ledger.step("Style Analyst", "start", f"Finding your archetype from {len(picks)} quiz answer(s), {len(closet)} closet item(s) and your feedback")
    out = run_agent(ledger, "Style Analyst", instructions("style_analyst"), content,
                    schema=STYLE_SCHEMA, schema_name="archetype", effort="low").output
    known = {i["id"] for i in closet}
    bad = [i for i in out["pieces_that_fit"] if i not in known]
    if bad:
        ledger.safety("grounding", "Style Analyst", f"Removed {len(bad)} item id(s) not in the closet.", bad)
        out["pieces_that_fit"] = [i for i in out["pieces_that_fit"] if i in known]
    ledger.step("Style Analyst", "done", f"{out['primary']}" + (f" + {out['secondary']}" if out["secondary"] != "none" else ""), out)
    return out


READ_SCHEMA = obj_schema({
    "signature": {"type": "string"},
    "bullets": {"type": "array", "items": {"type": "string"}},
    "primary": {"type": "string", "enum": list(color_style.ARCHETYPES)},
    "secondary": {"type": "string", "enum": list(color_style.ARCHETYPES) + ["none"]},
    "third": {"type": "string", "enum": list(color_style.ARCHETYPES) + ["none"]},
    "blend_why": {"type": "string"},
    "goal_title": {"type": "string"},
    "goal_look": {"type": "string"},
    "strategy": {"type": "array", "items": obj_schema({
        "move": {"type": "string", "enum": ["Keep wearing", "Add", "Phase out", "Try next", "Styling habit"]},
        "text": {"type": "string"},
    })},
    "questions": {"type": "array", "items": obj_schema({
        "q": {"type": "string"},
        "options": {"type": "array", "items": {"type": "string"}},
        "multi": {"type": "boolean"},
    })},
})


def stylist_read(ledger: Ledger, dataset: str) -> dict:
    """The one stylist writes down its read on the user from their feedback so far."""
    prof = store.profile(dataset)
    closet = store.closet(dataset)
    k = stylists.learned(dataset, prof)
    content = (
        f"MY CLOSET:\n{closet_brief(closet)}\n\nABOUT ME:\n{profile_brief(prof, include_body=False)}\n"
        f"{color_style.color_brief(prof)}\n\n{stylists.point_of_view(prof, dataset)}\n\n"
        "ARCHETYPES:\n" + "\n".join(f"- {n}: {color_style.ARCHETYPES[n]}" for n in stylists.ARCHETYPES)
        + f"\n\nI've given you {k['notes']} reactions ({k['loves']} loves, {k['nos']} not-for-me). What's your read on me?"
    )
    ledger.step("Stylist", "start", f"Updating its read on you from {k['notes']} reaction(s)")
    out = run_agent(ledger, "Stylist", instructions("stylist_read"), content,
                    schema=READ_SCHEMA, schema_name="stylist_read", effort="low").output
    out["bullets"] = [safety.clean_untrusted(b, 200)[0] for b in out["bullets"][:6]]
    out["goal_title"] = safety.clean_untrusted(out["goal_title"], 80)[0]
    out["goal_look"] = safety.clean_untrusted(out["goal_look"], 800)[0]
    out["strategy"] = [{"move": m["move"], "text": safety.clean_untrusted(m["text"], 220)[0]} for m in out["strategy"][:7]]
    out["questions"] = [{"q": safety.clean_untrusted(q["q"], 160)[0], "multi": bool(q["multi"]),
                         "options": [safety.clean_untrusted(o, 60)[0] for o in q["options"][:6]]}
                        for q in out["questions"][:3] if q["q"].strip() and len(q["options"]) >= 2]
    ledger.step("Stylist", "done", out["signature"][:160], out)
    return out


RANGE = obj_schema({"best": {"type": "number"}, "low": {"type": "number"}, "high": {"type": "number"}})
BODY_SCHEMA = obj_schema({
    "measurements_in": obj_schema({k: RANGE for k in ("height", "shoulders", "bust", "waist", "hips", "inseam", "foot_length")}),
    "sizes": obj_schema({"top": {"type": "string"}, "bottom": {"type": "string"}, "dress": {"type": "string"},
                         "inseam_label": {"type": "string", "enum": ["petite", "regular", "long"]}}),
    "body_shape": {"type": "string"},
    "flattering": {"type": "string"},
    "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    "notes": {"type": "string"},
})


def estimate_body(ledger: Ledger, dataset: str, photo_path, height_in: float | None, shoe: str) -> dict:
    url = "data:image/jpeg;base64," + base64.b64encode(safety.prepare_photo(photo_path.read_bytes(), max_side=1024)).decode()
    hint = f"My height is {height_in} inches. " if height_in else "I haven't given my height. "
    hint += f"My shoe size is US women's {shoe}." if shoe else ""
    ledger.step("Body Estimator", "start", "Estimating measurements and sizes from your full-body photo")
    out = run_agent(
        ledger, "Body Estimator", instructions("body_estimator"),
        [{"role": "user", "content": [{"type": "input_text", "text": hint + " Estimate my measurements and sizes."},
                                      {"type": "input_image", "image_url": url, "detail": "high"}]}],
        schema=BODY_SCHEMA, schema_name="body_estimate", effort="low",
    ).output
    m = out["measurements_in"]
    ledger.step("Body Estimator", "done", "Estimated " + ", ".join(f"{k} {v['best']:g}" for k, v in m.items())
                + f" · sizes {out['sizes']['top']}/{out['sizes']['bottom']} · confidence {out['confidence']}", out)
    return out
