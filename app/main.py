"""Closet Twin web server: serves the app and the agent API on http://127.0.0.1:8000."""

from __future__ import annotations

import json
import traceback
from datetime import date
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import aesthetic, body_model, color_style, config, cutout, ledger as ledger_mod, memory, outfit_rules, photo_tryon, safety, store, stylists
from .agents import analyst
from .agents import cataloger, orchestrator, orienter
from .ledger import BudgetExceeded, Ledger
from .tools import calendar_tools, weather

app = FastAPI(title="Closet Twin")


@app.on_event("startup")
def _cutout_backfill():
    """Product-style cutouts for pieces added before cutouts existed (background thread, about 1 s each)."""
    import threading

    def run():
        for ds in store.DATASETS:
            cutout.backfill(ds)
    threading.Thread(target=run, daemon=True).start()


@app.middleware("http")
async def no_stale_pages(request, call_next):
    """Browsers must always load the current app files (no stale cached JavaScript)."""
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


def _personal(name: Optional[str] = None) -> str:
    """Photos of a real person always belong to 'user' (never the committed sample data set)."""
    return "user"


def _dataset(name: Optional[str]) -> str:
    name = name or config.DEFAULT_DATASET
    if name not in store.DATASETS:
        raise HTTPException(400, f"Unknown data set {name!r}")
    return name


def _run(mode: str, dataset: str, fn, max_usd: Optional[float] = None):
    """Run one agent flow with budgets, logging and friendly errors."""
    if not config.key_is_set():
        raise HTTPException(500, "No API key found. Put PORTKEY_API_KEY (or your own OPENAI_API_KEY) in .env in this folder or the folder above it.")
    try:
        ledger_mod.check_rate_limit()
    except BudgetExceeded as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=429)
    lg = Ledger(mode, dataset, max_usd=max_usd)
    try:
        result = fn(lg)
        run = lg.save("ok")
        return {"ok": True, "result": result, "run": run}
    except BudgetExceeded as e:
        run = lg.save("stopped_budget")
        return JSONResponse({"ok": False, "error": str(e), "run": run}, status_code=429)
    except ValueError as e:
        run = lg.save("error")
        return JSONResponse({"ok": False, "error": str(e), "run": run}, status_code=400)
    except Exception as e:
        traceback.print_exc()
        lg.step("Orchestrator", "error", f"{type(e).__name__}: {e}")
        run = lg.save("error")
        return JSONResponse({"ok": False, "error": f"Something went wrong: {type(e).__name__}. Try again.", "run": run}, status_code=500)


# ---- status ---------------------------------------------------------------

@app.get("/api/status")
def status():
    return {
        "key_set": config.key_is_set(),
        "provider": config.provider(),
        "model": config.MODEL_NAME,
        "default_dataset": config.DEFAULT_DATASET,
        "spent_today_usd": round(ledger_mod.spent_today_usd(images=False), 4),
        "spent_today_images_usd": round(ledger_mod.spent_today_usd(images=True), 4),
        "limits": {
            "max_tokens_per_run": config.MAX_TOKENS_PER_RUN,
            "max_usd_per_run": config.MAX_USD_PER_RUN,
            "max_usd_per_live_web_run": config.MAX_USD_PER_LIVE_WEB_RUN,
            "max_usd_per_day": config.MAX_USD_PER_DAY,
            "max_runs_per_minute": config.MAX_RUNS_PER_MINUTE,
        },
    }


# ---- profile & closet -----------------------------------------------------

@app.get("/api/profile")
def get_profile(dataset: Optional[str] = None):
    return store.profile(_dataset(dataset))


@app.put("/api/profile")
def put_profile(data: dict, dataset: Optional[str] = None):
    # Merge, so a page with a stale copy can't wipe fields set elsewhere (consent, analysis, calendar link).
    ds = _dataset(dataset)
    old = store.profile(ds)
    if isinstance(data.get("stylist"), dict):
        # the stylist block is shared with server-side writers (answers, her read, push date): merge, never replace,
        # and only the page's house rules can change it here
        data["stylist"] = {**(old.get("stylist") or {}), **{k: v for k, v in data["stylist"].items() if k == "extra_rules"}}
    store.save_profile(ds, old | data)
    return {"ok": True}


@app.get("/api/closet")
def get_closet(dataset: Optional[str] = None):
    ds = _dataset(dataset)
    return memory.with_size_guesses(ds, store.closet(ds))


