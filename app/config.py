"""Paths, model, keys and spending limits shared by every agent.

Every agent uses one model, gpt-6-luna, through Portkey's OpenAI-compatible
gateway with the course key. The model name is a constant on purpose.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values

APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent
PROMPTS_DIR = APP_DIR / "prompts"
STATIC_DIR = PROJECT_DIR / "static"
DATA_DIR = PROJECT_DIR / "data"
LOG_DIR = PROJECT_DIR / "logs"

# Look for .env in the repo first, then one folder up (the teaching staff's submissions/.env).
# load_dotenv never overrides a value that is already set, so the repo's own .env wins.
# Empty values are skipped, so a copied .env.example (PORTKEY_API_KEY=) can't hide the real key one folder up.
ENV_FILES = [PROJECT_DIR / ".env", PROJECT_DIR.parent / ".env"]
for _env in ENV_FILES:
    if _env.is_file():
        for _k, _v in dotenv_values(_env).items():
            if _v and _v.strip() and not os.environ.get(_k, "").strip():
                os.environ[_k] = _v.strip()

MODEL_NAME = "gpt-6-luna"
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"

# Which data set the app uses: "sample" ships with the repo, "user" is your own
# closet in data/user/ (never committed). Switch in the app header or with STYLIST_DATA.
DEFAULT_DATASET = os.getenv("STYLIST_DATA", "sample")

# Spending guardrails. A bug or a bad actor cannot burn through the budget:
# every model call checks these before it is sent. The dollar caps can be changed in .env.
MAX_TOKENS_PER_RUN = 150_000        # one button press (all agents together)
MAX_USD_PER_RUN = float(os.getenv("MAX_USD_PER_RUN", "0.05"))
MAX_USD_PER_LIVE_WEB_RUN = float(os.getenv("MAX_USD_PER_LIVE_WEB_RUN", "0.15"))      # live web search is billed per search
MAX_WEB_SEARCHES_PER_CALL = 5
MAX_USD_PER_DAY = float(os.getenv("MAX_USD_PER_DAY", "1.00"))              # summed from logs/runs.jsonl
MAX_RUNS_PER_MINUTE = 6
MAX_BULK_ADD = 16                   # photos or links per bulk-add run
BULK_WORKERS = 8                    # photos tagged at the same time within a run
MAX_MODEL_CALLS_PER_RUN = 14        # stops tool loops that never finish
MAX_CRITIC_ROUNDS = 2               # critic can send work back at most twice
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
VISION_MAX_SIDE = 768               # photos are shrunk before the model sees them

MODEL_TIMEOUT_SECONDS = 90


def provider() -> str:
    """'portkey' (course key, preferred) or 'openai' (your own key, e.g. after the course ends)."""
    if os.getenv("PORTKEY_API_KEY", "").strip():
        return "portkey"
    if os.getenv("OPENAI_API_KEY", "").strip():
        return "openai"
    return "none"


def api_key() -> str:
    key = os.getenv("PORTKEY_API_KEY", "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "No API key found. Put PORTKEY_API_KEY (or your own OPENAI_API_KEY) in a .env file "
            "in this folder or the folder above it."
        )
    return key


# Optional photo-real try-on runs on the user's OWN OpenAI key (course rule: the course
# key is gpt-6-luna only). Without OPENAI_API_KEY the rest of the app works unchanged.
IMAGE_MODEL = "gpt-image-2.5-sunburst"
IMAGE_SIZE = "1024x1536"
IMAGE_QUALITY = "medium"
MAX_PHOTO_TRYONS_PER_DAY = int(os.getenv("MAX_PHOTO_TRYONS_PER_DAY", "10"))
MAX_USD_PER_PHOTO_TRYON = float(os.getenv("MAX_USD_PER_PHOTO_TRYON", "0.40"))
PHOTO_MAX_SIDE = 1536
# 360° turntable: 7 new angles around one try-on image (the 8th is the image itself)
# image runs bill Olivia's own OPENAI_API_KEY, so they get their own daily cap instead of eating the course key's
IMAGE_MODES = {"photo_tryon", "photo_turntable", "product_shot", "mockup"}
MAX_USD_PER_DAY_IMAGES = float(os.getenv("MAX_USD_PER_DAY_IMAGES", "2.00"))
MAX_PRODUCT_SHOTS_PER_DAY = int(os.getenv("MAX_PRODUCT_SHOTS_PER_DAY", "60"))
MAX_USD_PER_PRODUCT_SHOT = float(os.getenv("MAX_USD_PER_PRODUCT_SHOT", "0.08"))
MAX_TURNTABLES_PER_DAY = int(os.getenv("MAX_TURNTABLES_PER_DAY", "3"))
MAX_USD_PER_TURNTABLE = float(os.getenv("MAX_USD_PER_TURNTABLE", "0.40"))


def openai_key() -> str:
    return os.getenv("OPENAI_API_KEY", "").strip()


def key_is_set() -> bool:
    return provider() != "none"


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
