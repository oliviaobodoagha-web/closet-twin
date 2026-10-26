"""One small agent loop on the OpenAI Responses API (through Portkey).

run_agent() sends an agent's instructions + input to gpt-6-luna, runs any
function tools the model asks for, and repeats until the model returns its
final structured answer. Every call goes through the run Ledger first, so
budgets and the loop guard apply to all agents the same way.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Callable

from openai import OpenAI

from . import config
from .ledger import Ledger


@lru_cache(maxsize=1)
def client() -> OpenAI:
    if config.provider() == "openai":
        # Your own OpenAI key (e.g. after the course key is retired): same model, direct to OpenAI.
        return OpenAI(api_key=config.api_key(), timeout=config.MODEL_TIMEOUT_SECONDS, max_retries=1)
    return OpenAI(
        api_key=config.api_key(),
        base_url=config.PORTKEY_BASE_URL,
        timeout=config.MODEL_TIMEOUT_SECONDS,
        max_retries=1,
        # Every run must be a real run: never let the gateway replay a cached answer.
        default_headers={"x-portkey-provider": "openai", "x-portkey-cache-force-refresh": "true"},
    )


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    fn: Callable[..., Any]

    def spec(self) -> dict:
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "strict": True,
        }


@dataclass
class AgentResult:
    output: Any
    citations: list[dict] = field(default_factory=list)
    searches: list[str] = field(default_factory=list)
    seen_urls: list[str] = field(default_factory=list)  # every page the web search returned or opened


def obj_schema(properties: dict, required: list[str] | None = None) -> dict:
    """Strict JSON schema helper: every property required, no extras."""
    return {
        "type": "object",
        "properties": properties,
        "required": required if required is not None else list(properties),
        "additionalProperties": False,
    }


def run_agent(
    ledger: Ledger,
    agent: str,
    instructions: str,
    input_items: list | str,
    *,
    schema: dict | None = None,
    schema_name: str = "answer",
    tools: list[Tool] | None = None,
    web_search: bool = False,
    effort: str = "low",
    max_turns: int = 6,
    max_tool_calls: int | None = None,
) -> AgentResult:
    tools = tools or []
    by_name = {t.name: t for t in tools}
    tool_specs = [t.spec() for t in tools]
    if web_search:
        tool_specs.append({"type": "web_search"})

    items: list = [{"role": "user", "content": input_items}] if isinstance(input_items, str) else list(input_items)
    kwargs: dict[str, Any] = {
        "model": config.MODEL_NAME,
        "instructions": instructions,
        "reasoning": {"effort": effort},
        # Same key for the same agent so the stable prefix (instructions + closet) is cached.
        "prompt_cache_key": f"closet-twin-{agent}",
    }
    if tool_specs:
        kwargs["tools"] = tool_specs
    if max_tool_calls:
        # Hard cap on built-in tool calls (web searches) inside one model response.
        kwargs["max_tool_calls"] = max_tool_calls
    if web_search:
        # Ask for the result URLs of each search, so links can be checked against what the search really saw.
        kwargs["include"] = ["web_search_call.action.sources"]
    if schema:
        kwargs["text"] = {"format": {"type": "json_schema", "name": schema_name, "schema": schema, "strict": True}}

    citations: list[dict] = []
    searches: list[str] = []
    seen_urls: list[str] = []
    for _turn in range(max_turns):
        ledger.before_call(agent)
        t0 = time.time()
        response = client().responses.create(input=items, **kwargs)
        n_search = sum(1 for o in response.output if o.type == "web_search_call")
        row = ledger.record_call(agent, response.usage, web_searches=n_search, seconds=time.time() - t0)
        ledger.step(agent, "model", f"model call: {row['input_tokens']:,} in ({row['cached_tokens']:,} cached) / {row['output_tokens']:,} out", row)

        calls = []
        for o in response.output:
            if o.type == "web_search_call":
                summary, query, urls = _web_action(getattr(o, "action", None))
                searches.append(query)
                seen_urls += urls
                ledger.step(agent, "tool", summary)
            elif o.type == "function_call":
                calls.append(o)
            elif o.type == "message":
                for part in o.content:
                    for ann in getattr(part, "annotations", None) or []:
                        if getattr(ann, "type", "") == "url_citation":
                            citations.append({"url": ann.url, "title": getattr(ann, "title", "")})

        if not calls:
            text = response.output_text or ""
            return AgentResult(json.loads(text) if schema else text, citations, searches, seen_urls)

        items += [o.model_dump(exclude_none=True) for o in response.output]
        for call in calls:
            tool = by_name.get(call.name)
            try:
                args = json.loads(call.arguments or "{}")
                result = tool.fn(**args) if tool else {"error": f"unknown tool {call.name}"}
            except Exception as e:  # a broken tool call should not crash the run
                result = {"error": f"{type(e).__name__}: {e}"}
            ledger.step(agent, "tool", f"{call.name}({_short(call.arguments)})", _preview(result))
            items.append({"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(result)})

    ledger.safety("loop", agent, f"Stopped {agent}: it kept calling tools for {max_turns} turns without answering.")
    raise RuntimeError(f"{agent} did not finish within {max_turns} turns.")


def _web_action(action: Any) -> tuple[str, str, list[str]]:
    """One web_search_call action -> (trace line, query sent to the web, URLs it returned or opened)."""
    kind = getattr(action, "type", "") or "search"
    if kind == "open_page":
        url = getattr(action, "url", None) or ""
        return (f"open_page: {url}" if url else "open_page"), "", [url] if url else []
    if kind == "find_in_page":
        url = getattr(action, "url", None) or ""
        return f"find_in_page: '{_short(getattr(action, 'pattern', ''), 40)}' in {url}", "", [url] if url else []
    query = getattr(action, "query", None) or "; ".join(getattr(action, "queries", None) or [])
    urls = [s.url for s in getattr(action, "sources", None) or [] if getattr(s, "url", None)]
    found = f" ({len(urls)} result link(s))" if urls else ""
    return (f"web_search: {query}{found}" if query else f"web_search{found}"), query, urls


def _short(text: str | None, n: int = 90) -> str:
    text = (text or "").replace("\n", " ")
    return text if len(text) <= n else text[: n - 1] + "…"


def _preview(result: Any) -> Any:
    raw = json.dumps(result)
    return result if len(raw) < 1500 else raw[:1500] + "…"
