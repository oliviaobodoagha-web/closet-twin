"""Make an HTML file self-contained: every local <img src="..."> becomes a base64 data URI.

    python docs/inline_assets.py docs/report_src.html report.html

Remote URLs (CDNs) are left alone. Fails loudly if an image is missing, so a
submitted file never has a broken screenshot.
"""

from __future__ import annotations

import base64
import mimetypes
import re
import sys
from pathlib import Path


def inline(src: Path, dest: Path) -> None:
    html = src.read_text(encoding="utf-8")
    missing = []

    def repl(m: re.Match) -> str:
        path = m.group(2)
        if path.startswith(("http:", "https:", "data:")):
            return m.group(0)
        file = (src.parent / path).resolve()
        if not file.exists():
            missing.append(path)
            return m.group(0)
        mime = mimetypes.guess_type(file.name)[0] or "image/png"
        data = base64.b64encode(file.read_bytes()).decode()
        return f'{m.group(1)}"data:{mime};base64,{data}"'

    html = re.sub(r'(<img[^>]*?\ssrc=)"([^"]+)"', repl, html)
    if missing:
        raise SystemExit(f"Missing images: {missing}")
    dest.write_text(html, encoding="utf-8")
    print(f"Wrote {dest} ({dest.stat().st_size / 1e6:.1f} MB, all images embedded)")


if __name__ == "__main__":
    inline(Path(sys.argv[1]), Path(sys.argv[2]))
