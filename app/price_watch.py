"""Price tracker: a watchlist of product links, drop alerts and per-store trends (no model calls)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from . import link_import, safety, store
from .ledger import Ledger

MAX_CHECKS_PER_RUN = 20


def _path(dataset: str):
    return store.folder(dataset) / "watchlist.json"


def _load(dataset: str) -> list[dict]:
    path = _path(dataset)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def _save(dataset: str, items: list[dict]) -> None:
    _path(dataset).write_text(json.dumps(items, indent=2), encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def add(dataset: str, url: str, name: str, store_name: str = "", price: Optional[float] = None,
        image: Optional[str] = None) -> dict:
    items = _load(dataset)
    url = link_import.check_url(url)
    found = next((i for i in items if i["url"] == url), None)
    if found:
        return summarize(found)
    entry = {
        "id": f"w-{uuid.uuid4().hex[:6]}",
        "url": url,
        "name": safety.clean_untrusted(name or "", 120)[0] or url,
        "store": safety.clean_untrusted(store_name or "", 60)[0],
        "image": image if (image or "").startswith(("http://", "https://")) else None,
        "added_at": _now(),
        "history": [{"at": _now(), "price": float(price)}] if price else [],
    }
    items.append(entry)
    _save(dataset, items)
    return summarize(entry)


def remove(dataset: str, item_id: str) -> None:
    _save(dataset, [i for i in _load(dataset) if i["id"] != item_id])


def summarize(entry: dict) -> dict:
    """Entry plus current, lowest, first price, % change since added, and whether the last check dropped."""
    prices = [h["price"] for h in entry.get("history", []) if h.get("price")]
    current = prices[-1] if prices else None
    first = prices[0] if prices else None
    return entry | {
        "current": current,
        "lowest": min(prices) if prices else None,
        "first": first,
        "change_pct": round((current - first) / first * 100, 1) if prices else None,
        "dropped": len(prices) >= 2 and prices[-1] < prices[-2],
    }


def listing(dataset: str) -> list[dict]:
    return [summarize(i) for i in _load(dataset)]


def check(ledger: Ledger, dataset: str) -> dict:
    """Refetch up to 20 prices from the product pages; drops come first."""
    items = _load(dataset)
    checked = failed = 0
    for entry in items[:MAX_CHECKS_PER_RUN]:
        try:
            price = link_import.fetch_product(entry["url"])["price"]
        except Exception:
            price = None
        checked += 1
        if price is None:
            failed += 1
            continue
        entry.setdefault("history", []).append({"at": _now(), "price": price})
        entry["history"] = entry["history"][-60:]
    _save(dataset, items)
    out = sorted((summarize(i) for i in items), key=lambda e: (not e["dropped"], e["name"].lower()))
    drops = [e for e in out if e["dropped"]]
    ledger.step("Price Watch", "done", f"Checked {checked} link(s): {len(drops)} drop(s), {failed} page(s) gave no price")
    return {"items": out, "drops": drops, "trends": store_trends(dataset)}


def store_trends(dataset: str) -> dict:
    """Per store: items tracked, average % change since added, and how many dropped on the last check."""
    trends: dict[str, dict] = {}
    for e in listing(dataset):
        t = trends.setdefault(e["store"] or "unknown", {"tracked": 0, "avg_change_pct": None, "dropped": 0, "_c": []})
        t["tracked"] += 1
        t["dropped"] += int(e["dropped"])
        if e["change_pct"] is not None:
            t["_c"].append(e["change_pct"])
    for t in trends.values():
        changes = t.pop("_c")
        t["avg_change_pct"] = round(sum(changes) / len(changes), 1) if changes else None
    return trends
