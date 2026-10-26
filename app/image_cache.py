"""Never pay twice for the same picture.

Every image call (mock-ups, outfit boards, goal picture, product shots, photo try-ons) is keyed by what it would
send: model, prompt, size and the bytes of every input photo. If that exact picture was drawn before and its file
is still there, the saved file is used instead ($0). Two requests for the same picture at once share one drawing:
the second waits for the first, then reuses it.
"""

from __future__ import annotations

import hashlib
import json
import threading
from contextlib import contextmanager
from pathlib import Path

from . import store

_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()


def key(*parts) -> str:
    """Hash of the prompt/settings (str) and input photos (Path or bytes), in order."""
    h = hashlib.sha256()
    for p in parts:
        if isinstance(p, Path):
            p = p.read_bytes() if p.exists() else f"<missing {p.name}>"
        h.update(p if isinstance(p, bytes) else str(p).encode())
        h.update(b"\0")
    return h.hexdigest()[:32]


@contextmanager
def claim(k: str):
    """Only one drawing per key at a time; a twin request waits here, then finds the saved picture."""
    with _guard:
        lock = _locks.setdefault(k, threading.Lock())
    with lock:
        yield


def _index_path(dataset: str) -> Path:
    return store.folder(dataset) / "image_cache.json"


def _index(dataset: str) -> dict:
    try:
        return json.loads(_index_path(dataset).read_text())
    except (OSError, ValueError):
        return {}


def find(dataset: str, k: str) -> Path | None:
    """The saved picture for this key, if it is still on disk."""
    rel = _index(dataset).get(k)
    path = store.folder(dataset) / rel if rel else None
    return path if path and path.exists() else None


def keep(dataset: str, k: str, path: Path) -> None:
    with _guard:
        index = _index(dataset)
        index[k] = str(path.relative_to(store.folder(dataset)))
        _index_path(dataset).write_text(json.dumps(index, indent=1))


def forget(dataset: str, filename: str) -> None:
    """She rejected this picture: never hand it out again."""
    with _guard:
        index = _index(dataset)
        keep_ = {k: v for k, v in index.items() if Path(v).name != filename}
        if len(keep_) != len(index):
            _index_path(dataset).write_text(json.dumps(keep_, indent=1))
