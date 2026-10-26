"""Add a closet item from a product link (Open Graph / JSON-LD, then the Cataloger on the photo).

Everything read from the page is untrusted: it is cleaned by safety.clean_untrusted
before any agent sees it, and URLs are checked so the server never fetches its own network.
"""

from __future__ import annotations

import ipaddress
import json
import re
import time
import socket
import ssl
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Optional

import certifi

from . import config, cutout, safety, store
from .agents import cataloger
from .ledger import Ledger

_SSL = ssl.create_default_context(cafile=certifi.where())
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
MAX_PAGE_BYTES = 2 * 1024 * 1024
MAX_URL_LEN = 2000


# ---- fetching (with a basic SSRF guard) ------------------------------------

def check_url(url: str) -> str:
    """Only public http(s) URLs: no localhost, private, link-local or reserved addresses."""
    url = (url or "").strip()
    if not url or len(url) > MAX_URL_LEN:
        raise ValueError("That link is empty or too long.")
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("Only http(s) links are allowed.")
    host = parts.hostname
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise ValueError("That link points to a private address.")
    try:
        addrs = {a[4][0] for a in socket.getaddrinfo(host, parts.port or 443, proto=socket.IPPROTO_TCP)}
    except socket.gaierror:
        raise ValueError("I couldn't find that website.")
    for a in addrs:
        ip = ipaddress.ip_address(a.split("%")[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise ValueError("That link points to a private address.")
    return url


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)  # a redirect must not sneak into a private network either
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_SafeRedirect, urllib.request.HTTPSHandler(context=_SSL))


MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")


def fetch(url: str, max_bytes: int = MAX_PAGE_BYTES, accept: str = "text/html,*/*", ua: str = UA) -> bytes:
    """GET a public URL with a browser-like User-Agent (10 s timeout, size-capped)."""
    req = urllib.request.Request(check_url(url), headers={
        "User-Agent": ua, "Accept": accept, "Accept-Language": "en-US,en;q=0.9",
    })
    with _OPENER.open(req, timeout=10) as r:
        return r.read(max_bytes + 1)[:max_bytes]


# ---- parsing ---------------------------------------------------------------

class _MetaParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.ld: list[str] = []
        self.title = ""
        self._in = None

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
            if key and "content" in a and key not in self.meta:
                self.meta[key] = a["content"]
        elif tag == "script" and "ld+json" in a.get("type", "").lower():
            self._in = "ld"
            self.ld.append("")
        elif tag == "title" and not self.title:
            self._in = "title"

    def handle_endtag(self, tag):
        if tag in ("script", "title"):
            self._in = None

    def handle_data(self, data):
        if self._in == "ld":
            self.ld[-1] += data
        elif self._in == "title":
            self.title += data


def _ld_product(blocks: list[str]) -> dict:
    """First schema.org Product found in the JSON-LD blocks (handles lists and @graph)."""
    stack = []
    for b in blocks:
        try:
            stack.append(json.loads(b.strip()))
        except ValueError:
            continue
    while stack:
        node = stack.pop(0)
        if isinstance(node, list):
            stack.extend(node)
        elif isinstance(node, dict):
            kind = node.get("@type")
            kinds = kind if isinstance(kind, list) else [kind]
            if "Product" in kinds or "ProductGroup" in kinds:
                return node
            stack.extend(v for v in node.values() if isinstance(v, (list, dict)))
    return {}


def _first(v):
    return v[0] if isinstance(v, list) and v else v


def _name(v) -> str:
    v = _first(v)
    if isinstance(v, dict):
        return str(v.get("name") or v.get("url") or "")
    return str(v or "")


def to_price(v) -> Optional[float]:
    m = re.search(r"\d[\d,]*(?:\.\d+)?", str(v or ""))
    if not m:
        return None
    try:
        price = float(m.group(0).replace(",", ""))
    except ValueError:
        return None
    return price if 0 < price < 100_000 else None


