"""Optional photo-real try-on: your photo + your clothes' photos + a real place -> a realistic image of you.

Runs on the user's OWN OpenAI key (OPENAI_API_KEY) with gpt-image-2.5-sunburst, never
the course key. Your photo is sent to OpenAI only after you tick the consent box in Me,
and nothing here is committed to git (data/user/ is ignored). Capped per image and per day.
"""

from __future__ import annotations

import base64
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from pathlib import Path

from openai import OpenAI

from . import config, image_cache, safety, store
from .ledger import BudgetExceeded, Ledger

AGENT = "Photo Try-On"

# Real places, described for when you haven't uploaded your own photo of the place.
SCENES = {
    "classroom": "a classroom in Yale School of Management's Evans Hall: a round 'drum' classroom with curved, blue-tinted glass walls, tiered rows of light wood desks, and a whiteboard at the front, daylight from the courtyard",
    "office": "a bright modern office with a white desk, a monitor, a black task chair and floor-to-ceiling windows",
    "gym": "a university gym (like Yale's Payne Whitney Gym) with rubber flooring, a mirror wall and spin bikes",
    "coffee": "a cozy New Haven coffee shop with a wooden counter, a chalkboard menu, warm pendant lights and small marble tables",
    "street": "a sunny sidewalk on a New England college campus with brick buildings and autumn trees",
    "dinner": "a warmly lit, elegant restaurant in New Haven at night, candles on white tablecloths",
    "studio": "a softly lit ivory boutique fitting room with a full-length gold mirror",
}


def me_photo_path(dataset: str):
    return store.folder(dataset) / "me.jpg"


def face_photo_path(dataset: str):
    """Face close-up: color analysis, and a second likeness reference for photo try-ons."""
    return store.folder(dataset) / "face.jpg"


def wrist_photo_path(dataset: str):
    """Optional inner-wrist close-up (veins help judge undertone), used only for color analysis."""
    return store.folder(dataset) / "wrist.jpg"


def place_photo_path(dataset: str, scene: str):
    return store.folder(dataset) / "places" / f"{scene}.jpg"


def status(dataset: str) -> dict:
    prof = store.profile(dataset)
    return {
        "key_set": bool(config.openai_key()),
        "model": config.IMAGE_MODEL,
        "has_photo": me_photo_path(dataset).exists(),
        "has_face": face_photo_path(dataset).exists(),
        "has_wrist": wrist_photo_path(dataset).exists(),
        "consent": bool(prof.get("photo_consent")),
        "places": sorted(p.stem for p in (store.folder(dataset) / "places").glob("*.jpg")) if (store.folder(dataset) / "places").exists() else [],
        "used_today": tryons_today(),
        "max_per_day": config.MAX_PHOTO_TRYONS_PER_DAY,
    }


def tryons_today(mode: str = "photo_tryon") -> int:
    path = config.LOG_DIR / "runs.jsonl"
    if not path.exists():
        return 0
    today = datetime.now(timezone.utc).date().isoformat()
    n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("mode") == mode and r.get("status") == "ok" and r.get("started_at", "").startswith(today):
            n += 1
    return n


def save_photo(dataset: str, raw: bytes, scene: str | None = None, closeup: str | None = None) -> None:
    jpeg = safety.prepare_photo(raw, max_side=config.PHOTO_MAX_SIDE)
    if closeup:
        path = face_photo_path(dataset) if closeup == "face" else wrist_photo_path(dataset)
    else:
        path = place_photo_path(dataset, scene) if scene else me_photo_path(dataset)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(jpeg)


POSES = {
    "standing": "Full-body, natural standing pose facing the camera.",
    "turn": "Full-body, three-quarter turn to show the side and the back of the outfit, looking over the shoulder.",
    "sitting": "Seated at a desk or table as people really sit, the outfit visible from the waist up and the shoes visible.",
    "walking": "Full-body, mid-stride walking toward the camera, natural movement in the fabric.",
}


