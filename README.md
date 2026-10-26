# Closet Twin

**Your own AI stylist, Margaux-Sloan, who dresses you from your real closet for your real calendar and weather, and learns from every note you give her.** She reads your color season, style archetypes and an inspiration board, plans each part of your day from clothes you own, names the few pieces worth buying next (and draws them on request), shops the live web in your size, and shows looks on a photo of you. Behind the one stylist voice, a team of agents (planner, critic, recommender, scout, tailor, cataloger and more) plus hard code checks make sure every suggestion uses real items, fits the weather and the dress code, stays in your palette, and never repeats something you said no to.

Built by Olivia Obodoagha for MGT 409: AI Foundations for Managers (Yale SOM, Fall 2026).

- Report: `report.html` · Slides: `slides.html` (submitted on Canvas)
- Fresh clone to running app: about 3 minutes (steps below). Tested on Python 3.9.6 (macOS built-in `/usr/bin/python3`) and 3.14.7.

---

## Run it (fresh clone, about 3 minutes)

You need **Python 3.9 or newer** and an internet connection (model calls and the weather). No Node, no database.

**1. Get the code**

```bash
git clone <this-repo-url> closet-twin
cd closet-twin
```

**2. Install** (a virtual environment keeps it clean)

macOS / Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Windows (PowerShell):

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