@app.post("/api/closet/photo")
async def catalog_photo(file: UploadFile = File(...), note: str = Form(""), dataset: Optional[str] = Form(None)):
    ds = _dataset(dataset)
    raw = await file.read()
    try:
        jpeg = safety.prepare_photo(raw)
    except ValueError as e:
        raise HTTPException(400, str(e))

    def flow(lg: Ledger):
        turn, sure = orienter.upright(lg, jpeg)
        photo = cataloger.rotate_jpeg(jpeg, turn)
        item = cataloger.catalog_photo(lg, photo, " ".join(x for x in (note, "" if sure else orienter.UNSURE_NOTE) if x))
        if not item["is_clothing"]:
            raise ValueError("I couldn't find a clothing item or shoes in that photo.")
        return cutout.apply_color_words(ds, cutout.finish(ds, store.add_item(ds, item, photo)))

    return _run("add_to_closet", ds, flow)


@app.post("/api/closet")
def save_item(item: dict, dataset: Optional[str] = None):
    ds = _dataset(dataset)
    item.pop("size_guess", None)  # computed on read, never stored
    item.pop("section", None)
    item.pop("v", None)
    items = store.closet(ds)
    items = [item if i["id"] == item.get("id") else i for i in items]
    if not any(i["id"] == item.get("id") for i in items):
        return store.add_item(ds, item, None)
    store.save_closet(ds, items)
    return item


@app.delete("/api/closet/{item_id}")
def delete_item(item_id: str, dataset: Optional[str] = None):
    store.delete_item(_dataset(dataset), item_id)
    return {"ok": True}


@app.get("/api/images/{dataset}/{filename}")
def image(dataset: str, filename: str):
    path = store.image_path(_dataset(dataset), filename)
    if not path:
        raise HTTPException(404)
    return FileResponse(path)


# ---- stylist point of view & feedback ---------------------------------------

def _note_push(ds: str, res: dict) -> None:
    """Remember when the stylist last offered a bolder 'Push:' option, so she pushes about every two weeks."""
    plan = res.get("plan") or res
    if any(a.get("title", "").lower().startswith("push") for b in plan.get("blocks") or [] for a in b.get("alternates") or []):
        p = store.profile(ds)
        p["stylist"] = {**(p.get("stylist") or {}), "last_push": date.today().isoformat()}
        store.save_profile(ds, p)


@app.get("/api/stylist")
def get_stylist(dataset: Optional[str] = None):
    ds = _dataset(dataset)
    prof = store.profile(ds)
    st = prof.get("stylist") or {}
    return {**stylists.meta(), "blend": stylists.blend(prof), "learned": stylists.learned(ds, prof),
            "read": st.get("read"), "questions": stylists.pending_questions(prof),
            "answers": (st.get("answers") or [])[-12:], "push_due": stylists.push_due(prof),
            "aesthetic": prof.get("aesthetic"),
            # what each note / house rule became (a rule checked in code, or guidance every styling agent reads)
            "effects": outfit_rules.explain(prof, store.closet(ds))}


class Answer(BaseModel):
    id: str
    q: str
    a: str


class AnswersRequest(BaseModel):
    dataset: Optional[str] = None
    answers: list[Answer]


@app.post("/api/stylist/answers")
def stylist_answers(req: AnswersRequest):
    """Answers to the stylist's check-in questions; every styling agent reads them (no model call)."""
    ds = _dataset(req.dataset)
    p = store.profile(ds)
    st = p.get("stylist") or {}
    got = st.get("answers") or []
    for a in req.answers[:6]:
        text, _ = safety.clean_untrusted(a.a, 300)
        q, _ = safety.clean_untrusted(a.q, 160)
        if text.strip():
            got = [x for x in got if x.get("id") != a.id[:40]] + [{"id": a.id[:40], "q": q, "a": text, "at": date.today().isoformat()}]
    st["answers"] = got[-40:]
    p["stylist"] = st
    store.save_profile(ds, p)
    return {"ok": True, "questions": stylists.pending_questions(p), "answers": st["answers"][-12:]}


class BlendRequest(BaseModel):
    dataset: Optional[str] = None
    primary: str
    secondary: str = ""
    third: str = ""


@app.post("/api/stylist/blend")
def set_blend(req: BlendRequest):
    """Pick your archetype blend by hand (no model call)."""
    ds = _dataset(req.dataset)
    picks = [a for a in (req.primary, req.secondary, req.third) if a]
    if req.primary not in stylists.GUIDE or any(a not in stylists.GUIDE for a in picks) or len(set(picks)) != len(picks):
        raise HTTPException(400, "Pick different archetypes from the list")
    p = store.profile(ds)
    old = p.get("archetype") or {}
    p["archetype"] = {**old, "primary": req.primary, "secondary": req.secondary, "third": req.third, "source": "manual"}
    store.save_profile(ds, p)
    return {"ok": True, "blend": stylists.blend(p)}


class RulesRequest(BaseModel):
    dataset: Optional[str] = None
    rules: list[str]