def describe(item: dict) -> str:
    color = "/".join(c["name"] for c in item.get("colors", [])) or item.get("color", "")
    bits = [color, item.get("fabric", ""), item.get("fit", "") + " fit" if item.get("fit") else "",
            item.get("length", "") if item.get("length") not in (None, "", "regular") else "", item.get("subtype", "")]
    return " ".join(b for b in bits if b).strip() or item.get("name", "")


# Likeness first: copying her quick selfie "exactly" copied the flyaways and the straight face, but asking for "a good
# photo of me on a good day" (smoothed hair, warm smile, flattering light) drifted to a generic pretty face. So polish
# is grooming only, and likeness wins when they pull apart.
IDENTITY = ("This must be unmistakably me. Keep my exact face: face shape, eyes, eyebrows, nose, lips, jawline, natural "
            "skin tone and texture. Keep my real hair color, length, texture and style. Keep my real body: height, "
            "shoulder width, bust, waist, hips, arms and legs in the same proportions as image 1. Do not slim, enlarge, "
            "reshape, airbrush or beautify my face or body, and don't make me look like a model or a different person.")
LOOK = ("Polish only the grooming, not who I am: my hair neat and tidy in its real style (no frizz or flyaways), clothes "
        "pressed and well fitted, soft even daylight, relaxed upright posture, a natural relaxed expression with a slight "
        "smile. If polish and likeness ever conflict, likeness wins.")

# What she can tick under a try-on ("What's wrong with this photo?"). Each becomes an instruction for every later try-on.
ISSUES = {
    "hair": "my hair looked messy or wrong; keep my real hair, just neat",
    "smile": "my expression looked blank or unhappy; a natural, relaxed slight smile on my own face",
    "face": "my face didn't look like me; keep my real facial features exactly",
    "body": "my body shape or size was changed; keep my real body exactly",
    "clothes": "a piece of the outfit was wrong, missing or added",
    "fit": "the clothes fit wrong (too tight, too loose or the wrong length)",
    "coat": "I was wearing my coat indoors; carry it over my arm or leave it off inside",
    "pose": "the pose looked awkward or stiff",
    "scene": "the place or background was wrong",
    "light": "the light or colors looked off",
}


def notes(profile: dict) -> str:
    """Her feedback on earlier try-ons, newest last; it applies to every try-on after it."""
    fb = (profile.get("tryon_feedback") or [])[-5:]
    said = []
    for f in fb:
        said += [ISSUES[k] for k in f.get("issues", []) if k in ISSUES and ISSUES[k] not in said]
        if f.get("detail"):
            said.append(f"she says: {f['detail'].rstrip('.')}")
    return ("Corrections from me on earlier photos (follow them): " + "; ".join(said) + ".") if said else ""


def build_prompt(items_with_photo: list[dict], items_text: list[dict], scene: str, has_place: bool, fit_notes: list[str],
                 pose: str = "standing", corrections: str = "", has_face: bool = False) -> str:
    n = 3 if has_face else 2
    lines = [
        "Image 1 is a full-length photo of me" + (" and image 2 is a close-up of my face, for my exact features" if has_face else "") + ".",
        IDENTITY,
        LOOK,
        "Dress me in this exact outfit:",
    ]
    for it in items_with_photo:
        lines.append(f"- Image {n} shows my {it.get('name', 'garment')}: match its exact color, fabric, cut and details.")
        n += 1
    for it in items_text:
        lines.append(f"- {it.get('name', 'item')}: {describe(it)}.")
    if has_place:
        lines.append(f"Image {n} is a photo of the real place: put me in that exact location, keeping its background, light and perspective.")
    else:
        lines.append(f"Setting: {SCENES.get(scene, SCENES['studio'])}.")
    if fit_notes:
        lines.append("Show the fit honestly, as measured by my fit check: " + "; ".join(fit_notes) + ".")
    if scene not in ("street",) and any(i.get("category") == "outerwear" and "blazer" not in (i.get("subtype") or "").lower()
                                         for i in items_with_photo + items_text):
        lines.append("I'm indoors: carry the coat over my arm (or leave it off) so the outfit underneath shows.")
    if corrections:
        lines.append(corrections)
    lines.append(POSES.get(pose, POSES["standing"]) + " Photorealistic, natural light, realistic fabric drape. "
                 "Only me in the frame. No text, watermarks or logos.")
    return "\n".join(lines)


