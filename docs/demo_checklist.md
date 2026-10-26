# Closet Twin: demo checklist

A running list of what to show when presenting the app. Claude adds to it whenever a feature lands.
Run the app with `.venv/bin/python run.py` and open http://localhost:8000. Switch to **My closet** first
(Sample is the practice closet). Before the demo, check the top-right meter: today's spend vs the $1 cap.

## 1. Wardrobe recognition (getting clothes in)

- [ ] **Bulk photo upload.** Closet → Add → Upload photos, pick several at once. Point out: it starts right
  away, the progress panel shows each photo, 8 are tagged at a time, and pieces land sorted by section.
- [ ] **Sideways photos come out upright.** Upload a photo taken sideways. Point out: the Photo Orienter takes
  3 votes and turns the photo only when 2 agree (96% right on my own photos, up from 84%).
- [ ] **Product shots.** Show a flat-lay photo next to its closet tile: the Product Photographer redraws it
  upright, steamed and on a clean background, like a store photo.
- [ ] **"What's wrong?" redo.** Edit → Redo product shot → tick Color / Product type / Wrinkled etc. Point out:
  the answers fix the piece's name and colour, and stay with it for every later redo.
- [ ] **Upload a receipt.** Add → Upload receipt → a screenshot or PDF of an order email (save every page).
  Point out: the Receipt Reader lists items with their printed size and price, you tick what to add, the
  pictures are cut from the receipt, and the product shot shows only the piece, never the model.
- [ ] **Re-upload the same receipt.** Nothing is duplicated: pieces are matched by the SKU on the receipt.
- [ ] **Incomplete receipt warning.** Upload a PDF missing pages: the app says what's missing.
- [ ] **Paste a link.** Amazon / Abercrombie / Quince / Gap links pull the photo, price and store. For stores
  that block apps (J.Crew, Zara…): right-click the photo → Copy Image → ⌘V into the box with the link.
- [ ] **Size guesses + fit cards.** After adding, each piece shows "Your size: likely XL"; tap how it fits and
  the size estimate updates. Add a bag, hat or jewelry: no size or fit card appears (belts still ask).
- [ ] **Shoe size guess.** Open a pair of shoes in the closet (e.g. the dark brown Doc Martens): it
  shows "Your size: likely 12 wide". Point out how it gets there:
  1. **Starts from my shoe size and width** saved in Me (12, wide), so every new pair gets a guess right away.
  2. **Learns brands from returns.** Mark a pair "I returned it: too small" and that brand's next guess moves
     up half a size ("brand runs small on you").
  3. **Learns my foot from fit answers.** Tap how a pair fits (perfect / snug / tight / loose): the size turns
     into a foot length (a US 12 is about 11.2 in) nudged by the fit, and that refines my foot measurement.
  4. **Uses it when shopping.** In Shop, the Fit Tailor matches that foot length and width against the store's
     own size chart to pick the size before I buy.
- [ ] **Edit and sections.** Change a piece's section (e.g. Tanks & camis → Tops & blouses) and it moves on Save.
  Mark something out of season (snowflake/sun icon) and it moves to "Out of season · packed away".
- [ ] **Duplicate check.** Upload the same photo twice: a slim "⚠ possible duplicate" line appears above the closet
  (it never covers anything); Review opens both pieces side by side (same photo, same receipt item number, or same kind + color). Remove the extra, or
  "Not duplicates" and it's never flagged again. Nothing is deleted without asking.
- [ ] **Styled remove dialog.** Bin icon → "Remove / Keep it".
- [ ] **Learned colour words.** Rename a colour in Edit (e.g. raspberry → fuchsia): the app remembers it, but
  only for that same shade (so reds and corals keep their own names).

## 2. Styling engine (what to wear)

- [ ] **Plan my outfits.** Today → Plan my outfits. Point out: it reads my real Outlook day (coffee chats, case
  interview demo) and the hourly weather; the Day Planner drafts and the Style Critic checks every outfit before I
  see it. If a revision comes back worse, the app keeps the round the critic scored highest.
- [ ] **Styled, not just dressed.** Each look gets a finishing piece that suits the setting (structured tote for
  recruiting, no backpack). Colour rules a stylist uses: my Bright Winter palette near the face, one leather family
  (black flats with black, never brown boots under all-black), matching metals, at most three colours.
- [ ] **Intentional, not random.** Press Plan my outfits again (or refresh): same closet, calendar, weather and
  feedback → the same pick, instantly, no AI call ("this is still your stylist's pick"). Change something (mark a piece
  out of season, a new event) → it re-plans and says what changed. ↻ Fresh take asks for a new look on purpose.
  The 3-piece recommendations (with their pictures) work the same way for the same look.