@app.post("/api/stylist/rules")
def save_rules(req: RulesRequest):
    """House rules, saved on their own as she types (no model call)."""
    ds = _dataset(req.dataset)
    rules = [safety.clean_untrusted(r, 160)[0].strip() for r in req.rules[:15]]
    p = store.profile(ds)
    p["stylist"] = {**(p.get("stylist") or {}), "extra_rules": [r for r in rules if r]}
    store.save_profile(ds, p)
    return {"ok": True, "rules": p["stylist"]["extra_rules"]}


class GoalRequest(BaseModel):
    dataset: Optional[str] = None


@app.post("/api/stylist/goal")
def stylist_goal(req: GoalRequest):
    """Picture of the look she's dressing you toward (image model, her own key, under the image cap)."""
    ds = _dataset(req.dataset)
    return _run_photo(ds, lambda lg: aesthetic.draw_goal(lg, ds), mode="mockup", max_usd=0.08)


class ReadRequest(BaseModel):
    dataset: Optional[str] = None


@app.post("/api/stylist/read")
def stylist_read(req: ReadRequest):
    """The stylist rewrites its read on you from your feedback; it may suggest a new blend (shown, not applied)."""
    ds = _dataset(req.dataset)

    def flow(lg: Ledger):
        res = analyst.stylist_read(lg, ds)
        p = store.profile(ds)
        st = p.get("stylist") or {}
        suggest = [a for a in (res["primary"], res["secondary"], res["third"]) if a != "none"]
        stamp = date.today().strftime("%Y%m%d")
        st["pending_qs"] = [{**q, "id": f"f{stamp}-{len(p.get('feedback') or [])}-{i}"} for i, q in enumerate(res["questions"])]
        old_goal = (st.get("read") or {}).get("goal") or {}
        goal = {"title": res["goal_title"], "look": res["goal_look"]}
        if old_goal.get("look") == goal["look"] and old_goal.get("image"):
            goal["image"] = old_goal["image"]
        st["read"] = {"signature": res["signature"], "bullets": res["bullets"], "suggested_blend": suggest,
                      "strategy": res["strategy"], "goal": goal,
                      "blend_why": res["blend_why"], "n_feedback": stylists.learned(ds, p)["notes"], "at": date.today().isoformat()}
        p["stylist"] = st
        store.save_profile(ds, p)
        return st["read"]

    return _run("stylist_read", ds, flow)


class Feedback(BaseModel):
    dataset: Optional[str] = None
    kind: str = "outfit"
    rating: str
    item_ids: list = []
    label: str = ""
    note: str = ""


@app.post("/api/feedback")
def post_feedback(fb: Feedback):
    ds = _dataset(fb.dataset)
    if fb.rating not in ("love", "no", "note") or fb.kind not in ("outfit", "product", "item", "recommendation", "styling"):
        raise HTTPException(400, "rating must be love/no/note and kind outfit/product/item/recommendation/styling")
    note, _ = safety.clean_untrusted(fb.note, 200)
    label, _ = safety.clean_untrusted(fb.label, 100)
    prof = store.profile(ds)
    before = {b["label"] for b in outfit_rules.bans(prof)}
    entries = prof.get("feedback", [])
    entries.append({"kind": fb.kind, "rating": fb.rating, "item_ids": [str(i)[:80] for i in fb.item_ids[:10]],
                    "label": label, "note": note, "at": date.today().isoformat()})
    prof["feedback"] = entries[-stylists.MAX_FEEDBACK:]
    store.save_profile(ds, prof)
    # the hard rules this note created, so the page can say exactly what will be enforced from now on
    new_bans = [b["label"] for b in outfit_rules.bans(prof) if b["label"] not in before]
    return {"ok": True, "feedback": prof["feedback"], "new_bans": new_bans}


# ---- day context ----------------------------------------------------------

@app.get("/api/day")
def day_context(dataset: Optional[str] = None, day: Optional[str] = None):
    ds = _dataset(dataset)
    day = day or date.today().isoformat()
    prof = store.profile(ds)
    events, source = store.day_events(ds, day)
    return {
        "date": day,
        "events": events,
        "calendar_source": source,
        "weather": weather.forecast(prof.get("lat", 41.31), prof.get("lon", -72.93), day),
        "season": weather.season_for(day, prof.get("lat", 41.31)),
    }


class CalendarLink(BaseModel):
    dataset: Optional[str] = None
    url: str = ""
    timezone: str = ""