def run(ledger: Ledger, dataset: str, items: list[dict], scene: str, zones_by_item: dict | None = None, pose: str = "standing") -> dict:
    key = config.openai_key()
    if not key:
        raise ValueError("Photo try-on needs your own OPENAI_API_KEY in .env (the course key is for gpt-6-luna only). Everything else works without it.")
    prof = store.profile(dataset)
    if not prof.get("photo_consent"):
        raise ValueError("Tick the consent box in Me first: your photo is sent to OpenAI to make the image.")
    me = me_photo_path(dataset)
    if not me.exists():
        raise ValueError("Add a full-body photo of yourself in the Me tab first.")
    if tryons_today() >= config.MAX_PHOTO_TRYONS_PER_DAY:
        ledger.safety("budget", AGENT, f"Daily limit of {config.MAX_PHOTO_TRYONS_PER_DAY} photo try-ons reached.")
        raise BudgetExceeded(f"You've used today's {config.MAX_PHOTO_TRYONS_PER_DAY} photo try-ons. The 3D twin is still free.")
    if not items:
        raise ValueError("Put an outfit on your twin first.")

    with_photo, text_only, files = [], [], [me.open("rb")]
    face = face_photo_path(dataset)
    if face.exists():  # a second look at her face keeps the likeness when the outfit photos crowd the prompt
        files.append(face.open("rb"))
    for it in items[:8]:
        # a store or receipt photo shows it on a model: give the try-on the redrawn piece alone
        name = it.get("shot") if it.get("photo_from") in ("receipt", "pasted") and it.get("shot") else it.get("image")
        img = store.image_path(dataset, name) if name else None
        if not img and it.get("mockup_path"):  # a recommended piece she doesn't own yet: its drawn mock-up
            img = Path(it["mockup_path"])
        if img and len(files) < 9 + face.exists():
            with_photo.append(it)
            files.append(img.open("rb"))
        else:
            text_only.append(it)
    place = place_photo_path(dataset, scene)
    if place.exists():
        files.append(place.open("rb"))

    fit_notes = []
    for it in items:
        for z in (zones_by_item or {}).get(it.get("id"), []):
            if z.get("status") not in ("good", "unknown"):
                fit_notes.append(f"{it.get('name', 'item')} is {z['status']} at the {z['zone']}")
    pose = pose if pose in POSES else "standing"
    prompt = build_prompt(with_photo, text_only, scene, place.exists(), fit_notes, pose, notes(prof), face.exists())
    ledger.step(AGENT, "start", f"Photo try-on ({pose}) in '{scene}' with {len(with_photo)} garment photo(s), "
                f"{len(text_only)} described item(s){', real place photo' if place.exists() else ''}", {"prompt": prompt})

    out_dir = store.folder(dataset) / "tryons"
    out_dir.mkdir(exist_ok=True)
    k = image_cache.key(config.IMAGE_MODEL, "tryon", prompt, config.IMAGE_SIZE, config.IMAGE_QUALITY, *[Path(f.name) for f in files])
    with image_cache.claim(k):
        found = image_cache.find(dataset, k)
        if found:
            # same photos, outfit, scene and notes as a picture already made: show that one, $0
            for f in files:
                f.close()
            ledger.step(AGENT, "reuse", f"{found.name}: this exact try-on was made before, reused: $0")
            return next((g for g in gallery(dataset) if g.get("image") == found.name), {"image": found.name}) | {"prompt": prompt}
        ledger.before_call(AGENT)
        t0 = time.time()
        try:
            client = OpenAI(api_key=key, timeout=180, max_retries=1)
            result = client.images.edit(
                model=config.IMAGE_MODEL, image=files, prompt=prompt,
                size=config.IMAGE_SIZE, quality=config.IMAGE_QUALITY, output_format="jpeg",
            )
        finally:
            for f in files:
                f.close()
        row = ledger.record_image_call(AGENT, result.usage, seconds=time.time() - t0)
        ledger.step(AGENT, "model", f"image call: {row['input_tokens']:,} in ({row['image_input_tokens']:,} image) / {row['output_tokens']:,} out, ${row['cost_usd']:.3f}", row)
        name = f"tryon-{uuid.uuid4().hex[:8]}.jpg"
        (out_dir / name).write_bytes(base64.b64decode(result.data[0].b64_json))
        image_cache.keep(dataset, k, out_dir / name)
    entry = {"image": name, "scene": scene, "pose": pose, "key": look_key(items, scene, pose),
             "items": [i.get("name", "") for i in items], "cost_usd": row["cost_usd"],
             "at": datetime.now(timezone.utc).isoformat()}
    index = gallery(dataset)
    index.append(entry)
    (out_dir / "index.json").write_text(json.dumps(index[-200:], indent=1))
    ledger.step(AGENT, "done", f"Saved {name}")
    return entry | {"prompt": prompt}


