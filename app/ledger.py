"""Run ledger: counts every token and dollar, enforces budgets, and records a trace.

One Ledger = one button press in the app. Each agent step appends a trace event
(what the agent did, which tool it called, what it cost), which the app shows in
the Run Trace panel and writes to logs/runs.jsonl for the tokenomics report.
"""

from __future__ import annotations

import json
import time
import uuid
from collections import deque
from datetime import datetime, timezone

from . import config, pricing


class BudgetExceeded(RuntimeError):
    """Raised before a model call that would break a spending limit."""


_recent_runs: deque[float] = deque()


def check_rate_limit() -> None:
    now = time.time()
    while _recent_runs and now - _recent_runs[0] > 60:
        _recent_runs.popleft()
    if len(_recent_runs) >= config.MAX_RUNS_PER_MINUTE:
        raise BudgetExceeded(
            f"Rate limit: at most {config.MAX_RUNS_PER_MINUTE} runs per minute. Wait a moment and try again."
        )
    _recent_runs.append(now)


def spent_today_usd(images: bool | None = None) -> float:
    """Today's spend. images=True: only image runs (own OpenAI key); False: only course-key runs; None: all."""
    path = config.LOG_DIR / "runs.jsonl"
    if not path.exists():
        return 0.0
    today = datetime.now(timezone.utc).date().isoformat()
    total = 0.0
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not row.get("started_at", "").startswith(today):
            continue
        if images is not None and (row.get("mode") in config.IMAGE_MODES) != images:
            continue
        total += row.get("totals", {}).get("cost_usd", 0.0)
    return total


class Ledger:
    def __init__(self, mode: str, dataset: str, max_tokens: int | None = None, max_usd: float | None = None,
                 max_calls: int | None = None):
        self.run_id = uuid.uuid4().hex[:10]
        self.mode = mode
        self.dataset = dataset
        self.started = time.time()
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.max_tokens = max_tokens or config.MAX_TOKENS_PER_RUN
        self.max_usd = max_usd or config.MAX_USD_PER_RUN
        self.max_calls = max_calls or config.MAX_MODEL_CALLS_PER_RUN
        self.calls: list[dict] = []
        self.trace: list[dict] = []
        self.safety_events: list[dict] = []
        self.is_image = mode in config.IMAGE_MODES
        self.max_usd_day = config.MAX_USD_PER_DAY_IMAGES if self.is_image else config.MAX_USD_PER_DAY
        self._day_spent_at_start = spent_today_usd(images=self.is_image)

    # ---- budgets -------------------------------------------------------
    @property
    def tokens(self) -> int:
        return sum(c["input_tokens"] + c["output_tokens"] for c in self.calls)

    @property
    def cost(self) -> float:
        return sum(c["cost_usd"] for c in self.calls)

    def before_call(self, agent: str) -> None:
        if len(self.calls) >= self.max_calls:
            self._stop(agent, f"Stopped: this run reached {self.max_calls} model calls (loop guard).")
        if self.tokens >= self.max_tokens:
            self._stop(agent, f"Stopped: this run used its {self.max_tokens:,}-token budget.")
        if self.cost >= self.max_usd:
            self._stop(agent, f"Stopped: this run hit its ${self.max_usd:.2f} spending cap." if self.max_usd >= 0.01 else f"Stopped: this run hit its ${self.max_usd:.4f} spending cap.")
        if self._day_spent_at_start + self.cost >= self.max_usd_day:
            self._stop(agent, f"Stopped: today's ${self.max_usd_day:.2f} {'image ' if self.is_image else ''}budget is used up.")

    def _stop(self, agent: str, message: str) -> None:
        self.safety("budget", agent, message)
        raise BudgetExceeded(message)

    # ---- recording -----------------------------------------------------
    def record_call(self, agent: str, usage, web_searches: int = 0, seconds: float = 0.0) -> dict:
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        details = getattr(usage, "input_tokens_details", None)
        cached = (getattr(details, "cached_tokens", 0) or 0) if details else 0
        out_details = getattr(usage, "output_tokens_details", None)
        reasoning = (getattr(out_details, "reasoning_tokens", 0) or 0) if out_details else 0
        row = {
            "agent": agent,
            "input_tokens": input_tokens,
            "cached_tokens": cached,
            "output_tokens": output_tokens,
            "reasoning_tokens": reasoning,
            "web_searches": web_searches,
            "seconds": round(seconds, 2),
            "cost_usd": pricing.call_cost(input_tokens, cached, output_tokens, web_searches),
        }
        self.calls.append(row)
        return row

    def record_image_call(self, agent: str, usage, seconds: float = 0.0) -> dict:
        details = getattr(usage, "input_tokens_details", None)
        image_in = (getattr(details, "image_tokens", 0) or 0) if details else 0
        text_in = (getattr(details, "text_tokens", 0) or 0) if details else 0
        input_tokens = getattr(usage, "input_tokens", 0) or (image_in + text_in)
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        row = {
            "agent": agent, "input_tokens": input_tokens, "cached_tokens": 0, "output_tokens": output_tokens,
            "reasoning_tokens": 0, "web_searches": 0, "seconds": round(seconds, 2),
            "image_input_tokens": image_in, "text_input_tokens": text_in,
            "cost_usd": pricing.image_cost(text_in, image_in, output_tokens),
        }
        self.calls.append(row)
        return row

    def step(self, agent: str, kind: str, summary: str, detail=None) -> None:
        self.trace.append({
            "t": round(time.time() - self.started, 2),
            "agent": agent,
            "kind": kind,
            "summary": summary,
            "detail": detail,
        })

    def safety(self, kind: str, agent: str, message: str, detail=None) -> None:
        event = {"kind": kind, "agent": agent, "message": message, "detail": detail}
        self.safety_events.append(event)
        self.step(agent, "safety", message, detail)

    # ---- summaries -----------------------------------------------------
    def totals(self) -> dict:
        by_agent: dict[str, dict] = {}
        for c in self.calls:
            a = by_agent.setdefault(c["agent"], {
                "calls": 0, "input_tokens": 0, "cached_tokens": 0, "output_tokens": 0,
                "web_searches": 0, "cost_usd": 0.0,
            })
            a["calls"] += 1
            for k in ("input_tokens", "cached_tokens", "output_tokens", "web_searches", "cost_usd"):
                a[k] += c[k]
        return {
            "calls": len(self.calls),
            "input_tokens": sum(c["input_tokens"] for c in self.calls),
            "cached_tokens": sum(c["cached_tokens"] for c in self.calls),
            "output_tokens": sum(c["output_tokens"] for c in self.calls),
            "reasoning_tokens": sum(c["reasoning_tokens"] for c in self.calls),
            "web_searches": sum(c["web_searches"] for c in self.calls),
            "cost_usd": self.cost,
            "seconds": round(time.time() - self.started, 1),
            "by_agent": by_agent,
        }

    def summary(self) -> dict:
        return {
            "run_id": self.run_id,
            "mode": self.mode,
            "dataset": self.dataset,
            "started_at": self.started_at,
            "totals": self.totals(),
            "trace": self.trace,
            "safety_events": self.safety_events,
            "budget": {"max_tokens": self.max_tokens, "max_usd": self.max_usd, "max_usd_day": self.max_usd_day},
        }

    def save(self, status: str) -> dict:
        data = self.summary() | {"status": status}
        config.LOG_DIR.mkdir(exist_ok=True)
        with (config.LOG_DIR / "runs.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(data) + "\n")
        return data
