"""Inspo Stylist: recreate an Instagram/Pinterest look from her own closet (vision)."""

from __future__ import annotations

import base64
import re
import urllib.parse
from datetime import datetime, timezone

from .. import config, link_import, safety, store
from ..ledger import Ledger
from ..llm import obj_schema, run_agent
from .common import CATEGORIES, closet_brief, instructions, profile_brief

MAX_PINS = 4

INSPO_SCHEMA = obj_schema({
    "look": obj_schema({
        "summary": {"type": "string"},
        "vibe_words": {"type": "array", "items": {"type": "string"}},
        "pieces": {"type": "array", "items": obj_schema({
            "description": {"type": "string"},
            "category": {"type": "string", "enum": CATEGORIES},
            "color": {"type": "string"},
        })},
    }),
    "recreate": obj_schema({
        "item_ids": {"type": "array", "items": {"type": "string"}},
        "how": {"type": "string"},
    }),
    "missing": {"type": "array", "items": obj_schema({
        "description": {"type": "string"},
        "category": {"type": "string", "enum": CATEGORIES},
        "search_query": {"type": "string"},
    })},
})


def _recreate(ledger: Ledger, dataset: str, jpegs: list[bytes], source: str) -> dict:
    prof = store.profile(dataset)
    closet = store.closet(dataset)
    text = (f"WHAT I OWN:\n{closet_brief(closet)}\n\nABOUT ME:\n{profile_brief(prof, include_body=False)}\n\n"
            f"Recreate the look in {'these images' if len(jpegs) > 1 else 'this image'} from my closet.")
    content = [{"type": "input_text", "text": text}] + [
        {"type": "input_image", "image_url": "data:image/jpeg;base64," + base64.b64encode(j).decode(), "detail": "low"}
        for j in jpegs
    ]
    ledger.step("Inspo Stylist", "start", f"Reading {len(jpegs)} inspo image(s) from {source} (shrunk, EXIF removed)")
    out = run_agent(ledger, "Inspo Stylist", instructions("inspo"), [{"role": "user", "content": content}],
                    schema=INSPO_SCHEMA, schema_name="inspo", effort="low").output

    ids = out["recreate"]["item_ids"]
    bad = safety.unknown_item_ids(ids, closet)
    if bad:
        ledger.safety("grounding", "Inspo Stylist", f"Dropped {len(bad)} item id(s) that aren't in the closet.", bad)
    out["recreate"]["item_ids"] = [i for i in dict.fromkeys(ids) if i not in bad]
    by_id = {i["id"]: i for i in closet}
    out["recreate"]["items"] = [{"id": i, "name": by_id[i]["name"], "image": by_id[i].get("image")}
                                for i in out["recreate"]["item_ids"]]
    out["source"] = source

    # The stylist learns from inspiration: keep the last 30 vibes on the profile.
    words = [safety.clean_untrusted(w, 40)[0] for w in out["look"]["vibe_words"][:6]]
    prof = store.profile(dataset)
    prof["inspo"] = (prof.get("inspo", []) + [{
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": safety.clean_untrusted(out["look"]["summary"], 200)[0],
        "vibe_words": words,
    }])[-30:]
    store.save_profile(dataset, prof)
    ledger.step("Inspo Stylist", "done", f"{len(out['recreate']['item_ids'])} closet piece(s), {len(out['missing'])} missing; "
                f"vibes: {', '.join(words)}")
    return out


def from_photo(ledger: Ledger, dataset: str, jpeg: bytes) -> dict:
    return _recreate(ledger, dataset, [jpeg], "screenshot")


# ---- Pinterest ---------------------------------------------------------------

_PIN_IMG_RE = re.compile(r"https://i\.pinimg\.com/[^\s\"'<>\\]+?\.(?:jpg|jpeg|png|webp)", re.IGNORECASE)


def board_rss_url(board_url: str) -> str:
    """https://www.pinterest.com/<user>/<board>/ -> https://www.pinterest.com/<user>/<board>.rss"""
    parts = urllib.parse.urlsplit(board_url.strip())
    host = (parts.hostname or "").lower()
    if not (host == "pinterest.com" or host.endswith(".pinterest.com")):
        raise ValueError("That isn't a Pinterest board link.")
    segs = [s for s in parts.path.split("/") if s]
    if len(segs) < 2:
        raise ValueError("Paste a board link like pinterest.com/<user>/<board>.")
    board = segs[1].removesuffix(".rss")
    return f"https://www.pinterest.com/{segs[0]}/{board}.rss"


def pin_images(text: str, limit: int = MAX_PINS) -> list[str]:
    """Unique pin image URLs, upgraded to the 736px version."""
    urls = []
    for u in _PIN_IMG_RE.findall(text):
        u = re.sub(r"pinimg\.com/\d+x(\d+)?/", "pinimg.com/736x/", u)
        if u not in urls and "/avatars/" not in u and "/75x75" not in u:
            urls.append(u)
    return urls[:limit]


def from_pinterest(ledger: Ledger, dataset: str, board_url: str) -> dict:
    rss = board_rss_url(board_url)
    blocked = ValueError("Pinterest blocked that board; upload screenshots instead.")
    # The board's HTML is rendered by JavaScript (only logos come back), so read its RSS feed.
    try:
        urls = pin_images(link_import.fetch(rss).decode("utf-8", errors="replace"))
    except Exception as e:
        ledger.step("Inspo Stylist", "error", f"Pinterest feed failed ({type(e).__name__})")
        urls = []
    if not urls:
        raise blocked
    jpegs = []
    for u in urls:
        try:
            jpegs.append(safety.prepare_photo(link_import.fetch(u, config.MAX_UPLOAD_BYTES, "image/*")))
        except Exception:
            continue
    if not jpegs:
        raise blocked
    ledger.step("Inspo Stylist", "tool", f"Downloaded {len(jpegs)} pin image(s) from the board")
    return _recreate(ledger, dataset, jpegs, "pinterest")
