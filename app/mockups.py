"""Stylist mock-ups: a picture of each recommended piece, and the outfit it makes with what she already owns.

For each of the Wardrobe Recommender's 3 pieces, the image model (her own OPENAI_API_KEY, like the try-on)
1. draws the new piece as a store product photo (it doesn't exist in her closet yet), then
2. lays it out with the closet pieces it pairs with as an editorial outfit flat-lay, styled for the look she asked for.
No photo of her is used here; "See it on me" goes through the photo try-on and its consent.
About $0.05 per piece, under the shared daily image cap.
"""

from __future__ import annotations

import base64
import io
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI
from PIL import Image

from . import config, cutout, image_cache, outfit_rules, store
from .ledger import BudgetExceeded, Ledger

AGENT = "Mock-up Artist"
EST_USD = 0.05  # two image calls per piece


def folder(dataset: str):
    path = store.folder(dataset) / "mockups"
    path.mkdir(exist_ok=True)
    return path


def _photo(dataset: str, item: dict):
    """Cleanest picture of a closet piece: its product shot, else the cutout, else the photo."""
    for name in (item.get("shot"), item.get("cutout"), item.get("image")):
        path = store.image_path(dataset, name) if name else None
        if path:
            return path
    return None


def piece_prompt(gap: dict) -> str:
    colors = " / ".join(c.get("name", "") for c in gap.get("colors") or []) or "a color from the description"
    return (f"E-commerce product photo of a {gap['piece']}, in {colors}. Shown the way a store shows it: on an invisible "
            "mannequin for clothing (a pair at a three-quarter angle for shoes, upright for bags), freshly steamed, front view, "
            "centered with space around it, plain pure white background, soft even studio light. No person, no text, no logo.")


def board_prompt(gap: dict, names: list[str], look: str) -> str:
    listed = "; ".join(f"image {n + 2}: my {name}" for n, name in enumerate(names))
    return (f"An editorial outfit flat-lay for a fashion magazine, styled as one complete outfit"
            + (f" for the look '{look}'" if look else "") + ". "
            f"Arrange exactly these pieces, neatly laid out as they'd be worn (top above bottom, shoes at the bottom, bag to the "
            f"side): image 1: the new {gap['piece']}; {listed}. Keep every piece identical to its picture: same color, cut, "
            "print and details, but freshly steamed and pressed, with no wrinkles or creases. Draw nothing else: no person, no extra clothes, no props, no text or labels. Soft ivory linen "
            "background, soft daylight from the top left, gentle shadows.")


def _save_png(raw: bytes, path) -> None:
    jpeg = io.BytesIO()
    Image.open(io.BytesIO(raw)).convert("RGB").save(jpeg, "JPEG", quality=92)
    png, _ = cutout.process(jpeg.getvalue())  # white studio background -> transparent, like closet tiles
    path.write_bytes(png)


def make(ledger: Ledger, dataset: str, gaps: list[dict], look: str = "") -> list[dict]:
    """[{piece, image, board}] in the same order as gaps (image/board are file names, or None if a step failed)."""
    key = config.openai_key()
    if not key:
        raise ValueError("Mock-ups need your own OPENAI_API_KEY in .env (the recommendations work without it).")
    if EST_USD * len(gaps) > ledger.max_usd:
        raise BudgetExceeded(f"Mock-ups cost about ${EST_USD * len(gaps):.2f}, over this run's ${ledger.max_usd:.2f} cap.")
    by_id = {i["id"]: i for i in store.closet(dataset)}
    # her no's: a banned piece (a stale page can still send one) or closet piece is never drawn
    bans = outfit_rules.bans(store.profile(dataset))
    never = " " + outfit_rules.never_line(bans)
    for g in gaps:
        if outfit_rules.banned(g, bans):
            ledger.step(AGENT, "blocked", f"Not drawing {g['piece']}", outfit_rules.ban_reason(g, bans))
        g["outfit_ids"] = [i for i in g.get("outfit_ids") or [] if i in by_id and not outfit_rules.banned(by_id[i], bans)]
    gaps = [g for g in gaps if not outfit_rules.banned(g, bans)]
    out_dir = folder(dataset)
    token = uuid.uuid4().hex[:8]
    client = OpenAI(api_key=key, timeout=180, max_retries=1)
    ledger.step(AGENT, "start", f"Drawing {len(gaps)} piece(s) and their outfits" + (f" for '{look}'" if look else ""),
                {"piece_prompt": piece_prompt(gaps[0]) if gaps else "", "board_prompt": board_prompt(gaps[0], ["<closet pieces>"], look) if gaps else ""})

    def one(n_gap):
        n, gap = n_gap
        res = {"piece": gap["piece"], "image": None, "board": None}
        calls = []
        prompt = piece_prompt(gap) + never
        k = image_cache.key(config.IMAGE_MODEL, "piece", prompt, "1024x1024", "medium")
        with image_cache.claim(k):
            piece = image_cache.find(dataset, k)
            if piece:
                calls.append((None, 0, f"piece: {gap['piece']} (already drawn, reused)"))
            else:
                ledger.before_call(AGENT)
                t0 = time.time()
                r = client.images.generate(model=config.IMAGE_MODEL, prompt=prompt, size="1024x1024",
                                           quality="medium", output_format="png")
                calls.append((r.usage, time.time() - t0, f"piece: {gap['piece']}"))
                piece = out_dir / f"{token}-{n}-piece.png"
                _save_png(base64.b64decode(r.data[0].b64_json), piece)
                image_cache.keep(dataset, k, piece)
        res["image"] = piece.name
        pieces = [by_id[i] for i in gap.get("outfit_ids") or [] if i in by_id]
        photos = [(p["name"], _photo(dataset, p)) for p in pieces]
        photos = [(name, path) for name, path in photos if path][:6]
        if photos:
            prompt = board_prompt(gap, [x for x, _ in photos], look) + never
            k = image_cache.key(config.IMAGE_MODEL, "board", prompt, "1024x1024", "medium", piece, *[path for _, path in photos])
            with image_cache.claim(k):
                board = image_cache.find(dataset, k)
                if board:
                    calls.append((None, 0, f"outfit: {gap.get('outfit_title') or gap['piece']} (already drawn, reused)"))
                else:
                    ledger.before_call(AGENT)
                    t0 = time.time()
                    files = [piece.open("rb")] + [path.open("rb") for _, path in photos]
                    try:
                        r = client.images.edit(model=config.IMAGE_MODEL, image=files, prompt=prompt,
                                               size="1024x1024", quality="medium", output_format="jpeg")
                    finally:
                        for f in files:
                            f.close()
                    calls.append((r.usage, time.time() - t0, f"outfit: {gap.get('outfit_title') or gap['piece']}"))
                    board = out_dir / f"{token}-{n}-board.jpg"
                    board.write_bytes(base64.b64decode(r.data[0].b64_json))
                    image_cache.keep(dataset, k, board)
            res["board"] = board.name
        return res, calls

    with ThreadPoolExecutor(max_workers=3) as pool:
        done = list(pool.map(one, enumerate(gaps)))
    results = []
    for res, calls in done:
        for usage, secs, what in calls:
            if usage is None:
                ledger.step(AGENT, "reuse", f"{what}: $0")
                continue
            row = ledger.record_image_call(AGENT, usage, seconds=secs)
            ledger.step(AGENT, "model", f"{what}: ${row['cost_usd']:.3f}", row)
        results.append(res)
    ledger.step(AGENT, "done", f"{sum(1 for r in results if r['image'])} piece(s), {sum(1 for r in results if r['board'])} outfit board(s)")
    return results
