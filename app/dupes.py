"""Duplicate check: the same photo uploaded twice, or two pieces that look like the same garment.

Nothing is removed on its own: the closet shows the pairs and she decides (remove one, or "not duplicates",
which is remembered on both pieces so the pair never comes back).
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from . import cutout, store

SAME_PHOTO = 4     # mean pixel difference (0-255) of two 32x32 thumbnails that are the same photo, re-saved
SAME_COLOR = 12    # Lab distance between main colors for "same kind and color"


def thumb(path):
    """32x32 color thumbnail. The same photo uploaded twice differs by ~0-2 per pixel; two photos of
    different pieces on the same carpet still differ by 10+ (a 64-bit hash called those the same)."""
    try:
        img = Image.open(path)
        img.draft("RGB", (128, 128))  # fast JPEG decode at low resolution
        return np.asarray(img.convert("RGB").resize((32, 32)), dtype=np.float32)
    except Exception:
        return None


def _why(a: dict, b: dict, ha, hb) -> str | None:
    if b["id"] in (a.get("not_dupes") or []) or a["id"] in (b.get("not_dupes") or []):
        return None
    if a.get("sku") and b.get("sku"):  # receipts print a SKU: different SKUs are different pieces
        return "same item number on the receipt" if a["sku"] == b["sku"] else None
    if ha is not None and hb is not None and float(np.abs(ha - hb).mean()) <= SAME_PHOTO:
        return "same photo"
    ca, cb = (a.get("colors") or [{}])[0], (b.get("colors") or [{}])[0]
    if (a.get("category") == b.get("category") and (a.get("subtype") or "").lower() == (b.get("subtype") or "").lower()
            and (a.get("length") or "") == (b.get("length") or "")
            and {c.get("name") for c in a.get("colors") or []} == {c.get("name") for c in b.get("colors") or []}
            and (a.get("pattern") or "").lower() == (b.get("pattern") or "").lower()
            and cutout._shade_gap(ca.get("hex"), cb.get("hex")) <= SAME_COLOR):
        return f"same kind ({a.get('subtype') or a.get('category')}) and color"
    return None


def pairs(dataset: str) -> list[dict]:
    """Every pair that might be the same piece: [{a, b, why}] with a the one added first."""
    items = store.closet(dataset)
    thumbs = {}
    for it in items:
        path = store.image_path(dataset, it["image"]) if it.get("image") else None
        thumbs[it["id"]] = thumb(path) if path else None
    out = []
    for i, a in enumerate(items):
        for b in items[i + 1:]:
            why = _why(a, b, thumbs[a["id"]], thumbs[b["id"]])
            if why:
                out.append({"a": a["id"], "b": b["id"], "why": why})
    return out


def not_dupes(dataset: str, a: str, b: str) -> None:
    """She says these two are different pieces: remember it on both."""
    for x, y in ((a, b), (b, a)):
        item = next((i for i in store.closet(dataset) if i["id"] == x), None)
        if item:
            store.update_item(dataset, x, {"not_dupes": sorted(set(item.get("not_dupes") or []) | {y})})