@app.post("/api/calendar/link")
def set_calendar_link(req: CalendarLink):
    """Save (or clear, with an empty url) a private iCal link. It is tested once, stored locally, never logged."""
    ds = _dataset(req.dataset)
    prof = store.profile(ds)
    if req.timezone:
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(req.timezone)
        except Exception:
            raise HTTPException(400, "Unknown time zone (use a name like America/New_York).")
        prof["timezone"] = req.timezone
    if not req.url.strip():
        prof.pop("calendar_url", None)
        store.save_profile(ds, prof)
        return {"ok": True, "connected": False}
    try:
        url = calendar_tools.normalize_url(req.url)
        raw = calendar_tools.fetch_ics(url)
        n = _count_events(raw)
    except calendar_tools.CalendarLinkError as e:
        raise HTTPException(400, str(e))
    prof["calendar_url"] = url
    store.save_profile(ds, prof)
    return {"ok": True, "connected": True, "events_in_feed": n}


def _count_events(raw: bytes) -> int:
    from icalendar import Calendar
    return len(Calendar.from_ical(raw).walk("VEVENT"))


@app.get("/api/calendar/status")
def calendar_status(dataset: Optional[str] = None):
    ds = _dataset(dataset)
    prof = store.profile(ds)
    return {"connected": bool(prof.get("calendar_url")), "uploaded": store.calendar_path(ds).exists(),
            "timezone": prof.get("timezone", ""), "sample": ds == "sample"}


@app.post("/api/calendar")
async def upload_calendar(file: UploadFile = File(...), dataset: Optional[str] = Form(None)):
    ds = _dataset(dataset)
    raw = await file.read()
    if len(raw) > 2 * 1024 * 1024 or b"BEGIN:VCALENDAR" not in raw[:2000]:
        raise HTTPException(400, "Please upload an .ics calendar file (under 2 MB).")
    store.calendar_path(ds).write_bytes(raw)
    return {"ok": True}


# ---- agent flows ----------------------------------------------------------

class PlanRequest(BaseModel):
    dataset: Optional[str] = None
    day: Optional[str] = None
    fresh: bool = False  # "Fresh take": plan again even if nothing changed


class ShopRequest(BaseModel):
    dataset: Optional[str] = None
    request: str
    live_web: bool = False


@app.post("/api/plan")
def plan(req: PlanRequest):
    ds = _dataset(req.dataset)
    day = req.day or date.today().isoformat()
    prof = store.profile(ds)
    events, _ = store.day_events(ds, day)
    inputs = memory.fingerprint(ds, day, events, weather.forecast(prof.get("lat", 41.31), prof.get("lon", -72.93), day))
    saved = memory.saved_plan(ds, day)
    if saved and not req.fresh and saved.get("inputs") == inputs:
        # nothing changed since the stylist picked: same pick, no model call
        return {"ok": True, "result": saved | {"kept": True}, "run": None}
    what = memory.changed((saved or {}).get("inputs"), inputs)

    def flow(lg):
        res = orchestrator.run_plan_day(lg, ds, day)
        memory.tag_plan(ds, day, inputs)
        _note_push(ds, res)
        return res | {"inputs": inputs, "changed": what, "fresh": req.fresh}

    return _run("plan_day", ds, flow)


@app.post("/api/shop")
def shop(req: ShopRequest):
    ds = _dataset(req.dataset)
    if not req.request.strip():
        raise HTTPException(400, "Tell me what you're looking for.")
    cap = config.MAX_USD_PER_LIVE_WEB_RUN if req.live_web else None
    return _run("shop_live" if req.live_web else "shop", ds,
                lambda lg: orchestrator.run_shop(lg, ds, req.request[:300], req.live_web), max_usd=cap)


# ---- wardrobe memory: saved plans, feedback taps, swaps, returns ------------

@app.get("/api/plan/saved")
def plan_saved(dataset: Optional[str] = None, day: Optional[str] = None):
    return {"plan": memory.saved_plan(_dataset(dataset), day or date.today().isoformat())}


class OutfitFeedback(BaseModel):
    dataset: Optional[str] = None
    day: Optional[str] = None
    block_label: str = ""
    item_ids: list = []
    tags: list = []
    note: str = ""


@app.post("/api/outfit/feedback")
def outfit_feedback(fb: OutfitFeedback):
    ds = _dataset(fb.dataset)
    day = (fb.day or date.today().isoformat())[:10]
    saved = memory.saved_plan(ds, day) or {}
    wx = saved.get("weather") or {}
    wx_note = f"high {wx.get('high_f')}F, low {wx.get('low_f')}F" if wx.get("high_f") is not None else ""
    try:
        learned = memory.record_feedback(ds, day, fb.block_label, [str(i) for i in fb.item_ids], [str(t) for t in fb.tags], fb.note, wx_note)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "learned": learned, "stats": memory.wear_stats(ds)}


class SwapRequest(BaseModel):
    dataset: Optional[str] = None
    day: Optional[str] = None
    block_index: int = 0
    block: dict
    reason: str = ""


