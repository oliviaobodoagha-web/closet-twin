"""Receipt Reader: a receipt, order confirmation or order page (photo, screenshot or PDF) -> what was bought.

Each line comes back with its printed size and price, so pieces added this way arrive with size_label already
set: the strongest evidence the size estimate gets. Order emails and order pages show a thumbnail beside each
line: the reader boxes it, and the piece's photo is cut straight out of the receipt (then cleaned up by the
cutout model and redrawn as a product shot). A PDF is turned into page images first (pypdfium2, local), so a
saved order email works the same as a screenshot. Paper receipts have no photos; those get one pasted later.
"""

from __future__ import annotations

import base64
import io

from PIL import Image

MAX_PAGES = 8  # a printed order email runs 5-6 pages

from ..ledger import Ledger
from ..llm import obj_schema, run_agent
from .common import CATEGORIES, SEASONS, instructions

AGENT = "Receipt Reader"

LINE = obj_schema({
    "is_clothing": {"type": "boolean"},
    "name": {"type": "string"},
    "brand": {"type": "string"},
    "sku": {"type": "string"},
    "color": {"type": "string"},
    "size": {"type": "string"},
    "price": {"type": "number"},
    "quantity": {"type": "integer"},
    "category": {"type": "string", "enum": CATEGORIES},
    "subtype": {"type": "string"},
    "layer": {"type": "string", "enum": ["main", "base", "n/a"]},
    "formality": {"type": "integer"},
    "warmth": {"type": "integer"},
    "seasons": {"type": "array", "items": {"type": "string", "enum": SEASONS}},
    "confidence": {"type": "string", "enum": ["high", "low"]},
    "photo_box": {"type": "array", "items": {"type": "number"}},
    "page": {"type": "integer"},
})
SCHEMA = obj_schema({"store": {"type": "string"}, "date": {"type": "string"}, "lines": {"type": "array", "items": LINE},
                     "incomplete": {"type": "string"}})


def pdf_pages(pdf: bytes, width: int = 1400) -> list[bytes]:
    """The first MAX_PAGES pages of a PDF as JPEGs `width` px wide (rendered locally). The reader gets 1400 px;
    photos are cut from a sharper 2800 px render, since email thumbnails are small."""
    import pypdfium2 as pdfium
    try:
        doc = pdfium.PdfDocument(pdf)
    except Exception as e:
        raise ValueError("That PDF couldn't be opened. Try a screenshot of the receipt instead.") from e
    pages = []
    for i in range(min(len(doc), MAX_PAGES)):
        page = doc[i]
        img = page.render(scale=width / max(page.get_width(), 1)).to_pil().convert("RGB")
        out = io.BytesIO()
        img.save(out, "JPEG", quality=88)
        pages.append(out.getvalue())
    if not pages:
        raise ValueError("That PDF has no pages.")
    return pages


def read(ledger: Ledger, pages: list[bytes]) -> dict:
    """pages: JPEG page images (a photo or screenshot is one page), EXIF already stripped."""
    content = [{"type": "input_text", "text": "List what I bought."}]
    for n, jpeg in enumerate(pages, 1):
        if len(pages) > 1:
            content.append({"type": "input_text", "text": f"Page {n}:"})
        content.append({"type": "input_image", "image_url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode(),
                        "detail": "high"})
    ledger.step(AGENT, "start", f"Reading the receipt ({len(pages)} page{'s' if len(pages) > 1 else ''})")
    out = run_agent(ledger, AGENT, instructions("receipt"), [{"role": "user", "content": content}],
                    schema=SCHEMA, schema_name="receipt", effort="low").output
    for ln in out["lines"]:
        ln["formality"] = min(max(int(ln.get("formality") or 3), 1), 5)
        ln["warmth"] = min(max(int(ln.get("warmth") or 2), 1), 5)
        ln["quantity"] = max(int(ln.get("quantity") or 1), 1)
        ln["page"] = min(max(int(ln.get("page") or 1), 1), len(pages))
    n = sum(ln["is_clothing"] for ln in out["lines"])
    if out.get("incomplete"):
        ledger.step(AGENT, "tool", f"Looks incomplete: {out['incomplete']}")
    ledger.step(AGENT, "done", f"{out['store'] or 'Receipt'}: {n} clothing item(s), {len(out['lines']) - n} other line(s)", out)
    return out


def to_item(line: dict, store: str, date: str) -> dict:
    """A receipt line as a closet item (no photo yet)."""
    item = {
        "is_clothing": True, "name": line["name"][:80], "category": line["category"], "subtype": line["subtype"],
        "layer": line.get("layer", "n/a"),
        "colors": [{"name": line["color"].lower(), "hex": ""}] if line.get("color") else [],
        "pattern": "", "fabric": "", "formality": line["formality"], "warmth": line["warmth"],
        "seasons": line.get("seasons") or [], "fit": "regular", "length": "regular",
        "toe_box": "n/a", "heel_in": 0, "walkable": line["category"] == "shoes", "comfort": 3,
        "notes": f"Added from a {store or 'store'} receipt{' (' + date + ')' if date else ''}; no photo yet.",
        "source": "receipt", "brand": line.get("brand", ""), "store": store, "price": line.get("price") or None,
    }
    if line.get("sku"):
        item["sku"] = line["sku"][:40]
    if line.get("size"):
        item["size_label"] = line["size"][:20]
    return item


def crop_photo(receipt_jpeg: bytes, box: list) -> bytes | None:
    """The product thumbnail the reader boxed, with a little margin; None if the box is unusable."""
    if not isinstance(box, list) or len(box) != 4:
        return None
    try:
        x0, y0, x1, y1 = (min(max(float(v), 0.0), 1.0) for v in box)
    except (TypeError, ValueError):
        return None
    if x1 - x0 < 0.02 or y1 - y0 < 0.01:
        return None
    img = Image.open(io.BytesIO(receipt_jpeg))
    w, h = img.size
    pad_x, pad_y = 0.15 * (x1 - x0), 0.15 * (y1 - y0)  # model boxes run a little tight or loose
    crop = img.crop((int(max(0, x0 - pad_x) * w), int(max(0, y0 - pad_y) * h),
                     int(min(1, x1 + pad_x) * w), int(min(1, y1 + pad_y) * h)))
    if min(crop.size) < 40:
        return None
    out = io.BytesIO()
    crop.convert("RGB").save(out, "JPEG", quality=92)
    return out.getvalue()
