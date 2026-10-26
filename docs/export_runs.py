"""Export real runs from logs/runs.jsonl as committed evidence, plus per-mode token stats.

    python docs/export_runs.py

Writes docs/runs_evidence.jsonl (sample data set only, so no personal data) and
docs/tokenomics.json. Gateway replays (identical usage to an earlier run and
finishing implausibly fast) are dropped, so every number comes from a real run.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "logs" / "runs.jsonl"
PERSONAL_MODES = {"analyze_color", "photo_tryon", "analyze_body", "photo_turntable"}


def is_replay(run: dict, seen: set) -> bool:
    t = run["totals"]
    key = (t["input_tokens"], t["cached_tokens"], t["output_tokens"], t["calls"])
    replay = key in seen and t["seconds"] < 0.25 * 10 * max(t["calls"], 1)
    seen.add(key)
    return replay


def main() -> None:
    rows = [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines() if l.strip()]
    seen: set = set()
    real, dropped = [], 0
    for r in rows:
        if r.get("mode") == "test" or not r["totals"]["calls"]:
            continue
        if is_replay(r, seen):
            dropped += 1
            continue
        real.append(r)

    # Runs that look at a person's photo never go into committed evidence.
    evidence = [r for r in real if r["dataset"] == "sample" and r["mode"] not in PERSONAL_MODES]
    with (ROOT / "docs" / "runs_evidence.jsonl").open("w", encoding="utf-8") as f:
        for r in evidence:
            f.write(json.dumps(r) + "\n")

    stats = {}
    for mode in sorted({r["mode"] for r in real}):
        rs = [r for r in real if r["mode"] == mode and r.get("status") == "ok"]
        if not rs:
            continue
        med = lambda k: statistics.median(r["totals"][k] for r in rs)  # noqa: E731
        stats[mode] = {
            "runs": len(rs),
            "median_calls": med("calls"),
            "median_input_tokens": med("input_tokens"),
            "median_cached_tokens": med("cached_tokens"),
            "median_output_tokens": med("output_tokens"),
            "median_web_searches": med("web_searches"),
            "median_cost_usd": round(med("cost_usd"), 5),
            "mean_cost_usd": round(statistics.mean(r["totals"]["cost_usd"] for r in rs), 5),
            "max_cost_usd": round(max(r["totals"]["cost_usd"] for r in rs), 5),
            "median_seconds": med("seconds"),
            "cached_share_pct": round(100 * sum(r["totals"]["cached_tokens"] for r in rs) / max(sum(r["totals"]["input_tokens"] for r in rs), 1), 1),
        }
    llm = [r for r in real if r["mode"] not in ("photo_tryon",) and r.get("status") == "ok"]
    inp = sum(r["totals"]["input_tokens"] for r in llm)
    cached = sum(r["totals"]["cached_tokens"] for r in llm)
    out = {"real_runs": len(real), "replays_dropped": dropped, "by_mode": stats,
           "caching": {"runs": len(llm), "input_tokens": inp, "cached_tokens": cached, "cached_pct": round(100 * cached / max(inp, 1), 1)}}
    (ROOT / "docs" / "tokenomics.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