@app.post("/api/outfit/swap")
def outfit_swap(req: SwapRequest):
    from .agents import planner
    ds = _dataset(req.dataset)
    day = (req.day or date.today().isoformat())[:10]

    def flow(lg):
        new = planner.swap_block(lg, ds, day, req.block, req.reason)
        merged = {**req.block, **{k: v for k, v in new.items() if v}}
        memory.replace_block(ds, day, req.block_index, merged)
        return {"block": merged}

    return _run("swap_outfit", ds, flow)


class ChooseRequest(BaseModel):
    dataset: Optional[str] = None
    day: Optional[str] = None
    block_index: int = 0
    alt_index: int = 0


@app.post("/api/outfit/choose")
def outfit_choose(req: ChooseRequest):
    """'Wear this instead': an alternate becomes the outfit and the old pick becomes an alternate (no model call),
    so feedback, try-on and the no-repeat memory all follow her choice."""
    ds = _dataset(req.dataset)
    day = (req.day or date.today().isoformat())[:10]
    saved = memory.saved_plan(ds, day)
    blocks = (saved or {}).get("plan", {}).get("blocks", [])
    if not 0 <= req.block_index < len(blocks):
        raise HTTPException(404, "That plan isn't saved anymore. Plan the day again.")
    b = blocks[req.block_index]
    alts = b.get("alternates") or []
    if not 0 <= req.alt_index < len(alts):
        raise HTTPException(404, "That option isn't there anymore.")
    alt = alts[req.alt_index]
    old = {"title": b.get("chosen") or "Stylist's pick", "item_ids": b["item_ids"], "why": b.get("why", ""),
           "stylist_note": b.get("stylist_note", ""), "items": b.get("items", [])}
    by_id = {i["id"]: i for i in store.closet(ds)}
    back = alt.get("title") == "Stylist's pick"  # switching back: no "your pick" tag
    new = {**b, "item_ids": alt["item_ids"], "items": [by_id[i] for i in alt["item_ids"] if i in by_id],
           "why": alt.get("why", ""), "stylist_note": alt.get("stylist_note", ""), "chosen": "" if back else alt.get("title", ""),
           "alternates": [old if n == req.alt_index else a for n, a in enumerate(alts)]}
    memory.replace_block(ds, day, req.block_index, new)
    return {"ok": True, "block": new}


@app.get("/api/wardrobe/memory")
def wardrobe_memory(dataset: Optional[str] = None):
    return memory.summary(_dataset(dataset))


class ReturnReport(BaseModel):
    dataset: Optional[str] = None
    reason: str
    note: str = ""


@app.post("/api/closet/{item_id}/return")
def return_item(item_id: str, rep: ReturnReport):
    try:
        item, learned = memory.record_return(_dataset(rep.dataset), item_id, rep.reason, rep.note)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "item": item, "learned": learned}


# ---- color season & style archetype -----------------------------------------

@app.get("/api/style/meta")
def style_meta():
    return {"quiz": color_style.QUIZ, "archetypes": color_style.ARCHETYPES,
            "seasons": {k: {"traits": v["traits"], "palette": v["palette"], "neutrals": v["neutrals"],
                            "metals": v["metals"], "avoid": v["avoid"]} for k, v in color_style.SEASONS.items()}}


class AnalyzeRequest(BaseModel):
    dataset: Optional[str] = None
    answers: list = []


class ColorRequest(BaseModel):
    dataset: Optional[str] = None
    measured: dict


@app.post("/api/analyze/color")
def analyze_color(req: ColorRequest):
    ds = _personal()
    prof = store.profile(ds)
    face = photo_tryon.face_photo_path(ds)
    if not face.exists() or not prof.get("photo_consent"):
        raise HTTPException(400, "Take a face close-up first (daylight, hair back, little makeup).")
    m = req.measured
    for k in ("skin_rgb", "brow_rgb", "eye_rgb"):
        v = m.get(k)
        if not (isinstance(v, list) and len(v) == 3 and all(isinstance(x, (int, float)) and 0 <= x <= 255 for x in v)):
            raise HTTPException(400, f"Bad measurement: {k}")

    def flow(lg: Ledger):
        res = analyst.analyze_color(lg, ds, face, m)
        p = store.profile(ds)
        p["color_season"] = {"season": res["season"], "why": res["why"], "top3": res["top3"],
                             "confidence": res["pick"]["confidence"], "lighting": res["pick"]["lighting_quality"],
                             "measured": {k: res["measured"][k] for k in ("undertone", "depth", "chroma", "chroma_level", "contrast", "eye_color")},
                             "source": "measured close-up"}
        store.save_profile(ds, p)
        return res

    return _run("analyze_color", ds, flow)


