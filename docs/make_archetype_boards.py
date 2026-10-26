"""One-off: draw the 7 style-archetype pictures shown on Margaux-Sloan's archetype tiles (static/archetypes/*.jpg).

Run once with your OPENAI_API_KEY in .env:  .venv/bin/python docs/make_archetype_boards.py
No personal data: fictional models, cropped at the chin. About $0.04 per picture.
"""

from __future__ import annotations

import base64
import io
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from openai import OpenAI  # noqa: E402
from PIL import Image  # noqa: E402

from app import config, stylists  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "static" / "archetypes"
MODELS = {"Classic": "a woman with light olive skin", "Elegant Chic": "a woman with deep brown skin",
          "Natural": "a woman with fair freckled skin", "Romantic": "a woman with medium brown skin",
          "Dramatic": "a woman with dark skin", "Creative": "a woman with light brown skin", "Gamine": "a woman with pale skin"}


# One unmistakable outfit per archetype. The piece lists overlap (coats, trousers), so the first drawings all came
# out as "long coat + trousers"; each look here avoids the others' signatures.
LOOKS = {
    "Classic": ("a navy blazer with gold buttons over a crisp white button-down, a knee-length camel pencil skirt, pearl "
                "studs, a thin brown belt, low nude pumps and a structured top-handle bag. Traditional and tidy. "
                "No long coat, no trousers"),
    "Elegant Chic": ("head-to-toe tonal ivory and oatmeal: a fluid silk blouse tucked into high-waisted wide-leg "
                     "trousers that pool over pointed slingbacks, one fine gold chain, a small sleek clutch. Long, "
                     "clean and quiet-luxury. No coat, no blazer, no pattern"),
    "Natural": ("a slouchy cream chunky knit sweater, loose sand-colored linen drawstring pants, flat leather slides "
                "and a big woven basket bag, earthy and relaxed, a little rumpled on purpose. No coat, no blazer, no "
                "tailoring"),
    "Dramatic": ("a bold red sculptural blazer with sharp exaggerated shoulders worn as a short dress, black opaque "
                 "tights, pointed black knee-high boots and a wide gold cuff. Striking, high contrast, powerful. "
                 "No long coat, no trousers"),
    "Gamine": ("1960s mod and playful: a short A-line shift dress in a bold black-and-white geometric print with a "
               "white Peter Pan collar, white ankle socks, black patent Mary Jane flats, a black beret and a tiny "
               "round bag. Youthful and quirky. No blazer, no stripes, no loafers"),
}


def prompt(name: str) -> str:
    g = stylists.GUIDE[name]
    outfit = LOOKS.get(name) or (f"one complete outfit built from {g['pieces']}; fabrics: {g['fabrics']}; silhouette: "
                                 f"{g['lines']}; colors: {g['colors']}; details: {g['details']}")
    return (f"Editorial fashion photograph showing the '{name}' style archetype: {MODELS[name]} wearing {outfit}. "
            f"Full outfit visible from the chin down to the shoes, standing naturally, framed "
            "so the face is out of frame above the top edge. Clean warm ivory studio backdrop, soft daylight, magazine "
            "quality, realistic fabric texture. No text, no logos, no face.")


def draw(client: OpenAI, name: str) -> str:
    res = client.images.generate(model=config.IMAGE_MODEL, prompt=prompt(name), size="1024x1536",
                                 quality=config.IMAGE_QUALITY, output_format="jpeg")
    img = Image.open(io.BytesIO(base64.b64decode(res.data[0].b64_json))).convert("RGB")
    img.thumbnail((640, 960))
    path = OUT / f"{name.lower().replace(' ', '-')}.jpg"
    img.save(path, "JPEG", quality=85)
    return path.name


if __name__ == "__main__":
    key = config.openai_key()
    if not key:
        sys.exit("Needs OPENAI_API_KEY in .env")
    OUT.mkdir(exist_ok=True)
    client = OpenAI(api_key=key, timeout=240, max_retries=1)
    todo = [n for n in stylists.ARCHETYPES if not (OUT / f"{n.lower().replace(' ', '-')}.jpg").exists()]
    with ThreadPoolExecutor(4) as pool:
        for name, fut in [(n, pool.submit(draw, client, n)) for n in todo]:
            try:
                print("ok", fut.result())
            except Exception as e:
                print("failed", name, type(e).__name__, str(e)[:160])
