"""Her aesthetic board: inspiration she shows Margaux-Sloan (photos, a Pinterest board or pin, an influencer or blog page).

The stylist reads the pictures (vision) into an aesthetic: which archetypes they express, vibe words, colors,
signature pieces and styling moves. Each new batch updates the same aesthetic, so the read sharpens as she adds more.
The pictures are kept small in her data folder (git-ignored) so the board shows what she shared.
"""

from __future__ import annotations

import base64
import re
import uuid
from datetime import date
from urllib.parse import urljoin, urlsplit

from . import config, image_cache, link_import, outfit_rules, safety, store, stylists
from .agents import inspo
from .agents.common import instructions, profile_brief
from .ledger import Ledger
from .llm import obj_schema, run_agent

MAX_IMAGES = 6       # per batch sent to the model
MAX_BOARD = 18       # pictures kept on the board
_OG_RE = re.compile(r'<meta[^>]+property=["\']og:image(?::secure_url)?["\'][^>]+content=["\']([^"\']+)', re.I)
_IMG_RE = re.compile(r'<img[^>]+src=["\']([^"\']+\.(?:jpe?g|webp|png)(?:\?[^"\']*)?)', re.I)

AESTHETIC_SCHEMA = obj_schema({
    "summary": {"type": "string"},
    "archetypes": {"type": "array", "items": obj_schema({
        "name": {"type": "string", "enum": stylists.ARCHETYPES},
        "weight": {"type": "integer"},
        "why": {"type": "string"},
    })},
    "vibe_words": {"type": "array", "items": {"type": "string"}},
    "colors": {"type": "array", "items": obj_schema({"name": {"type": "string"}, "hex": {"type": "string"}})},
    "signature_pieces": {"type": "array", "items": {"type": "string"}},
    "styling_moves": {"type": "array", "items": {"type": "string"}},
    "season_note": {"type": "string"},
    "user_note": {"type": "string"},
})


def folder(dataset: str):
    path = store.folder(dataset) / "aesthetic"
    path.mkdir(exist_ok=True)
    return path


def board(profile: dict) -> dict:
    return profile.get("aesthetic") or {}


def _clean(s: str, n: int) -> str:
    return safety.clean_untrusted(s, n)[0]


def images_from_link(url: str) -> tuple[list[bytes], str]:
    """Pictures behind a link, and what kind of link it was. Raises ValueError with a friendly message."""
    host = (urlsplit(url).hostname or "").lower()
    if host.endswith("instagram.com"):
        kind = "instagram"
    elif host == "pinterest.com" or host.endswith(".pinterest.com") or host == "pin.it":
        kind = "pinterest"
    else:
        kind = "link"
    urls: list[str] = []
    if kind == "pinterest" and "/pin/" not in url and host != "pin.it":
        try:  # a board: its RSS feed lists the pins (the page itself is drawn by JavaScript)
            urls = inspo.pin_images(link_import.fetch(inspo.board_rss_url(url)).decode("utf-8", "replace"), MAX_IMAGES)
        except ValueError:
            raise
        except Exception:
            urls = []
    if not urls:
        try:
            page = link_import.fetch(url).decode("utf-8", "replace")
        except Exception:
            page = ""
        urls = inspo.pin_images(page, MAX_IMAGES) if kind == "pinterest" else []
        urls += [urljoin(url, u) for u in _OG_RE.findall(page)]
        if kind == "link":
            urls += [urljoin(url, u) for u in _IMG_RE.findall(page) if not re.search(r"logo|icon|sprite|avatar", u, re.I)]
        urls = list(dict.fromkeys(urls))[:MAX_IMAGES]
    jpegs = []
    for u in urls:
        try:
            jpegs.append(safety.prepare_photo(link_import.fetch(link_import.check_url(u), config.MAX_UPLOAD_BYTES, "image/*")))
        except Exception:
            continue
    if not jpegs:
        if kind == "instagram":
            raise ValueError("Instagram hides its pages from apps unless you're logged in. Screenshot 3–6 posts "
                             "from the page and upload them instead; that works just as well.")
        raise ValueError("I couldn't get pictures from that link (the site blocks apps). Upload screenshots instead.")
    return jpegs, kind


