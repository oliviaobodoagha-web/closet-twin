"""Reads and writes the closet, profile, calendar and shop catalog for a data set.

data/sample/  ships with the repo so the app runs from a fresh clone.
data/user/    is your own closet, photos, measurements and calendar (git-ignored).
"""

from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path

from . import config

DATASETS = ("sample", "user")


def folder(dataset: str) -> Path:
    if dataset not in DATASETS:
        raise ValueError(f"Unknown data set {dataset!r}")
    path = config.DATA_DIR / dataset
    if dataset == "user" and not (path / "profile.json").exists():
        _start_user_folder(path)
    return path


def _start_user_folder(path: Path) -> None:
    """First time in 'user' mode: start from the sample profile with an empty closet."""
    sample = config.DATA_DIR / "sample"
    (path / "images").mkdir(parents=True, exist_ok=True)
    profile = json.loads((sample / "profile.json").read_text())
    profile["name"] = ""
    (path / "profile.json").write_text(json.dumps(profile, indent=2))
    (path / "closet.json").write_text("[]")
    # No calendar yet: connect a live iCal link or upload an .ics in the Me tab.


def _read(dataset: str, name: str, default):
    path = folder(dataset) / name
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write(dataset: str, name: str, data) -> None:
    (folder(dataset) / name).write_text(json.dumps(data, indent=2), encoding="utf-8")


def closet(dataset: str) -> list[dict]:
    return _read(dataset, "closet.json", [])


def save_closet(dataset: str, items: list[dict]) -> None:
    _write(dataset, "closet.json", items)


_add_lock = threading.Lock()  # bulk add runs several catalogers at once


def add_item(dataset: str, item: dict, photo_jpeg: bytes | None) -> dict:
    with _add_lock:
        return _add_item(dataset, item, photo_jpeg)


def update_item(dataset: str, item_id: str, fields: dict) -> dict | None:
    """Merge fields into one item (safe alongside bulk adds)."""
    with _add_lock:
        items = closet(dataset)
        item = next((i for i in items if i["id"] == item_id), None)
        if item:
            item.update(fields)
            save_closet(dataset, items)
        return item


def _add_item(dataset: str, item: dict, photo_jpeg: bytes | None) -> dict:
    items = closet(dataset)
    item = dict(item)
    item["id"] = item.get("id") or f"c-{uuid.uuid4().hex[:6]}"
    if photo_jpeg:
        images = folder(dataset) / "images"
        images.mkdir(exist_ok=True)
        (images / f"{item['id']}.jpg").write_bytes(photo_jpeg)
        item["image"] = f"{item['id']}.jpg"
    items.append(item)
    save_closet(dataset, items)
    return item


def delete_item(dataset: str, item_id: str) -> None:
    items = [i for i in closet(dataset) if i["id"] != item_id]
    save_closet(dataset, items)
    for photo in [folder(dataset) / "images" / f"{item_id}{ext}" for ext in (".jpg", ".cut.png", ".shot.png")]:
        if photo.exists():
            photo.unlink()


def profile(dataset: str) -> dict:
    return _read(dataset, "profile.json", {})


def save_profile(dataset: str, data: dict) -> None:
    _write(dataset, "profile.json", data)


def catalog() -> list[dict]:
    """Offline shop catalog (fictional brands and reviews) used when live web search is off."""
    return json.loads((config.DATA_DIR / "sample" / "catalog.json").read_text(encoding="utf-8"))


def calendar_path(dataset: str) -> Path:
    return folder(dataset) / "calendar.ics"


def day_events(dataset: str, day: str) -> tuple[list[dict], str]:
    """(events, source) for a day. Source: 'live link', 'uploaded file', 'sample day' or 'none'.

    A live iCal link wins over an uploaded file; if the link fails, the uploaded file is used.
    """
    from .tools import calendar_tools

    prof = profile(dataset)
    tz = prof.get("timezone") or None
    if dataset == "sample":
        return calendar_tools.events_for(calendar_path(dataset), day, remap_to_day=True), "sample day"
    url = (prof.get("calendar_url") or "").strip()
    if url:
        try:
            return calendar_tools.events_from_ics(calendar_tools.fetch_ics(url), day, tz_name=tz), "live link"
        except calendar_tools.CalendarLinkError as e:
            if calendar_path(dataset).exists():
                return calendar_tools.events_for(calendar_path(dataset), day, tz_name=tz), f"uploaded file (live link failed: {e})"
            return [], f"none (live link failed: {e})"
    if calendar_path(dataset).exists():
        return calendar_tools.events_for(calendar_path(dataset), day, tz_name=tz), "uploaded file"
    return [], "none"


def image_path(dataset: str, filename: str) -> Path | None:
    path = (folder(dataset) / "images" / Path(filename).name)
    return path if path.exists() else None
