"""Build report.html: fill docs/report_src.html with numbers from real runs, then embed every image.

    python docs/build_report.py [--plan RUN_ID] [--shop RUN_ID]

Numbers come from logs/runs.jsonl (Sample runs only), docs/tokenomics.json (current-code medians) and
docs/safety_test_results.txt. Olivia's own test results come from docs/user_test.json.
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
sys.path.insert(0, str(DOCS))
from inline_assets import inline  # noqa: E402

# runs per active user per month (Section 5); feedback, bans, fingerprints and the price tracker are free code
PER_MONTH = {"plan": 30, "swap": 10, "recommend": 4, "mockups": 1, "shop": 4, "shop_live": 4, "stylist_read": 4,
             "goal": 1, "aesthetic": 2, "photo": 5, "tryon": 30, "spin": 1}
IMAGES = {"mockups", "goal", "tryon", "spin"}
# the plan run shown step by step: Sample, Oct 27, sent back by code every round, best round shown
DEFAULT_PLAN = "d1f3879557"


def runs() -> list[dict]:
    return [json.loads(l) for l in (ROOT / "logs" / "runs.jsonl").read_text().splitlines() if l.strip()]


def pick(rows, mode, run_id=None):
    """A real Sample run (never Olivia's data), the given one or the latest."""
    cands = [r for r in rows if r["mode"] == mode and r.get("status") == "ok" and r["totals"]["seconds"] > 5
             and r.get("dataset") == "sample"]
    if run_id:
        cands = [r for r in cands if r["run_id"] == run_id] or cands
    return cands[-1] if cands else None


def totals_str(t) -> str:
    return (f"{t['calls']} model calls, {t['input_tokens']:,} input tokens ({t['cached_tokens']:,} cached), "
            f"{t['output_tokens']:,} output, ${t['cost_usd']:.4f}, {t['seconds']:.0f} s")


def trace_steps(run) -> str:
    out = []
    keep = ("tool", "safety", "check", "blocked", "verdict", "done", "fallback", "stop")
    for s in run["trace"]:
        if s["kind"] not in keep:
            continue
        summary = s["summary"]
        if s["kind"] == "verdict":  # the critic's verdict line, without its full essay
            summary = summary.split(". ")[0] + "."
        if len(summary) > 190:
            summary = summary[:187].rsplit(" ", 1)[0] + "…"
        text = html.escape(summary)
        if s["kind"] == "tool":
            text = f"called <code>{text}</code>"
        elif s["kind"] == "safety":
            text = f"🛡 <b>safety:</b> {text}"
        elif s["kind"] in ("check", "blocked") and s["agent"] == "Orchestrator":
            text = f"<b>code check:</b> {text}"
        if summary.startswith("Dropped alternate") and out and "dropped alternate" in out[-1]:
            continue  # one line per round is enough
        if summary.startswith("Dropped alternate"):
            text = "<b>code check:</b> dropped alternate(s) that broke a style rule"
        out.append(f'<li><span class="pill">{s["t"]:.1f}s</span><b>{html.escape(s["agent"])}</b>: {text}</li>')
    calls = [s for s in run["trace"] if s["kind"] == "model"]
    if calls:
        out.append(f'<li><span class="pill">ledger</span>{len(calls)} model calls: ' + "; ".join(
            f'{html.escape(c["agent"])} {c["detail"]["input_tokens"]:,} in ({c["detail"]["cached_tokens"]:,} cached) / {c["detail"]["output_tokens"]:,} out'
            for c in calls) + "</li>")
    return "\n".join(out)


def money(x: float) -> str:
    return f"${x:,.2f}" if x >= 1 else f"${x:.4f}" if x < 0.01 else f"${x:.3f}"


def main() -> None:
    args = sys.argv[1:]
    plan_id = args[args.index("--plan") + 1] if "--plan" in args else DEFAULT_PLAN
    shop_id = args[args.index("--shop") + 1] if "--shop" in args else None
    rows = runs()
    tok_all = json.loads((DOCS / "tokenomics.json").read_text())
    cur, old = tok_all["by_mode_current_code"], tok_all["by_mode"]
    cache = tok_all["caching"]
    user = json.loads((DOCS / "user_test.json").read_text()) if (DOCS / "user_test.json").exists() else {}

    plan = pick(rows, "plan_day", plan_id)
    shop = pick(rows, "shop_live", shop_id)

    def med(mode):
        """Current-code medians; a mode with no runs since the code changed falls back to all real runs."""
        return cur.get(mode) or old.get(mode, {})

    typical = {
        "Plan my day (fresh)": "plan_day",
        "Find what's missing (text)": "recommend",
        "Draw them: 6 mock-ups (image)": "mockup_set",
        "Stylist read": "stylist_read",
        "Goal picture (image)": "goal_picture",
        "Shop, practice catalog": "shop",
        "Shop, live web": "shop_live",
        "Add pieces (bulk photos)": "bulk_add",
        "Photo try-on (image)": "photo_tryon",
    }
    tt = ['<tr><th>Run type</th><th class="n">Runs</th><th class="n">Calls</th><th class="n">Input</th><th class="n">Cached</th>'
          '<th class="n">Output</th><th class="n">Web</th><th class="n">Cost (median)</th><th class="n">Max</th><th class="n">Time</th></tr>']
    for name, mode in typical.items():
        m = med(mode)
        if not m:
            continue
        tt.append(f"<tr><td>{name}</td><td class='n'>{m['runs']}</td><td class='n'>{m['median_calls']:g}</td><td class='n'>{m['median_input_tokens']:,.0f}</td>"
                  f"<td class='n'>{m['median_cached_tokens']:,.0f}</td><td class='n'>{m['median_output_tokens']:,.0f}</td><td class='n'>{m['median_web_searches']:g}</td>"
                  f"<td class='n'>{money(m['median_cost_usd'])}</td><td class='n'>{money(m['max_cost_usd'])}</td><td class='n'>{m['median_seconds']:.0f} s</td></tr>")

    def c_of(mode, fallback):
        return med(mode).get("median_cost_usd", fallback)

    c = {
        "plan": c_of("plan_day", 0.005), "swap": c_of("swap_outfit", 0.0005), "recommend": c_of("recommend", 0.0015),
        "mockups": c_of("mockup_set", 0.183), "shop": c_of("shop", 0.0025), "shop_live": c_of("shop_live", 0.055),
        "stylist_read": c_of("stylist_read", 0.0011), "goal": c_of("goal_picture", 0.011), "aesthetic": c_of("aesthetic", 0.0006),
        "photo": old.get("add_to_closet", {}).get("median_cost_usd", 0.0004),
        "tryon": c_of("photo_tryon", 0.059), "spin": c_of("photo_turntable", 0.245),
    }
    c_color = med("analyze_color").get("median_cost_usd", 0.0003)
    c_style = med("analyze_style").get("median_cost_usd", 0.0004)
    names = {"plan": "Plan my day (fresh)", "swap": "Show another option", "recommend": "Find what's missing (text)",
             "mockups": "Draw them: 6 mock-ups", "shop": "Shop, catalog", "shop_live": "Shop, live web",
             "stylist_read": "Stylist read", "goal": "Goal picture", "aesthetic": "Board read", "photo": "Add a piece (photo)",
             "tryon": "Daily try-on of the plan", "spin": "360° view"}
    line = {k: PER_MONTH[k] * c[k] for k in PER_MONTH}
    month = sum(line.values())
    image_month = sum(v for k, v in line.items() if k in IMAGES)
    text_month = month - image_month
    no_tryon = month - line["tryon"]
    feed = no_tryon - line["shop_live"] + PER_MONTH["shop_live"] * c["shop"]
    st = ['<tr><th>Item</th><th class="n">Per run</th><th class="n">Runs / user / month</th><th class="n">Per user / month</th></tr>']
    for k, n in PER_MONTH.items():
        tag = " <span class='small'>(image)</span>" if k in IMAGES else ""
        st.append(f"<tr><td>{names[k]}{tag}</td><td class='n'>{money(c[k])}</td><td class='n'>{n}</td><td class='n'>{money(line[k])}</td></tr>")
    st.append(f"<tr><td><b>Total per active user</b> (text {money(text_month)} + pictures {money(image_month)})</td><td></td><td></td><td class='n'><b>{money(month)}</b></td></tr>")
    for users in (1, 100, 10_000):
        st.append(f"<tr><td>{users:,} user{'s' if users > 1 else ''}</td><td></td><td class='n'>per month / per year</td>"
                  f"<td class='n'>{money(month * users)} / {money(month * users * 12)}</td></tr>")

    results = (DOCS / "safety_test_results.txt").read_text().splitlines()
    m_ = re.search(r"\((.*?)\): (\d+)/(\d+) passed", results[0])
    n_live = sum(1 for l in results if l.startswith("[") and "] live " in l)
    safety_summary = (f"{m_.group(2)} of {m_.group(3)} checks pass, {int(m_.group(3)) - n_live} offline"
                      + (f" plus {n_live} live against the real agents" if n_live else "")) if m_ else results[0]
    keep = [l for l in results if l.startswith("[")]
    key_words = ("is quarantined", "contains no body", "invented item forces", "best-round", "daily budget",
                 "never sent without consent", "/api/plan with unchanged", "plan: penny loafers",
                 "never returned or opened", "answered before any paid search", "try-on prompt keeps",
                 "live injection: poisoned", "live privacy")
    total = len(keep)
    keep = [l for l in keep if any(k in l for k in key_words)]
    sr = []
    for l in keep:
        ok = l.startswith("[PASS]")
        body = l.split("] ", 1)[1].split("  (")[0]
        sr.append(f"<tr><td>{html.escape(body)}</td><td class='ok'>{'✅ pass' if ok else '❌ fail'}</td></tr>")
    sr.append(f"<tr><td colspan='2' class='small'>{len(keep)} of {total} checks shown; all {total} in docs/safety_test_results.txt</td></tr>")

    e = html.escape
    shoes_after = (user.get("tasks") or {}).get("shoes", {}).get("after", {})
    outfit_after = (user.get("tasks") or {}).get("outfit", {}).get("after", {})
    impact = f"""<p><b>Real user test: me, on my real closet and calendar.</b> {e(user.get('impact_intro', ''))}</p>
<table>
  <tr><th>Task</th><th>Before (alone)</th><th>With Closet Twin</th><th>Outcome</th></tr>
  <tr><td>Choose a full outfit for a recruiting day (campus event, career office hours, three consulting conversations)</td><td><b>{e(user.get('before_outfit', ''))}</b> (timed)</td><td><b>{e(user.get('after_outfit', ''))}</b> to open, review and approve the plan (timed; the plan itself took 158 s and ${outfit_after.get('cost_usd', 0):.4f} earlier that morning)</td><td>About <b>19× faster</b>; approved ("Love this direction") and wearable</td></tr>
  <tr><td>Find a polished, walkable shoe in women's <b>12 wide</b></td><td><b>{e(user.get('before_shoes', ''))}</b> (my last real search, self-reported)</td><td><b>{e(user.get('after_shoes', ''))}</b>, 3 live searches, ${shoes_after.get('cost_usd', 0):.3f} (the first answered free by my loafer ban)</td><td>A critic-approved Naturalizer flat in 12 W at DSW, and 3 Mary Janes in 12 W; I would buy, and I tracked one's price</td></tr>
  <tr><td>Cost</td><td>A personal stylist session is about $100+/hour</td><td>About {money(month)} per user per month in model and picture cost</td><td>Section 5</td></tr>
</table>
<p><b>In my words:</b> "{e(user.get('quote', ''))}"</p>
<p class="small">Not measured: clicks, the apps I used before, and any classmates (one real user). Numbers from <code>docs/user_test.json</code>.</p>"""
    slide_cards = f"""    <div class="card"><div class="big">{e(user.get('before_outfit', ''))} → {e(user.get('after_outfit', ''))}<small>choosing my outfit for a real recruiting day (timed)</small></div></div>
    <div class="card"><div class="big">{e(user.get('before_shoes', ''))} → {e(user.get('after_shoes', ''))}<small>finding a walkable 12 W shoe I'd buy (before self-reported)</small></div></div>"""
    slide_note = f'  <p class="note" style="margin-top:.8em">"{e(user.get("quote", ""))}" (me, the first real user)</p>'

    fills = {
        "IMPACT_BLOCK": impact,
        "SLIDE_IMPACT_CARDS": slide_cards,
        "SLIDE_IMPACT_NOTE": slide_note,
        "REPO_URL": user.get("repo_url", "https://github.com/oliviaobodoagha-web/closet-twin"),
        "PLAN_RUN_ID": plan["run_id"] if plan else "n/a",
        "PLAN_RUN_TOTALS": totals_str(plan["totals"]) if plan else "",
        "PLAN_TRACE_STEPS": trace_steps(plan) if plan else "",
        "SHOP_RUN_SENTENCE": (f"In the Sample run shown (<code>{shop['run_id']}</code>, {totals_str(shop['totals'])}), the first round "
                              "found one lead, the Critic said <i>revise</i> because the listing didn't confirm the size or color, "
                              "and the second search found nothing better, so the app showed the lead with the Critic's notes." if shop else ""),
        "TOKEN_TABLE": "\n".join(tt),
        "SCALE_TABLE": "\n".join(st),
        "FEED_COST": f"${feed:.2f}",
        "NO_TRYON_MONTH": f"${no_tryon:.2f}",
        "TEXT_MONTH": f"${text_month:.2f}",
        "IMAGE_MONTH": f"${image_month:.2f}",
        "IMAGE_SHARE": f"{100 * image_month / month:.0f}%",
        "LIVE_SHARE": f"{100 * line['shop_live'] / month:.0f}%",
        "CACHE_SUMMARY": f"{cache['cached_tokens']:,} of {cache['input_tokens']:,} input tokens served from cache across {cache['runs']} real runs ({cache['cached_pct']:.0f}%)",
        "SAFETY_SUMMARY": safety_summary,
        "ONBOARD_COST": money(40 * c["photo"] + c_color + c_style),
        "COST_PER_USER_MONTH": money(month),
        "CLASS_COST": money(month * 350 * 12),
        "SAFETY_ROWS": "\n".join(sr),
        # slides
        "PLAN_COST": (f"{plan['totals']['calls']} calls, {money(plan['totals']['cost_usd'])}, {plan['totals']['seconds']:.0f} s" if plan else ""),
        "PLAN_MEDIAN": money(c["plan"]),
        "SHOP_MEDIAN": money(c["shop"]),
        "LIVE_MEDIAN": money(c["shop_live"]),
        "COST_10K": money(month * 10_000),
        "SAFETY_PASS": results[0].split(": ")[-1].replace(" passed", ""),
    }
    src = (DOCS / "report_src.html").read_text(encoding="utf-8")
    for k, v in fills.items():
        src = src.replace("{{" + k + "}}", v)
    # anything Olivia still has to provide stays visibly highlighted
    src = re.sub(r'<(span|td) class="todo">(.*?)</\1>',
                 lambda m: m.group(0) if "{{" in m.group(2) else f"<{m.group(1)}>{m.group(2)}</{m.group(1)}>", src, flags=re.S)
    built = DOCS / "_report_filled.html"
    built.write_text(src, encoding="utf-8")
    inline(built, ROOT / "report.html")
    built.unlink()

    slides = (DOCS / "slides_src.html").read_text(encoding="utf-8")
    for k, v in fills.items():
        slides = slides.replace("{{" + k + "}}", v)
    slides = re.sub(r'<span class="todo">(.*?)</span>', lambda m: m.group(0) if "{{" in m.group(1) else m.group(1), slides, flags=re.S)
    built = DOCS / "_slides_filled.html"
    built.write_text(slides, encoding="utf-8")
    inline(built, ROOT / "slides.html")
    built.unlink()
    left = sorted(set(re.findall(r"\{\{(\w+)\}\}", src)))
    print("plan run:", plan and plan["run_id"], "| shop run:", shop and shop["run_id"], "| per user/month:", money(month),
          f"(text {money(text_month)}, pictures {money(image_month)})")
    if left:
        print("Still TODO:", left)


if __name__ == "__main__":
    main()
