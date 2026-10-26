# Test kit (for graders)

Everything a grader needs to try **every input in the app** without their own photos, clothes or calendar. Nothing here is a real person, store or order.

**Before you start:** the staff `.env` one folder up has both keys (`PORTKEY_API_KEY` for text, `OPENAI_API_KEY` for pictures). Start the app (`.venv/bin/python run.py`) and open http://127.0.0.1:8000.

## Two ways to look around

- **Sample** (header toggle): a ready closet, profile, stylist setup and practice shop. Set the date to **2026-10-27** to see a saved plan instantly with no model call. Any other date plans fresh, with the sample calendar moved onto that day.
- **My closet**: starts empty on your machine (`data/user/`, git-ignored). The app keeps every photo, closet add, receipt and calendar here, never in Sample, so use this kit to fill it.

## Build a test closet in My closet (about 10 minutes)

| # | Where in the app | Use | Expect |
|---|---|---|---|
| 1 | **Me → 1 Your face & colors** (tick consent, upload) | `fake_person_face.jpg` | Color season with reasons |
| 2 | **Me → 2 Your body** (tick consent, upload; or type sizes) | `fake_person_full_body.jpg` | Size estimate with ranges |
| 3 | **Me → 3 Your style**: board **Upload pictures** and/or the quiz | `../aesthetic/*.jpg` | Board read, archetype pictures, then Margaux-Sloan's read, goal look and strategy |
| 4a | **Closet → Upload photos** (select all) | `clothes/*.jpg` (8: black trousers, jeans, white shirt, pink sweater, tan tote, white sneakers, black leggings, grey half-zip) | Each tagged, cut out, color words |
| 4b | **Closet → Paste a link** | `https://raw.githubusercontent.com/oliviaobodoagha-web/closet-twin/main/data/sample/test_kit/product_link/product_page.html` | Black ruffle blouse added from a (fictional) product page |
| 4c | **Closet → Upload receipt**, then pick lines | `receipt_fictional.pdf` (or `.jpg`) | 3 lines: navy sweater, black ballet flats, camel coat |
| 5a | **Me → 5 Your week → iCal link** (time zone `America/New_York`) | `https://raw.githubusercontent.com/oliviaobodoagha-web/closet-twin/main/data/sample/test_kit/sample_day.ics` | Calendar connected by link |
| 5b | …or **upload .ics** instead | `sample_day.ics` | Same 5 events: spin, class, lunch, coffee chat, dinner (repeats daily, so any date works) |
| 6 | **Me → 2 Your body → Real places for try-ons** (optional; pick Classroom or Coffee shop, then Upload place photo) | `places/classroom.jpg`, `places/coffee_shop.jpg` | Try-ons can use these real places as scenes |
| 7 | **Today → Plan my outfits** | | One look per part of the day, critic review, alternates, trace |
| 8 | **Today → Find what's missing** → **Draw them** | | 3 pieces with outfits; pictures only after the tap |
| 9 | **Shop**: e.g. *black ballet flats in wide width*; tick **Search real stores in my size** for live web | | Picks with real links; try a request that breaks a no (e.g. *men's penny loafers* after ✕-ing them) |
| 10 | **Shop → Inspiration**: upload a screenshot, or paste a board | `../aesthetic/*.jpg`, or `https://www.pinterest.com/whowhatwear/street-style/` | Look recreated from the closet + what's missing |
| 11 | **Fitting Room**: put a look on, **photo try-on**, **360°**, **Not right? Tell me** | | The fake person in the outfit |
| 12 | Leave **♡ / Not for me / Tell** notes, then plan again | | ✓ Saved line, new hard rule, Me tab shows what each note became |
| 13 | **Runs & Safety** | | Tokens, cost and trace for every run |

The person in `fake_person_*.jpg`, the clothes in `clothes/` (except the pink sweater drawing), the product photo and the place photos were made with `gpt-image-2.5-sunburst`. The person is **AI-generated, not a real person**. The store on the receipt and product page doesn't exist.

## Costs and heads-up

- Text steps ≈ $0.001–0.004 each; a fresh plan ≈ $0.005–0.013 (30 s – 4 min); live web shop ≈ $0.05–0.10.
- Pictures need `OPENAI_API_KEY`: receipt product shots, mock-ups (≈ $0.19 for six), goal picture, try-on (≈ $0.02–0.07 each).
- Once the body photo is in, Today makes **one automatic try-on photo per day** of the first look (≈ $0.07).
- Every 3 notes refreshes Margaux-Sloan's read and goal picture (≈ $0.013).
- The background-removal model (4.6 MB) downloads on the first closet photo.
- To start over, delete `data/user/`. To reset Sample, `git checkout data/sample`.