class BodyRequest(BaseModel):
    height_in: Optional[float] = None


@app.post("/api/analyze/body")
def analyze_body(req: BodyRequest):
    ds = _personal()
    prof = store.profile(ds)
    photo = photo_tryon.me_photo_path(ds)
    if not photo.exists() or not prof.get("photo_consent"):
        raise HTTPException(400, "Add your full-body photo (with the consent box ticked) first.")
    shoe = f"{prof.get('sizes', {}).get('shoe', '')} {prof.get('sizes', {}).get('shoe_width', '')}".strip()

    def flow(lg: Ledger):
        est = analyst.estimate_body(lg, ds, photo, req.height_in, shoe)
        p = store.profile(ds)
        p["body_photo_estimate"] = {k: [v["best"], v["low"], v["high"]] for k, v in est["measurements_in"].items()}
        if req.height_in:
            p["body_photo_estimate"]["height"] = [req.height_in, req.height_in, req.height_in]
        p["body_shape"] = {"shape": est["body_shape"], "flattering": est["flattering"], "confidence": est["confidence"]}
        store.save_profile(ds, body_model.refine(p))
        return est

    return _run("analyze_body", ds, flow)


class FitReport(BaseModel):
    dataset: Optional[str] = None
    size_label: str
    fit: str  # perfect | snug | tight | loose


@app.post("/api/closet/{item_id}/fit")
def report_fit(item_id: str, rep: FitReport):
    """An owned item's size + how it fits refines the body estimate."""
    ds = _dataset(rep.dataset or "user")
    items = store.closet(ds)
    item = next((i for i in items if i["id"] == item_id), None)
    if not item:
        raise HTTPException(404, "That piece isn't in your closet anymore (it was removed).")
    if rep.fit not in body_model.FIT_SHIFT:
        raise HTTPException(400, "Unknown fit (use perfect, snug, tight or loose).")
    # the item remembers its size, so a later return for size can teach the brand rule too
    item.update(size_label=rep.size_label[:20], fit_verdict=rep.fit)
    store.save_closet(ds, items)
    implied = body_model.evidence(item, rep.size_label, rep.fit)
    p = store.profile(ds)
    ev = [e for e in p.get("fit_evidence", []) if e.get("item_id") != item_id]
    ev.append({"item_id": item_id, "name": item.get("name"), "category": item.get("category"),
               "size_label": rep.size_label[:20], "fit": rep.fit, "implied": implied})
    p["fit_evidence"] = ev
    p = body_model.refine(p)
    store.save_profile(ds, p)
    return {"ok": True, "implied": implied, "measurements_in": p["measurements_in"],
            "measurements_range": p["measurements_range"], "sizes": p.get("sizes"), "source": p["measurements_source"]}


@app.post("/api/analyze/style")
def analyze_style(req: AnalyzeRequest):
    ds = _dataset(req.dataset)
    answers = [str(a) for a in req.answers[:3]]

    def flow(lg: Ledger):
        res = analyst.analyze_style(lg, ds, answers)
        p = store.profile(ds)
        p["archetype"] = {"primary": res["primary"], "secondary": res["secondary"] if res["secondary"] != "none" else "",
                          "third": res["third"] if res["third"] not in ("none", res["secondary"]) else "", "source": "analyst",
                          "evidence": res["evidence"], "pieces_to_add": res["pieces_to_add"], "quiz": answers}
        store.save_profile(ds, p)
        return res

    return _run("analyze_style", ds, flow)


# ---- optional photo-real try-on (user's own OPENAI_API_KEY) ----------------

@app.get("/api/photo-tryon/status")
def photo_status(dataset: Optional[str] = None):
    return photo_tryon.status(_personal())


@app.post("/api/me/photo")
async def upload_me_photo(file: UploadFile = File(...), dataset: Optional[str] = Form(None), consent: bool = Form(False)):
    ds = _personal()
    if not consent:
        raise HTTPException(400, "Please tick the consent box: your photo is sent to OpenAI when you make a photo try-on.")
    try:
        photo_tryon.save_photo(ds, await file.read())
    except ValueError as e:
        raise HTTPException(400, str(e))
    prof = store.profile(ds)
    prof["photo_consent"] = True
    store.save_profile(ds, prof)
    return {"ok": True}


@app.post("/api/me/closeup")
async def upload_closeup(file: UploadFile = File(...), kind: str = Form("face"), dataset: Optional[str] = Form(None), consent: bool = Form(False)):
    ds = _personal()
    if kind not in ("face", "wrist"):
        raise HTTPException(400, "kind must be face or wrist")
    if not consent:
        raise HTTPException(400, "Please tick the consent box: your photo is sent to OpenAI for color analysis.")
    try:
        photo_tryon.save_photo(ds, await file.read(), closeup=kind)
    except ValueError as e:
        raise HTTPException(400, str(e))
    store.save_profile(ds, store.profile(ds) | {"photo_consent": True})
    return {"ok": True}


