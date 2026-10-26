"""Product Photographer: turns a flat-lay closet photo into an upright store-style product shot.

A cutout can remove the floor, but a sweater photographed lying flat still looks flat. The image model
(gpt-image on Olivia's own OPENAI_API_KEY, like the photo try-on) redraws the same garment standing upright
on an invisible mannequin, front view, on white; the cutout model then removes the white so it sits on the
closet tile. The original photo is kept: the try-on and the color swatches still use the real one.
About $0.02 per piece, capped per day (MAX_PRODUCT_SHOTS_PER_DAY) and per shot.
"""

from __future__ import annotations

import base64
import io
import time

from openai import OpenAI
from PIL import Image

from . import config, cutout, image_cache, photo_tryon, store
from .ledger import BudgetExceeded, Ledger

AGENT = "Product Photographer"
SIZE, QUALITY = "1024x1024", "medium"
EST_USD = 0.02

HOW = {
    "tops": "on an invisible mannequin (ghost mannequin), front view, sleeves hanging naturally at the sides",
    "layers": "on an invisible mannequin, front view, straps or shoulders as worn",
    "blazers": "on an invisible mannequin, front view, buttoned as it is in the photo, lapels and sleeves hanging naturally",
    "jackets": "on an invisible mannequin, front view, sleeves hanging naturally at the sides",
    "dresses": "on an invisible mannequin, front view, full length, skirt falling naturally",
    "pants": "standing upright as if worn by an invisible person, front view, waistband at the top, legs straight down",
    "skirts": "as if worn by an invisible person, front view, waistband at the top, hem falling naturally",
    "swim": "front view as if worn by an invisible person",
    "activewear": "on an invisible mannequin, front view",
    "shoes": "a pair, three-quarter side view, standing on their soles",
    "accessories": "front view, standing upright",
}

# What she can tick in "What's wrong?" (Edit -> Redo product shot). Each becomes an instruction for the next shot.
ISSUES = {
    "color": "the color was wrong",
    "type": "it was drawn as the wrong kind of garment",
    "neckline": "the neckline or collar was wrong",
    "sleeves": "the sleeves were wrong (length, shape or cuffs)",
    "shape": "the length, fit or shape was wrong",
    "pattern": "the pattern, print or fabric texture was wrong",
    "details": "buttons, zips, logos, lace or other details were wrong",
    "extra": "something was added or left out",
    "wrinkles": "it looked wrinkled or creased; show it freshly steamed, smooth and pressed",
    "angle": "it wasn't upright, front-facing or fully in frame",
}


def corrections(item: dict) -> str:
    """Her feedback on earlier shots of this piece, newest last; it stays with the piece for every redo."""
    notes = item.get("shot_feedback") or []
    if not notes:
        return ""
    lines = []
    for n in notes[-3:]:
        said = "; ".join(ISSUES[k] for k in n.get("issues", []) if k in ISSUES)
        lines.append(" ".join(x for x in (said and f"Last time {said}.", n.get("detail") and f"The owner says: {n['detail'].rstrip('.')}.") if x))
    return ("Corrections from the owner, who checked earlier versions against the real garment (follow them over "
            "anything you infer from the photo): " + " ".join(lines) + " ")