def parse_product(page: str, base_url: str = "") -> dict:
    """Title, brand, store, price, currency and image from Open Graph / JSON-LD, cleaned."""
    p = _MetaParser()
    try:
        p.feed(page)
    except Exception:  # broken HTML: keep whatever was parsed so far
        pass
    m, ld = p.meta, _ld_product(p.ld)
    offers = _first(ld.get("offers")) or {}
    if isinstance(offers, dict) and not offers.get("price") and isinstance(offers.get("offers"), list):
        offers = _first(offers["offers"]) or {}
    offers = offers if isinstance(offers, dict) else {}

    raw = {
        "title": _name(ld.get("name")) or m.get("og:title") or m.get("twitter:title") or p.title,
        "brand": _name(ld.get("brand")) or m.get("product:brand") or m.get("og:brand") or "",
        "store": m.get("og:site_name") or "",
    }
    flags: list[str] = []
    out: dict = {}
    for k, v in raw.items():
        out[k], f = safety.clean_untrusted(v, 160)
        flags += f
    out["price"] = to_price(offers.get("price") or offers.get("lowPrice") or m.get("product:price:amount")
                            or m.get("og:price:amount"))
    out["currency"] = re.sub(r"[^A-Z]", "", str(offers.get("priceCurrency") or m.get("product:price:currency")
                                                 or m.get("og:price:currency") or "USD").upper())[:3] or "USD"
    # og:image first: JSON-LD images are often small thumbnails.
    image = m.get("og:image:secure_url") or m.get("og:image") or m.get("twitter:image") or _name(ld.get("image")) or ""
    image = urllib.parse.urljoin(base_url, image.strip()) if image.strip() else ""
    out["image"] = image if image.startswith(("http://", "https://")) else ""
    gallery = ld.get("image") if isinstance(ld.get("image"), list) else [ld.get("image")]
    gallery = [urllib.parse.urljoin(base_url, _name(g).strip()) for g in gallery if _name(g).strip()]
    out["images"] = list(dict.fromkeys([u for u in [out["image"]] + gallery if u.startswith(("http://", "https://"))]))[:6]
    host = (urllib.parse.urlsplit(base_url).hostname or "")
    if re.search(r"(^|\.)amazon\.[a-z.]+$", host):
        _amazon(page, out)
    if not out["store"] and base_url:
        out["store"] = (urllib.parse.urlsplit(base_url).hostname or "").removeprefix("www.")
    out["flags"] = sorted(set(flags))
    return out


def _amazon(page: str, out: dict) -> None:
    """Amazon has no Open Graph tags: read the main photo, price and a clean title from its own markup."""
    # every gallery photo, main one first; import picks the one that shows the whole garment
    urls = re.findall(r'data-old-hires="(https://m\.media-amazon\.com/[^"]+)"', page) + \
        re.findall(r'"hiRes":"(https://m\.media-amazon\.com/[^"]+)"', page)
    out["images"] = list(dict.fromkeys(urls))[:6] or out.get("images", [])
    if not out["image"] and out["images"]:
        out["image"] = out["images"][0]
    if out["price"] is None:
        m = re.search(r'"priceAmount":([0-9.]+)', page)
        out["price"] = to_price(m.group(1)) if m else None
    t = re.sub(r"^Amazon(\.[a-z.]+)?\s*:\s*", "", out["title"])
    out["title"] = re.split(r"\s+:\s+", t)[0].strip()


def fetch_product(url: str) -> dict:
    page = fetch(url).decode("utf-8", errors="replace")
    info = parse_product(page, url)
    if not _usable_title(info["title"], url) or info["title"].lower() in _GENERIC_TITLES:
        # big stores sometimes answer with a robot-check page; one retry as a phone browser often gets through
        time.sleep(1)
        info = parse_product(fetch(url, ua=MOBILE_UA).decode("utf-8", errors="replace"), url)
    return info


# ---- import ----------------------------------------------------------------

_CATEGORY_WORDS = [
    ("shoes", "sneaker shoe boot loafer heel pump sandal flat mule clog oxford"),
    ("dress", "dress gown jumpsuit romper"),
    ("outerwear", "coat jacket blazer parka puffer trench vest anorak"),
    ("activewear", "legging sports bra workout running tight"),
    ("bottom", "jean pant trouser skirt short chino"),
    ("accessory", "bag tote belt scarf hat necklace earring sunglasses wallet"),
    ("top", "shirt tee top blouse sweater cardigan polo tank hoodie sweatshirt pullover"),
]


_GENERIC_TITLES = ("amazon.com", "robot check", "access denied", "page not found", "just a moment", "attention required")
BLOCKED_MSG = ("That store doesn't let apps read its pages. On the product page, right-click the photo -> Copy Image, "
               "then paste it into the link box (Cmd+V) with the link and press Add.")


def _slug_title(url: str) -> str:
    """Product name from the URL path, e.g. amazon.com/Womens-Quilted-Jacket/dp/B0... -> 'Womens Quilted Jacket'."""
    parts = [p for p in urllib.parse.urlsplit(url).path.split("/") if p]
    best = max((p for p in parts if "-" in p and not re.fullmatch(r"[A-Z0-9]{10}", p)), key=len, default="")
    return re.sub(r"[-_]+", " ", urllib.parse.unquote(best)).strip()[:80]


def _usable_title(title: str, url: str) -> str:
    t = (title or "").strip()
    host = (urllib.parse.urlsplit(url).hostname or "").removeprefix("www.")
    if not t or t.lower() in _GENERIC_TITLES or t.lower() in (host, host.split(".")[0]) or len(t) < 4:
        t = _slug_title(url)
    return t


