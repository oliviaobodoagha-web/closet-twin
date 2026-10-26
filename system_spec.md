# Closet Twin · system spec (single source of truth for AI sessions)

> **Every new AI session: read this file first, then only your module's card (§7).** Keep this file compact.
> When a feature or module is done: tick it in §6, update §7, add one line to §8. Personal/session detail lives in
> `HANDOFF.md` (git-ignored, local only); read it only if your module needs Olivia's data or recent history.

## 1. What it is
AI stylist web app for Yale SOM MGT 409 final project (due **2026-10-26 6 p.m. ET**, Olivia submits on Canvas:
repo link + `report.html` + `slides.html`). One stylist persona, **Margaux-Sloan**, dresses the user from their real
closet for their real calendar + weather, built on style archetypes, color season and an inspiration board, and
learns from feedback. Internally multi-agent (planner, critic, recommender, scout, tailor, cataloger…).

## 2. Stack & run
- Python 3.9+ (dev venv is 3.14; **no 3.12-only syntax**), FastAPI + uvicorn, plain HTML/CSS/JS (ES modules), JSON
  files for storage, OpenAI SDK. No DB, no Node.
- Text model `gpt-6-luna` via Portkey (`PORTKEY_API_KEY`) or `OPENAI_API_KEY`; images `gpt-image-2.5-sunburst` on
  `OPENAI_API_KEY`. `.env` looked up in repo folder, then parent. Weather: keyless public API.
- Run `.venv/bin/python run.py --no-browser` → http://localhost:8000. Tests `.venv/bin/python tests/safety_tests.py`
  → **59/59** must pass. Restart the server after Python edits.
