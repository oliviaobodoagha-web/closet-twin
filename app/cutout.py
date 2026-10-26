"""Product-style cutouts and measured colors for closet photos.

A small background-removal model (U2-Net-p, 4.6 MB, Apache-2.0, from the rembg project; ISNet is used
instead if models/isnet-general-use.onnx is present) separates the garment from the floor or bed. That
gives two things:
  1. a transparent PNG shown on a clean light tile in the closet, like a store's product shot;
  2. the garment's real pixels for its color swatches. Indoor light tints photos, so the brightest
     background (a white door or wall) is used as a white reference first. Color *names* stay with the
     Closet Cataloger and with Olivia's own corrections (see learn_color, tied to the shade they were made on), because a phone camera under
     warm light can turn fuchsia into raspberry and navy into black, and no pixel math can undo that.
Runs locally on the CPU (about a second per photo); no API cost. If the model can't load, items just
keep their original photo.
"""

from __future__ import annotations

import io
import re
import threading
import urllib.request

import numpy as np
from PIL import Image

from . import config, store

MODELS = config.PROJECT_DIR / "models"
SMALL = ("u2netp.onnx", 320, (0.485, 0.456, 0.406), (0.229, 0.224, 0.225))
LARGE = ("isnet-general-use.onnx", 1024, (0.5, 0.5, 0.5), (1.0, 1.0, 1.0))
SMALL_URL = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx"

_session = None
_spec = None
_lock = threading.Lock()


def _load():
    """The ONNX session, loaded once (downloads the 4.6 MB small model the first time)."""
    global _session, _spec
    if _session is not None:
        return _session
    with _lock:
        if _session is not None:
            return _session
        import onnxruntime as ort
        MODELS.mkdir(exist_ok=True)
        spec = LARGE if (MODELS / LARGE[0]).exists() else SMALL
        path = MODELS / spec[0]
        if not path.exists():
            urllib.request.urlretrieve(SMALL_URL, path)
        _session, _spec = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"]), spec
    return _session


def mask(img: Image.Image) -> np.ndarray:
    """Garment probability 0..1 per pixel, same size as img."""
    sess = _load()
    _, size, mean, std = _spec
    x = np.asarray(img.convert("RGB").resize((size, size), Image.LANCZOS), dtype=np.float32) / 255.0
    x = ((x - mean) / std).transpose(2, 0, 1)[None].astype(np.float32)
    out = sess.run(None, {sess.get_inputs()[0].name: x})[0][0, 0]
    out = (out - out.min()) / (out.max() - out.min() + 1e-8)
    return np.asarray(Image.fromarray((out * 255).astype(np.uint8)).resize(img.size, Image.LANCZOS), dtype=np.float32) / 255.0


def _exposure_gain(rgb: np.ndarray, m: np.ndarray) -> np.ndarray:
    """Per-channel gain that makes the brightest background (a white door, wall or sheet) read white.
    No bright background, no correction."""
    bg = rgb[m < 0.05]
    if len(bg) < 500:
        return np.ones(3)
    lum = bg.mean(axis=1)
    ref = bg[lum >= np.percentile(lum, 97)].mean(axis=0)
    if ref.min() < 110 or (ref.max() - ref.min()) > 60:  # too dark or clearly colored: not a white reference
        return np.ones(3)
    return np.clip(240.0 / ref, 1.0, 1.8)


def _lab(rgb: np.ndarray) -> np.ndarray:
    c = np.asarray(rgb, dtype=np.float64) / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    xyz = c @ np.array([[0.4124, 0.2126, 0.0193], [0.3576, 0.7152, 0.1192], [0.1805, 0.0722, 0.9505]])
    xyz /= np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], axis=-1)


def main_colors(pixels: np.ndarray, k: int = 3) -> list[str]:
    """Hex of the main garment colors (k-means in Lab), biggest first, each covering at least 15%."""
    if len(pixels) > 20000:
        pixels = pixels[np.random.default_rng(0).choice(len(pixels), 20000, replace=False)]
    lab = _lab(pixels)
    centers = lab[np.linspace(0, len(lab) - 1, k).astype(int)]
    for _ in range(12):
        labels = ((lab[:, None] - centers[None]) ** 2).sum(-1).argmin(1)
        centers = np.array([lab[labels == j].mean(0) if (labels == j).any() else centers[j] for j in range(k)])
    counts = np.bincount(labels, minlength=k)
    return ["#%02X%02X%02X" % tuple(np.median(pixels[labels == j], axis=0).round().astype(int))
            for j in np.argsort(-counts) if counts[j] / len(labels) >= 0.15]


def _rgb(h: str):
    h = (h or "").lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)] if len(h) == 6 else None


def _nearest(anchor: str, measured: list[str]) -> str:
    """Swatch for one named color: the measured garment color closest to the cataloger's own guess, if it's
    close enough to be the same color (a white letter on a navy sweater keeps its own swatch)."""
    a = _rgb(anchor)
    if not a:
        return measured[0]
    lab = _lab(np.array([a] + [_rgb(m) for m in measured]))
    d = ((lab[1:] - lab[0]) ** 2).sum(1) ** 0.5
    j = int(d.argmin())
    return measured[j] if d[j] < 30 else anchor