def _text_item(title: str, brand: str) -> dict:
    """No usable photo: a plain item from the title (no model call). Refuses to guess when the title
    names no garment, so a blocked page can't turn a jacket into a 'top'."""
    low = title.lower()
    category = subtype = None
    for cat, words in _CATEGORY_WORDS:
        hit = next((w for w in words.split() if re.search(rf"\b{w}", low)), None)
        if hit:
            category, subtype = cat, hit
            break
    if not category:
        raise ValueError(BLOCKED_MSG)
    colors = [c for c in ("black", "white", "navy", "camel", "beige", "cream", "grey", "gray", "brown", "red",
                          "pink", "blue", "green", "olive", "burgundy", "tan", "ivory") if c in low][:2]
    return {
        "is_clothing": True, "name": title[:80], "category": category, "subtype": subtype,
        "colors": [{"name": c, "hex": ""} for c in colors], "pattern": "", "fabric": "",
        "formality": 3, "warmth": 3 if category == "outerwear" else 2, "seasons": [],
        "fit": "regular", "length": "regular", "toe_box": "n/a", "heel_in": 0, "walkable": category == "shoes",
        "comfort": 3, "notes": f"Added from a link{' (' + brand + ')' if brand else ''}; no photo.",
    }


def _best_photo(ledger: Ledger, urls: list[str]) -> bytes | None:
    """First product photo that shows the whole garment (not touching the frame); stores often crop the
    main shot tight. Falls back to the roomiest one."""
    best, best_margin = None, -1.0
    for n, u in enumerate(urls[:6]):
        try:
            jpeg = safety.prepare_photo(fetch(u, config.MAX_UPLOAD_BYTES, "image/*"))
        except Exception as e:
            ledger.step("Link Import", "error", f"Product photo {n + 1} unavailable ({type(e).__name__})")
            continue
        try:
            margin = cutout.edge_margin(jpeg)
        except Exception:  # no cutout model: take the main photo
            return jpeg
        if margin > best_margin:
            best, best_margin = jpeg, margin
        if margin >= 0.02:
            ledger.step("Link Import", "tool", f"Using product photo {n + 1}: the whole garment is in frame")
            return jpeg
    if best is not None:
        ledger.step("Link Import", "tool", "No photo showed the whole garment with room around it; using the roomiest one")
    return best


def _page_from_url(url: str) -> dict:
    """What the link alone tells us when the page can't be read: a name from the URL and the store's host."""
    host = (urllib.parse.urlsplit(url).hostname or "").removeprefix("www.") if url else ""
    return {"title": _slug_title(url) if url else "", "brand": "", "store": host, "price": None, "image": "", "images": [], "flags": []}


def import_link(ledger: Ledger, dataset: str, url: str, photo: bytes | None = None) -> dict:
    """Add a store product. photo: the product photo she copied from the page herself (Copy Image -> paste);
    then a store that won't let apps read its pages still works, and the page is only read for name and price."""
    ledger.step("Link Import", "start", f"Reading product page: {urllib.parse.urlsplit(url).hostname}" if url
                else "Adding a product photo you pasted")
    try:
        info = fetch_product(url) if url else _page_from_url(url)
    except ValueError:
        raise
    except Exception as e:
        ledger.step("Link Import", "error", f"Page fetch failed: {type(e).__name__}")
        if photo is None:
            raise ValueError(BLOCKED_MSG)
        info = _page_from_url(url)
    if info["flags"]:
        ledger.safety("prompt_injection", "Link Import", "Cleaned suspicious text from the product page.", info["flags"])
    ledger.step("Link Import", "tool", f"Found: {info['title'] or '(no title)'} | {info['brand']} | {info['price']}",
                {k: v for k, v in info.items() if k != "flags"})
    info["title"] = _usable_title(info["title"], url) if url else ""
    if not info["title"] and photo is None:
        raise ValueError(BLOCKED_MSG)

    jpeg = photo or _best_photo(ledger, info.get("images") or ([info["image"]] if info["image"] else []))

    if jpeg:
        note = (f"Product page title: {info['title']}" if info["title"] else "A product photo from a store") \
            + (f"; brand: {info['brand']}" if info["brand"] else "")
        item = cataloger.catalog_photo(ledger, jpeg, note)
        if not item.get("is_clothing"):
            if photo is not None:
                raise ValueError("I couldn't find a clothing item or shoes in that photo.")
            item = _text_item(info["title"], info["brand"])
            jpeg = None
    else:
        item = _text_item(info["title"], info["brand"])
    item.update({"source": "link", "url": url, "brand": info["brand"], "store": info["store"], "price": info["price"],
                 "photo_from": "pasted" if photo is not None else "page"})
    saved = store.add_item(dataset, item, jpeg)
    ledger.step("Link Import", "done", f"Added {saved['name']}" + ("" if jpeg else " (no photo)"))
    return saved
