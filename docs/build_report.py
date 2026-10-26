"""Build report.html: fill docs/report_src.html with numbers from real runs, then embed every image.

    python docs/build_report.py [--plan RUN_ID] [--shop RUN_ID]

Numbers come from logs/runs.jsonl, docs/tokenomics.json and docs/safety_test_results.txt.
Olivia's own test results go in docs/user_test.json (anything missing stays highlighted as TODO).
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

PER_MONTH = {"plan": 30, "swap": 10, "shop": 4, "shop_live": 4, "recommend": 4, "inspo": 4, "photo": 5, "tryon": 30, "spin": 2}


def runs() -> list[dict]:
    return [json.loads(l) for l in (ROOT / "logs" / "runs.jsonl").read_text().splitlines() if l.strip()]


def pick(rows, mode, run_id=None):
    cands = [r for r in rows if r["mode"] == mode and r.get("status") == "ok" and r["totals"]["seconds"] > 5]
    if run_id:
        cands = [r for r in cands if r["run_id"] == run_id]
    return cands[-1] if cands else None


def totals_str(t) -> str:
    return (f"{t['calls']} model calls, {t['input_tokens']:,} input tokens ({t['cached_tokens']:,} cached), "
            f"{t['output_tokens']:,} output, ${t['cost_usd']:.4f}, {t['seconds']:.0f} s")


def trace_steps(run) -> str:
    out = []
    keep = ("tool", "safety", "verdict", "done", "fallback", "stop")
    for s in run["trace"]:
        if s["kind"] not in keep:
            continue
        d = s.get("detail") or {}
        if s["kind"] == "model":
            continue
        text = html.escape(s["summary"])
        if s["kind"] == "tool":
            text = f"called <code>{text}</code>"
        elif s["kind"] == "safety":
            text = f"🛡 <b>safety:</b> {text}"
        out.append(f'<li><span class="pill">{s["t"]:.1f}s</span><b>{html.escape(s["agent"])}</b>: {text}</li>')
    # one line per model call with its tokens
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
    plan_id = args[args.index("--plan") + 1] if "--plan" in args else None
    shop_id = args[args.index("--shop") + 1] if "--shop" in args else None
    rows = runs()
    tok_all = json.loads((DOCS / "tokenomics.json").read_text())
    tok = tok_all["by_mode"]
    cache = tok_all["caching"]
    user = json.loads((DOCS / "user_test.json").read_text()) if (DOCS / "user_test.json").exists() else {}

    plan = pick(rows, "plan_day", plan_id)
    shop = pick(rows, "shop", shop_id)

    # typical run per mode (medians of real runs)
    plan_like = [m for m in ("plan_day", "experiment_effort_low") if m in tok]
    def med(mode): return tok.get(mode, {})
    typical = {
        "Plan my day": med("plan_day"),
        "Shop (sample catalog)": med("shop"),
        "Shop (live web)": med("shop_live"),
        "Add to closet (1 photo)": med("add_to_closet"),
        "Color season (close-up)": med("analyze_color"),
        "Style archetype": med("analyze_style"),
        "Show another option (swap)": med("swap_outfit"),
        "Stylist recommends (closet gaps)": med("recommend"),
        "Inspiration (Pinterest board)": med("inspo"),
        "Add by product link": med("add_by_link"),
    }
    tt = ['<tr><th>Run type</th><th class="n">Real runs</th><th class="n">Model calls</th><th class="n">Input</th><th class="n">Cached</th><th class="n">Output</th><th class="n">Web searches</th><th class="n">Cost (median)</th><th class="n">Time</th></tr>']
    for name, m in typical.items():
        if not m:
            continue
        tt.append(f"<tr><td>{name}</td><td class='n'>{m['runs']}</td><td class='n'>{m['median_calls']:g}</td><td class='n'>{m['median_input_tokens']:,.0f}</td>"
                  f"<td class='n'>{m['median_cached_tokens']:,.0f}</td><td class='n'>{m['median_output_tokens']:,.0f}</td><td class='n'>{m['median_web_searches']:g}</td>"
                  f"<td class='n'>{money(m['median_cost_usd'])}</td><td class='n'>{m['median_seconds']:.0f} s</td></tr>")

    c = {
        "plan": med("plan_day").get("median_cost_usd", 0.002), "swap": med("swap_outfit").get("median_cost_usd", 0.0006),
        "shop": med("shop").get("median_cost_usd", 0.0016), "shop_live": med("shop_live").get("median_cost_usd", 0.065),
        "recommend": med("recommend").get("median_cost_usd", 0.0015), "inspo": med("inspo").get("median_cost_usd", 0.0005),
        "photo": med("add_to_closet").get("median_cost_usd", 0.0002),
        # photo runs are personal, so they are not in the committed evidence: measured $0.023 per image, $0.245 per 360°
        "tryon": 0.023, "spin": 0.245,
    }
    c_color = med("analyze_color").get("median_cost_usd", 0.0003)
    c_style = med("analyze_style").get("median_cost_usd", 0.0004)
    names = {"plan": "Dress me (daily plan)", "swap": "Show another option", "shop": "Shop, catalog", "shop_live": "Shop, live web",
             "recommend": "Stylist recommends", "inspo": "Inspiration", "photo": "Add a piece (photo)",
             "tryon": "Daily outfit on the real you (own key)", "spin": "360° view (own key)"}
    month = sum(PER_MONTH[k] * c[k] for k in PER_MONTH)
    c_plan, c_shop, c_live, c_photo, c_tryon = c["plan"], c["shop"], c["shop_live"], c["photo"], c["tryon"]
    live_share = PER_MONTH["shop_live"] * c_live / month
    tryon_share = (PER_MONTH["tryon"] * c_tryon + PER_MONTH["spin"] * c["spin"]) / month
    feed = month - PER_MONTH["shop_live"] * c_live + PER_MONTH["shop_live"] * c_shop
    st = ['<tr><th>Item</th><th class="n">Per run</th><th class="n">Runs / user / month</th><th class="n">Per user / month</th></tr>']
    for k, n in PER_MONTH.items():
        st.append(f"<tr><td>{names[k]}</td><td class='n'>{money(c[k])}</td><td class='n'>{n}</td><td class='n'>{money(c[k] * n)}</td></tr>")
    st.append(f"<tr><td><b>Total per active user</b></td><td></td><td></td><td class='n'><b>{money(month)}</b></td></tr>")
    for users in (1, 100, 10_000):
        st.append(f"<tr><td>{users:,} user{'s' if users > 1 else ''}</td><td></td><td class='n'>per month / per year</td>"
                  f"<td class='n'>{money(month * users)} / {money(month * users * 12)}</td></tr>")

    head = (DOCS / "safety_test_results.txt").read_text().splitlines()[0]
    m_ = re.search(r"\((.*?)\): (\d+)/(\d+) passed", head)
    n_live = 4 if m_ and "live" in m_.group(1) else 0
    safety_summary = (f"{m_.group(2)} of {m_.group(3)} checks pass, {int(m_.group(3)) - n_live} offline"
                      + (f" plus {n_live} live" if n_live else "")) if m_ else head
    safety_lines = (DOCS / "safety_test_results.txt").read_text().splitlines()[2:]
    keep = [l for l in safety_lines if l.startswith("[")]
    key_words = ("quarantined", "0px hidden", "contains no body", "invented item forces", "per-run dollar cap",
                 "loop guard", "daily budget", "GPS/EXIF", "never sent without consent", "live injection: poisoned",
                 "live privacy", "live budget")
    total = len(keep)
    keep = [l for l in keep if any(k in l for k in key_words)]
    sr = []
    for l in keep:
        ok = l.startswith("[PASS]")
        body = html.escape(l.split("] ", 1)[1])
        sr.append(f"<tr><td>{body}</td><td>{'✅ pass' if ok else '❌ fail'}</td></tr>")
    sr.append(f"<tr><td colspan='2' class='small'>{len(keep)} of {total} checks shown; all {total} in docs/safety_test_results.txt</td></tr>")

    def u(key, fallback):
        v = user.get(key)
        return html.escape(str(v)) if v else fallback

    plan_s = med("plan_day").get("median_seconds", 30)
    shop_s = med("shop").get("median_seconds", 20)
    if user.get("before_outfit"):
        e = html.escape
        impact = f"""<p><b>Real user test: me.</b> {e(user.get('impact_intro', ''))}</p>