**3. Add the key.** The app looks for a `.env` file **in this folder first, then in the folder one level above it** (so the teaching staff's `submissions/.env` works with no setup). Otherwise:

```bash
cp .env.example .env
```

and fill in the keys:

| Key | Needed for |
|---|---|
| `PORTKEY_API_KEY` (course key) | **Everything text:** plans, recommendations, shopping, closet tagging, stylist read. All text agents run on `gpt-6-luna`. |
| `OPENAI_API_KEY` (optional, your own) | **Pictures only** (`gpt-image-2.5-sunburst`): outfit mock-ups, product shots, the goal picture, photo try-on and 360° spin. Without it those buttons say what's missing and everything else works. If `PORTKEY_API_KEY` is absent, text agents also fall back to this key (same model). |

**4. Start it**

```bash
.venv/bin/python run.py
```

Your browser opens **http://127.0.0.1:8000** (Windows: `.venv\Scripts\python run.py`). Use `--no-browser` to skip opening it, or `PORT=8001` for another port. Stop with Ctrl+C.

## Try it in 3 minutes (Sample data)

The app opens on the **Sample** data set: 22 closet items, a sample profile and stylist setup, a 17-product practice shop, and a sample day (spin class, MBA class, consulting lunch, a recruiter coffee chat, dinner).

1. **Today → Plan my outfits.** Margaux-Sloan reads the calendar and live weather and dresses each part of the day. The first plan can take **30 s to 3½ min** (the critic can send it back up to twice); a repeat of the same day with the same closet and notes comes back instantly from the saved plan, with no model call. Open the trace to see the code checks and the critic. Each look has alternates, **♡ Love it / Not for me** and a **Tell Margaux-Sloan** box.
2. **Today → Find what's missing.** Three pieces worth buying, each with a full outfit from your closet (text only, about $0.002). **Draw them** makes the mock-up pictures (about $0.19 for six, own key); nothing is drawn until you tap. **Shop this in my size** jumps to the Shop tab.
3. **Shop.** Try *"polished flats for a coffee chat I can walk in"*. The practice catalog is free; tick **Search real stores in my size** for the live web (links are kept only if the search actually saw that page). A request that breaks one of your no's is answered right away, before any search.
4. **Me.** The 5-step setup: face & colors (season), body (photo or sizes), style (aesthetic board and/or quiz, archetype pictures, then her read, goal look and strategy), wardrobe, week (calendar). Below it: your notes and house rules, each saying what it became (a hard rule checked in code, or guidance every styling agent reads).
5. **Fitting Room.** Put a look together and see it on a photo of you (own key).
6. **Runs & Safety.** Every run's tokens, cost and step-by-step trace.

## Grader test kit (no personal data needed)

`data/sample/test_kit/` has everything needed to try every input in the app yourself on fictional data: an AI-generated **fake person** (face close-up for colors, full-body photo for sizes and try-on), **8 clothing photos**, a fictional **product page link**, a fictional **receipt** (PDF + photo), the **sample calendar** as an `.ics` file and as an **iCal link**, **inspiration pictures** and a public Pinterest board, and two **real-place photos** for try-on scenes. Its [README](data/sample/test_kit/README.md) is a 13-step checklist: which tab, which file, what to expect.

- **Free right away:** Sample ships a saved plan for **2026-10-26**. Set the date picker to 10/26 and it loads instantly with no model call. Any other date runs a fresh plan; the sample calendar moves onto whatever day you pick.
- **Do it yourself in My closet:** the app keeps photos, closet adds and receipts in My closet (empty on your machine, never committed), so build a test closet there from the kit in about 10 minutes. Checked from a fresh clone: clothes + receipt + calendar → an approved 3-look plan ($0.006) and a photo try-on of the fake person ($0.066).
- **Your own key for pictures:** photo try-on and mock-ups need `OPENAI_API_KEY`. With a body photo in, Today makes one automatic try-on per day (≈ $0.07).

## What it does

- **One stylist, Margaux-Sloan.** One voice in the UI; agent names show up only in traces. Her point of view comes from your style archetypes (shown as pictures), color season, aesthetic board, quiz answers, check-in answers, house rules and every note you leave.
- **Closet.** Add by photo (single or bulk), product link or receipt (photo or PDF). Each piece is tagged, cut out from the background, given plain color words and a size guess, and checked for duplicates.
- **Day plan.** Calendar + weather → planner ⇄ critic (at most 2 revisions, best round kept) → code checks for grounding (only your items), no-repeat, style rules and your season palette → alternates, each validated.
- **Learning loop.** ♡ / Not for me / Tell notes, check-ins and house rules update your profile, and every styling agent reads it. Each note shows a **✓ Saved** line saying how it's used, and names any new hard rule.
- **Taste bans in code.** Things you said no to (for example men's-style loafers, very short hemlines) become banned terms checked in plans, alternates, recommendations, shop picks and picture prompts; a recommendation that hits one is replaced, not shown.
- **House rules in code.** Some rules are enforced, not just suggested: e.g. "backpack for school" swaps any other bag out of school looks (class, office hours, CDO…) and tells you why.
- **Saved results (fingerprints).** A plan or recommendation is saved under a fingerprint of its inputs (date, calendar, closet, notes, bans). Same inputs → saved result, no model call; anything changes → fresh run. **Fresh take** forces a new one.
- **Picture reuse.** Any image already drawn (same model, prompt, size and input photos) is reused for $0 (`app/image_cache.py`); two identical requests at once share one drawing.
- **Photo try-on** keeps your exact face and body proportions: your face close-up goes in as a second reference, and "polish" means grooming only. **Not right? Tell me** redoes it with your correction.

## Cost (measured on gpt-6-luna)

| Action | Typical cost |
|---|---|
| Plan a day (fresh) | ≈ $0.005–0.013 (saved plan: $0) |
| Recommendations (text) | ≈ $0.002 |
| Mock-up pictures (6, on tap) | ≈ $0.19 |
| Live web shop | ≈ $0.045 when the critic approves first time, ≈ $0.08–0.10 when it asks for a second search |
| Practice-catalog shop | ≈ $0.002 |
| Photo try-on | ≈ $0.02–0.07 per image |

## Safety and cost controls

- **Prompt injection:** reviews, web pages and calendar invites are untrusted: hidden HTML and zero-width characters are stripped, instruction-like text is quarantined, the rest is fenced in `<untrusted>` tags.
- **Privacy:** only the Fit Tailor sees your measurements; web searches get store size labels only and are scanned for leaks. Photo EXIF (GPS) is removed.
- **Grounding:** outfits can only use your closet items; shop picks can only link to pages the search saw. Code enforces both.
- **Budgets** (change in `.env`): $0.05 per text run ($0.15 live web), $1.00 per day for text, $2.00 per day for images, 150k tokens and 14 model calls per run, 6 runs per minute.
- **Tests:** 59 offline checks (attacks, grounding, palette, best round, fingerprints, taste bans, live-shop link check, picture reuse, house rules, try-on likeness):

```bash
.venv/bin/python tests/safety_tests.py          # offline, free, 59/59
.venv/bin/python tests/safety_tests.py --live   # real agents vs. attacks, about $0.01
```

## The agents

Fourteen text agents, one prompt each in `app/prompts/` (all `gpt-6-luna`, strict JSON outputs), coordinated by code in `app/agents/orchestrator.py`:

| Agent | Job |
|---|---|
| Day Planner | Splits the day into blocks and dresses each from your closet (`get_calendar`, `get_weather` tools) |
| Style Critic | Checks weather, dress code, comfort, style and truth; approves or sends work back |
| Wardrobe Recommender | Names the 3 pieces worth buying next, each with an outfit |
| Shopping Scout | Finds products in your size (practice catalog or live web search) |
| Fit Tailor | Picks the size to buy from size charts (`fit_check`, deterministic math) |
| Closet Cataloger | Turns a clothing photo into structured data |
| Orienter | Finds the garment in a messy photo before cataloging |
| Receipt Reader | Reads items from a receipt photo or PDF |
| Inspo Stylist | Recreates a screenshot or Pinterest look from your closet |
| Color Analyst | Confirms your color season from a face close-up and code measurements |
| Style Analyst | Archetype blend from the quiz, closet and feedback |
| Aesthetic Reader | Reads your inspiration board |
| Stylist Read | Margaux-Sloan's read: signature, goal look, strategy, follow-up questions |
| Body Estimator | Size estimate (with ranges) from one photo |

Pictures (mock-ups, product shots, goal picture, try-on, 360° spin) use `gpt-image-2.5-sunburst` on `OPENAI_API_KEY`.

- **Plan:** Planner → code checks → Critic → revise (≤ 2) → best round → alternates → you
- **Shop:** ban pre-check → Scout → link check → Tailor → Critic → second search if revised → you
- **Recommend:** Recommender → ban check (backups replace) → you → (on tap) mock-ups

## Sample data vs. your own closet

| Data set | Where | What |
|---|---|---|
| **Sample** (default) | `data/sample/` | Ready-made closet, profile, calendar and practice shop (fictional brands). Ships with the repo. |
| **My closet** | `data/user/` | Your own photos, sizes, notes and calendar. Created on first use and **git-ignored, never committed.** |

Switch with the **Sample / My closet** toggle in the header, or start in your own set with `STYLIST_DATA=user .venv/bin/python run.py`. Connect a calendar in **Me → Your week** with a private iCal link or an `.ics` file. The background-removal model (4.6 MB) downloads into `models/` the first time you add a photo.

## Using it after the course

- **Keys:** the app prefers `PORTKEY_API_KEY`; if it's gone, text agents switch to your own `OPENAI_API_KEY` with the same model.
- **Caps are settings:** `MAX_USD_PER_RUN`, `MAX_USD_PER_LIVE_WEB_RUN`, `MAX_USD_PER_DAY`, `MAX_USD_PER_DAY_IMAGES`, `MAX_PHOTO_TRYONS_PER_DAY`, `MAX_USD_PER_PHOTO_TRYON` in `.env`. Also set a monthly limit in your OpenAI account.
- **Your data** lives in `data/user/` on your laptop; back it up to keep it.

## Project layout

```
run.py                 start the app (PORT, --no-browser)
app/main.py            FastAPI server + core API;  app/routes_extra.py  closet links/receipts/bulk, inspo, aesthetic, watch
app/config.py          .env lookup (repo, then parent folder), model, budgets
app/llm.py             agent loop on the Responses API;  app/ledger.py  budgets, loop guard, logs/runs.jsonl
app/safety.py          injection fencing, privacy, grounding, photo cleaning
app/stylists.py        Margaux-Sloan persona, archetype guide, point of view, questions
app/outfit_rules.py    hard style checks, taste bans, house rules
app/memory.py          saved plans/recs and fingerprints;  app/image_cache.py  picture reuse
app/aesthetic.py       inspiration board, goal picture;  app/mockups.py  recommendation pictures
app/agents/            planner, critic, recommender, scout, tailor, cataloger, orienter, receipt, inspo, analyst, orchestrator
app/prompts/           one prompt per agent + _shared_rules.md + fashion_fundamentals.md
static/                web app (HTML/CSS/JS ES modules)
data/sample/           sample closet, profile, calendar, practice shop
tests/safety_tests.py  59 offline attack and malfunction checks
```

## Troubleshooting

- **"No API key found"**: put `PORTKEY_API_KEY` in `.env` in this folder or the folder above, then restart.
- **Port 8000 is busy**: `PORT=8001 .venv/bin/python run.py` and open http://127.0.0.1:8001.
- **A picture button asks for a key**: pictures need your own `OPENAI_API_KEY`.
- **Weather says "seasonal estimate"**: the live forecast couldn't be reached, so the planner uses monthly normals.
- **First plan feels slow**: 30 s to 3½ min is normal for a fresh plan with critic revisions; the same day again is instant.

## Credits and open source

- **Seasonal color analysis:** measurements and 12-season scoring adapted from [tkamali2020/Seasonal-Color-Analysis](https://github.com/tkamali2020/Seasonal-Color-Analysis) (Apache 2.0), ported in `app/color_measure.py`.
- **Face landmarks:** [MediaPipe Face Landmarker](https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker) (Apache 2.0), loaded in the browser from a CDN.
- **Background removal:** U2-Net-p model from the [rembg](https://github.com/danielgatis/rembg) project (Apache 2.0), run locally with onnxruntime.
- **Style archetype names:** follow Emma Irene Cavanagh's [style archetypes](https://emmairenecavanagh.com/style-archetype/); descriptions and quiz wording are our own.
