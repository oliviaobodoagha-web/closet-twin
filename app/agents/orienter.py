"""Photo Orienter: turns flat-lay photos upright before they are tagged.

Measured on Olivia's own 23 photos turned all four ways (92 cases): asking the cataloger "which way is up"
inside its tagging call got 84% right; picking the upright view from a 2x2 sheet of the background-removed
garment got 93%; three such picks on differently shuffled sheets, turning only when 2+ agree, got 96%.
That last one is what runs here: 3 small calls at the same time, about $0.0005 a photo.
"""

from __future__ import annotations

import base64
import io
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image, ImageDraw

from .. import cutout
from ..ledger import Ledger
from ..llm import obj_schema, run_agent
from .common import instructions

AGENT = "Photo Orienter"
SCHEMA = obj_schema({"reasoning": {"type": "string"}, "upright_option": {"type": "string", "enum": ["A", "B", "C", "D"]}})
# each vote shows the four turns (degrees clockwise) in a different order, so a bias toward one letter or
# position can't decide the answer
ORDERS = [(0, 90, 180, 270), (180, 270, 0, 90), (90, 0, 270, 180)]


def _garment_on_white(img: Image.Image) -> Image.Image:
    m = cutout.mask(img)
    alpha = Image.fromarray((np.clip((m - 0.15) / 0.7, 0, 1) * 255).astype(np.uint8))
    out = Image.new("RGB", img.size, "white")
    out.paste(img, mask=alpha)
    box = alpha.point(lambda v: 255 if v > 40 else 0).getbbox()
    return out.crop(box) if box else out


def _sheet(garment: Image.Image, order: tuple, cell: int = 384) -> str:
    g = garment.copy()
    g.thumbnail((cell - 24, cell - 24))
    sheet = Image.new("RGB", (cell * 2, cell * 2), "white")
    draw = ImageDraw.Draw(sheet)
    for n, (label, deg) in enumerate(zip("ABCD", order)):
        t = g.rotate(-deg, expand=True, fillcolor="white")
        x, y = (n % 2) * cell, (n // 2) * cell
        sheet.paste(t, (x + (cell - t.width) // 2, y + (cell - t.height) // 2))
        draw.rectangle([x, y, x + cell - 1, y + cell - 1], outline="#cccccc")
        draw.rectangle([x + 4, y + 4, x + 36, y + 36], fill="black")
        draw.text((x + 15, y + 13), label, fill="white")
    buf = io.BytesIO()
    sheet.save(buf, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


# Told to the cataloger when the votes split: a sideways pair of shorts can pass for a short-sleeve top
# (leg openings read as sleeves, the waistband as a collar), as happened with Olivia's cream shorts.
UNSURE_NOTE = ("The photo's orientation was uncertain, so it may be sideways. Before naming it, check top vs "
               "bottoms: two leg openings with a waistband (button, zip fly, belt loops or elastic) mean shorts, "
               "pants or a skirt; a neck opening between two sleeves means a top.")


def upright_turn(ledger: Ledger, jpeg: bytes) -> int:
    """Degrees to turn the photo clockwise so the garment stands upright (0 when unsure)."""
    return upright(ledger, jpeg)[0]


def upright(ledger: Ledger, jpeg: bytes) -> tuple[int, bool]:
    """(degrees to turn clockwise, sure): sure only when all three votes agree."""
    try:
        garment = _garment_on_white(Image.open(io.BytesIO(jpeg)).convert("RGB"))
    except Exception as e:  # no cutout model: leave the photo as taken
        ledger.step(AGENT, "error", f"Skipped (cutout unavailable: {type(e).__name__})")
        return 0, False
    def vote(order):
        out = run_agent(ledger, AGENT, instructions("orienter"), [{"role": "user", "content": [
            {"type": "input_text", "text": "Which option shows the garment upright, as worn?"},
            {"type": "input_image", "image_url": _sheet(garment, order), "detail": "high"},
        ]}], schema=SCHEMA, schema_name="orientation", effort="low").output
        return order["ABCD".index(out["upright_option"])]

    with ThreadPoolExecutor(max_workers=len(ORDERS)) as pool:  # the 3 votes run at once
        votes = list(pool.map(vote, ORDERS))
    best = max(set(votes), key=votes.count)
    turn = best if votes.count(best) >= 2 else 0
    sure = votes.count(best) == len(votes)
    ledger.step(AGENT, "done", f"Votes {votes} -> turn {turn}° clockwise" + ("" if votes.count(best) >= 2 else " (no majority: left as taken)")
                + ("" if sure else "; votes split, so the cataloger is asked to double-check top vs bottoms"))
    return turn, sure