<table>
  <tr><th>Task</th><th>How I do it today</th><th>With Closet Twin</th><th>Source</th></tr>
  <tr><td>Choose a full outfit for a mixed day (gym → class → coffee chat → dinner)</td><td>{e(user['before_outfit'])}</td><td>{e(user.get('after_outfit', ''))}</td><td>My own timed test</td></tr>
  <tr><td>Find a polished, comfortable shoe in size 11 wide</td><td>{e(user.get('before_shoes', ''))}</td><td>{e(user.get('after_shoes', ''))}</td><td>My own timed test</td></tr>
  <tr><td>Know which size to buy before ordering</td><td>Order two sizes, return one</td><td>One size with zone-by-zone reasons</td><td>App output</td></tr>
  <tr><td>Cost</td><td>A personal stylist session is about $100+/hour</td><td>About {money(month)} per month in model cost</td><td>Section 5</td></tr>
</table>
<p><b>In my words:</b> "{e(user.get('quote', ''))}"</p>"""
        slide_cards = f"""    <div class="card"><div class="big">{e(user['before_outfit'])} → {e(user.get('after_outfit', ''))}<small>choosing a mixed-day outfit (my timed test)</small></div></div>
    <div class="card"><div class="big">{e(user.get('before_shoes', ''))} → {e(user.get('after_shoes', ''))}<small>finding a comfortable 11W shoe (my timed test)</small></div></div>"""
        slide_note = f'  <p class="note" style="margin-top:.8em">"{e(user.get("quote", ""))}" (me, the first real user)</p>'
    else:
        impact = f"""<div class="callout warn"><b>Status: estimates, pending my own timed test.</b> I haven't yet run a timed before-and-after test on my own closet. The numbers below combine public survey data with what the app measurably does in its logs, and they are labelled as estimates. My timed test and a quote will replace them (the protocol is below).</div>
