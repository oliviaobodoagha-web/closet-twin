"""Extra endpoints: add by link, inspo recreation, and the price watchlist."""

from __future__ import annotations

import json
import re
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from . import aesthetic, config, cutout, dupes, ledger as ledger_mod, link_import, memory, photo_tryon, product_shot, price_watch, safety, store
from .agents import cataloger, inspo, orienter, receipt
from .agents.common import BASE_LAYER_WORDS, CATEGORIES, SECTIONS, from_section, section
from .ledger import BudgetExceeded, Ledger

router = APIRouter()


def _dataset(name: Optional[str]) -> str:
    name = name or config.DEFAULT_DATASET
    if name not in store.DATASETS:
        raise HTTPException(400, f"Unknown data set {name!r}")
    return name


def _url(url: str) -> str:
    try:
        return link_import.check_url(url)
    except ValueError as e:
        raise HTTPException(400, str(e))


def _run(mode: str, dataset: str, fn, needs_key: bool = True, max_calls: Optional[int] = None,
         max_usd: Optional[float] = None):
    """Same wrapper as main._run: budgets, logging and friendly errors."""
    if needs_key and not config.key_is_set():
        raise HTTPException(500, "No API key found. Put PORTKEY_API_KEY (or your own OPENAI_API_KEY) in .env in this folder or the folder above it.")
    try:
        ledger_mod.check_rate_limit()
    except BudgetExceeded as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=429)
    lg = Ledger(mode, dataset, max_calls=max_calls, max_usd=max_usd)
    try:
        result = fn(lg)
        return {"ok": True, "result": result, "run": lg.save("ok")}
    except BudgetExceeded as e:
        return JSONResponse({"ok": False, "error": str(e), "run": lg.save("stopped_budget")}, status_code=429)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e), "run": lg.save("error")}, status_code=400)
    except Exception as e:
        traceback.print_exc()
        lg.step("Orchestrator", "error", f"{type(e).__name__}: {e}")
        return JSONResponse({"ok": False, "error": f"Something went wrong: {type(e).__name__}. Try again.",
                             "run": lg.save("error")}, status_code=500)


class LinkRequest(BaseModel):
    url: str
    dataset: Optional[str] = None


class WatchRequest(BaseModel):
    url: str
    name: str = ""
    store: Optional[str] = None
    price: Optional[float] = None
    image: Optional[str] = None
    dataset: Optional[str] = None


class DatasetRequest(BaseModel):
    dataset: Optional[str] = None


# ---- add by link -------------------------------------------------------------

@router.post("/api/closet/link")
def add_by_link(req: LinkRequest):
    ds, url = _dataset(req.dataset), _url(req.url)
    return _run("add_by_link", ds, lambda lg: cutout.finish(ds, link_import.import_link(lg, ds, url)))


@router.post("/api/closet/link-photo")
async def add_link_with_photo(file: UploadFile = File(...), url: str = Form(""), dataset: Optional[str] = Form(None)):
    """A product photo she copied from the store page (Copy Image -> paste), with its link if she has it.
    For stores that don't let apps read their pages: nothing is fetched from the store but the page itself."""
    ds = _dataset(dataset)
    url = _url(url) if url.strip() else ""
    try:
        jpeg = safety.prepare_photo(await file.read())
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _run("add_by_link", ds, lambda lg: cutout.finish(ds, link_import.import_link(lg, ds, url, jpeg)))


# ---- add from a receipt ------------------------------------------------------