def reject(dataset: str, image: str, issues: list[str], detail: str) -> None:
    """'What's wrong with this photo?': remember her notes for every later try-on and drop this image (and its
    360° spin), so the same look is made again instead of served from the gallery."""
    prof = store.profile(dataset)
    prof["tryon_feedback"] = (prof.get("tryon_feedback") or [])[-9:] + [
        {"issues": [k for k in issues if k in ISSUES], "detail": detail, "image": image,
         "at": datetime.now(timezone.utc).isoformat()}]
    store.save_profile(dataset, prof)
    image_cache.forget(dataset, image)
    index = gallery(dataset)
    keep = [g for g in index if g.get("image") != image]
    (store.folder(dataset) / "tryons" / "index.json").write_text(json.dumps(keep, indent=1))


def look_key(items: list[dict], scene: str, pose: str) -> str:
    """Same outfit + scene + pose = same look, so the app can reuse an image instead of paying again."""
    ids = sorted(str(i.get("id") or i.get("name", "")) for i in items)
    return "|".join(ids) + f"@{scene}#{pose}"


def forget_item(dataset: str, item_id: str) -> int:
    """An item was corrected: drop cached try-ons that used the old version, so the next one is redone."""
    index = gallery(dataset)
    keep = [g for g in index if g.get("type") == "turntable" or item_id not in g.get("key", "").split("@")[0].split("|")]
    stale = {g["image"] for g in index if g not in keep}
    keep = [g for g in keep if not (g.get("type") == "turntable" and g.get("image") in stale)]
    for img in stale:
        image_cache.forget(dataset, img)
    if len(keep) != len(index):
        (store.folder(dataset) / "tryons" / "index.json").write_text(json.dumps(keep, indent=1))
    return len(index) - len(keep)


def gallery(dataset: str) -> list[dict]:
    path = store.folder(dataset) / "tryons" / "index.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return []


# ---------------------------------------------------------------- 360° turntable
# Degrees I've turned to my right, as seen by a camera that stays put. Frame order = one full turn.
ANGLES = {
    45: "turned 45 degrees to my right: a three-quarter front view of my left side, face still partly visible",
    90: "turned 90 degrees to my right: a full side profile of my left side",
    135: "turned 135 degrees to my right: a three-quarter back view of my back and left side, face turned away",
    180: "turned all the way around: a straight back view, the camera sees my back and the back of my head, no face",
    225: "turned 135 degrees to my left: a three-quarter back view of my back and right side, face turned away",
    270: "turned 90 degrees to my left: a full side profile of my right side",
    315: "turned 45 degrees to my left: a three-quarter front view of my right side, face still partly visible",
}


