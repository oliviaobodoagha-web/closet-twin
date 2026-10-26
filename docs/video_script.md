# Closet Twin: demo video with the test kit (2–3 min, optional Canvas item)

A screen recording of a **blank copy of the app** (fresh GitHub clone, empty My closet) that you fill with the grader
test kit's fictional person, on camera. Your real closet and data are never touched or shown.

## The blank copy

- Folder: `~/Desktop/AI Foundations Yo/closet-twin-video` (a fresh clone of the public repo, packages installed). It uses
  the `.env` in `AI Foundations Yo/` one level up, so nothing to set up.
- Open **http://localhost:8001** in Chrome. If it isn't running, start it in Terminal:

      cd ~/Desktop/"AI Foundations Yo"/closet-twin-video && PORT=8001 .venv/bin/python run.py --no-browser

- Kit files are in `closet-twin-video/data/sample/test_kit/` (open that folder in Finder before recording).
- Switch the header to **My closet** (it starts empty). Run costs are logged in this copy, separate from your real one.
- **Fully blank:** no clothes, no calendar, no season, no style, no notes. (The app normally seeds a new My closet with the
  Sample profile; that seed is saved as `data/user/profile.sample-seed.json.bak` and the profile was emptied.) Margaux-Sloan
  opens with her starter questions.
- Start over any time: stop the app, delete everything in `closet-twin-video/data/user/` **except** `profile.json`'s blank
  version (or ask Claude to blank it again), start again. Deleting the whole folder brings back the Sample-seeded profile.

## How to record

1. Chrome window about 1440×900, zoom 100%, other tabs closed, Do Not Disturb on.
2. **⌘⇧5 → Record Selected Portion** around the Chrome window; **Options →** your microphone. Stop with ■ in the menu bar.
3. Model steps take time (closet tagging ~10–20 s, a plan 30 s–4 min, a live shop ~40–80 s). Keep recording, then
   **trim the waits** in QuickTime (Edit → Trim, or Split Clip) or iMovie. Plan on 10–15 min of raw footage for a 3-min cut.
4. Easiest voice-over: talk while you click, and re-record any shot you fumble. Or record silently and add the voice in
   iMovie afterwards.

## Cost of one full run-through (billed to the course/own keys)

Closet photos ≈ $0.005 · receipt ≈ $0.001 (+ product shots ≈ $0.02 each) · face + body ≈ $0.001 · board + read +
goal picture ≈ $0.015 · plan ≈ $0.005–0.013 · recs ≈ $0.002 · **Draw them ≈ $0.19** · live shop ≈ $0.05–0.12 ·
automatic daily try-on ≈ $0.07 · 360° ≈ $0.25. **About $0.40 without 360°, $0.65 with it.** A second take of the same
step is often free (saved plan, reused pictures).

## Shot list and voice-over (≈ 2:45 after trimming)

| # | Time | On screen (kit file → where) | Say (roughly) |
|---|---|---|---|
| 1 | 0:00–0:15 | Header on **My closet**, empty Today tab. | "This is Closet Twin, an AI stylist that dresses you from your real closet for your real day. To show it end to end, I'm starting from an empty closet with a fictional test person." |
| 2 | 0:15–0:40 | **Me → 1 Face**: tick consent, upload `fake_person_face.jpg` → color season. **2 Body**: `fake_person_full_body.jpg` → size estimate. | "First she learns who she's dressing: her color season from a face close-up, measured by code and confirmed by an agent, and a size estimate from one full-body photo." |
| 3 | 0:40–1:00 | **Me → 3 Style**: board **Upload pictures** (`../aesthetic/*.jpg`) → board read, archetype pictures → Margaux-Sloan's read + goal picture. | "Then her style: an inspiration board and archetypes shown as pictures. Margaux-Sloan writes back her read, a goal look and a strategy." |
| 4 | 1:00–1:25 | **Closet → Upload photos**, select all 8 in `clothes/`; pieces appear tagged and cut out. Then **Upload receipt** → `receipt_fictional.pdf` → tick the 3 lines. | "Clothes go in by photo, product link or receipt. Each piece is tagged, cut out and given a size guess; a receipt adds the navy sweater, black flats and camel coat in one go." |
| 5 | 1:25–1:35 | **Me → 5 Your week**: upload `sample_day.ics` → 5 events. | "Her calendar: spin class, class, a club lunch, a recruiter coffee chat and dinner." |
| 6 | 1:35–2:05 | **Today → Plan my outfits** (trim the wait) → the looks, alternates, her notes. Open the **trace**: "sent back to the planner", the Critic's verdict. | "One look per part of the day, from her closet, for today's weather. Behind one stylist voice are 14 agents. Code checks every look before a critic does: only clothes she owns, the right dress code, her palette. Here you can see code sending a look back." |
| 7 | 2:05–2:20 | **Not for me** on a piece + reason → the "✓ Saved … hard rule" line. Plan again (or Shop: ask for that piece) → it's blocked. | "When she says no, it becomes a hard rule in code, and it never comes back: not in plans, recommendations, shopping or pictures." |
| 8 | 2:20–2:35 | **Find what's missing** → 3 pieces with outfits → **Draw them** (trim) → mock-ups. *Or* **Shop** with **Search real stores in my size**: *black ballet flats in wide width* → picks with real links. | "She names the three pieces worth buying next and draws them only when asked, or shops the live web in her size, keeping only links the search actually saw." |
| 9 | 2:35–2:50 | **Fitting Room** (the automatic try-on of today's look), then **Runs & Safety**. | "Here's the look on her. And every run shows its tokens and cost: a full day plan is about half a cent." |

Optional extras if you have time: paste the product link (`test_kit/README.md` step 4b), Inspiration with a Pinterest
board, the 360° view, a house rule.

## Things to demonstrate (pick 6–8 for a 3-minute video)

1. Today: a plan for a real day from the calendar and hourly weather, split into looks per event
2. Alternates ("Or wear") and Margaux-Sloan's note on each look
3. The run trace: code sends a plan back (too casual, all-neutral, banned piece), critic revise → approve, best round kept
4. Not for me + a reason → "✓ Saved" names the new hard rule (taste ban checked in code)
5. A house rule enforced in code (backpack for school looks)
6. Same day again → saved plan, instant, $0 (fingerprint); ↻ Fresh take forces a new one
7. Find what's missing: 3 pieces + outfits; Draw them only on tap; reused pictures cost $0
8. Shop: live search in my size (12 W), only links the search saw, size evidence, critic notes
9. A shop request that breaks a no is answered before any paid search
10. Price tracker (Watching)
11. Me tab: 5 steps, color season + drape test, archetype pictures, inspiration board, goal picture + strategy
12. Closet: add by photo, product link or receipt; cutout, color words, size guess, duplicate check
13. Fitting Room: photo try-on, 360° view, "Not right? Tell me"
14. Runs & Safety: tokens and cost per run, guardrails, safety tests (63/63)

## Blank version (fill in your own)

| # | Time | Feature to show | On screen (what to click) | What I'll say | Data set | Cost | ✓ |
|---|---|---|---|---|---|---|---|
| 1 | 0:00– | | | | | | ☐ |
| 2 | | | | | | | ☐ |
| 3 | | | | | | | ☐ |
| 4 | | | | | | | ☐ |
| 5 | | | | | | | ☐ |
| 6 | | | | | | | ☐ |
| 7 | | | | | | | ☐ |
| 8 | –3:00 | | | | | | ☐ |

Before recording: ☐ app running on :8001 ☐ header on My closet ☐ kit folder open in Finder ☐ mic on ☐ Do Not Disturb