<table>
  <tr><th>Task</th><th>Today (public data / estimate)</th><th>With Closet Twin (measured app behavior)</th><th>Source</th></tr>
  <tr><td>Choose a full outfit for a mixed day (gym → class → coffee chat → dinner)</td><td>12–18 minutes a morning</td><td>The agents return a plan, already checked by the Critic, in a median of <b>{plan_s:.0f} s</b>. Reviewing it and trying it on in 3D: about 2–3 minutes (estimate).</td><td>UK surveys (Section 2); app logs</td></tr>
  <tr><td>Find a polished, comfortable shoe in size 11 wide</td><td>Reading dozens of reviews across several stores: 30–60+ minutes (estimate)</td><td>Up to 3 checked picks, each with a size, width and comfort evidence, in a median of <b>{shop_s:.0f} s</b></td><td>Estimate; app logs</td></tr>
  <tr><td>Know which size to buy before ordering</td><td>Order two sizes and return one. Fit drives 53–70% of apparel returns.</td><td>One size, with zone-by-zone reasons from the size chart and reviews</td><td>Coresight, McKinsey; app output</td></tr>
  <tr><td>Cost</td><td>A personal stylist session is about $100+/hour</td><td>About <b>{money(month)}</b> per month in model cost</td><td>Section 5</td></tr>