def prompt(item: dict) -> str:
    sec = item.get("section") or ""
    color = " / ".join(c.get("name", "") for c in item.get("colors") or []) or "as in the photo"
    worn = item.get("photo_from") in ("receipt", "pasted")  # store photos usually show it on a model
    sub = (item.get("subtype") or "").lower()
    how = ("laid flat in a gentle curve, its whole length visible, clasp or buckle showing" if "belt" in sub
           else "laid flat in a soft curve, clasp showing" if sub in ("necklace", "bracelet") else HOW.get(sec, "upright, front view"))
    return (
        f"E-commerce product photo of exactly the garment in this photo: {item.get('name', 'the garment')}. "
        + (f"The photo may show it worn by a model with other clothes: draw only the {item.get('name', 'garment')}, "
           "no person and nothing else they wear. " if worn else "")
        + f"Show it {how}. "
        + (f"Details to keep: {item['notes'][:300].rstrip('.')}. " if item.get("notes") else "")
        + corrections(item)
        + ("It is a store photo; " if worn else "It was photographed lying flat on a floor in dim indoor light; ")
        + "show it the way a store shows it: freshly "
        "steamed and smooth, with no wrinkles or fold creases (keep real pleats, tucks and gathers). "
        "Keep it identical: the same cut, length and proportions, neckline, sleeves, fabric texture, knit or weave, "
        f"pattern or print, logos and text, buttons, zips, pockets and stitching. Its color is {color}: render that "
        "true color as in neutral daylight. Add nothing and remove nothing: no person, no visible mannequin, "
        "no hanger, no props, no extra garments. Plain pure white background, soft even studio light, a soft "
        "shadow, the whole garment centered with space around it."
    )


def shots_today() -> int:
    return photo_tryon.tryons_today(mode="product_shot")


def make(ledger: Ledger, dataset: str, item_id: str) -> dict:
    """Make (or remake) one item's product shot; returns the updated item."""
    key = config.openai_key()
    if not key:
        raise ValueError("Product shots need your own OPENAI_API_KEY in .env.")
    item = next((i for i in memory_items(dataset) if i["id"] == item_id), None)
    path = store.image_path(dataset, item["image"]) if item and item.get("image") else None
    if not path:
        raise ValueError("That piece has no photo to work from.")
    if ledger.cost + EST_USD > ledger.max_usd:
        raise BudgetExceeded(f"A product shot costs about ${EST_USD:.2f}, over this run's ${ledger.max_usd:.2f} cap.")
    ledger.step(AGENT, "start", f"Upright product shot of {item['name']}", {"prompt": prompt(item)})
    name = f"{item_id}.shot.png"
    k = image_cache.key(config.IMAGE_MODEL, "shot", prompt(item), SIZE, QUALITY, path)
    with image_cache.claim(k):
        found = image_cache.find(dataset, k)
        if found:
            # same photo, same notes: this exact shot was drawn before
            if found != path.parent / name:
                (path.parent / name).write_bytes(found.read_bytes())
            ledger.step(AGENT, "reuse", f"{name}: same photo and notes as a shot already drawn, reused: $0")
            return store.update_item(dataset, item_id, {"shot": name})
        item = _draw(ledger, dataset, item, item_id, path, name)
        image_cache.forget(dataset, name)  # the file was overwritten: older keys for it are stale
        image_cache.keep(dataset, k, path.parent / name)
        return item


def _draw(ledger: Ledger, dataset: str, item: dict, item_id: str, path, name: str) -> dict:
    key = config.openai_key()
    ledger.before_call(AGENT)
    t0 = time.time()
    client = OpenAI(api_key=key, timeout=180, max_retries=1)
    with path.open("rb") as f:
        res = client.images.edit(model=config.IMAGE_MODEL, image=[f], prompt=prompt(item),
                                 size=SIZE, quality=QUALITY, output_format="png")
    row = ledger.record_image_call(AGENT, res.usage, seconds=time.time() - t0)
    shot = base64.b64decode(res.data[0].b64_json)
    # white studio background -> transparent, cropped with a margin, like every other closet tile
    jpeg = io.BytesIO()
    Image.open(io.BytesIO(shot)).convert("RGB").save(jpeg, "JPEG", quality=92)
    png, _ = cutout.process(jpeg.getvalue())
    (path.parent / name).write_bytes(png)
    ledger.step(AGENT, "done", f"Saved {name} (${row['cost_usd']:.3f})")
    return store.update_item(dataset, item_id, {"shot": name})


def memory_items(dataset: str) -> list[dict]:
    """Closet items with their section (the prompt depends on it)."""
    from .agents.common import section
    items = store.closet(dataset)
    for it in items:
        it["section"] = section(it)
    return items