def spin_prompt(view: str) -> str:
    return (
        "Image 1 is a photo of me in an outfit. Image 2 is another photo of me, for my real face, hair color and texture, and body. "
        "Make the same photo again with exactly the same person, outfit, hairstyle as in image 1, body shape and proportions, the same room, "
        "light, camera height and distance, full body head to toe and centered, in the same relaxed standing pose. "
        f"The only change: I have {view}. Keep every garment identical, including how the back of it looks. "
        "Do not slim or reshape my body. Photorealistic. Only me in the frame. No text or watermarks."
    )


def spin_key(image: str) -> str:
    return f"spin:{image}"


def run_turntable(ledger: Ledger, dataset: str, image: str) -> dict:
    """7 new angles around an existing standing try-on image, made in parallel; returns 8 frames."""
    key = config.openai_key()
    if not key:
        raise ValueError("The 360° view needs your own OPENAI_API_KEY in .env.")
    if not store.profile(dataset).get("photo_consent"):
        raise ValueError("Tick the consent box in Me first: your photo is sent to OpenAI to make the images.")
    out_dir = store.folder(dataset) / "tryons"
    src = out_dir / Path(image).name
    me = me_photo_path(dataset)
    if not src.exists() or not me.exists():
        raise ValueError("Make the standing photo of this look first, then spin it.")
    for g in gallery(dataset):
        if g.get("key") == spin_key(src.name):
            return g
    if tryons_today("photo_turntable") >= config.MAX_TURNTABLES_PER_DAY:
        ledger.safety("budget", AGENT, f"Daily limit of {config.MAX_TURNTABLES_PER_DAY} 360° views reached.")
        raise BudgetExceeded(f"You've used today's {config.MAX_TURNTABLES_PER_DAY} 360° views. Saved ones still spin for free.")
    est = 0.035 * len(ANGLES)  # measured: about $0.03 per angle with two input photos
    if est > ledger.max_usd:
        ledger.safety("budget", AGENT, f"Estimated ${est:.2f} is over the ${ledger.max_usd:.2f} cap.")
        raise BudgetExceeded(f"A 360° view would cost about ${est:.2f}, over the ${ledger.max_usd:.2f} cap.")
    ledger.step(AGENT, "start", f"360° view of {src.name}: {len(ANGLES)} angles in parallel", {"prompt": spin_prompt("<angle>")})
    for _ in ANGLES:
        ledger.before_call(AGENT)
    client = OpenAI(api_key=key, timeout=180, max_retries=1)
    stem = src.stem.replace("tryon-", "")

    def one(angle: int):
        t0 = time.time()
        with src.open("rb") as a, me.open("rb") as b:
            res = client.images.edit(model=config.IMAGE_MODEL, image=[a, b], prompt=spin_prompt(ANGLES[angle]),
                                     size=config.IMAGE_SIZE, quality=config.IMAGE_QUALITY, output_format="jpeg")
        name = f"spin-{stem}-{angle:03d}.jpg"
        (out_dir / name).write_bytes(base64.b64decode(res.data[0].b64_json))
        return angle, name, res.usage, time.time() - t0

    with ThreadPoolExecutor(max_workers=len(ANGLES)) as pool:
        done = list(pool.map(one, ANGLES))
    frames = {0: src.name}
    for angle, name, usage, secs in done:
        row = ledger.record_image_call(AGENT, usage, seconds=secs)
        ledger.step(AGENT, "model", f"{angle}°: {row['input_tokens']:,} in / {row['output_tokens']:,} out, ${row['cost_usd']:.3f}", row)
        frames[angle] = name
    entry = {"type": "turntable", "key": spin_key(src.name), "image": src.name,
             "frames": [frames[a] for a in sorted(frames)], "cost_usd": round(ledger.cost, 4),
             "at": datetime.now(timezone.utc).isoformat()}
    index = gallery(dataset)
    index.append(entry)
    (out_dir / "index.json").write_text(json.dumps(index[-200:], indent=1))
    ledger.step(AGENT, "done", f"360° view saved ({len(entry['frames'])} frames, ${ledger.cost:.3f})")
    return entry