</table>
<p><b>Next: a real-user test.</b> Protocol:</p>
<ol>
  <li>On a normal morning, time how long it takes me to choose an outfit for a mixed day.</li>
  <li>Then time the same day with Closet Twin on my own closet: about 10 items cataloged from photos, plus my real calendar.</li>
  <li>Time one search for a comfortable size 11 wide shoe, done the usual way and then with the Shop tab.</li>
  <li>Record which plans I would actually wear, and why.</li>
  <li>Then repeat with 2–3 classmates.</li>
</ol>"""
        slide_cards = f"""    <div class="card"><div class="big">{plan_s:.0f} s<small>for a checked day plan (measured) vs 12–18 min choosing by hand (surveys)</small></div></div>
    <div class="card"><div class="big">{shop_s:.0f} s<small>for 3 checked shoe picks with size and width (measured) vs 30–60+ min of review reading (estimate)</small></div></div>"""
        slide_note = '  <p class="note" style="margin-top:.8em">Estimates for now. Next: my own timed before-and-after test on my real closet, then 2–3 classmates.</p>'
    fills = {
        "IMPACT_BLOCK": impact,
        "SLIDE_IMPACT_CARDS": slide_cards,
        "SLIDE_IMPACT_NOTE": slide_note,
        "MORNING_SENTENCE": (f" My own: {html.escape(user['morning_minutes_before'])} on a busy morning." if user.get("morning_minutes_before") else ""),
        "SHOE_SENTENCE": (f" My last search for comfortable, stylish flats took {html.escape(user['shoe_search_before'])}." if user.get("shoe_search_before") else ""),
        "REPO_URL": user.get("repo_url", "https://github.com/TODO/closet-twin"),
        "PLAN_RUN_ID": plan["run_id"] if plan else "n/a",
        "PLAN_RUN_TOTALS": totals_str(plan["totals"]) if plan else "",
        "PLAN_TRACE_STEPS": trace_steps(plan) if plan else "",
        "SHOP_RUN_SENTENCE": (f"In the run shown (<code>{shop['run_id']}</code>): {totals_str(shop['totals'])}." if shop else ""),
        "TOKEN_TABLE": "\n".join(tt),
        "SCALE_TABLE": "\n".join(st),
        "FEED_COST": money(feed),
        "LIVE_SHARE": f"{100 * live_share:.0f}%",
        "CACHE_SUMMARY": f"{cache['cached_tokens']:,} of {cache['input_tokens']:,} input tokens served from cache across {cache['runs']} real agent runs ({cache['cached_pct']:.0f}%); about 60% on plan runs approved in one round",
        "SAFETY_SUMMARY": safety_summary,
        "TRYON_SHARE": f"{100 * tryon_share:.0f}%",
        "ONBOARD_COST": money(40 * c_photo + c_color + c_style),
        "COST_PER_USER_MONTH": money(month),
        "CLASS_COST": money(month * 350 * 12),
        "SAFETY_ROWS": "\n".join(sr),
        # slides
        "PLAN_COST": (f"{plan['totals']['calls']} calls, {money(plan['totals']['cost_usd'])}, {plan['totals']['seconds']:.0f} s" if plan else ""),
        "PLAN_MEDIAN": money(c_plan),
        "SHOP_MEDIAN": money(c_shop),
        "LIVE_MEDIAN": money(c_live),
        "COST_10K": money(month * 10_000),
        "SAFETY_PASS": (DOCS / "safety_test_results.txt").read_text().splitlines()[0].split(": ")[-1].replace(" passed", ""),
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
    left = [k for k in fills if "{{" + k + "}}" in src]
    print("plan run:", plan and plan["run_id"], "| shop run:", shop and shop["run_id"], "| per user/month:", money(month))
    if left:
        print("Still TODO:", left)


if __name__ == "__main__":
    main()
