"""Token prices and cost math for gpt-6-luna (USD per 1M tokens, standard tier).

Prices come from the course's Lecture 11 tokenomics starter, which cites
https://developers.openai.com/api/docs/pricing (checked 2026-10-06).
"""

from __future__ import annotations

PRICE_INPUT = 0.10
PRICE_CACHED_INPUT = 0.01
PRICE_OUTPUT = 0.50
# The built-in web search tool is billed per call on top of tokens.
PRICE_PER_WEB_SEARCH = 0.01


def call_cost(input_tokens: int, cached_tokens: int, output_tokens: int, web_searches: int = 0) -> float:
    fresh = max(input_tokens - cached_tokens, 0)
    return (
        fresh * PRICE_INPUT + cached_tokens * PRICE_CACHED_INPUT + output_tokens * PRICE_OUTPUT
    ) / 1e6 + web_searches * PRICE_PER_WEB_SEARCH


# gpt-image-2.5 (own OpenAI key), USD per 1M tokens, from
# https://developers.openai.com/api/docs/pricing (checked 2026-10-24).
IMAGE_PRICE_TEXT_INPUT = 5.00
IMAGE_PRICE_IMAGE_INPUT = 8.00
IMAGE_PRICE_IMAGE_OUTPUT = 30.00


def image_cost(text_in: int, image_in: int, image_out: int) -> float:
    return (text_in * IMAGE_PRICE_TEXT_INPUT + image_in * IMAGE_PRICE_IMAGE_INPUT + image_out * IMAGE_PRICE_IMAGE_OUTPUT) / 1e6