- [ ] **Hard style rules in code.** Two statement colors together (burgundy + rust), brown shoes under all-black, or
  jeans on a recruiting day can't reach me: the main pick goes back to the planner, an option is dropped. The critic
  can also veto any option it wouldn't send me out in.
- [ ] **Outfit options.** Under each pick: "Or wear" with two alternates (e.g. "Bright-red polish", "Burgundy
  classic"), each with its reason. Tap **Wear this instead**: it becomes the outfit (tagged "your pick") and the
  stylist's pick moves into the options; feedback, try-on and the no-repeat memory follow my choice. Free, no AI call.
- [ ] **Before/after numbers.** Same closet, same day: before the fixes the critic sent it back 3 times and never
  approved (7 calls); after, approved first time (3 calls, 22 s, $0.002).
- [ ] **No repeats + feedback.** Give an outfit feedback (wore it / banger / not for me), plan again: worn
  pieces rest, loved ones come back.
- [ ] **The next 3 pieces, as pictures.** Today → type the look I'm going for ("polished recruiting") → Find what's
  missing. The Wardrobe Recommender names exactly 3 pieces that pull my closet together (it noticed my black pants read
  casual and my parka is sporty: navy tailored trousers, a black wool coat, black loafers). The Mock-up Artist draws
  each piece as a store photo and an editorial outfit board with my real closet pieces (Tory Burch flats, Kate Spade
  tote). Fresh picks show "No pictures yet · Draw them (about $0.19)" and draw only on that tap (saved picks keep their
  pictures). A picture is never paid for twice: ask for the same one again (or tap twice, or in two tabs) and the
  saved file is reused for $0; the trace says "already drawn, reused". A jeans outfit for a polished look is caught in code.
- [ ] **See it on me.** Under a piece: See it on me → Fitting Room → Make it real: me in the outfit, the new piece drawn
  from its mock-up. …and shop the top pick still finds it in my size.
- [ ] **Shop this in my size.** Under any of the 3 picks: Shop this in my size → Shop tab with the search filled in. On
  My closet it waits for **Find it** and says the cost first (live stores, about a minute, about $0.07); on Sample it
  searches the practice catalog right away. No picks? "Search more broadly" or "Try the practice catalog".
- [ ] **Inspo.** Recreate an Instagram/Pinterest look from my own closet.

## 3. Outfit presentation

- [ ] **Closet tiles.** Store-style product shots on light tiles, grouped by section with counts.
- [ ] **Section rail.** A navy rail on the right, from the top of the page (↑ Top, Tops, Pants, Dresses, Shoes…).
  Click a section to jump there; the gold highlight follows you as you scroll. It sits beside the closet, never over
  it; on a phone it folds into a small ↑ / ☰ pill.
- [ ] **Today's outfit cards.**

## 4. Virtual try-on

- [ ] **Fitting Room.** Put an outfit on the twin; switch scenes; take a snapshot. The 360° / Not right? buttons,
  caption and fix panel sit under the photo, so the whole look stays visible (desktop and phone).
- [ ] **Photo try-on.** Me in the outfit (uses the clean product shot for store/receipt pieces). It keeps my real
  face, skin, hair and body but looks camera-ready: neat hair, a natural smile, coat carried indoors.
- [ ] **"Not right? Tell me."** Under any try-on photo: tick Hair / Want a smile / Doesn't look like me / Coat on indoors…
  plus a note → Redo with these fixes. The notes go into every photo after it.
- [ ] **Fit Tailor.** In Shop, a product's size and zone-by-zone fit before buying. For shoes, show it picking
  the size from foot length + width against the store's chart (see "Shoe size guess" above).

## 5. Shop, safety and cost

- [ ] **Live shop, links you can trust.** Shop → live web → "black tailored straight-leg trousers, soft comfortable
  waistband, polished drape" (~$0.045, or ~$0.08–0.10 and ~80 s when the critic asks for a second search): 3 real picks (JCPenney, Lands' End, Nordstrom) with store links.
  Trace: each search with its result count, the page it opened, and "39 trusted link(s) the search returned or opened";
  a link the search never saw is dropped, and if every pick is dropped her note says so honestly ("I couldn't verify a
  link I'd stand behind…") instead of praising a hidden pick. Ask for something you ruled out ("pleated mini skirt" when you said never very short): she
  answers right away, $0, no search. A size the page didn't confirm shows as a grey note, not a green ✓; no price seen
  shows "Price at store", not "$0". Screenshots `personal/a5_shop_live.jpg`, `a5_shop_trace.jpg`.

- [ ] **Shop + price tracking.** Track a product's price; ↻ Check prices.
- [ ] **Runs & Safety tab.** Show a run's trace (which agent did what), its cost, and a safety event
  (e.g. suspicious text cleaned from a product page or review).
- [ ] **Budget caps.** The meter: per-run and daily caps; image work has its own $2/day cap.

## 6. One stylist: Margaux-Sloan

- [ ] **Setup in five steps.** Me tab is now "Set up Margaux-Sloan": 1 Face & colors → 2 Body → 3 Style → 4 Wardrobe
  → 5 Week, with a ✓ progress strip at the top. Everything already added stays.
- [ ] **Her strategy and the goal.** In step 3, after your inspiration or quiz: Margaux-Sloan's read, a picture of the goal
  look she's dressing you toward (e.g. houndstooth tweed jacket + hot-pink knit for a Bright Winter), and her strategy
  (Keep wearing / Add / Phase out / Try next / Styling habit) naming real closet pieces.
- [ ] **House rules stick.** They save as you type ("✓ saved") and no refresh or other save can wipe them.
- [ ] **House rules are enforced.** "I will wear my backpack to school" → every class/campus look (plan, alternates,
  recommendation outfits) carries the argyle backpack, and she says "I swapped your tote for your backpack: your house
  rule says …"; a dinner or theatre look can still use the tote. Under the rules box: "→ Checked in code: …".
- [ ] **She shows what each note did.** Me → What you've told me: each note says "→ Hard rule, checked in code …: never …"
  or "→ Read before every plan, pick and shop search". ✕ Forget removes just that one note.
- [ ] **She listens: no's are hard rules.** Tap ✕ Not for me + a note ("looks like men's shoes") on a piece, then ↻ Fresh
  take: men's-style loafers never come back (plans, picks, shop, pictures), while slim/pointed/ballet loafers still can.
  Runs & Safety trace shows "Taste bans checked in code" and any "Blocked …: why".
  Right under the note a green line stays: "✓ Saved. New hard rule: never men's-style loafers … checked in code on plans,
  picks, shop results and pictures". A ♡ says she reads it before every plan, pick and shop search; it's still shown
  after a reload.
- [ ] **She says what she left out.** Under her note on a plan, the 3 picks or shop results, a calm green-edged line in
  her voice: "I left your black floral long-sleeve mini dress out: you told me never very short or low-cut." It comes
  from the code's ban check, not the model, and it's on the saved picks too (free to show, no AI call).
- [ ] **See the styles.** Me tab → each of the 7 archetypes has a picture (static/archetypes/, drawn once by
  docs/make_archetype_boards.py), so someone new sees Classic vs Romantic vs Dramatic at a glance.
- [ ] **Show her your aesthetic.** In Margaux-Sloan's card: paste a Pinterest board/pin or a blog/lookbook page, or
  upload screenshots (Instagram: screenshot 3–6 posts; Instagram hides pages from apps). She shows the pictures as a
  board and reads them into archetypes with weights, vibe words, colors, signature pieces, how it's styled, and how to
  wear it in your season's colors → "Use as my blend". Every plan and recommendation then dresses you toward it.
- [ ] **One stylist, not four.** Me tab → Margaux-Sloan (half quiet-luxury Margaux, half uptown-prep Sloane). She builds
  every look around your style archetypes (7 archetypes from the style-archetype guides; tap your foundation, current
  season and accent, or take the 3-question quiz in the same card).
- [ ] **She asks you questions.** Today tab: "Margaux-Sloan has a question" (parts of your life, how bold, how much
  jewelry/bags, color approach, what never to wear). Answers go into every plan and recommendation.
- [ ] **She learns.** Every 3 reactions she rewrites "her read on you" and writes new follow-up questions about what
  she's unsure of (e.g. why you turned something down). The meter goes Getting to know you → Learning your eye → Knows your taste.
- [ ] **Feedback everywhere.** ♡ / Not for me + note on each outfit and each recommended piece, and a "Tell
  Margaux-Sloan" box with quick tags (Too business, Too masculine, Not my colors, Love this direction…).
- [ ] **Push, every couple of weeks.** About every 14 days one option is titled "Push: …", a bolder step she then asks about.
- [ ] **Your colors, used.** Me → Your colors shows your signature colors; looks carry one of them, and a day of
  all black-and-white is sent back by a code check when you own pieces in your season's colors.
- [ ] **Fashion fundamentals.** Color scheme on purpose (about 60/30/10), balanced proportions, mixed textures, one
  formality level, and 1–3 accessories when the moment calls for them.

## Before you present

- [x] Paste the Outlook calendar link in Me (so Plan my outfits uses real events). Connected 2026-10-26.
- [ ] Reload the page (⌘R) so you're on the latest version.
- [ ] Have a receipt screenshot/PDF and one sideways photo ready on the Desktop.