- Data sets: `data/sample/` (committed demo) and `data/user/` (Olivia's, git-ignored). Header toggle switches.

## 3. Architecture
```
static/index.html + app.js (core, plan, recs, stylist card, Me setup) · today_ui.js · wardrobe_ui.js (closet)
       real_me.js (photo try-on) · shop_extra.js (inspo/shop) · face_measure.js · styles.css
        │ fetch /api/*
app/main.py (core endpoints) · app/routes_extra.py (closet links/receipts/bulk, inspo, aesthetic, watch)
        │
agents/  orchestrator → planner ⇄ critic (≤2 revisions, best round kept) │ recommender → mockups │
         scout → tailor → critic │ cataloger, orienter, receipt │ inspo │ analyst (color, style, stylist_read)
core/    llm.run_agent · ledger (budgets, loop guard, logs) · safety (fencing, photo prep, grounding) ·
         stylists (persona, archetype GUIDE, point_of_view, questions) · aesthetic (board, goal picture) ·
         outfit_rules (hard style checks) · memory (saved plans/recs, fingerprints) · color_style · store (JSON)
prompts/ one .md per agent + _shared_rules.md + fashion_fundamentals.md (styling agents)
```

## 4. Data flows
- **Plan day:** `/api/plan` → fingerprint match? return saved (no model call) : orchestrator → planner (calendar,
  weather tools; `stylists.point_of_view`) → code checks (grounding, no-repeat, `outfit_rules`, season palette) →
  critic → revise ≤2 → best round → alternates validated → saved. UI: blocks, alternates, feedback, Tell box.
- **Recommend:** `/api/recommend` → fingerprint/saved → recommender (3 pieces + outfit each, ~$0.002) → "Draw them" tap
  → `/api/recommend/mockups` (6 images: piece photo + outfit board, ~$0.19; never drawn without the tap) → "See it on me" → photo try-on.
- **Closet add:** photo/bulk/link/receipt → orienter → cataloger → cutout + color words → `store` (+ dupes check).
- **Style setup (Me tab, 5 steps):** 1 face close-up → Color Analyst → season · 2 body photo → size estimate ·
  3 aesthetic board (`/api/aesthetic/*`) and/or quiz/tiles (`/api/stylist/blend`, `/api/analyze/style`) →
  `/api/stylist/read` (signature, goal look, strategy, follow-up questions) → `/api/stylist/goal` (goal picture) ·
  4 closet · 5 calendar (iCal link / .ics).
- **Learning loop:** ♡/✕/notes (`/api/feedback`), check-in answers (`/api/stylist/answers`), house rules
  (`/api/stylist/rules`, autosave) → profile → `point_of_view` for every styling agent; read refreshes every 3 notes.
- **Every run:** `Ledger` enforces caps (text $0.05/run, $1/day; images $2/day) and logs to `logs/runs.jsonl`
  (shown in Runs & Safety tab; source for tokenomics).

## 5. Rules for every module
- Never read/print/commit `.env` values; no hardcoded keys. Never commit `data/user/`, personal photos,
  `style inspirations/`, `HANDOFF.md`. Commit/push only with Olivia's go-ahead.
- UI style posh/preppy (ivory, navy, gold), not black/pink. One stylist voice in the UI; agent names only in traces.
- App must be standalone: stylist behavior is built into the app, not done by the AI in chat.
- Visual first: newcomers should understand styles from pictures.
- Verify in the browser before claiming UI works; keep tests 59/59; report failures plainly.
- Ask before image-heavy runs on real data (images cost ~$0.04 each).
- Own only your module's files (§7). If you must touch another module's file, say so and keep the edit minimal.
- Update `docs/demo_checklist.md` for demo-worthy features.
- **End of every module:** set its §7 status to done (with what wasn't verified), tick §6, add one §8 line, and write
  the start prompt for the next module into §9 (replace the old one). Then give Olivia that prompt in chat.

## 6. Feature checklist
**App**
- [x] Closet: photo/bulk upload, product links, receipts (photo/PDF), cutouts, color words, size guesses, dupes, section rail
- [x] Day plan: calendar + weather, planner⇄critic, alternates, hard style rules, season palette check, fingerprints
- [x] Recommendations: 3 pieces + outfit + mock-up pictures, whole-life coverage, feedback per piece
- [x] Shop: live search in size, Fit Tailor, price watch; Inspo recreate
- [x] Try-on: avatar + photo try-on (identity kept, polish), 360° spin, "Not right? Tell me"
- [x] Margaux-Sloan: one persona, archetype blend + pictures, quiz, aesthetic board, read + goal picture + strategy,
      check-ins, push cadence, house rules autosave, Tell box, fashion fundamentals
- [x] Me tab: 5-step setup with progress strip
- [x] Safety: injection fencing, privacy (no measurements to web), grounding, budgets/loop guard, photo checks, palette, best-round, fingerprints, taste bans, live-shop link check, ban pre-check, picture reuse, feedback reply, backpack house rule, try-on likeness (59 offline tests)
- [x] Runs & Safety tab: per-run tokens, cost, traces
- [x] Live shop search fixed (size-range evidence, shopper queries, broader retry, rounds merged, empty state with retry)
- [x] Taste bans enforced in code (no men's loafers) → A1
- [x] Defense tests for palette, best-round, fingerprints, taste bans (43 offline) → A3
- [x] Look & feel polish: honest Body step, Me tab folded behind ⓘ, phone layout, "I left out …" lines, no paid calls on page load → A2
- [x] Fresh plan + recs on real data after A1 (compare with old; live shop → A5) → A4
- [x] Live shop keeps real finds: link check trusts pages the search actually saw, trusted list in trace, honest
      note when every pick is dropped, offline test, one paid re-test with ≥1 pick; fresh recs ask before drawing
      mock-ups (no surprise ~$0.19) → A5
- [ ] Guided first-run walkthrough (future build, `docs/future_build.md`)

**Submission**
- [ ] README updated for today's features + Python version + data-set switching
- [ ] `report.html` rebuilt (10–15 pages, all 8 sections with evidence) via `docs/build_report.py`
- [ ] `slides.html` rebuilt (≤10 slides, reveal.js CDN, embedded images)
- [ ] Evidence refreshed: `docs/export_runs.py`, screenshots, real-user test (`docs/user_test.json`)
- [ ] Git: first commit + public repo (or add `Zlisto`), Olivia's go-ahead
- [ ] Fresh-clone dry run (`.env` one folder up, ≤10 min)

## 7. Modules
Each module = one fresh AI session. Start prompt: the one in §9, or *"Read `final project/system_spec.md`, then do
module M#. Own only its files. When done, update §6–§9 of system_spec.md and give me the next module's prompt."*

**TA grade (2026-10-26, official page as source of truth):** Tier 2 (upper), ~77.5/100 *if pushed*. Tier 3 needs a
real user with measured before/after time or quality (org-level costing is already there). Official page: course
model is **gpt-6-luna only** (don't switch to 5.6); staff `.env` has both keys, so image features bill staff (caps apply).

Two phases. **Phase A finishes the app** (only phase allowed to edit `app/`, `static/`, `tests/`); then the code is
frozen and **Phase B gets the project submitted**. A modules own disjoint files, so A1, A2 and A3 can run in parallel.

**Order:** A1 ∥ A2 ∥ A3 → A4 (needs A1) ∥ A5 (live-shop fix, found by A4) ∥ A6 (Fitting Room, Olivia's list) → *code freeze* → B1 ∥ B2 → B3 → B4 → B5 → B1 final push → Canvas.

### Phase A · finish the app
| # | Module | Owns (only these files) | Done when | Pts | Status |
|---|---|---|---|---|---|
| A1 | **Stylist taste enforcement ("stop recommending me men's loafers")** | `app/stylists.py`, `app/outfit_rules.py`, `app/agents/recommender.py`, `app/agents/scout.py`, `app/agents/orchestrator.py`, `app/aesthetic.py`, `app/prompts/*.md`, `app/memory.py` | Dislikes become **hard filters in code**, not just prompt text: anything Olivia rejected (♡/✕ notes, Tell box tags like "Too masculine", check-in "never" answers, house rules) is turned into banned terms/pieces (e.g. loafers, "men's", boxy) checked in `outfit_rules` for plans, recs, shop picks, mock-up and goal prompts; a recommendation that hits a ban is replaced, not shown. Saved recs invalidated when bans change (fingerprint includes them). Olivia's known dislike recorded: black loafers = "looks like men's shoes, too business, not my style". Verified: fresh recs + fresh plan on her data contain no loafers and use her board/season colors; before/after written in §8 | Works + Look&feel | **done** (fresh recs verified; fresh plan left to A4) |
| A2 | Look & feel polish | `static/index.html`, `static/styles.css`, `static/*.js` | Sample Me tab no longer shows "Body ✓ Done" without a photo (body step = photo or measurements actually present); Me tab less of a text wall (collapse long helper text into "ⓘ" / `<details>`, shorter blurbs); Shop empty state + recs "Shop this in my size" flow checked; verified in browser at desktop and phone width | ~1–2 | **done** (desktop + 375px checked on saved results + sample; a live shop and a fresh recommend with a real `blocked` shop pick not run, rendered from test data) |
| A3 | Defense tests for new code checks | `tests/safety_tests.py` only | 2–3 offline tests added and passing: palette_flag sends an all-neutral plan back; an ungrounded round never wins best-round; fingerprint hit makes no model call; (after A1) a banned piece (loafers) never reaches recs/shop. Total checks updated in §2 | Safety ~1 | **done** (15 offline checks, 43/43; mutation-tested only by reasoning, not by breaking app code) |
| A4 | Fresh run on real data + compare | none (read-only + runs) | After A1: fresh plan + fresh recs + one live shop on Olivia's data (~$0.30, ask first); plain-language comparison vs old (old plan: ivory shirt/black pants/blazer/flats/beige tote/parka, alternates Burgundy polish & Bright-red statement; old recs: navy trousers, black wool coat, black loafers); results noted in §8 for the report | feeds report | **done** (plan $0.011 + recs $0.0016 pass every check; page auto-drew 6 mock-ups $0.185 unasked, a fresh rec on My closet really costs ~$0.19; live shop $0.0975 → 0 picks, link-check bug → A5, so no live-shop after-result; screenshots `docs/screenshots/personal/a4_*`) |
| A5 | **Live shop link check drops real finds** | `app/llm.py`, `app/agents/scout.py`, `app/agents/orchestrator.py` (`run_shop` only), `app/prompts/scout.md`, `static/app.js` (`showRecs` / mock-up prompt only), `tests/safety_tests.py` (add only) | Cause (A4 diagnosis): `allowed` = only `url_citation` footnotes on the final JSON message (`scout.py:154`); the model often skips them with a JSON schema, and pages it opened (`web_search_call` `open_page`, logged as blank "web_search", `llm.py:121`) never count; `allowed` isn't logged; `stylist_take` is written before the drop, so it praises a pick then shows "No picks". Fix: also trust every URL the search returned or opened (Responses `include=["web_search_call.action.sources"]` + `action.url`), same `ungrounded_links` normalising; links never seen are still dropped; trusted-link count + list in the trace; when every pick is dropped, replace the take with an honest line; offline test (opened/sourced URL kept, unseen URL dropped, empty → honest take); 43+ tests pass; one paid re-test (black tailored straight-leg trousers, ~$0.09, ask first) gives ≥1 approved pick. **Also (mock-ups):** a fresh rec run on My closet auto-draws 6 mock-ups (~$0.185, `showRecs` in `static/app.js` calls `drawMockups` whenever `run` is set; A4 hit this unasked). Fix: fresh recs show the existing "No pictures yet" ask with the cost (~$0.19) and draw only on her tap; saved picks with pictures still show them; verified in the browser with network log, no paid run | Works + Safety + Cost | **done** (47/47 offline, $0; live re-test $0.046: `include` works through Portkey, 39 trusted links / 0 cited, 3 picks kept with real JCPenney, Lands' End, Nordstrom links, all 3 would have been dropped before; mock-ups wait for the tap, checked with a stubbed `/api/recommend` + network log, no paid image run; `app.js?v=a5`, one-line `index.html` bump. **Not met/unverified:** the critic said *revise*, not approve (JCPenney black/18 unconfirmed, Lands' End jersey not tailored, Nordstrom over $75), so no approved pick yet; *fixed after:* a revise now always gets round 2 (newest picks first, ~$0.08–0.10 per revised live shop vs ~$0.045), offline-tested only, no paid re-run; *also after (Olivia's runs 10:28/10:32):* a request that breaks a no ("pleated mini skirt" vs never very short, $0.096 for 0 picks) is now answered before any search ($0, 0 calls, checked on the real endpoint); "not confirmed" sizes move to a grey size note instead of the green ✓; unseen price = 0 → "Price at store", seen prices say "from search · check at store" (prompt + `renderShop` in `app.js`, Olivia OK'd, `?v=a5b`; cards checked with stubbed picks; a wrong price the model read from a snippet can still slip through); *picture reuse (Olivia asked, outside A5's files: new `app/image_cache.py`, `mockups.py`, `aesthetic.py` goal, `product_shot.py`, `photo_tryon.py`):* every image call is keyed by model + prompt + size + input photo bytes, so the same picture is reused ($0, "reuse" step in the trace), two identical requests at once share one drawing, a rejected try-on / redone product shot is forgotten; today's only true repeat was the 09:54 mock-up set drawn twice ($0.185 wasted); offline-tested with a fake image client, not run live, pictures made before this change aren't in the cache; *saved-note line (Olivia asked; `app.js` fbHTML/sendFeedback/sendTell, one `.fb-saved` CSS rule, `/api/feedback` returns `new_bans`):* under each note a lasting "✓ Saved …" line says what it does (all styling agents read it, next run is fresh; a Not for me names the new hard rule, enforced on plans, picks, shop and pictures; Love doesn't change pictures directly, so it doesn't claim to), and saved notes show again after a reload; checked with a stubbed `/api/feedback` (nothing written), `?v=a5c`; *house rule + Me tab (Olivia asked; `outfit_rules.py` carry_rules/apply_carry/explain, `recommender.py`, `run_plan_day`, `planner.md` + `recommender.md`, `memory._ban_inputs`, `/api/stylist` effects, Me tab in `app.js`, `.became` CSS):* all 3 saved recs had used the beige tote for school events (CDO Office Hours, Welcome Back Cider, WIM lunch) because `planner.md` said "tote for class" and house rules weren't checked in code; now a house rule naming a bag for school swaps any other bag out of school looks (plans, alternates, recs; school = title/place words like class, office hours, CDO, Student Commons, SOM, welcome back) and tells her why; the rule is in the fingerprint, so old tote picks re-run on the next Find what's missing (~$0.002); Me tab: each note says what it became (hard rule checked in code vs read by every styling agent), each house rule says checked in code or not; Forget removed every note from the same day (matched by date) → now removes only that one (checked with a stubbed save); `?v=a5e`; not run live, a vaguely titled school event can be missed; the card's "✓ Confirmed in your size" chip shows even when the text says size isn't confirmed (A2 renderer); the honest all-dropped note seen only in tests; a real tap-to-draw not run) |
| A6 | **Fitting Room fixes** (Olivia's list, given at the start of the session) | `static/real_me.js`; Fitting Room functions in `static/app.js` (`openFitting`, `addToOutfit`, `restoreOutfit`, `renderOutfit`, `setScene`, `setMove`, `initFittingControls`, ~:891–1000) only; the `#tab-fitting` section of `static/index.html`; Fitting Room rules in `static/styles.css`; `app/photo_tryon.py` (keep its `image_cache` calls); `app/body_model.py`; the `/api/photo-tryon*` + `/api/tryons*` endpoints in `app/main.py` only; `tests/safety_tests.py` (add only) | Every issue on Olivia's list reproduced, fixed and checked in the browser (desktop + 375 px); free paths checked first (saved try-ons in the gallery, stubbed `/api/photo-tryon`); at most the paid try-ons Olivia OKs (~$0.05–0.06 each; an identical try-on is reused for $0); tests still pass | Works + Look&feel | **done** (Olivia's list: 1 issue, buttons covering the look; fixed in `real_me.js` + Fitting Room CSS only, `real_me.js?v=a6b`; checked at desktop + 375 px on saved try-ons and a saved 360° spin, fix panel opened, $0, no paid try-on; no code logic changed so no new test, 58/58; `styles.css` has no version bump of its own, a cached browser may need a hard reload) |

### Phase B · submit (code frozen)
| # | Module | Owns (only these files) | Done when | Pts | Status |
|---|---|---|---|---|---|
| B1 | Repo + fresh-clone | `README.md`, `.env.example`, `requirements.txt` (+ optional `requirements-extra.txt`), `.gitignore`, `run.py` | README matches the app (no personas, no "Wore it/Save"; ♡/Not for me, 5-step Me, board, archetype pictures, goal + strategy, fingerprints, live shop, OPENAI_API_KEY also for mock-ups/product shots/goal, current costs, first plan ~30–40 s, tested Python versions); real fresh clone + `.env` one level up installs and runs on `/usr/bin/python3` 3.9 and 3.12/3.13 (split heavy deps if needed); `git status` clean of personal files; commit + push + public or add `zlisto` **only with Olivia's go-ahead**; repo URL → `docs/user_test.json` `repo_url` | 5–20 | todo |
| B2 | Impact: real user test | `docs/user_test.json` (from template), `docs/screenshots/personal/` | Timed before/after on Olivia's real closet + calendar (outfit choice) and one wide-shoe search vs Shop tab; plans she'd wear; a quote; screenshots; ideally 1–2 classmates | 2.5 + Tier 3 | todo |
| B3 | Evidence refresh (sample data only) | `docs/runs_evidence.jsonl`, `docs/tokenomics.json`, `docs/export_runs.py`, `docs/safety_test_results.txt`, `docs/cost_experiments.json`, non-personal `docs/screenshots/*` | Fresh runs (plan fresh, recommend + mock-ups, stylist read, aesthetic read, catalog shop, 1 live shop; ~$0.30, Olivia OK); `export_runs.py`; `safety_tests.py --live` saved; new screenshots (plan + alternates + trace, Margaux-Sloan card with tiles/board/goal, recs with mock-ups, live shop picks, Runs tab, a code rule sending a plan back); old persona/3D-avatar screenshots replaced | feeds ~5 | todo |
| B4 | Report rewrite | `docs/report_src.html`, `docs/build_report.py` | Real repo link; Margaux-Sloan, outfit_rules + taste bans, fingerprints, best-round, alternates, recommender + mock-ups, stylist read/goal, aesthetic board, live-shop retry/merge in text + diagram; one agent count everywhere; new traced run; tokenomics match code (planner + critic **medium**, current medians ≈ $0.0048/plan, live shop ≈ $0.08–0.09, image/mock-up/goal lines); safety count matches results file; §7 real-user numbers (B2) + A4 before/after; explain 12W (Olivia) vs 11W (sample); no "3D"; 10–15 printed pages | ~7 | todo |
| B5 | Slides | `docs/slides_src.html` | ≤10 slides; fix Blair quote (:115), agent count (:90), "8 try-ons" (:145), "low effort" (:149); add Margaux-Sloan / archetype / board / goal visuals (sample only); numbers match report; build after B4 | ~2 | todo |

## 8. Changelog (one line per finished module/feature, newest last)
- 2026-10-26 One stylist Margaux-Sloan; archetypes + pictures; aesthetic board; goal + strategy; 5-step Me tab;
  house-rules autosave fix; Python 3.9 syntax fixes.
- 2026-10-26 Live web shop fixed: was returning 0 picks (in-stock rule too strict, stacked-quote queries, no retry);
  now size-range evidence, shopper queries, broader retry, merged rounds, critic accepts size range. Test: "black
  wide-width ballet flats" → 3 approved picks (DSW, Clarks, DSW), size 12 W listed, ~$0.09/run.
- 2026-10-26 A1 taste bans: `outfit_rules.bans()` builds scoped no's from ✕ notes, Tell tags, check-in "never", house rules, avoid list (men's-style loafers out, feminine loafers fine; negation-aware); enforced in plans/alternates, recs (backups replace), shop, mock-up + goal prompts; `bans` in fingerprint; blocks shown in trace. Before: recs had black penny loafers; after (fresh, $0.0016): hot-pink knit, houndstooth jacket, black trousers, all with ballet flats, no loafers.
- 2026-10-26 A3 defense tests: +15 offline checks (43/43, $0): palette_flag sends an all-neutral day back; an ungrounded 5/5 round never beats a grounded 1/5 one; fingerprint hit on /api/plan + /api/recommend = saved result, no run, no model call (changed input or Fresh take does run); taste bans block penny loafers in plan/alternates/recs/live shop/mock-up/goal prompts while slim loafers + ballet flats pass and "non-itchy" isn't itchy.
- 2026-10-26 A2 look & feel: Body step done only with a photo, photo size estimate or entered sizes (Sample shows "Sample sizes"; Sample never shows personal photos/drape test); Me tab ~40% less text (ⓘ toggles, folded board analysis, color rules, real places, iCal help); phone: 2-column sizes form, rec text under its picture; plan/recs/shop show `blocked` as "I left your … out: you told me …" in her voice; "Shop this in my size" runs the practice catalog right away but waits for Find it on a live (paid) search; saved recs reload on data-set switch; saved recs without pictures no longer auto-draw mock-ups on page load (that cost ~$0.55 today during testing); assets versioned `?v=a2f`.
- 2026-10-26 A4 fresh run on Olivia's data ($0.295 total). **Plan** (Mon 10/26, $0.011, 5 calls, 158 s): before = one neutral look all day (ivory shirt, black pants, blazer, flats, beige tote, parka), color only in alternates (Burgundy polish, Bright-red statement); after = 2 looks split by event: campus = ivory knit + black pants + blazer + ballet flats + parka + **backpack** (house rule), recruiting = **red satin blouse** (Bright Winter) as the main look + tote ("switch from your backpack at 13:50"); code sent round 1 back (too casual + all-neutral palette flag), 4 alternates dropped with reasons, critic vetoed a rust alternate, approved round 2 (style 3/5). **Recs** ($0.0016): before = navy trousers, black wool coat, black penny loafers; after = black tailored trousers (with the red blouse), electric-blue blouse, black-and-icy-white houndstooth jacket (board); no loafers, a mini dress blocked ("very short"), the ✕'d pink knit not repeated. Same: black pants + blazer + flats core. Worse/open: plan 158 s (not 30–40 s), first look still all black/ivory and alternates neutral, beige blazer/tote near the face in 2 rec outfits, fresh recs auto-draw 6 mock-ups ($0.185), live shop 0 picks (link check → A5).

- 2026-10-26 A5 live-shop link check + no surprise pictures. Before: trusted links = only citation footnotes (the model gives none with a JSON answer), so A4's trousers search dropped all 4 real finds (JCPenney, Macy's) → 0 picks while her note praised a Style & Co pant; 4 of 11 live shops lost picks this way; opened pages logged as blank "web_search". After: every search-result/opened URL is trusted (unseen links still dropped), trace shows queries, opened pages and "N trusted link(s)" with the list; same search ($0.046, 4 calls, 39 s) → 3 picks with real links (Liz Claiborne Maya JCPenney $36, Lands' End Starfish $49, Nordstrom), critic *revise* (size/color/budget notes); all-dropped → honest note. Fresh recs: text ~$0.002, pictures ~$0.19 only on "Draw them" (A4 paid $0.185 unasked). +4 offline tests (47/47). Then: a critic *revise* always gets a second search even with 3 picks, newest round's picks first (+1 test, 48/48; ~$0.08–0.10 when revised, ~$0.045 when approved first time; not re-run live). Then, from Olivia's own runs: shop request vs bans checked first ($0 instead of ~$0.10 for 0 picks), unconfirmed sizes no longer get the green ✓, "$0" → "Price at store" (+3 tests, 51/51). Picture reuse: identical image requests (mock-ups, goal, product shot, try-on) reuse the saved file for $0, simultaneous twins share one drawing (A4's double mock-up set cost $0.185 extra) (+3 tests, 54/54). Notes now say they're saved and how they're used, naming any new hard rule (+1 test, 55/55). Backpack house rule checked in code (tote → backpack for school looks), Me tab explains every note/rule, Forget no longer erases same-day notes (+3 tests, 58/58). Try-on likeness (after A6, Olivia asked; `photo_tryon.py` prompt only): recent try-ons stopped looking like her because the prompt asked for "a good photo of me on a good day" (smoothed hair, warm smile, flattering light) on top of up to 6 outfit photos; now an identity block (exact face, hair, body proportions; no slimming, airbrushing or beautifying) comes first, polish is grooming only and likeness wins, softer hair/smile corrections, and her face close-up goes in as image 2 (one live try-on of the 11:16 classroom look, $0.071: **still doesn't look like her** per Olivia, face and body both off; likely cause: 7–8 input images (one photo per garment) + a new scene make the model redraw her; the Oct 24–25 try-ons that looked closer used her photo + text-only clothes, ~$0.02; untried fixes for Future work: clothes-only edit keeping her photo's pose/body, or text-only garments by default); offline prompt test (59/59); same outfit still shows its saved picture until "Not right? → face didn't look like me".
- 2026-10-26 A6 Fitting Room: before, the 360° and Not right? buttons (big uppercase pill at the top), the caption and the fix panel were all drawn on top of the try-on photo, hiding her chest/face in a standing look; after, the photo has its own frame and the buttons, caption and fix panel sit underneath (fix panel scrolls instead of covering), on desktop and 375 px; $0, 58/58.

## 9. Next module prompt (written by the module that just finished; replace, don't append)
**Open now: B1 ∥ B2.** A5 and A6 are both done, so Phase A is complete.

**B1 ∥ B2** (Phase A done 2026-10-26 → **code freeze**: no edits to `app/`, `static/`, `tests/`; a real bug
found now goes to Olivia first). B1 and B2 own disjoint files, so they can run in parallel. One server on port 8000.

**B1 prompt:**

> Read "final project/system_spec.md" first (single source of truth), then do module B1 (repo + fresh clone). Code is
> frozen: own only `README.md`, `.env.example`, `requirements.txt` (+ optional `requirements-extra.txt`), `.gitignore`,
> `run.py`; don't edit `app/`, `static/`, `tests/`.
>
> 1. Rewrite README to match the app as it is now (§1, §3, §4, §6): one stylist Margaux-Sloan (no personas, no
>    "Wore it/Save"), ♡ / Not for me, 5-step Me tab, aesthetic board, archetype pictures, goal + strategy, taste bans,
>    fingerprints (saved results, no model call), live shop with trusted-link check, mock-ups only on "Draw them"
>    (~$0.19), `OPENAI_API_KEY` also needed for mock-ups/product shots/goal picture, current costs (plan ≈ $0.005–0.011,
>    recs text ≈ $0.002, live shop ≈ $0.045 approved first time, ≈ $0.08–0.10 when the critic asks for a second search), first plan can take 30–160 s, tested Python versions, data-set switch,
>    59 offline safety tests; photo try-ons keep her exact face and body proportions (face close-up sent as a second reference, polish = grooming only); the backpack-to-school house rule is checked in code (school looks swap other bags for it); Me tab says what every note and house rule became; every ♡ / Not for me / Tell note shows a ✓ Saved line saying how it's used (and names a new hard rule); a picture already drawn is reused for $0 (`app/image_cache.py`); a shop request that breaks a no is answered free, before any search.
> 2. Real fresh clone into a temp folder with `.env` one level up: install and run on `/usr/bin/python3` (3.9) and
>    3.12/3.13 if present; split heavy deps into `requirements-extra.txt` if 3.9 can't install them; time it (≤10 min).
> 3. `git status` must show no personal files (`data/user/`, photos, `style inspirations/`, `HANDOFF.md`, `.env`, logs).
> 4. Ask me before `git init`/commit/push and before making the repo public (or adding `zlisto`). After pushing, put
>    the repo URL in `docs/user_test.json` `repo_url` only if B2 has created that file (else tell B2/me).
>
> Never read or print .env values. When done: tick §6 Submission items, set B1 status in §7, one §8 line, write the B3
> prompt into §9 (keep B2's if it's still open), give me the next prompt and a short summary.

**B2 prompt:**

> Read "final project/system_spec.md" first (single source of truth), then do module B2 (real user test, for Impact
> and Tier 3). Code is frozen; own only `docs/user_test.json` (copy from `docs/user_test_TEMPLATE.json`) and
> `docs/screenshots/personal/`. Server on port 8000 (don't restart unless it's down).
>
> 1. Plan the test with me first: (a) choosing tomorrow's outfit from my real closet + calendar, timed the old way
>    (me alone) vs with the app (saved plan or one fresh plan, ~$0.01); (b) one wide-shoe or size-18 search timed in a
>    normal store site vs the Shop tab live (~$0.05–0.09). Ask before every paid run; no image runs unless I say so.
> 2. Record per task: minutes before/after, did I find something I'd wear/buy (yes/no + why), number of clicks/sites,
>    cost, and a short quote from me in my words. Use A4/A5 results in §8 as context, not as the test.
> 3. Ideally 1–2 classmates on Sample data (no personal data shown); same fields.
> 4. Screenshots of each "after" to `docs/screenshots/personal/b2_*.jpg`.
>
> Never read or print .env values. Don't commit. When done: set B2 status in §7 (with what wasn't measured), one §8
> line with the before/after numbers, write the B3 prompt into §9 (keep B1's if it's still open), give me the next
> prompt and a short summary.
