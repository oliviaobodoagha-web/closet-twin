"""Measure what each cost-cutting choice saves, and whether it hurts quality.

    python tests/cost_experiments.py           # about $0.03 on the course key

1. Closet format: one line per item vs. the same closet as JSON (input tokens).
2. Reasoning effort: Day Planner on "low" vs. "medium" (tokens, cost, critic scores, revisions).
3. Prompt caching: cached share of input tokens across all logged runs.
Results are printed and saved to docs/cost_experiments.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config, llm, store  # noqa: E402
from app.agents import common, orchestrator, planner  # noqa: E402
from app.ledger import Ledger  # noqa: E402

DAY = "2026-10-26"


def count_input_tokens(text: str) -> int:
    r = llm.client().responses.create(model=config.MODEL_NAME, input=text, max_output_tokens=16, reasoning={"effort": "low"})
    return r.usage.input_tokens


def closet_format() -> dict:
    closet = store.closet("sample")
    brief = common.closet_brief(closet)
    as_json = json.dumps(closet, indent=1)
    a, b = count_input_tokens(brief), count_input_tokens(as_json)
    print(f"Closet as one line per item: {a:,} tokens   as JSON: {b:,} tokens   ({100 * (1 - a / b):.0f}% fewer)")
    return {"brief_tokens": a, "json_tokens": b, "saving_pct": round(100 * (1 - a / b), 1), "items": len(closet)}


def effort_trial(effort: str, runs: int = 2) -> dict:
    real = planner.run_agent

    def with_effort(*args, **kw):
        kw["effort"] = effort
        return real(*args, **kw)

    planner.run_agent = with_effort
    rows = []
    try:
        for _ in range(runs):
            lg = Ledger(f"experiment_effort_{effort}", "sample")
            out = orchestrator.run_plan_day(lg, "sample", DAY)
            run = lg.save("ok")
            t = run["totals"]
            planner_rounds = sum(1 for s in run["trace"] if s["agent"] == "Day Planner" and s["kind"] == "start")
            scores = out["review"].get("scores", {})
            rows.append({
                "run_id": run["run_id"], "cost_usd": t["cost_usd"], "input": t["input_tokens"], "cached": t["cached_tokens"],
                "output": t["output_tokens"], "reasoning": t["reasoning_tokens"], "seconds": t["seconds"],
                "planner_rounds": planner_rounds, "final_verdict": out["review"]["verdict"],
                "critic_avg_score": round(sum(scores.values()) / max(len(scores), 1), 2),
            })
    finally:
        planner.run_agent = real
    avg = lambda k: round(sum(r[k] for r in rows) / len(rows), 5)  # noqa: E731
    summary = {k: avg(k) for k in ("cost_usd", "input", "output", "reasoning", "seconds", "planner_rounds", "critic_avg_score")}
    print(f"Planner effort={effort}: {summary}")
    return {"effort": effort, "runs": rows, "avg": summary}


def caching_from_logs() -> dict:
    path = config.LOG_DIR / "runs.jsonl"
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()] if path.exists() else []
    inp = sum(r["totals"]["input_tokens"] for r in rows)
    cached = sum(r["totals"]["cached_tokens"] for r in rows)
    print(f"Prompt caching across {len(rows)} logged runs: {cached:,} of {inp:,} input tokens cached ({100 * cached / max(inp, 1):.0f}%)")
    return {"runs": len(rows), "input_tokens": inp, "cached_tokens": cached, "cached_pct": round(100 * cached / max(inp, 1), 1)}


if __name__ == "__main__":
    results = {"closet_format": closet_format(), "effort": [effort_trial("low", 4), effort_trial("medium", 4)], "caching": caching_from_logs()}
    out = config.PROJECT_DIR / "docs" / "cost_experiments.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(results, indent=2))
    print(f"\nSaved {out}")
