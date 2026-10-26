"""Closet Cataloger: one photo in, one structured closet item out (vision)."""

from __future__ import annotations

import base64
import io

from PIL import Image

from ..ledger import Ledger
from ..llm import obj_schema, run_agent
from .common import CATEGORIES, SEASONS, instructions

ITEM_SCHEMA = obj_schema({
    "is_clothing": {"type": "boolean"},
    "name": {"type": "string"},
    "category": {"type": "string", "enum": CATEGORIES},
    "subtype": {"type": "string"},
    "layer": {"type": "string", "enum": ["main", "base", "n/a"]},
    "colors": {"type": "array", "items": obj_schema({"name": {"type": "string"}, "hex": {"type": "string"}})},
    "pattern": {"type": "string"},
    "fabric": {"type": "string"},
    "formality": {"type": "integer"},
    "warmth": {"type": "integer"},
    "seasons": {"type": "array", "items": {"type": "string", "enum": SEASONS}},
    "fit": {"type": "string"},
    "length": {"type": "string"},
    "toe_box": {"type": "string"},
    "heel_in": {"type": "number"},
    "walkable": {"type": "boolean"},
    "comfort": {"type": "integer"},
    "notes": {"type": "string"},
})


def catalog_photo(ledger: Ledger, jpeg: bytes, user_note: str = "") -> dict:
    url = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()
    text = "Describe this item for my closet."
    if user_note:
        text += f" My note about it: {user_note[:700]}"
    ledger.step("Closet Cataloger", "start", "Reading the photo (shrunk to 768px, EXIF/GPS removed)")
    result = run_agent(
        ledger,
        "Closet Cataloger",
        instructions("cataloger"),
        [{"role": "user", "content": [
            {"type": "input_text", "text": text},
            {"type": "input_image", "image_url": url, "detail": "high"},
        ]}],
        schema=ITEM_SCHEMA,
        schema_name="closet_item",
        effort="low",
    )
    item = result.output
    item["formality"] = min(max(int(item.get("formality", 3)), 1), 5)
    item["warmth"] = min(max(int(item.get("warmth", 2)), 1), 5)
    item["comfort"] = min(max(int(item.get("comfort", 3)), 1), 5)
    ledger.step("Closet Cataloger", "done", f"Tagged: {item['name']} ({item['category']}/{item['subtype']})", item)
    return item


def rotate_jpeg(jpeg: bytes, degrees_clockwise: int) -> bytes:
    """Turn a photo clockwise by 90/180/270 degrees."""
    if not degrees_clockwise % 360:
        return jpeg
    img = Image.open(io.BytesIO(jpeg)).rotate(-degrees_clockwise, expand=True)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=88)
    return out.getvalue()