@app.delete("/api/me/photo")
def delete_me_photo(dataset: Optional[str] = None):
    ds = _personal()
    for path in (photo_tryon.me_photo_path(ds), photo_tryon.face_photo_path(ds), photo_tryon.wrist_photo_path(ds)):
        if path.exists():
            path.unlink()
    prof = store.profile(ds)
    prof["photo_consent"] = False
    store.save_profile(ds, prof)
    return {"ok": True}


@app.get("/api/me/photo/{dataset}")
def get_me_photo(dataset: str, kind: str = "body"):
    ds = _personal()
    path = {"face": photo_tryon.face_photo_path, "wrist": photo_tryon.wrist_photo_path}.get(kind, photo_tryon.me_photo_path)(ds)
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path)


@app.post("/api/places/photo")
async def upload_place_photo(file: UploadFile = File(...), scene: str = Form(...), dataset: Optional[str] = Form(None)):
    ds = _personal()
    if scene not in photo_tryon.SCENES:
        raise HTTPException(400, f"scene must be one of {sorted(photo_tryon.SCENES)}")
    try:
        photo_tryon.save_photo(ds, await file.read(), scene=scene)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


class PhotoTryOn(BaseModel):
    dataset: Optional[str] = None
    items: list = []
    scene: str = "studio"
    zones: dict = {}
    pose: str = "standing"


@app.post("/api/photo-tryon")
def make_photo_tryon(req: PhotoTryOn):
    ds = _personal()
    if not config.openai_key():
        return JSONResponse({"ok": False, "error": "Photo try-on needs your own OPENAI_API_KEY in .env (the course key is for gpt-6-luna only). The 3D twin works without it."}, status_code=400)
    by_id = {i["id"]: i for i in store.closet(ds)}
    items = []
    for it in req.items[:8]:
        if not isinstance(it, dict):
            continue
        # closet items come from our own data; anything else (shop picks) only contributes safe text fields
        if it.get("id") in by_id:
            items.append(by_id[it["id"]])
        else:
            safe = {k: str(it.get(k, ""))[:80] for k in ("id", "name", "category", "subtype", "color", "fit", "length")}
            # a recommended piece drawn as a mock-up: the try-on gets its picture (only files we made, by name)
            from . import mockups
            pic = mockups.folder(ds) / str(it.get("mockup", "")).rsplit("/", 1)[-1]
            if it.get("mockup") and pic.is_file():
                safe["mockup_path"] = str(pic)
            items.append(safe)
    scene = req.scene if req.scene in photo_tryon.SCENES else "studio"
    return _run_photo(ds, lambda lg: photo_tryon.run(lg, ds, items, scene, req.zones, req.pose))


class TryOnFeedback(BaseModel):
    image: str
    issues: list = []
    detail: str = ""


@app.post("/api/photo-tryon/feedback")
def tryon_feedback(req: TryOnFeedback):
    """'What's wrong with this photo?': notes go into every later try-on; this image leaves the gallery."""
    ds = _personal()
    detail = safety.clean_untrusted((req.detail or "").strip(), 300)[0]
    issues = [str(k) for k in req.issues if str(k) in photo_tryon.ISSUES]
    if not issues and not detail:
        raise HTTPException(400, "Tick what's wrong (or add a note) so the next photo can fix it.")
    photo_tryon.reject(ds, req.image.rsplit("/", 1)[-1], issues, detail)
    return {"ok": True}


class Spin(BaseModel):
    image: str


@app.post("/api/photo-tryon/spin")
def make_turntable(req: Spin):
    ds = _personal()
    return _run_photo(ds, lambda lg: photo_tryon.run_turntable(lg, ds, req.image),
                      mode="photo_turntable", max_usd=config.MAX_USD_PER_TURNTABLE)


def _run_photo(ds, fn, mode="photo_tryon", max_usd=None):
    try:
        ledger_mod.check_rate_limit()
    except BudgetExceeded as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=429)
    lg = Ledger(mode, ds, max_usd=max_usd or config.MAX_USD_PER_PHOTO_TRYON)
    try:
        result = fn(lg)
        return {"ok": True, "result": result, "run": lg.save("ok")}
    except BudgetExceeded as e:
        return JSONResponse({"ok": False, "error": str(e), "run": lg.save("stopped_budget")}, status_code=429)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e), "run": lg.save("error")}, status_code=400)
    except Exception as e:
        traceback.print_exc()
        lg.step("Photo Try-On", "error", f"{type(e).__name__}: {str(e)[:200]}")
        return JSONResponse({"ok": False, "error": f"The image service returned an error: {type(e).__name__}. {str(e)[:160]}", "run": lg.save("error")}, status_code=500)