@router.post("/api/closet/receipt")
async def read_receipt(file: UploadFile = File(...), dataset: Optional[str] = Form(None)):
    """Step 1: read the receipt and list its lines; nothing is added until she picks them."""
    ds = _dataset(dataset)
    raw = await file.read()
    if len(raw) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(400, f"That file is larger than {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    try:
        # a PDF becomes page images, so its product photos can be cut out like a screenshot's
        is_pdf = raw[:5] == b"%PDF-"
        pages = receipt.pdf_pages(raw) if is_pdf else [safety.prepare_photo(raw, max_side=2000)]
        sharp = receipt.pdf_pages(raw, width=2800) if is_pdf else pages  # photos are cut from these
    except ValueError as e:
        raise HTTPException(400, str(e))
    # kept until the pieces are added, so their photos can be cut from it (data/user is git-ignored)
    token = uuid.uuid4().hex
    folder = store.folder(ds) / "receipts"
    folder.mkdir(exist_ok=True)
    for n, page in enumerate(sharp, 1):
        (folder / f"{token}-{n}.jpg").write_bytes(page)
    return _run("add_receipt", ds, lambda lg: {**receipt.read(lg, pages), "token": token}, max_calls=2)


class ReceiptAdd(BaseModel):
    dataset: Optional[str] = None
    token: str = ""  # the saved receipt image, for cutting out product photos
    store: str = ""
    date: str = ""
    lines: List[dict]


def _same_receipt_piece(items: list, name: str, store_name: str, sku: str = ""):
    """A piece already added from this store's receipt: the same SKU, or else (nearly) the same name. The
    reader words lines a little differently each time ("burgundy" one read, "purple" the next), so the SKU
    printed on the receipt is the reliable key."""
    from difflib import SequenceMatcher
    if sku:
        hit = next((i for i in items if i.get("source") == "receipt" and i.get("sku") == sku
                    and (i.get("store") or "").lower() == store_name.lower()), None)
        if hit:
            return hit
    key = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
    best, score = None, 0.0
    for i in items:
        if i.get("source") != "receipt" or (i.get("store") or "").lower() != store_name.lower():
            continue
        other = re.sub(r"[^a-z0-9]+", " ", i.get("name", "").lower()).strip()
        a, b = set(key.split()) - {"with", "and", "the"}, set(other.split()) - {"with", "and", "the"}
        # same words in another order ("leggings with side pocket" / "side pocket leggings") count as a match too
        r = max(SequenceMatcher(None, key, other).ratio(), len(a & b) / max(len(a | b), 1))
        if r > score:
            best, score = i, r
    return best if score >= 0.75 else None


@router.post("/api/closet/receipt/add")
def add_receipt_lines(req: ReceiptAdd):
    """Step 2: add the lines she ticked, each with its printed size and price (no model call)."""
    ds = _dataset(req.dataset)
    if not req.lines or len(req.lines) > 30:
        raise HTTPException(400, "Pick 1 to 30 items to add.")
    store_name = safety.clean_untrusted(req.store, 60)[0]
    date = safety.clean_untrusted(req.date, 30)[0]
    pages = {}
    if re.fullmatch(r"[0-9a-f]{32}", req.token or ""):
        for path in (store.folder(ds) / "receipts").glob(f"{req.token}-*.jpg"):
            pages[int(path.stem.rsplit("-", 1)[1])] = path.read_bytes()
    existing = store.closet(ds)
    added, filled, skipped = [], [], []
    for ln in req.lines:
        if ln.get("is_clothing") is False:  # shipping, tax, gift cards
            continue
        clean = {k: (safety.clean_untrusted(v, 80)[0] if isinstance(v, str) else v) for k, v in ln.items()}
        if clean.get("category") not in CATEGORIES:
            clean["category"] = "top"
        clean.setdefault("subtype", ""); clean.setdefault("name", "Item from receipt")
        clean.setdefault("formality", 3); clean.setdefault("warmth", 2)
        page = pages.get(int(ln.get("page") or 1))
        photo = receipt.crop_photo(page, ln.get("photo_box")) if page else None
        photo = safety.prepare_photo(photo) if photo else None
        # the same receipt uploaded again: give earlier pieces their photo instead of adding them twice
        same = _same_receipt_piece(existing, clean["name"], store_name, (clean.get("sku") or "").strip())
        if same:
            if photo and not same.get("image"):
                path = store.folder(ds) / "images" / f"{same['id']}.jpg"
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(photo)
                fixed = store.update_item(ds, same["id"], {"image": path.name, "photo_from": "receipt",
                                                           "notes": same.get("notes", "").replace("; no photo yet.", "; photo cut from the receipt.")})
                filled.append(cutout.finish(ds, fixed))
            else:
                skipped.append(same["name"])
            continue
        item = receipt.to_item(clean, store_name, date)
        if photo:
            item["notes"] = item["notes"].replace("; no photo yet.", "; photo cut from the receipt.")
            item["photo_from"] = "receipt"
        new_item = store.add_item(ds, item, photo)
        added.append(cutout.finish(ds, new_item) if photo else new_item)
    for n in pages:  # photos are cut: the receipt itself isn't kept
        (store.folder(ds) / "receipts" / f"{req.token}-{n}.jpg").unlink(missing_ok=True)
    return {"ok": True, "added": memory.with_size_guesses(ds, added), "filled": memory.with_size_guesses(ds, filled),
            "skipped": skipped}


@router.post("/api/closet/{item_id}/photo")
async def add_item_photo(item_id: str, file: UploadFile = File(...), dataset: Optional[str] = Form(None)):
    """Give a piece its photo (receipt pieces start without one): pasted, dragged in or picked."""
    ds = _dataset(dataset)
    item = next((i for i in store.closet(ds) if i["id"] == item_id), None)
    if not item:
        raise HTTPException(404, "That piece isn't in your closet anymore.")
    try:
        jpeg = safety.prepare_photo(await file.read())
    except ValueError as e:
        raise HTTPException(400, str(e))
    path = store.folder(ds) / "images" / f"{item_id}.jpg"
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(jpeg)
    for old in (f"{item_id}.cut.png", f"{item_id}.shot.png"):
        (path.parent / old).unlink(missing_ok=True)
    notes = (item.get("notes") or "").replace("; no photo yet.", ".")
    fixed = store.update_item(ds, item_id, {"image": path.name, "shot": None, "cutout": None, "notes": notes})
    photo_tryon.forget_item(ds, item_id)
    return {"ok": True, "item": memory.with_size_guesses(ds, [cutout.finish(ds, fixed)])[0]}


# ---- bulk add: several photos or links in one run ------------------------------

def _bulk(ledger: Ledger, jobs: list, one, bad: list) -> dict:
    """Run one(job) for each job, BULK_WORKERS at a time. A bad photo or blocked link is skipped, not fatal;
    hitting a budget stops the batch."""
    ledger.step("Closet Cataloger", "start", f"Bulk add: {len(jobs)} pieces, {config.BULK_WORKERS} at a time")

    def safe(job):
        try:
            return {"ok": True, "index": job[2], "item": one(job)}
        except BudgetExceeded:
            raise
        except ValueError as e:
            return {"ok": False, "index": job[2], "name": job[0], "error": str(e)}
        except Exception as e:
            traceback.print_exc()
            return {"ok": False, "index": job[2], "name": job[0], "error": f"{type(e).__name__}; try it again on its own"}

    with ThreadPoolExecutor(max_workers=config.BULK_WORKERS) as pool:
        done = list(pool.map(safe, jobs))
    done = sorted(done + bad, key=lambda d: d["index"])  # one result per upload, in upload order
    added = memory.with_size_guesses(ledger.dataset, [d["item"] for d in done if d["ok"]])
    skipped = [{"name": d["name"], "error": d["error"]} for d in done if not d["ok"]]
    ledger.step("Closet Cataloger", "done", f"Added {len(added)}, skipped {len(skipped)}")
    return {"results": done, "added": added, "skipped": skipped}


@router.post("/api/closet/bulk")
async def bulk_photos(files: List[UploadFile] = File(...), dataset: Optional[str] = Form(None)):
    ds = _dataset(dataset)
    if len(files) > config.MAX_BULK_ADD:
        raise HTTPException(400, f"Up to {config.MAX_BULK_ADD} photos at a time.")
    jobs, bad = [], []
    for n, f in enumerate(files):
        try:
            jobs.append((f.filename or "photo", safety.prepare_photo(await f.read()), n))
        except ValueError as e:
            bad.append({"ok": False, "index": n, "name": f.filename or "photo", "error": str(e)})

    def flow(lg):
        def one(job):
            turn, sure = orienter.upright(lg, job[1])
            photo = cataloger.rotate_jpeg(job[1], turn)
            item = cataloger.catalog_photo(lg, photo, "" if sure else orienter.UNSURE_NOTE)
            if not item["is_clothing"]:
                raise ValueError("No clothing or shoes found in that photo.")
            # color words go on after the swatches are measured, so they only touch the shade they were said about
            return cutout.apply_color_words(ds, cutout.finish(ds, store.add_item(ds, item, photo)))
        return _bulk(lg, jobs, one, bad)

    return _run("bulk_add", ds, flow, max_calls=4 * config.MAX_BULK_ADD + 2)


class BulkLinks(BaseModel):
    urls: List[str]
    dataset: Optional[str] = None


@router.post("/api/closet/links")
def bulk_links(req: BulkLinks):
    ds = _dataset(req.dataset)
    urls = [u.strip() for u in req.urls if u.strip()]
    if not urls or len(urls) > config.MAX_BULK_ADD:
        raise HTTPException(400, f"Paste 1 to {config.MAX_BULK_ADD} links, one per line.")
    jobs, bad = [], []
    for n, u in enumerate(urls):
        try:
            jobs.append((u, link_import.check_url(u), n))
        except ValueError as e:
            bad.append({"ok": False, "index": n, "name": u, "error": str(e)})

    def flow(lg):
        return _bulk(lg, jobs, lambda job: cutout.finish(ds, link_import.import_link(lg, ds, job[1])), bad)

    return _run("bulk_add", ds, flow)


# ---- possible duplicates -----------------------------------------------------

@router.get("/api/closet/dupes")
def closet_dupes(dataset: Optional[str] = None):
    return {"pairs": dupes.pairs(_dataset(dataset))}


class NotDupes(BaseModel):
    dataset: Optional[str] = None
    a: str
    b: str


@router.post("/api/closet/not-dupes")
def mark_not_dupes(req: NotDupes):
    dupes.not_dupes(_dataset(req.dataset), req.a, req.b)
    return {"ok": True}


# ---- upright product shots (image model, own OpenAI key) ---------------------

class ShotRequest(BaseModel):
    dataset: Optional[str] = None
    ids: Optional[List[str]] = None  # None: every piece with a photo and no shot yet


@router.post("/api/closet/shots")
def product_shots(req: ShotRequest):
    ds = _dataset(req.dataset)
    if not config.openai_key():
        raise HTTPException(400, "Upright product shots need your own OPENAI_API_KEY in .env (the rest of the closet works without it).")
    items = store.closet(ds)
    ids = req.ids or [i["id"] for i in items if i.get("image") and not i.get("shot")]
    ids = [i for i in ids if any(x["id"] == i and x.get("image") for x in items)]
    left = config.MAX_PRODUCT_SHOTS_PER_DAY - product_shot.shots_today()
    if left <= 0:
        raise HTTPException(429, f"Today's {config.MAX_PRODUCT_SHOTS_PER_DAY} product shots are used up; more tomorrow.")
    ids = ids[:min(left, 16)]  # at most 16 per run (about 30 s with 8 at a time)
    if not ids:
        return {"ok": True, "result": {"done": [], "failed": []}}

    def flow(lg):
        def one(item_id):
            try:
                return {"ok": True, "item": product_shot.make(lg, ds, item_id)}
            except BudgetExceeded:
                raise
            except Exception as e:
                traceback.print_exc()
                return {"ok": False, "id": item_id, "error": f"{type(e).__name__}: {str(e)[:120]}"}
        with ThreadPoolExecutor(max_workers=8) as pool:
            done = list(pool.map(one, ids))
        return {"done": [d["item"] for d in done if d["ok"]], "failed": [d for d in done if not d["ok"]],
                "remaining": max(0, len([i for i in store.closet(ds) if i.get("image") and not i.get("shot")]))}

    return _run("product_shot", ds, flow, needs_key=False, max_calls=len(ids) + 2,
                max_usd=config.MAX_USD_PER_PRODUCT_SHOT * len(ids))


class Reshoot(BaseModel):
    dataset: Optional[str] = None
    issues: List[str] = []  # keys of product_shot.ISSUES
    color: Optional[str] = None  # what color it really is
    kind: Optional[str] = None  # what it really is (blouse, quarter-zip, ...)
    detail: Optional[str] = None


def _swap_word(name: str, old: str, new: str) -> str:
    """"Fuchsia long-sleeve polo shirt" with polo -> blouse: swap the word in place, else add the new one at the front."""
    if old and re.search(re.escape(old), name, flags=re.I):
        out = re.sub(re.escape(old), new, name, count=1, flags=re.I)
    else:
        out = f"{new} {name}"
    return out[0].upper() + out[1:]


@router.post("/api/closet/{item_id}/reshoot")
def reshoot(item_id: str, req: Reshoot):
    """'What's wrong?' -> fix the piece's own facts (color, kind), keep her notes with it, redraw the shot."""
    ds = _dataset(req.dataset)
    if not config.openai_key():
        raise HTTPException(400, "Product shots need your own OPENAI_API_KEY in .env.")
    if product_shot.shots_today() >= config.MAX_PRODUCT_SHOTS_PER_DAY:
        raise HTTPException(429, f"Today's {config.MAX_PRODUCT_SHOTS_PER_DAY} product shots are used up; more tomorrow.")
    items = store.closet(ds)
    item = next((i for i in items if i["id"] == item_id), None)
    if not item or not item.get("image"):
        raise HTTPException(404, "That piece has no photo to work from.")
    issues = [k for k in req.issues if k in product_shot.ISSUES]
    detail = safety.clean_untrusted((req.detail or "").strip(), 300)[0]
    if not issues and not detail:
        raise HTTPException(400, "Tick what's wrong (or add a note) so the next shot can fix it.")
    fields = {}
    color = safety.clean_untrusted((req.color or "").strip(), 30)[0].lower()
    old = (item.get("colors") or [{}])[0]
    if color and color != (old.get("name") or "").lower():
        cutout.learn_color(ds, old.get("name", ""), color, old.get("hex", ""))
        fields["colors"] = [{"name": color, "hex": old.get("hex", "")}] + (item.get("colors") or [])[1:]
        fields["name"] = _swap_word(item["name"], old.get("name", ""), color)
    kind = safety.clean_untrusted((req.kind or "").strip(), 30)[0].lower()
    if kind and kind != (item.get("subtype") or "").lower():
        name = fields.get("name", item["name"])
        sub = (item.get("subtype") or "").lower()
        fields["name"] = _swap_word(name, sub, kind)
        fields["subtype"] = kind
        if item.get("category") == "top":
            fields["layer"] = "base" if any(w in kind for w in BASE_LAYER_WORDS) else "main"
    if fields:
        fields["edited"] = True
    note = {"issues": issues, "detail": detail}
    fields["shot_feedback"] = (item.get("shot_feedback") or [])[-4:] + [note]
    store.update_item(ds, item_id, fields)
    if any(k in fields for k in ("colors", "subtype", "name")):
        photo_tryon.forget_item(ds, item_id)

    def flow(lg):
        return {"item": memory.with_size_guesses(ds, [product_shot.make(lg, ds, item_id)])[0]}

    return _run("product_shot", ds, flow, needs_key=False, max_calls=3, max_usd=config.MAX_USD_PER_PRODUCT_SHOT)


# ---- fix an item the cataloger got wrong -------------------------------------

class ItemEdit(BaseModel):
    dataset: Optional[str] = None
    name: Optional[str] = None
    category: Optional[str] = None
    subtype: Optional[str] = None
    color: Optional[str] = None
    rotate: int = 0  # degrees clockwise
    section: Optional[str] = None  # tops, layers, pants, skirts, ... (sets category, and layer for tops)
    out_of_season: Optional[bool] = None  # packed away: kept in the closet, left out of daily outfits


@router.post("/api/closet/{item_id}/edit")
def edit_item(item_id: str, req: ItemEdit):
    ds = _dataset(req.dataset)
    items = store.closet(ds)
    item = next((i for i in items if i["id"] == item_id), None)
    if not item:
        raise HTTPException(404, "That item isn't in the closet.")
    if req.category and req.category not in CATEGORIES:
        raise HTTPException(400, f"Category must be one of: {', '.join(CATEGORIES)}.")
    before = json.loads(json.dumps(item))
    if req.section:
        if req.section not in SECTIONS:
            raise HTTPException(400, f"Section must be one of: {', '.join(SECTIONS)}.")
        item.update(from_section(req.section))
        if req.section == "skirts" and "skirt" not in (item.get("subtype") or "").lower():
            item["subtype"] = "skirt"
        if req.section == "pants" and "skirt" in (item.get("subtype") or "").lower():
            item["subtype"] = "pants"
        if req.section == "blazers" and "blazer" not in (item.get("subtype") or "").lower():
            item["subtype"] = "blazer"
        if req.section == "jackets" and "blazer" in (item.get("subtype") or "").lower():
            item["subtype"] = "jacket"
    for field in ("name", "category", "subtype"):
        val = (getattr(req, field) or "").strip()
        if val:
            item[field] = safety.clean_untrusted(val, 80)[0]
    if item.get("category") == "top":
        base_word = any(w in (item.get("subtype") or "").lower() for w in BASE_LAYER_WORDS)
        if req.section == "tops" and base_word:
            item["subtype"] = "top"  # moved out of Tanks & camis: drop "tank" so the kind matches where it lives
        elif not req.section and req.subtype and req.subtype.strip().lower() != (before.get("subtype") or "").lower():
            item["layer"] = "base" if base_word else "main"  # retyped tank -> blouse (or back): move it with the kind
    if req.color and req.color.strip():
        name = safety.clean_untrusted(req.color.strip(), 30)[0]
        if not item.get("colors") or item["colors"][0].get("name") != name:
            if item.get("colors"):
                cutout.learn_color(ds, item["colors"][0].get("name", ""), name, item["colors"][0].get("hex", ""))
            # keep the hex measured from the photo: a rename (raspberry -> fuchsia) fixes the word, not the pixels
            old = (item.get("colors") or [{}])[0]
            item["colors"] = [{"name": name, "hex": old.get("hex", "")}] + (item.get("colors") or [])[1:]
    if req.rotate % 360 and item.get("image"):
        path = store.image_path(ds, item["image"])
        if path:
            path.write_bytes(cataloger.rotate_jpeg(path.read_bytes(), req.rotate))
            item["photo_turned"] = (item.get("photo_turned", 0) + req.rotate) % 360
    looks_changed = item != before
    if req.out_of_season is not None:
        item["out_of_season"] = req.out_of_season
    if looks_changed:
        item["edited"] = True
    store.save_closet(ds, items)
    cleared = photo_tryon.forget_item(ds, item_id) if looks_changed else 0
    if req.rotate % 360:
        item = cutout.finish(ds, item)
    return {"ok": True, "item": memory.with_size_guesses(ds, [dict(item)])[0], "cleared_tryons": cleared}


# ---- inspo -------------------------------------------------------------------

@router.post("/api/inspo/photo")
async def inspo_photo(file: UploadFile = File(...), dataset: Optional[str] = Form(None)):
    ds = _dataset(dataset)
    try:
        jpeg = safety.prepare_photo(await file.read())
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _run("inspo", ds, lambda lg: inspo.from_photo(lg, ds, jpeg))


@router.post("/api/inspo/pinterest")
def inspo_pinterest(req: LinkRequest):
    ds, url = _dataset(req.dataset), _url(req.url)
    return _run("inspo", ds, lambda lg: inspo.from_pinterest(lg, ds, url))


# ---- aesthetic board: show Margaux-Sloan what you're going for -----------------

@router.post("/api/aesthetic/photos")
async def aesthetic_photos(files: list[UploadFile] = File(...), dataset: Optional[str] = Form(None)):
    ds = _dataset(dataset)
    jpegs = []
    for f in files[:aesthetic.MAX_IMAGES]:
        try:
            jpegs.append(safety.prepare_photo(await f.read()))
        except ValueError as e:
            raise HTTPException(400, str(e))
    if not jpegs:
        raise HTTPException(400, "Add at least one picture.")
    return _run("aesthetic", ds, lambda lg: aesthetic.read(lg, ds, jpegs, "your photos", f"{len(jpegs)} uploaded picture(s)"))


@router.post("/api/aesthetic/link")
def aesthetic_link(req: LinkRequest):
    ds, url = _dataset(req.dataset), _url(req.url)

    def flow(lg):
        jpegs, kind = aesthetic.images_from_link(url)
        lg.step("Stylist", "tool", f"Got {len(jpegs)} picture(s) from the {kind} link")
        return aesthetic.read(lg, ds, jpegs, kind, url)

    return _run("aesthetic", ds, flow)


@router.get("/api/aesthetic/img/{filename}")
def aesthetic_img(filename: str, dataset: Optional[str] = None):
    path = aesthetic.folder(_dataset(dataset)) / Path(filename).name
    if not re.fullmatch(r"a-[0-9a-f]{10}\.jpg", path.name) or not path.exists():
        raise HTTPException(404)
    return FileResponse(path)


@router.delete("/api/aesthetic")
def aesthetic_clear(dataset: Optional[str] = None):
    aesthetic.clear(_dataset(dataset))
    return {"ok": True}


# ---- price watch -------------------------------------------------------------

@router.get("/api/watch")
def watch_list(dataset: Optional[str] = None):
    ds = _dataset(dataset)
    return {"items": price_watch.listing(ds), "trends": price_watch.store_trends(ds)}


@router.post("/api/watch")
def watch_add(req: WatchRequest):
    ds, url = _dataset(req.dataset), _url(req.url)
    return {"ok": True, "item": price_watch.add(ds, url, req.name, req.store or "", req.price, req.image)}


@router.delete("/api/watch/{item_id}")
def watch_remove(item_id: str, dataset: Optional[str] = None):
    price_watch.remove(_dataset(dataset), item_id)
    return {"ok": True}


@router.post("/api/watch/check")
def watch_check(req: DatasetRequest):
    ds = _dataset(req.dataset)
    return _run("price_check", ds, lambda lg: price_watch.check(lg, ds), needs_key=False)