def read(ledger: Ledger, dataset: str, jpegs: list[bytes], source: str, label: str = "") -> dict:
    """The stylist studies the pictures and updates her read of the aesthetic."""
    jpegs = jpegs[:MAX_IMAGES]
    prof = store.profile(dataset)
    old = board(prof)
    known = ""
    if old.get("summary"):
        known = (f"\n\nWHAT MY BOARD SHOWED BEFORE ({len(old.get('pictures', []))} pictures): {old['summary']} "
                 f"Archetypes: {', '.join(_amount(a['weight']) + ' ' + a['name'] for a in old.get('archetypes', []))}. "
                 f"Vibes: {', '.join(old.get('vibe_words', []))}. Update this with the new pictures; keep what still holds.")
    text = (f"ABOUT ME:\n{profile_brief(prof, include_body=False)}\n\n{stylists.point_of_view(prof, dataset)}{known}\n\n"
            f"These {len(jpegs)} picture(s) are my aesthetic ({source}). What am I going for?")
    content = [{"type": "input_text", "text": text}] + [
        {"type": "input_image", "image_url": "data:image/jpeg;base64," + base64.b64encode(j).decode(), "detail": "low"}
        for j in jpegs]
    ledger.step("Stylist", "start", f"Studying {len(jpegs)} inspiration picture(s) from {source} (shrunk, EXIF removed)")
    out = run_agent(ledger, "Stylist", instructions("aesthetic"), [{"role": "user", "content": content}],
                    schema=AESTHETIC_SCHEMA, schema_name="aesthetic", effort="low").output

    pics = list(old.get("pictures", []))
    for j in jpegs:
        name = f"a-{uuid.uuid4().hex[:10]}.jpg"
        (folder(dataset) / name).write_bytes(j)
        pics.append({"file": name, "source": source, "at": date.today().isoformat()})
    for gone in pics[:-MAX_BOARD]:
        (folder(dataset) / gone["file"]).unlink(missing_ok=True)
    total = sum(max(0, a["weight"]) for a in out["archetypes"]) or 1
    arch = sorted(({"name": a["name"], "weight": round(100 * max(0, a["weight"]) / total), "why": _clean(a["why"], 160)}
                   for a in out["archetypes"]), key=lambda a: -a["weight"])[:3]
    prof = store.profile(dataset)
    prof["aesthetic"] = {
        "summary": _clean(out["summary"], 500), "archetypes": arch,
        "vibe_words": [_clean(w, 40) for w in out["vibe_words"][:8]],
        "colors": [{"name": _clean(c["name"], 30), "hex": c["hex"][:7]} for c in out["colors"][:6] if re.fullmatch(r"#[0-9a-fA-F]{6}", c["hex"][:7])],
        "signature_pieces": [_clean(p, 80) for p in out["signature_pieces"][:8]],
        "styling_moves": [_clean(m, 120) for m in out["styling_moves"][:6]],
        "season_note": _clean(out["season_note"], 450), "user_note": _clean(out["user_note"], 400),
        "pictures": pics[-MAX_BOARD:],
        "sources": (old.get("sources", []) + [{"kind": source, "label": _clean(label, 120), "at": date.today().isoformat()}])[-12:],
        "at": date.today().isoformat(),
    }
    store.save_profile(dataset, prof)
    weights = ", ".join(f"{a['name']} {a['weight']}%" for a in arch)
    ledger.step("Stylist", "done", f"{prof['aesthetic']['summary'][:120]} ({weights})")
    return prof["aesthetic"]


def _amount(weight: int) -> str:
    return "mostly" if weight >= 50 else "some" if weight >= 25 else "a touch of"