@app.get("/api/tryons")
def list_tryons():
    return photo_tryon.gallery(_personal())[::-1]


@app.get("/api/tryons/{dataset}/{filename}")
def tryon_image(dataset: str, filename: str):
    from pathlib import Path as _P
    path = store.folder(_personal()) / "tryons" / _P(filename).name
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path)


# ---- proactive recommendations ----------------------------------------------

class RecommendRequest(BaseModel):
    dataset: Optional[str] = None
    shop: bool = False
    look: str = ""  # the look she's going for, e.g. "polished recruiting"
    fresh: bool = False


class MockupRequest(BaseModel):
    look: str = ""
    gaps: list = []


@app.post("/api/recommend/mockups")
def recommend_mockups(req: MockupRequest):
    """Pictures for the 3 recommended pieces: each piece, and the outfit it makes with her closet."""
    from . import mockups
    ds = _personal()
    if not config.openai_key():
        return JSONResponse({"ok": False, "error": "Mock-ups need your own OPENAI_API_KEY in .env."}, status_code=400)
    known = {i["id"] for i in store.closet(ds)}
    gaps = []
    for g in req.gaps[:3]:  # round-tripped through the page: rebuild from safe fields only
        if not isinstance(g, dict) or not str(g.get("piece", "")).strip():
            continue
        gaps.append({
            "piece": safety.clean_untrusted(str(g["piece"]), 100)[0],
            "outfit_title": safety.clean_untrusted(str(g.get("outfit_title", "")), 60)[0],
            "colors": [{"name": safety.clean_untrusted(str(c.get("name", "")), 30)[0]} for c in (g.get("colors") or [])[:3] if isinstance(c, dict)],
            "outfit_ids": [str(i) for i in (g.get("outfit_ids") or [])[:7] if str(i) in known],
        })
    if not gaps:
        raise HTTPException(400, "Find what's missing first.")
    look = safety.clean_untrusted(req.look.strip(), 80)[0]

    def flow(lg):
        made = mockups.make(lg, ds, gaps, look)
        saved = memory.saved_recs(ds)  # keep the pictures with the saved picks, so a refresh shows them again
        if saved and [g["piece"] for g in saved["result"]["recommendations"]["gaps"]][:3] == [g["piece"] for g in gaps]:
            memory.save_recs(ds, saved | {"mockups": made})
        return made

    return _run_photo(ds, flow, mode="mockup", max_usd=0.06 * len(gaps))


@app.get("/api/mockups/{filename}")
def mockup_image(filename: str):
    from . import mockups
    path = mockups.folder(_personal()) / filename.rsplit("/", 1)[-1]
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path)


@app.post("/api/recommend")
def recommend(req: RecommendRequest):
    from .agents import recommender
    ds = _dataset(req.dataset)
    # A combined recommend + live shop run gets its own, larger cap.
    cap = 0.25 if req.shop else None
    look = safety.clean_untrusted(req.look.strip(), 80)[0]
    today = date.today()
    inputs = memory.fingerprint(ds, today.isoformat(), look=look, week=recommender.week_ahead(ds, today))
    saved = memory.saved_recs(ds) if ds == "user" else None
    if saved and not req.fresh and not req.shop and saved.get("inputs") == inputs:
        return {"ok": True, "result": saved["result"] | {"kept": True, "mockups": saved.get("mockups")}, "run": None}
    what = memory.changed((saved or {}).get("inputs"), inputs)

    def flow(lg):
        res = recommender.recommend(lg, ds, req.shop, look)
        if ds == "user":
            memory.save_recs(ds, {"inputs": inputs, "result": {k: v for k, v in res.items() if k != "shop"}, "mockups": None})
        return res | {"changed": what}

    return _run("recommend", ds, flow, max_usd=cap)


@app.get("/api/recommend/saved")
def recommend_saved():
    saved = memory.saved_recs(_personal())
    return {"result": (saved["result"] | {"kept": True, "mockups": saved.get("mockups")}) if saved else None}


@app.get("/api/runs")
def runs(limit: int = 30):
    path = config.LOG_DIR / "runs.jsonl"
    if not path.exists():
        return []
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return rows[-limit:][::-1]


try:
    from .routes_extra import router as extra_router  # add by link, inspiration, price tracker
    app.include_router(extra_router)
except ImportError as e:
    print(f"Extra routes not loaded: {e}")

app.mount("/", StaticFiles(directory=config.STATIC_DIR, html=True), name="static")