def process(jpeg: bytes) -> tuple[bytes, list[str]]:
    """(cutout PNG cropped to the whole garment, measured main color hexes)."""
    img = Image.open(io.BytesIO(jpeg)).convert("RGB")
    m = mask(img)
    rgb = np.asarray(img, dtype=np.float32)
    gain = _exposure_gain(rgb, m)
    fixed = np.clip(rgb * gain, 0, 255).astype(np.uint8)
    colors = main_colors(fixed[m > 0.7].astype(np.float32)) if (m > 0.7).sum() > 200 else []
    alpha = (np.clip((m - 0.15) / 0.7, 0, 1) * 255).astype(np.uint8)
    cut = Image.fromarray(fixed).convert("RGBA")
    cut.putalpha(Image.fromarray(alpha))
    box = Image.fromarray(alpha).point(lambda a: 255 if a > 40 else 0).getbbox()
    if box:
        # crop to the garment, then add a clear margin on a bigger canvas: store photos often run edge to edge
        cut = cut.crop(box)
        pad = int(0.05 * max(cut.size))
        framed = Image.new("RGBA", (cut.width + 2 * pad, cut.height + 2 * pad), (0, 0, 0, 0))
        framed.paste(cut, (pad, pad))
        cut = framed
    out = io.BytesIO()
    cut.save(out, "PNG", optimize=True)
    return out.getvalue(), colors


def attach(dataset: str, item_id: str) -> dict | None:
    """Make (or remake) the cutout for one closet item and store its measured colors."""
    item = next((i for i in store.closet(dataset) if i["id"] == item_id), None)
    path = store.image_path(dataset, item["image"]) if item and item.get("image") else None
    if not path:
        return None
    png, colors = process(path.read_bytes())
    name = f"{item_id}.cut.png"
    (path.parent / name).write_bytes(png)
    fields = {"cutout": name}
    if colors and item.get("colors"):
        fields["colors"] = [dict(c, hex=_nearest(c.get("hex"), colors)) for c in item["colors"]]
    return store.update_item(dataset, item_id, fields)


# ---- Olivia's color words: corrections teach the cataloger -------------------
# A correction is tied to the shade it was made on: "raspberry is fuchsia" was said about one deep pink, so it
# must not turn a red, coral or burgundy piece fuchsia. It applies only when the new piece's measured color is
# within SAME_SHADE (CIE Lab distance) of the corrected one.
SAME_SHADE = 20
DARK_L = 30  # Lab lightness below which a color fix is never generalized (dim-light darks are indistinguishable)


def _shade_gap(a: str, b: str) -> float:
    ra, rb = _rgb(a), _rgb(b)
    if not ra or not rb:
        return 999.0
    la, lb = _lab(np.array([ra, rb]))
    return float(((la - lb) ** 2).sum() ** 0.5)


def learn_color(dataset: str, said: str, means: str, hex_: str = "") -> None:
    """She renamed a color (raspberry -> fuchsia) on a piece with this measured hex: remember both."""
    said, means = said.strip().lower(), means.strip().lower()
    if not said or not means or said == means:
        return
    rgb = _rgb(hex_)
    if rgb and _lab(np.array([rgb]))[0][0] < DARK_L:
        # black, charcoal and navy all look alike in a dim floor photo: one "black -> charcoal" fix must not
        # rename every black piece after it (it did). The rename still applies to the piece she fixed.
        return
    prof = store.profile(dataset)
    words = prof.setdefault("color_words", {})
    words[said] = {"means": means, "hex": hex_}
    store.save_profile(dataset, prof)


def color_words(dataset: str) -> dict:
    """{said: {"means": ..., "hex": ...}} (older entries were plain strings, with no shade)."""
    return {k: (v if isinstance(v, dict) else {"means": v, "hex": ""})
            for k, v in (store.profile(dataset).get("color_words") or {}).items()}


def apply_color_words(dataset: str, item: dict) -> dict:
    """Rename colors she corrected before, only on the same shade; saves the item if anything changed."""
    words, changed = color_words(dataset), False
    for c in item.get("colors") or []:
        key = (c.get("name") or "").lower()
        w = words.get(key)
        if w and w["hex"] and _shade_gap(w["hex"], c.get("hex")) <= SAME_SHADE:
            c["name"] = w["means"]
            item["name"] = re.sub(re.escape(key), w["means"], item.get("name", ""), flags=re.I)
            changed = True
    if changed and item.get("id"):
        return store.update_item(dataset, item["id"], {"colors": item["colors"], "name": item["name"]})
    return item


def backfill(dataset: str) -> int:
    """Cutouts for items added before this existed."""
    n = 0
    for it in store.closet(dataset):
        if it.get("image") and not it.get("cutout"):
            try:
                attach(dataset, it["id"])
                n += 1
            except Exception as e:  # one odd photo shouldn't stop the rest
                print(f"cutout skipped for {it['id']}: {type(e).__name__}")
    return n


def finish(dataset: str, item: dict) -> dict:
    """After an add: product-style cutout + measured swatches. Never fails the add."""
    try:
        return attach(dataset, item["id"]) or item
    except Exception as e:
        print(f"cutout skipped for {item.get('id')}: {type(e).__name__}: {e}")
        return item


def edge_margin(jpeg: bytes) -> float:
    """Smallest gap between the garment and the photo's edge, as a fraction of the photo (0 = cut off)."""
    img = Image.open(io.BytesIO(jpeg)).convert("RGB")
    box = Image.fromarray((mask(img) > 0.5).astype(np.uint8) * 255).getbbox()
    if not box:
        return 0.0
    w, h = img.size
    return min(box[0] / w, box[1] / h, (w - box[2]) / w, (h - box[3]) / h)