def brief(profile: dict) -> list[str]:
    """Lines for the stylist's point of view."""
    a = board(profile)
    if not a.get("summary"):
        return []
    lines = [f"Their aesthetic board ({len(a.get('pictures', []))} inspiration pictures they shared): {a['summary']}",
             # weights in words: agent prompts carry no stray numbers (the privacy test checks for measurement values)
             "  board archetypes: " + ", ".join(f"{_amount(x['weight'])} {x['name']}" for x in a.get("archetypes", [])),
             "  vibe: " + ", ".join(a.get("vibe_words", []))]
    if a.get("signature_pieces"):
        lines.append("  signature pieces: " + "; ".join(a["signature_pieces"]))
    if a.get("styling_moves"):
        lines.append("  styling moves: " + "; ".join(a["styling_moves"]))
    lines.append("Dress them toward this board, translated into their season's colors and their own closet.")
    return lines


def clear(dataset: str) -> None:
    prof = store.profile(dataset)
    for p in board(prof).get("pictures", []):
        (folder(dataset) / p["file"]).unlink(missing_ok=True)
    prof.pop("aesthetic", None)
    store.save_profile(dataset, prof)


def draw_goal(ledger: Ledger, dataset: str) -> dict:
    """Draw her read's goal look as an editorial photo (no face), saved next to the board pictures."""
    import time

    from openai import OpenAI
    prof = store.profile(dataset)
    read_ = (prof.get("stylist") or {}).get("read") or {}
    goal = read_.get("goal") or {}
    if not goal.get("look"):
        raise ValueError("Margaux-Sloan hasn't written a goal look yet. Tap Update my read first.")
    key = config.openai_key()
    if not key:
        raise ValueError("The goal picture needs your own OPENAI_API_KEY in .env (her strategy works without it).")
    bans = outfit_rules.bans(prof)
    look = outfit_rules.draw_guard(goal["look"], bans)  # a banned piece in the look is never drawn
    if look.split(" Never draw:")[0] != goal["look"].strip().rstrip(",;"):
        ledger.step("Orchestrator", "blocked", "Goal picture: swapped out pieces she ruled out", {"was": goal["look"], "drawn": look})
    prompt = (f"Editorial fashion photograph of the look '{goal.get('title', '')}': a woman wearing {look} "
              "Full outfit visible from the chin down to the shoes, standing naturally, the face out of frame above the "
              "top edge. Draw every piece exactly as described: flats are feminine ballet-style flats, never loafers or men's "
              "shoes. Clean warm ivory studio backdrop, soft daylight, magazine quality, realistic fabric. "
              "No text, no logos, no face.")
    ledger.step("Stylist", "start", f"Drawing the goal look: {goal.get('title', '')}", {"prompt": prompt})
    k = image_cache.key(config.IMAGE_MODEL, "goal", prompt, "1024x1536", "medium")
    with image_cache.claim(k):
        found = image_cache.find(dataset, k)
        if found:
            name = found.name
            ledger.step("Stylist", "reuse", "goal picture already drawn for this exact look, reused: $0")
        else:
            ledger.before_call("Stylist")
            t0 = time.time()
            r = OpenAI(api_key=key, timeout=180, max_retries=1).images.generate(
                model=config.IMAGE_MODEL, prompt=prompt, size="1024x1536", quality="medium", output_format="jpeg")
            row = ledger.record_image_call("Stylist", r.usage, seconds=time.time() - t0)
            ledger.step("Stylist", "model", f"goal picture: ${row['cost_usd']:.3f}", row)
            name = f"a-{uuid.uuid4().hex[:10]}.jpg"
            (folder(dataset) / name).write_bytes(base64.b64decode(r.data[0].b64_json))
            image_cache.keep(dataset, k, folder(dataset) / name)
    prof = store.profile(dataset)
    st = prof.get("stylist") or {}
    rd = st.get("read") or {}
    if (rd.get("goal") or {}).get("look") == goal["look"]:
        old = rd["goal"].get("image")
        if old and old != name:
            (folder(dataset) / old).unlink(missing_ok=True)
        rd["goal"]["image"] = name
        store.save_profile(dataset, prof)
    return {"image": name}
