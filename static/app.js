// Closet Twin front end: talks to the FastAPI agent backend and drives the 3D fitting room.

const $ = (s, el = document) => el.querySelector(s)
const $$ = (s, el = document) => [...el.querySelectorAll(s)]
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))
const fmtK = (n) => (n >= 1000 ? (n / 1000).toFixed(1) + 'k' : String(n ?? 0))
const usd = (n, d = 4) => '$' + (n ?? 0).toFixed(d)

const AGENT_COLORS = {
  'Closet Cataloger': '#6b4e7a',
  'Wardrobe Recommender': '#8a5a2b',
  'Day Planner': '#24375f',
  'Fit Tailor': '#1f5c46',
  'Shopping Scout': '#8a6a3a',
  'Style Critic': '#7a1f2b',
  Orchestrator: '#5b6475',
}
const ZONE_COLORS = { good: '#3e8e63', snug: '#c9962b', tight: '#a8323e', short: '#a8323e', long: '#c46a2f', loose: '#3f6ea8', unknown: '#a7a29a' }
const SCENES = [['studio', 'Boutique'], ['classroom', 'Classroom'], ['office', 'Office desk'], ['gym', 'Gym'], ['coffee', 'Coffee shop'], ['street', 'Campus walk'], ['dinner', 'Dinner']]
const MOVES = [['idle', 'Stand'], ['sit', 'Sit'], ['walk', 'Walk']]

const state = {
  dataset: localStorage.getItem('ct-dataset') || 'sample',
  closet: [],
  profile: null,
  outfit: [],
  zones: {},
  room: null,
  scene: 'studio',
  move: 'idle',
  filter: 'all',
  runs: [],
  stylist: null,
  blend: [],
}

// ------------------------------------------------------------------ API
async function api(path, opts = {}) {
  const res = await fetch(path, opts)
  let data = null
  try { data = await res.json() } catch { /* no body */ }
  if (!res.ok || (data && data.ok === false)) {
    const msg = (data && (data.error || data.detail)) || `Request failed (${res.status})`
    const err = new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
    err.run = data && data.run
    throw err
  }
  return data
}
const q = (extra = {}) => new URLSearchParams({ dataset: state.dataset, ...extra }).toString()
const postJSON = (path, body) => api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

function toast(msg) {
  const t = $('#toast')
  t.textContent = msg
  t.classList.remove('hidden')
  clearTimeout(toast._t)
  toast._t = setTimeout(() => t.classList.add('hidden'), 3200)
}

// ------------------------------------------------------------------ header
async function refreshStatus() {
  try {
    const s = await api('/api/status')
    $('#key-warning').classList.toggle('hidden', s.key_set)
    $('#meter-today').textContent = `${usd(s.spent_today_usd)} of ${usd(s.limits.max_usd_per_day, 2)} daily cap`
    state.status = s
    renderLimits()
  } catch { /* server not up yet */ }
}

function updateMeter(run) {
  if (!run) return
  const t = run.totals
  $('#meter-last').innerHTML = `${fmtK(t.input_tokens)} in · ${fmtK(t.cached_tokens)} cached · ${fmtK(t.output_tokens)} out · <b>${usd(t.cost_usd)}</b>`
  refreshStatus()
}

function setDataset(ds) {
  state.dataset = ds
  localStorage.setItem('ct-dataset', ds)
  $$('.dataset-toggle button').forEach((b) => b.classList.toggle('active', b.dataset.ds === ds))
  state.outfit = []
  state.zones = {}
  restoreOutfit()
  $('#plan-out').innerHTML = ''
  $('#shop-out').innerHTML = ''
  refreshPhotoStatus()
  refreshCalendarStatus()
  $('#season-out').innerHTML = 'Not analyzed yet.'
  loadAll()
  document.dispatchEvent(new CustomEvent('ct:dataset', { detail: ds }))
}

// ------------------------------------------------------------------ tabs
function showTab(name) {
  $$('#tabs button').forEach((b) => b.classList.toggle('active', b.dataset.tab === name))
  $$('.tab').forEach((t) => t.classList.toggle('active', t.id === `tab-${name}`))
  if (name === 'runs') loadRuns()
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

// ------------------------------------------------------------------ garment icons
function garmentSVG(item) {
  const c = item.color_hex || item.colors?.[0]?.hex || '#cccccc'
  const sub = (item.subtype || '').toLowerCase()
  const cat = item.category
  const [r, g, b] = [1, 3, 5].map((i) => parseInt((c + '000000').slice(i, i + 2), 16) || 0)
  const dark = 0.299 * r + 0.587 * g + 0.114 * b < 70
  const stroke = dark ? 'rgba(20,33,61,0.5)' : 'rgba(20,33,61,0.3)'
  let shape
  if (cat === 'shoes') {
    const boot = sub === 'boots'
    const heel = sub === 'heels'
    shape = boot
      ? `<path d="M34 22h22v42c0 6 4 8 12 10l14 4c4 1 6 4 6 8v4H22l2-30z" fill="${c}" stroke="${stroke}" stroke-width="2"/><rect x="22" y="86" width="68" height="6" rx="3" fill="#1b1416"/>`
      : heel
        ? `<path d="M18 70c8-4 18-16 30-18 14-2 30 12 46 18 4 2 6 6 4 10H26z" fill="${c}" stroke="${stroke}" stroke-width="2"/><rect x="22" y="78" width="10" height="16" fill="#1b1416"/>`
        : `<path d="M14 64c0-8 6-12 12-12 10 0 14-10 24-10 8 0 10 8 20 12 10 4 20 4 24 12 3 6 0 14-6 14H20c-4 0-6-4-6-8z" fill="${c}" stroke="${stroke}" stroke-width="2"/><rect x="14" y="78" width="84" height="7" rx="3.5" fill="${sub === 'sneakers' || sub === 'running' ? '#f5f5f5' : '#1b1416'}"/>`
  } else if (sub === 'skirt') {
    shape = `<path d="M36 18h40l14 74H22z" fill="${c}" stroke="${stroke}" stroke-width="2"/><rect x="36" y="16" width="40" height="8" fill="${c}" stroke="${stroke}" stroke-width="2"/>`
  } else if (cat === 'bottom' || sub === 'leggings') {
    shape = `<path d="M32 14h48l6 84H62l-6-56-6 56H26z" fill="${c}" stroke="${stroke}" stroke-width="2"/><rect x="32" y="12" width="48" height="8" fill="${c}" stroke="${stroke}" stroke-width="2"/>`
  } else if (cat === 'dress') {
    shape = `<path d="M42 12h28l4 16 10 6-6 18 16 46H18l16-46-6-18 10-6z" fill="${c}" stroke="${stroke}" stroke-width="2"/>`
  } else if (sub === 'bag') {
    shape = `<path d="M40 38c0-18 32-18 32 0" fill="none" stroke="${c}" stroke-width="5"/><rect x="24" y="38" width="64" height="52" rx="8" fill="${c}" stroke="${stroke}" stroke-width="2"/>`
  } else if (sub === 'sports_bra') {
    shape = `<path d="M30 30l10-14h6l10 18 10-18h6l10 14v26H30z" fill="${c}" stroke="${stroke}" stroke-width="2"/>`
  } else {
    const long = !['tee', 'polo', 'tank'].includes(sub)
    const coat = cat === 'outerwear'
    const h = coat && sub !== 'blazer' ? 96 : 80
    shape = long
      ? `<path d="M40 14l-20 10-12 56 12 3 10-40v${h - 40}h52V43l10 40 12-3-12-56-20-10c-2 8-8 12-16 12s-14-4-16-12z" fill="${c}" stroke="${stroke}" stroke-width="2"/>${coat ? `<line x1="56" y1="26" x2="56" y2="${h}" stroke="${stroke}" stroke-width="2"/>` : ''}`
      : `<path d="M40 16l-24 12 8 16 10-5v53h44V39l10 5 8-16-24-12c-2 8-8 12-16 12s-14-4-16-12z" fill="${c}" stroke="${stroke}" stroke-width="2"/>`
  }
  return `<svg viewBox="0 0 112 112" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">${shape}</svg>`
}

function itemImg(item) {
  // upright product shot > background-removed cutout > the original photo
  // a store or receipt photo usually shows a model: never show that, only the redrawn piece (sketch until it's ready)
  if (['receipt', 'pasted'].includes(item.photo_from) && !item.shot) return garmentSVG(item)
  const file = item.shot || item.cutout || item.image
  if (file) return `<img class="${item.shot || item.cutout ? 'cut' : ''}" src="/api/images/${encodeURIComponent(state.dataset)}/${encodeURIComponent(file)}${item.v ? `?v=${item.v}` : ''}" alt="${esc(item.name)}" />`
  return garmentSVG(item)
}

// ------------------------------------------------------------------ status / trace helpers
function working(el, title, agents) {
  el.innerHTML = `<div class="status"><div class="spinner"></div><div><b>${esc(title)}</b><div class="agent-steps">${agents.map((a, i) => `<span class="${i === 0 ? 'on' : ''}">${esc(a)}</span>`).join('')}</div></div></div>`
  const spans = $$('.agent-steps span', el)
  let i = 0
  const timer = setInterval(() => {
    if (!spans.length) return
    spans[i].classList.remove('on')
    i = Math.min(i + 1, spans.length - 1)
    spans[i].classList.add('on')
  }, 6000)
  return () => clearInterval(timer)
}

function showError(el, err) {
  el.innerHTML = `<div class="status error"><div style="font-size:22px;color:var(--burgundy)">!</div><div><b>${esc(err.message)}</b>${err.run ? '<div class="muted small">The run was stopped and logged. See the trace below.</div>' : ''}</div></div>`
  if (err.run) {
    el.insertAdjacentHTML('beforeend', traceHTML(err.run, true))
    updateMeter(err.run)
  }
}

function agentPill(name) {
  const c = AGENT_COLORS[name] || '#999'
  return `<span class="agent-pill" style="background:${c}14;color:${c};border:1px solid ${c}55">${esc(name)}</span>`
}

function traceHTML(run, open = false) {
  const t = run.totals
  const steps = run.trace.map((s) => `<li class="${esc(s.kind)}"><span class="t">${s.t.toFixed(1)}s</span>${agentPill(s.agent)}<span class="msg">${esc(s.summary)}</span></li>`).join('')
  const nSafety = (run.safety_events || []).length
  return `<details class="trace" ${open ? 'open' : ''}>
    <summary><span>Run trace · ${esc(run.mode.replace('_', ' '))} · ${t.calls} model calls${nSafety ? ` · ⛨ ${nSafety} safety event${nSafety > 1 ? 's' : ''}` : ''}</span>
      <span class="totals"><span>${t.input_tokens.toLocaleString()} input</span><span>${t.cached_tokens.toLocaleString()} cached</span><span>${t.output_tokens.toLocaleString()} output</span>${t.web_searches ? `<span>${t.web_searches} web searches</span>` : ''}<span>${usd(t.cost_usd)}</span><span>${t.seconds}s</span></span></summary>
    <ul class="trace-list">${steps}</ul>
  </details>`
}

function criticHTML(review) {
  if (!review) return ''
  const scores = review.scores || {}
  const sc = Object.entries(scores).map(([k, v]) => `<div class="score"><div class="lbl">${esc(k.replace('_', ' '))}</div><b>${v}/5</b><div class="bar"><i style="width:${(v / 5) * 100}%"></i></div></div>`).join('')
  const issues = (review.issues || []).length ? `<div class="small muted" style="margin-top:8px">Notes: ${review.issues.map(esc).join(' · ')}</div>` : ''
  return `<div class="card glass critic">
    <div class="row between wrap gap"><h3>Your stylist's second look</h3><span class="verdict ${esc(review.verdict)}">${review.verdict === 'approve' ? '✓ APPROVED' : '✎ NEEDS CHANGES'}</span></div>
    <p style="margin:6px 0 0">${esc(review.user_note)}</p>
    ${sc ? `<div class="scores">${sc}</div>` : ''}${issues}
  </div>`
}

// ------------------------------------------------------------------ TODAY
// ------------------------------------------------------------------ STYLIST VOICE + FEEDBACK
function noteCard(text, big = false) {
  if (!text) return ''
  return `<div class="stylist-note ${big ? 'big' : ''}"><p>${esc(text)}</p><span class="sig">— ${esc(state.stylist?.name || 'Your stylist')}</span></div>`
}

// what she left out because of something you told her, in her voice: "I left out X: you said …"
function becauseText(why) {
  const w = String(why || '').split(/;\s+(?=[^;]*:)/)[0].replace(/^[^:]*:\s*/, '')  // drop the ban's own label
  const said = (w.match(/\("([^"]+)"\)/) || [])[1]
  if (said) return `you said “${said.replace(/[.\s]+$/, '')}”`
  let m
  if ((m = w.match(/^Check-in: never (.+)/i))) return `you told me never ${m[1]}`
  if ((m = w.match(/^On your avoid list: (.+)/i))) return `${m[1]} is on your avoid list`
  if ((m = w.match(/^You told me: (.+)/i))) return `you told me “${m[1]}”`
  if ((m = w.match(/^Not for me: (.+)/i))) return `you passed on ${m[1]}`
  if ((m = w.match(/^House rule: "?(.+?)"?$/i))) return `your house rule says “${m[1]}”`
  return w ? `you told me: ${w}` : 'you ruled it out'
}

function listenedHTML(blocked) {
  const seen = new Set()
  const rows = (blocked || []).filter((b) => b?.piece && !seen.has(b.piece.toLowerCase()) && seen.add(b.piece.toLowerCase()))
  if (!rows.length) return ''
  const did = (b) => {
    // store products keep their brand's capitals; descriptive pieces read mid-sentence
    const w = b.what || '', x = /shop/.test(w) ? b.piece : b.piece.charAt(0).toLowerCase() + b.piece.slice(1)
    const swapFor = (w.match(/^replaced with your (.+?) for '/) || [])[1]
    return swapFor ? `I swapped your ${x} for your ${swapFor.charAt(0).toLowerCase() + swapFor.slice(1)}` : /replaced/.test(w) ? `I swapped out ${x}` : /shop/.test(w) ? `I passed on ${x}`
      : /taken out of/.test(w) ? `I left your ${x} out` : /hidden/.test(w) ? `I took ${x} off your saved picks` : `I left out ${x}`
  }
  const lines = rows.slice(0, 3).map((b) => `<p>${esc(did(b))}: ${esc(becauseText(b.why))}.</p>`)
  if (rows.length > 3) lines.push(`<p>…and ${rows.length - 3} more for the same reasons.</p>`)
  return `<div class="listened">${lines.join('')}<span class="sig">— ${esc(state.stylist?.name || 'Your stylist')}, listening</span></div>`
}

// what a saved note does from now on, in plain words (true to the code: every note is read by every styling agent
// and makes the next plan/picks fresh; a "Not for me" also becomes a rule checked in code, pictures included)
function savedLine(rating, note, newBans) {
  const who = stylistName()
  if (rating === 'love') return `✓ Saved${note ? ` with your note “${esc(note)}”` : ''}. ${esc(who)} reads it before every plan, pick and shop search, and brings you more like this. Your next run uses it.`
  if (newBans?.length) return `✓ Saved. New hard rule: never ${newBans.map(esc).join('; never ')}. It's checked in code on plans, picks, shop results and pictures, so it won't come back.`
  return `✓ Saved${note ? ` with your note “${esc(note)}”` : ''}. ${esc(who)} won't suggest this again (it's on your no list, checked on plans, picks, shop results and pictures).`
}

function fbHTML(kind, ids, label) {
  // a note she already left on this piece shows as saved when the page comes back
  const had = (state.profile?.feedback || []).filter((f) => f.kind === kind && f.label === label && f.rating !== 'note').pop()
  const on = (r) => had?.rating === r ? ' chosen' : ''
  return `<div class="fb" data-kind="${esc(kind)}" data-ids="${esc(JSON.stringify(ids))}" data-label="${esc(label)}">
    <button type="button" class="fb-btn${on('love')}" data-fb="love">♡ Love it</button><button type="button" class="fb-btn${on('no')}" data-fb="no">Not for me</button>
    <button type="button" class="fb-link" data-fbnote>+ note</button><input type="text" class="fb-note hidden" maxlength="160" placeholder="Why? (optional, then pick)" />
    ${had ? `<div class="fb-saved small">${savedLine(had.rating, had.note, [])}</div>` : ''}</div>`
}

async function sendFeedback(btn) {
  const box = btn.closest('.fb')
  const note = $('.fb-note', box).value.trim()
  try {
    const r = await postJSON('/api/feedback', {
      dataset: state.dataset, kind: box.dataset.kind, rating: btn.dataset.fb,
      item_ids: JSON.parse(box.dataset.ids || '[]'), label: box.dataset.label, note,
    })
    if (state.profile && r.feedback) state.profile.feedback = r.feedback
    $$('.fb-btn', box).forEach((b) => b.classList.toggle('chosen', b === btn))
    $('.fb-note', box).classList.add('hidden')
    if (!$('.fb-saved', box)) box.insertAdjacentHTML('beforeend', '<div class="fb-saved small"></div>')
    $('.fb-saved', box).innerHTML = savedLine(btn.dataset.fb, note, r.new_bans)
    toast('Saved.')
    await loadStylist()
    maybeRefreshRead()
  } catch (e) {
    toast(`Couldn't save that: ${e.message}`)
  }
}

document.addEventListener('click', (e) => {
  const fb = e.target.closest('[data-fb]')
  if (fb) return sendFeedback(fb)
  const nb = e.target.closest('[data-fbnote]')
  if (nb) { const inp = $('.fb-note', nb.closest('.fb')); inp.classList.toggle('hidden'); inp.focus() }
})

// ---- "Tell Margaux-Sloan": feedback on the styling or the recommendations as a whole
const TELL_TAGS = ['Too business', 'Too casual', 'Too safe', 'Too bold', 'Not my colors', 'Too masculine', 'Not enough accessories', 'Too much', 'Love this direction', 'More like this']
const POSITIVE = new Set(['Love this direction', 'More like this'])

function stylistName() { return state.stylist?.name || 'your stylist' }

function tellHTML(kind, label) {
  return `<div class="card tell" data-tell="${esc(kind)}" data-label="${esc(label)}">
    <div class="kicker-sm">Tell ${esc(stylistName())}</div>
    <p class="muted small" style="margin:2px 0 8px">How did ${kind === 'styling' ? 'today’s styling' : 'these picks'} land? Tap what fits and add anything in your own words. I read every note before I style you again.</p>
    <div class="chips tell-tags">${TELL_TAGS.map((t) => `<button type="button" class="chip" data-tag="${esc(t)}">${esc(t)}</button>`).join('')}</div>
    <textarea class="tell-text" maxlength="300" placeholder="e.g. Loafers look like men's shoes on me. More weekend and going-out looks, please."></textarea>
    <div class="row gap" style="margin-top:6px"><button type="button" class="btn small primary" data-tell-send>Send to ${esc(stylistName())}</button></div>
  </div>`
}

async function sendTell(box) {
  const tags = $$('.tell-tags .chip.on', box).map((b) => b.dataset.tag)
  const text = $('.tell-text', box).value.trim()
  if (!tags.length && !text) return toast('Tap a tag or write a note first.')
  const rating = tags.length && tags.every((t) => POSITIVE.has(t)) ? 'love' : 'note'
  try {
    const r = await postJSON('/api/feedback', { dataset: state.dataset, kind: box.dataset.tell === 'styling' ? 'styling' : 'recommendation',
      rating, item_ids: [], label: `${box.dataset.label}${tags.length ? ': ' + tags.join(', ') : ''}`, note: text })
    if (state.profile && r.feedback) state.profile.feedback = r.feedback
    const rule = r.new_bans?.length ? ` New hard rule: never ${r.new_bans.map(esc).join('; never ')}, checked in code on plans, picks, shop results and pictures.` : ''
    box.innerHTML = `<div class="kicker-sm">Tell ${esc(stylistName())}</div><p class="small" style="margin:4px 0 0;color:var(--green)">✓ Saved. ${rating === 'love' ? 'More of this coming.' : 'I’ll style around that from now on.'} I read it before every plan, pick and shop search.${rule} Hit <b>↻ Fresh take</b> to see it applied.</p>`
    await loadStylist()
    maybeRefreshRead()
  } catch (e) { toast(`Couldn't send: ${e.message}`) }
}

// ---- check-in: the stylist asks you questions (starter questions are free; follow-ups come with her read)
function askHTML(qs, compact = false) {
  if (!qs?.length) return ''
  return `<div class="ask ${compact ? 'compact' : ''}">${qs.map((qq) => `
    <div class="ask-q" data-qid="${esc(qq.id)}" data-q="${esc(qq.q)}" data-multi="${qq.multi ? 1 : 0}">
      <b>${esc(qq.q)}</b>${qq.multi ? ' <span class="muted small">(pick any)</span>' : ''}
      <div class="chips">${qq.options.map((o) => `<button type="button" class="chip" data-opt="${esc(o)}">${esc(o)}</button>`).join('')}</div>
      <input type="text" class="ask-other" maxlength="200" placeholder="Or in your own words…" />
    </div>`).join('')}
    <div class="row gap"><button type="button" class="btn small primary" data-ask-send>Send answers</button></div></div>`
}

async function sendAnswers(box) {
  const answers = $$('.ask-q', box).map((el) => {
    const picks = $$('.chip.on', el).map((b) => b.dataset.opt)
    const other = $('.ask-other', el).value.trim()
    return { id: el.dataset.qid, q: el.dataset.q, a: [...picks, other].filter(Boolean).join('; ') }
  }).filter((a) => a.a)
  if (!answers.length) return toast('Pick an answer first.')
  try {
    await postJSON('/api/stylist/answers', { dataset: state.dataset, answers })
    toast(`${stylistName()}: thank you, that helps.`)
    state.profile = await api('/api/profile?' + q())
    await loadStylist()
    maybeRefreshRead()
  } catch (e) { toast(`Couldn't save: ${e.message}`) }
}

function renderAskBanner() {
  const el = $('#stylist-ask')
  if (!el) return
  const qs = (state.stylist?.questions || []).slice(0, 2)
  if (!qs.length || state.askHidden) { el.innerHTML = ''; return }
  el.innerHTML = `<div class="card glass checkin ask-card"><div class="row between"><div class="kicker-sm">${esc(stylistName())} has a question</div><button type="button" class="x" data-ask-hide title="Later">✕</button></div>
    <p class="muted small" style="margin:2px 0 8px">The more I know, the more every look sounds like you.</p>${askHTML(qs, true)}</div>`
}

document.addEventListener('click', (e) => {
  const tag = e.target.closest('.tell-tags .chip')
  if (tag) return tag.classList.toggle('on')
  const send = e.target.closest('[data-tell-send]')
  if (send) return sendTell(send.closest('.tell'))
  const opt = e.target.closest('.ask-q .chip')
  if (opt) {
    const qel = opt.closest('.ask-q')
    if (qel.dataset.multi !== '1') $$('.chip', qel).forEach((b) => b !== opt && b.classList.remove('on'))
    return opt.classList.toggle('on')
  }
  const as = e.target.closest('[data-ask-send]')
  if (as) return sendAnswers(as.closest('.ask'))
  if (e.target.closest('[data-ask-hide]')) { state.askHidden = true; renderAskBanner() }
})

const ROLES = ['Foundation', 'Current season', 'Accent']

// ---- the five setup steps on Me: progress strip + the wardrobe step
const STEPS = [['colors', 'Face & colors'], ['body', 'Body'], ['style', 'Style'], ['closet', 'Wardrobe'], ['week', 'Week']]

function stepDone(key) {
  const p = state.profile || {}
  return {
    colors: !!p.color_season?.season,
    body: !!(p.body_photo_estimate || (state.dataset === 'user' && (state.photo?.has_photo || Object.values(p.measurements_in || {}).some((v) => +v > 0)))),
    style: !!(p.archetype?.primary || p.aesthetic),
    closet: (state.closet || []).length > 0,
    week: !!p.calendar_url,
  }[key]
}

function renderSetup() {
  const nav = $('#setup-steps')
  if (!nav) return
  nav.innerHTML = STEPS.map(([k, label], i) => `<a href="#step-${k}" class="${stepDone(k) ? 'done' : ''}" data-step="${k}"><span>${stepDone(k) ? '✓' : i + 1}</span>${esc(label)}</a>`).join('')
  $$('[data-done]').forEach((el) => {
    // the sample's sizes are practice numbers, not a real body step
    const sample = el.dataset.done === 'body' && state.dataset === 'sample' && !stepDone('body')
    el.textContent = stepDone(el.dataset.done) ? '✓ Done' : sample ? 'Sample sizes' : ''
    el.classList.toggle('sample', sample)
  })
  const n = (state.closet || []).length
  const c = $('#setup-closet')
  if (c) c.innerHTML = `<div class="row between wrap gap"><div><b>${n ? `${n} piece${n === 1 ? '' : 's'} in your closet` : 'Your closet is empty'}</b>
    <p class="muted small" style="margin:2px 0 0">I style only from what's here.</p></div>
    <button class="btn primary small" type="button" data-goto-closet>${n ? 'Open my closet' : 'Add my clothes'} →</button></div>`
}

document.addEventListener('click', (e) => {
  const a = e.target.closest('[data-step]')
  if (a) { e.preventDefault(); $(`#step-${a.dataset.step}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }
  if (e.target.closest('[data-goto-closet]')) showTab('closet')
})
document.addEventListener('ct:closet-rendered', () => renderSetup())

let rulesTimer = null
document.addEventListener('input', (e) => {
  if (e.target.id !== 'house-rules') return
  state.rulesDraft = e.target.value
  $('#rules-saved').textContent = 'saving…'
  clearTimeout(rulesTimer)
  rulesTimer = setTimeout(saveRules, 700)
})

async function saveRules() {
  if (state.rulesDraft == null) return
  const rules = state.rulesDraft.split('\n').map((x) => x.trim()).filter(Boolean)
  try {
    const r = await postJSON('/api/stylist/rules', { dataset: state.dataset, rules })
    state.profile.stylist = { ...(state.profile.stylist || {}), extra_rules: r.rules }
    state.rulesDraft = null
    const el = $('#rules-saved')
    if (el) el.textContent = '✓ saved'
    try {
      state.stylist = await api(`/api/stylist?${q()}`)
      const fx = $('#rules-effect')
      if (fx) fx.innerHTML = rulesEffectHTML(state.stylist.effects?.rules)
    } catch { /* the rule is saved; the explanation catches up on the next load */ }
  } catch (e) {
    const el = $('#rules-saved')
    if (el) el.textContent = `not saved: ${e.message}`
  }
}

// what a note or house rule does from now on, in plain words (from outfit_rules.explain: true to the code)
function noteEffect(f, rules) {
  const clean = (r) => esc(String(r).replace(/^(next piece:\s*)?(push:\s*)?/i, ''))
  if (rules?.length) return `→ Hard rule, checked in code on plans, picks, shop and pictures: never ${rules.map(clean).join('; never ')}`
  if (f.rating === 'love') return '→ Read before every plan, pick and shop search: more like this'
  return '→ Read before every plan, pick and shop search'
}

function rulesEffectHTML(rules) {
  return (rules || []).map((r) => `<li><span class="fb-rating love">✓</span><span><b>${esc(r.rule)}</b>
    <span class="became">${r.became.length ? `→ Checked in code: ${r.became.map(esc).join('; ')}` : '→ Read by every styling agent before each plan, pick and shop search (not a rule I can check in code)'}</span></span></li>`).join('')
}

// the goal picture is drawn once per goal (image model, about $0.04)
let drawingGoal = false
async function drawGoal() {
  const g = state.stylist?.read?.goal
  if (!g?.look || g.image || drawingGoal) return
  drawingGoal = true
  try {
    const r = await postJSON('/api/stylist/goal', { dataset: state.dataset })
    updateMeter(r.run)
    await loadStylist()
  } catch (e) {
    const el = $('#goal-img')
    if (el) el.innerHTML = `<p class="small muted">No picture: ${esc(e.message)}</p>`
  } finally { drawingGoal = false }
}

async function loadStylist() {
  try { state.stylist = await api(`/api/stylist?${q()}`) } catch { state.stylist = null }
  if (state.stylist) state.blend = [...state.stylist.blend]
  if (state.stylist) $$('.stylist-note .sig').forEach((e) => { e.textContent = `— ${state.stylist.name}` })
  renderStylistCard()
  renderSetup()
  drawGoal()
  renderAskBanner()
}

// The stylist rewrites its read on you every few reactions (one small model call, ~$0.003)
async function maybeRefreshRead() {
  const st = state.stylist
  if (!st || st.learned.notes < st.reflect_every) return
  if (st.learned.notes - (st.read?.n_feedback || 0) < st.reflect_every) return
  await refreshRead(true)
}

async function refreshRead(quiet = false) {
  const btn = $('#read-btn')
  if (btn) { btn.disabled = true; btn.textContent = 'Thinking about your style…' }
  try {
    const r = await postJSON('/api/stylist/read', { dataset: state.dataset })
    updateMeter(r.run)
    state.profile = await api('/api/profile?' + q())
    await loadStylist()
    toast(quiet ? 'Your stylist updated its read on you.' : 'Read updated.')
  } catch (e) {
    if (!quiet) toast(`Couldn't update: ${e.message}`)
    if (btn) { btn.disabled = false; btn.textContent = '↻ Update my read' }
  }
}

async function saveBlend(list = state.blend) {
  if (!list.length) return toast('Pick at least one archetype.')
  try {
    await postJSON('/api/stylist/blend', { dataset: state.dataset, primary: list[0], secondary: list[1] || '', third: list[2] || '' })
    state.profile = await api('/api/profile?' + q())
    renderColorStyle()
    await loadStylist()
    toast(`Your blend: ${list.join(' + ')}`)
    refreshRead(true)
  } catch (e) { toast(`Couldn't save: ${e.message}`) }
}

// ---- aesthetic board: show Margaux-Sloan what you're going for
function boardHTML(st) {
  const b = st.aesthetic
  const img = (f) => `/api/aesthetic/img/${encodeURIComponent(f)}?${q()}`
  return `<div class="board-box">
    <div class="row between wrap gap"><div><div class="eyebrow" style="color:var(--gold-deep)">Show ${esc(st.name)} your aesthetic</div>
      <p class="muted small" style="margin:2px 0 0">A Pinterest board, a blog, or your own screenshots. I'll dress you toward it, in your colors.</p></div>
      ${b ? '<button type="button" class="btn ghost small" data-board-clear>Clear board</button>' : ''}</div>
    <div class="row gap wrap" style="margin-top:8px">
      <input type="url" id="board-url" placeholder="pinterest.com/you/board · a blog or lookbook page · instagram.com/…" style="flex:1;min-width:220px" />
      <button type="button" class="btn primary small" data-board-link>Show her</button>
      <label class="btn ghost small">Upload pictures<input type="file" id="board-files" accept="image/*" multiple hidden /></label>
    </div>
    <div class="muted small info-line" style="margin:4px 0 0">Up to 6 pictures (about $0.01). <details class="info"><summary title="Instagram">ⓘ</summary><span>Instagram hides pages from apps, so for an influencer, screenshot 3–6 posts and upload them.</span></details></div>
    <div id="board-status"></div>
    ${b ? `<div class="board-pics">${(b.pictures || []).slice().reverse().map((p) => `<img src="${img(p.file)}" alt="inspiration from ${esc(p.source)}" loading="lazy" />`).join('')}</div>
      <p class="read-sig">${esc(b.summary)}</p>
      <div class="chips small">${(b.vibe_words || []).map((w) => `<span class="chip static">${esc(w)}</span>`).join('')}
        ${(b.colors || []).map((c) => `<span class="chip static"><span class="swatch" style="background:${esc(c.hex)}"></span>${esc(c.name)}</span>`).join('')}</div>
      <details class="more"><summary>What I see in your board</summary><div class="board-cols small">
        <div><b>Board archetypes</b><ul>${(b.archetypes || []).map((a) => `<li><b>${esc(a.name)} ${a.weight}%</b> · ${esc(a.why)}</li>`).join('')}</ul>
          ${(b.archetypes || []).length && (b.archetypes || []).map((a) => a.name).join('|') !== st.blend.join('|') ? `<button type="button" class="btn small" data-board-blend>Use as my blend</button>` : ''}</div>
        <div><b>Signature pieces</b><ul>${(b.signature_pieces || []).map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div>
        <div><b>How it's styled</b><ul>${(b.styling_moves || []).map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div>
      </div>
      ${b.season_note ? `<p class="small"><b>In your colors:</b> ${esc(b.season_note)}</p>` : ''}</details>
      ${noteCard(b.user_note)}` : ''}
  </div>`
}

async function sendBoard(run, label) {
  const status = $('#board-status')
  const stop = working(status, label, ['Getting the pictures', `${stylistName()} is studying your board`])
  try {
    const r = await run()
    updateMeter(r.run)
    stop()
    status.innerHTML = ''
    state.profile = await api('/api/profile?' + q())
    await loadStylist()
    toast(`${stylistName()}: got it. I see ${r.result.archetypes.map((a) => a.name).join(' + ')}.`)
    refreshRead(true)
  } catch (e) {
    stop()
    showError(status, e)
  }
}

document.addEventListener('click', async (e) => {
  if (e.target.closest('[data-board-link]')) {
    const url = $('#board-url').value.trim()
    if (!url) return toast('Paste a link first.')
    return sendBoard(() => postJSON('/api/aesthetic/link', { dataset: state.dataset, url }), 'Reading that page…')
  }
  if (e.target.closest('[data-board-blend]')) return saveBlend(state.stylist.aesthetic.archetypes.map((a) => a.name))
  if (e.target.closest('[data-board-clear]')) {
    if (!confirm('Clear your aesthetic board? Margaux-Sloan forgets these pictures.')) return
    await api(`/api/aesthetic?${q()}`, { method: 'DELETE' })
    state.profile = await api('/api/profile?' + q())
    loadStylist()
  }
})
document.addEventListener('change', (e) => {
  if (e.target.id !== 'board-files' || !e.target.files.length) return
  const fd = new FormData()
  ;[...e.target.files].slice(0, 6).forEach((f) => fd.append('files', f))
  fd.append('dataset', state.dataset)
  sendBoard(() => api('/api/aesthetic/photos', { method: 'POST', body: fd }), 'Studying your pictures…')
})

function quizHTML() {
  const m = state.styleMeta
  if (!m) return ''
  const a = state.profile?.archetype || {}
  const picked = a.quiz || []
  return `<details class="arch-quiz" ${a.primary ? '' : 'open'}><summary class="small"><b>Not sure? Take the quiz</b> and I'll read it with your closet and reactions</summary>
    <form id="quiz-form" class="quiz">${m.quiz.map((qq, i) => `<fieldset><legend>${esc(qq.q)}</legend>${Object.entries(qq.options).map(([arch, label]) =>
      `<label><input type="radio" name="q${i}" value="${esc(arch)}" ${picked[i] === arch ? 'checked' : ''}/> ${esc(label)}</label>`).join('')}</fieldset>`).join('')}</form>
    <button class="btn primary small" id="analyze-style-btn" type="button">✦ Find my archetypes</button>
    <div id="arch-status"></div>
    ${a.source === 'analyst' && a.evidence?.length ? `<div class="small" style="margin-top:8px"><b>Why I chose ${esc([a.primary, a.secondary, a.third].filter(Boolean).join(' + '))}:</b><ul>${a.evidence.slice(0, 4).map((e) => `<li>${esc(e)}</li>`).join('')}</ul>
      ${a.pieces_to_add?.length ? `<b>Pieces to add:</b> ${esc(a.pieces_to_add.join(' · '))}` : ''}</div>` : ''}
  </details>`
}

function renderStylistCard() {
  const el = $('#stylist-card')
  if (!el) return
  const st = state.stylist
  if (!st) { el.innerHTML = '<h3>Your stylist</h3><p class="muted small">Your stylist is not available on this server yet.</p>'; return }
  const blend = state.blend || []
  const saved = st.blend.join('|') === blend.join('|')
  const k = st.learned
  const read = st.read
  const extra = state.profile?.stylist?.extra_rules || []
  const all = state.profile?.feedback || []
  const fb = all.map((f, i) => ({ ...f, i })).slice(-10).reverse()
  const became = new Map((st.effects?.notes || []).map((n) => [n.i, n.became]))
  const sugg = read?.suggested_blend || []
  const newBlend = sugg.length && sugg.join('|') !== st.blend.join('|')
  el.innerHTML = `
    <div class="row between wrap gap"><div><div class="eyebrow" style="color:var(--gold-deep)">Your stylist</div><h3 style="font-size:24px;margin:2px 0 4px">${esc(st.name)}</h3>
      <p class="muted small" style="margin:0">${esc(st.personality)}</p></div>
      </div>
    <div class="know">
      <div class="row between small"><b>${esc(k.stage)}</b><span class="muted">${k.notes} reaction${k.notes === 1 ? '' : 's'} · ${k.loves} ♡ · ${k.nos} ✕</span></div>
      <div class="know-bar"><span style="width:${Math.max(4, k.level)}%"></span></div>
    </div>
    ${boardHTML(st)}
    <div class="eyebrow" style="color:var(--muted);margin-top:14px">Your style archetypes</div>
    <div class="muted small info-line" style="margin:2px 0 0">Tap two or three, in order. <details class="info"><summary title="How a blend works">ⓘ</summary><span>Most people are a blend: your <b>foundation</b> (who you are long-term), your <b>current season</b>, and an optional <b>accent</b>. Not sure? Take the 3-question quiz below.</span></details></div>
    <div class="personas archetypes">${Object.entries(st.archetypes).map(([name, a]) => {
      const i = blend.indexOf(name)
      return `<button type="button" class="persona arch-tile ${i >= 0 ? 'selected' : ''}" data-arch="${esc(name)}">
        <img class="arch-img" src="/archetypes/${esc(name.toLowerCase().replace(/ /g, '-'))}.jpg?v=2" alt="${esc(name)} style: ${esc(a.pieces)}" loading="lazy" />
        <span class="p-name">${esc(name)}</span><span class="p-tag">${esc(a.also)}</span>
        <span class="p-phil">${esc(a.pieces)}</span><span class="p-phil"><b>Colors:</b> ${esc(a.colors)}</span>
        ${i >= 0 ? `<span class="p-check">${i + 1} · ${ROLES[i]}</span>` : ''}
      </button>`
    }).join('')}</div>
    ${quizHTML()}
    <div class="row gap wrap small" style="margin-bottom:14px"><b>${blend.length ? esc(blend.map((b, i) => `${b} (${ROLES[i].toLowerCase()})`).join(' + ')) : 'No blend yet'}</b>
      ${saved ? (blend.length ? '<span class="tag">saved</span>' : '') : '<button class="btn primary small" id="save-blend" type="button">Save my blend</button>'}</div>
    <div class="read-box">
      <div class="row between wrap gap"><div class="eyebrow" style="color:var(--gold-deep)">${esc(st.name)}'s read & strategy</div>
        <button class="btn ghost small" id="read-btn" type="button" ${k.notes || blend.length || st.aesthetic ? '' : 'disabled'}>↻ Update my read</button></div>
      ${read ? `<p class="read-sig">${esc(read.signature)}</p>
        ${read.goal?.look ? `<div class="goal">
          <div class="goal-img" id="goal-img">${read.goal.image ? `<img src="/api/aesthetic/img/${encodeURIComponent(read.goal.image)}?${q()}" alt="The goal look: ${esc(read.goal.title || '')}" />` : `<div class="status"><div class="spinner sm"></div><span class="small muted">Drawing the goal…</span></div>`}</div>
          <div><div class="kicker-sm">The goal I'm dressing you toward</div><h4 style="margin:2px 0 6px">${esc(read.goal.title || '')}</h4><p class="small">${esc(read.goal.look)}</p>
            ${(read.strategy || []).length ? `<div class="kicker-sm" style="margin-top:10px">My strategy</div><ol class="strategy small">${read.strategy.map((m) => `<li><span class="tag move-${esc(m.move.split(' ')[0].toLowerCase())}">${esc(m.move)}</span> ${esc(m.text)}</li>`).join('')}</ol>` : ''}</div>
        </div>` : ''}
        <details class="small"><summary>What I've noticed about you</summary><ul>${read.bullets.map((b) => `<li>${esc(b)}</li>`).join('')}</ul></details>
        <div class="muted small">Updated ${esc(read.at || '')} · refreshes every ${st.reflect_every} reactions.</div>
        ${newBlend ? `<div class="small" style="margin-top:8px">Your reactions point to <b>${esc(sugg.join(' + '))}</b>. ${esc(read.blend_why || '')} <button class="btn small" id="use-sugg" type="button">Use this blend</button></div>` : ''}`
        : `<p class="muted small">${k.notes || blend.length || st.aesthetic ? 'Tap Update and I\'ll tell you what I see, show you the goal look, and lay out my strategy.' : 'Show me your inspiration or take the quiz above, and I\'ll tell you what I see, show you the goal look, and lay out my strategy.'}</p>`}
    </div>
    <div class="checkin-box">
      <div class="eyebrow" style="color:var(--gold-deep)">Check-in with ${esc(st.name)}</div>
      ${st.questions.length ? askHTML(st.questions) : `<p class="muted small">No questions right now. I'll ask more as I learn from your reactions.</p>`}
      ${st.answers.length ? `<details class="small"><summary>What you've told me (${st.answers.length})</summary><ul>${st.answers.slice().reverse().map((a) => `<li><b>${esc(a.q)}</b> ${esc(a.a)}</li>`).join('')}</ul></details>` : ''}
    </div>
    <div class="stylist-bottom">
      <div><label class="eyebrow" for="house-rules" style="color:var(--muted)">Your own house rules</label> <span class="small muted" id="rules-saved">${extra.length ? '✓ saved' : ''}</span>
        <textarea id="house-rules" placeholder="One per line, e.g.&#10;Always a pop of pink&#10;Never pair black with navy">${esc(state.rulesDraft ?? extra.join('\n'))}</textarea>
        <div class="muted small">Saves as you type; these win over everything.</div>
        <ul class="learned rules-effect" id="rules-effect">${rulesEffectHTML(st.effects?.rules)}</ul></div>
      <div><div class="eyebrow" style="color:var(--muted)">What you've told me</div>
        ${fb.length ? `<ul class="learned">${fb.map((f) => `<li><span class="fb-rating ${f.rating === 'love' ? 'love' : 'no'}">${f.rating === 'love' ? '♡' : f.rating === 'note' ? '✎' : '✕'}</span><span><b>${esc(f.label || f.kind)}</b>${f.note ? ` · <i>${esc(f.note)}</i>` : ''}
          <span class="became">${noteEffect(f, became.get(f.i))}</span></span><button type="button" class="x" data-unlearn="${f.i}" title="Forget this">✕</button></li>`).join('')}</ul>`
          : '<p class="muted small">Nothing yet. Tap ♡ Love it or Not for me on outfits, picks and closet items.</p>'}
        ${k.loved_items.length ? `<div class="small" style="margin-top:6px"><b>You keep loving:</b> ${esc(k.loved_items.join(' · '))}</div>` : ''}
      </div>
    </div>`
  $$('[data-arch]', el).forEach((b) => b.addEventListener('click', () => {
    const n = b.dataset.arch
    const list = state.blend || []
    state.blend = list.includes(n) ? list.filter((x) => x !== n) : list.length < 3 ? [...list, n] : list
    if (!list.includes(n) && list.length >= 3) toast('Three at most: tap one to remove it first.')
    renderStylistCard()
  }))
  $('#save-blend', el)?.addEventListener('click', () => saveBlend())
  $('#use-sugg', el)?.addEventListener('click', () => saveBlend(sugg))
  $('#read-btn', el)?.addEventListener('click', () => refreshRead(false))
  $$('[data-unlearn]', el).forEach((b) => b.addEventListener('click', async () => {
    const p = structuredClone(state.profile)
    p.feedback = (p.feedback || []).filter((_f, i) => i !== +b.dataset.unlearn)  // only this note (several share a date)
    try {
      await api(`/api/profile?${q()}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(p) })
      state.profile = p
      await loadStylist()
      toast('Forgotten.')
    } catch (e) { toast(`Couldn't update: ${e.message}`) }
  }))
}

async function loadDay() {
  const day = $('#day').value
  try {
    const d = await api(`/api/day?${q({ day })}`)
    const w = d.weather
    const hourly = (w.hourly || []).map((h) => `<div>${esc(h.hour)}<b>${h.temp_f}°</b><span class="muted">${h.rain_pct ?? 0}%</span></div>`).join('')
    $('#weather-card').innerHTML = `
      <div class="row between"><h3>Weather</h3><span class="tag pink">${esc(d.season)}</span></div>
      <div class="weather-main"><div class="temp">${w.high_f}°<small> / ${w.low_f}°F</small></div>
      <div><div style="text-transform:capitalize;font-weight:600">${esc(w.summary)}</div>
      <div class="muted small">${w.rain_chance_pct != null ? `Rain ${w.rain_chance_pct}%` : 'Rain n/a'}${w.wind_mph != null ? ` · Wind ${w.wind_mph} mph` : ''}</div>
      <div class="muted small">${esc(w.source)}</div></div></div>
      ${hourly ? `<div class="hourly">${hourly}</div>` : ''}`
    const ev = d.events.map((e) => `<li><span class="time">${esc(e.start)}–${esc(e.end)}</span><div><b>${esc(e.title)}</b><div class="where">${esc(e.location)}</div></div></li>`).join('')
    $('#calendar-card').innerHTML = `<div class="row between"><h3>Calendar</h3><span class="tag">${esc((d.calendar_source || '').split(' (')[0] || 'calendar')}</span></div>
      ${ev ? `<ul class="timeline">${ev}</ul>` : '<div class="empty small">No events this day. Upload your calendar on the Me tab.</div>'}`
  } catch (e) {
    $('#weather-card').innerHTML = `<div class="muted">Couldn't load the day: ${esc(e.message)}</div>`
    $('#calendar-card').innerHTML = ''
  }
}

async function planDay(fresh = false) {
  const btn = $('#plan-btn')
  btn.disabled = true
  $('#plan-out').innerHTML = ''
  const stop = working($('#plan-status'), 'Planning your day…', ['Reading your calendar & weather', 'Building outfits around your archetypes', 'Double-checking every look', 'Revising if needed'])
  try {
    const r = await postJSON('/api/plan', { dataset: state.dataset, day: $('#day').value, fresh: fresh === true })
    $('#plan-status').innerHTML = ''
    renderPlan(r.result, r.run)
    updateMeter(r.run)
  } catch (e) {
    showError($('#plan-status'), e)
  } finally {
    stop()
    btn.disabled = false
  }
}

function renderPlan(res, run) {
  const p = res.plan
  state.lastPlan = p
  state.lastPlanRes = res
  state.lastPlanRun = run
  const blocks = p.blocks.map((b, i) => `
    <div class="card glass block" data-bi="${i}">
      <div class="when">${esc(b.start)} – ${esc(b.end)}</div>
      <h4>${esc(b.label)}</h4>
      <div>${b.events.map((e) => `<span class="tag">${esc(e)}</span>`).join('')}</div>
      <div class="thumbs">${b.items.map((it) => `<div class="thumb"><div class="img">${itemImg(it)}</div>${esc(it.name)}</div>`).join('')}</div>
      <p class="why">${esc(b.why)}</p>
      ${noteCard(b.stylist_note)}
      ${b.change_note ? `<div class="change">↺ ${esc(b.change_note)}</div>` : ''}
      <div class="row gap" style="margin-top:12px"><button class="btn small primary" data-tryblock="${i}">Try it on me</button><span class="tag pink">${esc(b.scene)}</span>${b.chosen ? `<span class="tag">your pick: ${esc(b.chosen)}</span>` : ''}</div>
      ${fbHTML('outfit', b.item_ids || [], `${b.label}${b.chosen ? ` (${b.chosen})` : ''}`)}
      ${(b.alternates || []).length ? `<div class="alts"><div class="kicker-sm">Or wear</div>${b.alternates.map((a, k) => `
        <div class="alt"><div class="alt-head"><b>${esc(a.title)}</b><button class="btn small ghost" type="button" data-choose="${i}:${k}">Wear this instead</button></div>
          <div class="thumbs sm">${(a.items || []).map((it) => `<div class="thumb"><div class="img">${itemImg(it)}</div>${esc(it.name)}</div>`).join('')}</div>
          <p class="why small">${esc(a.why)}</p></div>`).join('')}</div>` : ''}
    </div>`).join('')
  // why this pick (and not a new one): the stylist keeps it until something real changes
  const why = res.kept ? 'Same closet, calendar, weather and feedback as before, so this is still your stylist’s pick.'
    : res.changed?.length ? `Re-planned because ${res.changed.join(' and ')} changed.`
    : res.fresh ? 'A fresh take, as you asked.' : ''
  $('#plan-out').innerHTML = `
    ${why ? `<div class="kept-note small"><span>${esc(why)}</span><button class="btn small ghost" type="button" data-fresh>↻ Fresh take</button></div>` : ''}
    <div class="plan-head"><h3>${esc(p.headline)}</h3><p class="muted" style="margin:4px 0 0">${esc(p.weather_note)}</p></div>
    ${noteCard(p.stylist_take, true)}
    ${listenedHTML(res.blocked)}
    <div class="blocks">${blocks}</div>
    ${tellHTML('styling', `Styling for ${p.day || 'the day'}`)}
    ${criticHTML(res.review)}
    ${run ? traceHTML(run) : ''}`
  $$('[data-tryblock]').forEach((btn) => btn.addEventListener('click', () => {
    const b = p.blocks[+btn.dataset.tryblock]
    state.outfit = [...b.items]
    state.zones = {}
    openFitting(b.scene)
  }))
  $('#plan-out [data-fresh]')?.addEventListener('click', () => planDay(true))
  $$('[data-choose]').forEach((btn) => btn.addEventListener('click', async () => {
    const [bi, ai] = btn.dataset.choose.split(':').map(Number)
    btn.disabled = true
    try {
      const r = await postJSON('/api/outfit/choose', { dataset: state.dataset, day: $('#day').value, block_index: bi, alt_index: ai })
      p.blocks[bi] = r.block
      renderPlan(res, run)
      toast(`Switched to ${r.block.chosen}. Feedback and try-on now use this outfit.`)
      document.querySelector(`.block[data-bi="${bi}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    } catch (e) { btn.disabled = false; toast(`Couldn't switch: ${e.message}`) }
  }))
  document.dispatchEvent(new CustomEvent('ct:plan-rendered', { detail: { res, run } }))
}

// ------------------------------------------------------------------ CLOSET
async function loadCloset() {
  try {
    state.closet = await api(`/api/closet?${q()}`)
  } catch {
    state.closet = []
  }
  renderCloset()
}

// styled stand-in for window.confirm(): resolves true (ok) or false (cancel, Esc, click outside)
function askConfirm({ img = '', kicker = '', title, body = '', ok = 'OK', cancel = 'Cancel' }) {
  return new Promise((resolve) => {
    const wrap = document.createElement('div')
    wrap.className = 'ct-modal'
    wrap.innerHTML = `<div class="ct-modal-card" role="dialog" aria-modal="true" aria-label="${esc(title)}">
      ${img ? `<div class="ct-modal-img">${img}</div>` : ''}
      ${kicker ? `<div class="kicker-sm">${esc(kicker)}</div>` : ''}
      <h3>${esc(title)}</h3>${body ? `<p class="muted small">${esc(body)}</p>` : ''}
      <div class="ct-modal-actions"><button class="btn ghost" type="button" data-no>${esc(cancel)}</button><button class="btn primary danger-fill" type="button" data-yes>${esc(ok)}</button></div></div>`
    const done = (v) => { document.removeEventListener('keydown', onKey); wrap.classList.add('out'); setTimeout(() => wrap.remove(), 160); resolve(v) }
    const onKey = (e) => { if (e.key === 'Escape') done(false); if (e.key === 'Enter') done(true) }
    wrap.addEventListener('click', (e) => { if (e.target === wrap || e.target.closest('[data-no]')) done(false); if (e.target.closest('[data-yes]')) done(true) })
    document.addEventListener('keydown', onKey)
    document.body.appendChild(wrap)
    wrap.querySelector('[data-no]').focus()
  })
}

// closet sections (the server adds item.section): finer than category, like a store
const CLOSET_GROUPS = [['tops', 'Tops & blouses'], ['layers', 'Tanks & camis'], ['pants', 'Pants & shorts'], ['skirts', 'Skirts'], ['dresses', 'Dresses'],
  ['blazers', 'Blazers'], ['jackets', 'Jackets & coats'], ['activewear', 'Activewear'], ['swim', 'Swim'], ['shoes', 'Shoes'], ['accessories', 'Accessories']]
const sectionOf = (i) => i.section || i.category

// outline icons for the closet card's action row (24px grid, stroke = currentColor)
const ICONS = {
  love: '<path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z"/>',
  no: '<path d="M7 4h9l3 8v2h-6l1 5-2 1-5-8V4z"/><path d="M4 4v8"/>',
  edit: '<path d="M4 20l1-4L16 5l3 3L8 19l-4 1z"/><path d="M14 7l3 3"/>',
  try: '<path d="M12 6a2 2 0 1 1 2 2c-1 0-2 .7-2 2v1"/><path d="M12 11l-9 6h18z"/>',
  season: '<path d="M12 3v18M4.5 7.5l15 9M4.5 16.5l15-9"/><path d="M9.5 4.5L12 6l2.5-1.5M9.5 19.5L12 18l2.5 1.5"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M5 19l1.5-1.5M17.5 6.5L19 5"/>',
  remove: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
}
const icon = (k) => `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${ICONS[k]}</svg>`

function closetCard(it, fresh) {
  return `
    <div class="card item ${fresh.has(it.id) ? 'new-item' : ''} ${it.out_of_season ? 'stored' : ''}" data-id="${esc(it.id)}">
      <div class="img">${itemImg(it)}</div>
      <div class="name">${esc(it.name)}</div>
      ${it.out_of_season ? '<div><span class="tag stored-tag">out of season</span></div>' : ''}
      <div class="icon-row">
        <div class="fb fb-icons" data-kind="item" data-ids="${esc(JSON.stringify([it.id]))}" data-label="${esc(it.name)}">
          <button type="button" class="fb-btn ico" data-fb="love" title="Love it">${icon('love')}</button>
          <button type="button" class="fb-btn ico" data-fb="no" title="Not for me">${icon('no')}</button>
          <input type="text" class="fb-note hidden" maxlength="160" /></div>
        <span class="icon-gap"></span>
        <button class="ico" type="button" data-edit="${esc(it.id)}" title="Edit: name, type, color, photo, returned">${icon('edit')}</button>
        <button class="ico" type="button" data-try="${esc(it.id)}" title="Try it on">${icon('try')}</button>
        <button class="ico" type="button" data-season="${esc(it.id)}" title="${it.out_of_season ? 'Back in season: put it back into daily outfits' : 'Out of season: pack it away (kept, but left out of daily outfits)'}">${icon(it.out_of_season ? 'sun' : 'season')}</button>
        <button class="ico danger" type="button" data-del="${esc(it.id)}" title="Remove from closet">${icon('remove')}</button>
      </div>
    </div>`
}

function renderCloset(highlight) {
  const fresh = new Set([].concat(highlight || []))
  const cats = ['all', ...CLOSET_GROUPS.map(([c]) => c).filter((c) => state.closet.some((i) => sectionOf(i) === c))]
  const stored = state.closet.filter((i) => i.out_of_season).length
  if (stored) cats.push('out_of_season')
  const count = (c) => c === 'all' ? state.closet.length : c === 'out_of_season' ? stored : state.closet.filter((i) => sectionOf(i) === c).length
  const nameOf = (c) => c === 'all' ? 'All' : c === 'out_of_season' ? 'Out of season' : (CLOSET_GROUPS.find(([k]) => k === c) || [c, c])[1]
  $('#closet-filters').innerHTML = cats.map((c) => `<button class="chip ${state.filter === c ? 'active' : ''}" data-cat="${esc(c)}">${esc(nameOf(c))} (${count(c)})</button>`).join('')
  $$('#closet-filters .chip').forEach((b) => b.addEventListener('click', () => { state.filter = b.dataset.cat; renderCloset() }))
  if (!state.closet.length) {
    $('#closet-grid').innerHTML = `<div class="empty" style="grid-column:1/-1"><div class="big">✦</div><b>Your closet is empty.</b><p>Upload photos of your clothes and shoes above. Plain background, good light, one item per photo works best.</p></div>`
    return
  }
  const newestFirst = [...state.closet].reverse()
  let groups
  if (state.filter === 'all') {
    groups = CLOSET_GROUPS.map(([c, title]) => [title, newestFirst.filter((i) => sectionOf(i) === c && !i.out_of_season)])
    groups.push(['Out of season · packed away', newestFirst.filter((i) => i.out_of_season)])
    const known = new Set(CLOSET_GROUPS.map(([c]) => c))
    groups.push(['Other', newestFirst.filter((i) => !known.has(sectionOf(i)) && !i.out_of_season)])
  } else if (state.filter === 'out_of_season') {
    groups = [['Out of season · packed away', newestFirst.filter((i) => i.out_of_season)]]
  } else {
    groups = [[nameOf(state.filter), newestFirst.filter((i) => sectionOf(i) === state.filter)]]
  }
  $('#closet-grid').innerHTML = groups.filter(([, items]) => items.length).map(([title, items]) =>
    `<h3 class="closet-group">${esc(title)} <span class="muted small">${items.length}</span></h3>` + items.map((it) => closetCard(it, fresh)).join('')).join('')
  $('#closet-grid .new-item')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  $$('[data-try]').forEach((b) => b.addEventListener('click', () => {
    const it = state.closet.find((x) => x.id === b.dataset.try)
    addToOutfit(it)
    toast(`Added ${it.name} to the fitting room`)
  }))
  $$('[data-del]').forEach((b) => b.addEventListener('click', async () => {
    const it = state.closet.find((x) => x.id === b.dataset.del)
    if (!(await askConfirm({ img: itemImg(it), kicker: 'Remove from closet', title: it.name,
      body: 'It leaves your closet and the stylist stops picking it. If it’s just not the season, pack it away instead.',
      ok: 'Remove', cancel: 'Keep it' }))) return
    await api(`/api/closet/${encodeURIComponent(it.id)}?${q()}`, { method: 'DELETE' })
    document.querySelectorAll(`.followup[data-fid="${CSS.escape(it.id)}"]`).forEach((r) => r.remove())  // no fit question for a piece that's gone
    toast(`Removed ${it.name}`)
    await loadCloset()
  }))
  $$('[data-season]').forEach((b) => b.addEventListener('click', async () => {
    const it = state.closet.find((x) => x.id === b.dataset.season)
    try {
      const r = await postJSON(`/api/closet/${encodeURIComponent(it.id)}/edit`, { dataset: state.dataset, out_of_season: !it.out_of_season })
      Object.assign(it, r.item)
      toast(it.out_of_season ? `Packed away ${it.name}: it stays in your closet but won't be picked for outfits.` : `${it.name} is back in rotation.`)
      renderCloset(it.id)
    } catch (e) { toast(`Couldn't update: ${e.message}`) }
  }))
  document.dispatchEvent(new CustomEvent('ct:closet-rendered'))
}

// every add (camera, one photo, many photos) goes through the bulk flow in wardrobe_ui.js:
// per-photo progress, then the pieces appear in the closet with a size/fit card each
function addPhoto(ev, blob) {
  ev?.preventDefault()
  const files = blob ? [new File([blob], 'camera.jpg', { type: 'image/jpeg' })] : [...$('#photo-file').files]
  if (!files.length) return toast('Choose a photo first')
  window.ctBulkPhotos(files)
}

// ------------------------------------------------------------------ FITTING ROOM
function openFitting(scene) {
  showTab('fitting')
  if (scene) setScene(scene)
  renderOutfit()
}

function addToOutfit(item, zones) {
  const layerCats = { top: 'top', bottom: 'bottom', dress: 'dress', outerwear: 'outerwear', shoes: 'shoes', accessory: 'accessory', activewear: 'activewear' }
  const cat = layerCats[item.category] || item.category
  // a dress replaces top + bottom, and vice versa
  state.outfit = state.outfit.filter((o) => {
    if (o.id === item.id) return false
    if (cat === 'dress') return !['top', 'bottom', 'dress'].includes(o.category)
    if (cat === 'top' || cat === 'bottom') return o.category !== cat && o.category !== 'dress'
    if (cat === 'activewear') return !(o.category === 'activewear' && o.subtype === item.subtype)
    return o.category !== cat
  })
  state.outfit.push(item)
  if (zones) state.zones[item.id] = zones
  renderOutfit()
}

function saveOutfit() {
  try { localStorage.setItem(`ct-outfit-${state.dataset}`, JSON.stringify({ outfit: state.outfit, zones: state.zones })) } catch { /* storage off */ }
}

function restoreOutfit() {
  try {
    const saved = JSON.parse(localStorage.getItem(`ct-outfit-${state.dataset}`) || 'null')
    if (saved) { state.outfit = saved.outfit || []; state.zones = saved.zones || {} }
  } catch { /* storage off */ }
}

function renderOutfit() {
  saveOutfit()
  const list = $('#outfit-list')
  if (!state.outfit.length) {
    list.innerHTML = `<li class="muted small">Nothing on yet. Use "Try on" in your closet, a planned outfit, or a shop pick.</li>`
  } else {
    list.innerHTML = state.outfit.map((it, i) => `<li><span class="swatch" style="background:${esc(it.color_hex || it.colors?.[0]?.hex || '#ccc')}"></span><span>${esc(it.name)}${state.zones[it.id] ? ' <span class="tag pink">fit checked</span>' : ''}</span><button class="x" data-rm="${i}" title="Take off">✕</button></li>`).join('')
    $$('[data-rm]', list).forEach((b) => b.addEventListener('click', () => {
      state.outfit.splice(+b.dataset.rm, 1)
          renderOutfit()
    }))
  }
  const reports = state.outfit.filter((it) => state.zones[it.id])
  $('#fit-report').innerHTML = reports.length
    ? reports.map((it) => `<div class="fit-block"><b>${esc(it.name)}</b>${it.size_to_buy ? ` · size ${esc(it.size_to_buy)}` : ''}<div>${zoneChips(state.zones[it.id])}</div></div>`).join('')
    : `<p class="muted small">Your stylist's fit verdicts (snug, tight, loose, length) show here for shop picks it has checked against your measurements, and they're used when your photo is made.</p>`
}

function zoneChips(zones) {
  return (zones || []).map((z) => `<span class="zone-chip" title="${esc(z.note)}"><i style="background:${ZONE_COLORS[z.status] || '#888'}"></i>${esc(z.zone.replace('_', ' '))}: ${esc(z.status)}</span>`).join('')
}

function setScene(name) {
  state.scene = name
  $$('#scene-btns .chip').forEach((b) => b.classList.toggle('active', b.dataset.scene === name))
}

function setMove(name) {
  state.move = name
  $$('#move-btns .chip').forEach((b) => b.classList.toggle('active', b.dataset.move === name))
}

function initFittingControls() {
  $('#scene-btns').innerHTML = SCENES.map(([k, l]) => `<button class="chip ${k === state.scene ? 'active' : ''}" data-scene="${k}">${l}</button>`).join('')
  $('#move-btns').innerHTML = MOVES.map(([k, l]) => `<button class="chip ${k === state.move ? 'active' : ''}" data-move="${k}">${l}</button>`).join('')
  $$('#scene-btns .chip').forEach((b) => b.addEventListener('click', () => setScene(b.dataset.scene)))
  $$('#move-btns .chip').forEach((b) => b.addEventListener('click', () => setMove(b.dataset.move)))
  $('#snap-btn').addEventListener('click', () => {
    const img = [...document.querySelectorAll('#rm-view .rm-photo')].find((i) => !i.classList.contains('off') && !i.classList.contains('dim'))
    if (!img) return toast('Make a photo of this look first')
    const a = document.createElement('a')
    a.href = img.src
    a.download = `closet-twin-${state.scene}.jpg`
    a.click()
  })
  renderOutfit()
}

// ------------------------------------------------------------------ SHOP
const EXAMPLES = ['polished shoes for a coffee chat I can walk in', 'warm tall-length trousers', 'cozy sweater in a bold color', 'wide running shoes for spin class', 'a dress for a dinner out']

async function shop(ev) {
  ev?.preventDefault()
  const request = $('#shop-q').value.trim()
  if (!request) return toast('Tell me what you are looking for')
  const live = $('#live-web').checked
  $('#shop-out').innerHTML = ''
  const btn = $('#shop-form button[type=submit]')
  btn.disabled = true
  const stop = working($('#shop-status'), live ? 'Searching real stores in your size… (about a minute)' : 'Searching the practice catalog…', [live ? 'Searching real stores in your size' : 'Searching', 'Checking the fit against your measurements', 'Double-checking the picks'])
  try {
    const r = await postJSON('/api/shop', { dataset: state.dataset, request, live_web: live })
    $('#shop-status').innerHTML = ''
    renderShop(r.result, r.run)
    updateMeter(r.run)
  } catch (e) {
    showError($('#shop-status'), e)
  } finally {
    stop()
    btn.disabled = false
  }
}

function renderShop(res, run) {
  const picks = res.picks?.picks || []
  const fits = res.fits?.fits || []
  const fitFor = (p) => fits.find((f) => f.product_ref === p.product_id || f.product_ref === p.url) || null
  const cards = picks.map((p, i) => {
    const f = fitFor(p)
    return `<div class="card glass pick">
      <div class="pick-head"><span class="swatch" style="background:${esc(p.color_hex || '#ccc')}"></span>
        <div style="flex:1"><h4 style="font-size:17px">${esc(p.name)}</h4><div class="brand-line">${esc(p.brand)} · ${esc(p.color)}</div></div>
        <div class="price">${p.price_usd ? `$${Math.round(p.price_usd)}` : '<span class="small">Price at store</span>'}${p.url && !p.product_id && p.price_usd ? '<div class="small muted" style="font-weight:400">from search · check at store</div>' : ''}</div></div>
      <p class="why">${esc(p.why)}</p>
      ${noteCard(p.stylist_note)}
      ${(p.review_quotes || []).slice(0, 3).map((qt) => `<blockquote>“${esc(qt.replace(/^[\s"“”']+|[\s"“”']+$/g, ''))}”</blockquote>`).join('')}
      ${p.confirmed_sizes ? `<div class="size-ok">✓ Confirmed in your size: ${esc(p.confirmed_sizes)}</div>` : ''}
      <div class="small muted">${p.agree_count ? `${p.agree_count} review(s) agree · ` : ''}${esc(p.sizes_note)}</div>
      ${f ? `<div class="fitbox"><div class="row between"><b>Fit check · size ${esc(f.size_to_buy)}</b><span class="comfort ${esc(f.comfort_verdict)}">${esc(f.comfort_verdict)}</span></div>
        <div style="margin:6px 0">${zoneChips(f.zones)}</div><div class="small">${esc(f.summary)}</div>${f.skip ? '<div class="small" style="color:var(--bad)">Tailor suggests skipping this one.</div>' : ''}</div>` : ''}
      <div class="row gap wrap"><button class="btn small primary" data-trypick="${i}">Try it on me</button>${p.url ? `<a class="btn small ${p.store ? 'primary' : 'ghost'}" href="${esc(p.url)}" target="_blank" rel="noopener noreferrer">${p.store ? `View at ${esc(p.store)} ↗` : 'View product ↗'}</a><button class="btn small ghost" type="button" data-track="${esc(JSON.stringify({ url: p.url, name: p.name, store: p.store || p.brand || '', price: p.price_usd, image: p.image || '' }))}">☆ Track price</button>` : ''}</div>
      ${fbHTML('product', [p.product_id || p.url], p.name)}
    </div>`
  }).join('')
  $('#shop-out').innerHTML = `
    ${noteCard(res.picks?.stylist_take, true)}
    ${listenedHTML(res.blocked)}
    ${picks.length ? `<div class="picks">${cards}</div>` : `<div class="empty"><div class="big">✦</div><b>No picks I could stand behind this time.</b><p>${esc(res.picks?.note || res.review?.user_note || '')}</p>
      ${(res.searches || []).length ? `<p class="small muted">I searched: ${res.searches.filter(Boolean).map((x) => `“${esc(x)}”`).join(' · ')}</p>` : ''}
      <div class="row gap wrap" style="justify-content:center"><button class="btn small primary" type="button" data-shop-broader>Search more broadly</button>
        <button class="btn small ghost" type="button" data-shop-catalog>Try the practice catalog</button></div></div>`}
    ${res.picks?.note && picks.length ? `<p class="muted small">${esc(res.picks.note)}</p>` : ''}
    ${criticHTML(res.review)}
    ${run ? traceHTML(run) : ''}`
  $('[data-shop-broader]')?.addEventListener('click', () => {
    $('#shop-q').value = `${$('#shop-q').value.replace(/\s*\(any similar style.*$/, '')} (any similar style, any store that carries my size)`
    shop()
  })
  $('[data-shop-catalog]')?.addEventListener('click', () => { $('#live-web').checked = false; shop() })
  $$('[data-trypick]').forEach((b) => b.addEventListener('click', () => {
    const p = picks[+b.dataset.trypick]
    const f = fitFor(p)
    const item = {
      id: p.product_id || p.url, name: p.name, category: p.category, subtype: p.subtype, color_hex: p.color_hex,
      fit: p.fit || 'regular', length: p.length || 'regular', toe_box: p.toe_box || 'regular', heel_in: p.heel_in ?? 1,
      size_to_buy: f?.size_to_buy,
    }
    addToOutfit(item, f?.zones)
    const shoppingFor = { shoes: 'street', activewear: 'gym' }
    openFitting(state.scene === 'studio' ? shoppingFor[item.category] || 'studio' : null)
    toast(`Trying on ${p.name}. See the fit notes beside you.`)
  }))
}

// ------------------------------------------------------------------ ME
const FIELDS = [
  ['Basics', [['name', 'Name', 'text'], ['city', 'City', 'text'], ['lat', 'Latitude', 'number'], ['lon', 'Longitude', 'number'], ['budget_per_item_usd', 'Budget per item ($)', 'number']]],
  ['Measurements (inches)', [['measurements_in.height', 'Height', 'number'], ['measurements_in.shoulders', 'Shoulders', 'number'], ['measurements_in.bust', 'Bust', 'number'], ['measurements_in.waist', 'Waist', 'number'], ['measurements_in.hips', 'Hips', 'number'], ['measurements_in.inseam', 'Inseam', 'number'], ['measurements_in.foot_length', 'Foot length', 'number']]],
  ['Store sizes', [['sizes.top', 'Top', 'text'], ['sizes.bottom', 'Bottom', 'text'], ['sizes.dress', 'Dress', 'text'], ['sizes.shoe', 'Shoe', 'text'], ['sizes.shoe_width', 'Shoe width', 'select:narrow,medium,wide,extra wide'], ['sizes.inseam_label', 'Inseam length', 'select:petite,regular,long']]],
  ['Style', [['style.words', 'Style words', 'list'], ['style.love_colors', 'Colors I love', 'list'], ['style.avoid', 'Avoid', 'list'], ['comfort', 'Comfort rules', 'lines']]]
]
const getPath = (o, p) => p.split('.').reduce((a, k) => (a == null ? a : a[k]), o)
const setPath = (o, p, v) => { const ks = p.split('.'); const last = ks.pop(); const t = ks.reduce((a, k) => (a[k] ??= {}), o); t[last] = v }

function renderProfile() {
  const p = state.profile || {}
  $('#profile-form').innerHTML = FIELDS.map(([title, fields]) => `<fieldset><legend>${esc(title)}</legend>${fields.map(([path, label, type]) => {
    const v = getPath(p, path)
    let input
    if (type.startsWith('select:')) input = `<select name="${path}">${type.slice(7).split(',').map((o) => `<option ${o === v ? 'selected' : ''}>${o}</option>`).join('')}</select>`
    else if (type === 'list') input = `<input type="text" name="${path}" value="${esc((v || []).join(', '))}" placeholder="comma separated" />`
    else if (type === 'lines') input = `<textarea name="${path}" placeholder="one per line">${esc((v || []).join('\n'))}</textarea>`
    else if (type === 'color') input = `<input type="color" name="${path}" value="${esc(v || '#8d5a3b')}" />`
    else input = `<input type="${type}" step="any" name="${path}" value="${esc(v ?? '')}" />`
    return `<div class="field"><label>${esc(label)}</label>${input}</div>`
  }).join('')}</fieldset>`).join('')
}

async function saveProfile() {
  const p = structuredClone(state.profile || {})
  for (const [, fields] of FIELDS) for (const [path, , type] of fields) {
    const el = $(`[name="${path}"]`)
    let v = el.value
    if (type === 'number') v = v === '' ? null : Number(v)
    else if (type === 'list') v = v.split(',').map((s) => s.trim()).filter(Boolean)
    else if (type === 'lines') v = v.split('\n').map((s) => s.trim()).filter(Boolean)
    setPath(p, path, v)
  }
  delete p.stylist  // house rules save on their own; the server owns the rest of this block
  try {
    await api(`/api/profile?${q()}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(p) })
    state.profile = p
    toast('Profile saved.')
  } catch (e) {
    toast(`Couldn't save: ${e.message}`)
  }
}

async function uploadICS(ev) {
  ev.preventDefault()
  const f = $('#ics-file').files[0]
  if (!f) return toast('Choose an .ics file first')
  const fd = new FormData()
  fd.append('file', f)
  fd.append('dataset', state.dataset)
  try {
    await api('/api/calendar', { method: 'POST', body: fd })
    $('#ics-status').innerHTML = '<p class="small" style="color:var(--good)">✓ Calendar uploaded.</p>'
    loadDay()
  } catch (e) {
    $('#ics-status').innerHTML = `<p class="small" style="color:var(--bad)">${esc(e.message)}</p>`
  }
}

// ------------------------------------------------------------------ RUNS
async function loadRuns() {
  try {
    state.runs = await api('/api/runs?limit=100')
  } catch {
    state.runs = []
  }
  renderRuns()
}

function renderLimits() {
  const s = state.status
  if (!s) return
  const l = s.limits
  $('#limits-card').innerHTML = `<h3>⛨ Spending guardrails (enforced in code before every model call)</h3>
    <div class="limits"><span class="tag pink">model: ${esc(s.model)}</span><span class="tag">${l.max_tokens_per_run.toLocaleString()} tokens / run</span>
    <span class="tag">${usd(l.max_usd_per_run, 2)} / run</span>${l.max_usd_per_live_web_run ? `<span class="tag">${usd(l.max_usd_per_live_web_run, 2)} / live-web run</span>` : ''}
    <span class="tag">${usd(l.max_usd_per_day, 2)} / day</span><span class="tag">${l.max_runs_per_minute} runs / minute</span>
    <span class="tag">spent today: ${usd(s.spent_today_usd)}</span></div>`
}

function renderRuns() {
  const runs = state.runs
  const byMode = {}
  for (const r of runs.filter((r) => r.status === 'ok')) (byMode[r.mode] ??= []).push(r)
  const avg = (arr, f) => arr.reduce((a, r) => a + f(r), 0) / (arr.length || 1)
  const labels = { plan_day: 'Plan my day', shop: 'Shop', add_to_closet: 'Add to closet' }
  const safetyCount = runs.reduce((a, r) => a + (r.safety_events || []).length, 0)
  $('#run-stats').innerHTML = Object.entries(byMode).map(([m, arr]) => `<div class="card glass stat"><div class="k">${esc(labels[m] || m)} · ${arr.length} runs</div><div class="v">${usd(avg(arr, (r) => r.totals.cost_usd))}</div>
      <div class="small muted">avg ${fmtK(Math.round(avg(arr, (r) => r.totals.input_tokens)))} in (${fmtK(Math.round(avg(arr, (r) => r.totals.cached_tokens)))} cached) · ${fmtK(Math.round(avg(arr, (r) => r.totals.output_tokens)))} out · ${avg(arr, (r) => r.totals.seconds).toFixed(0)}s</div></div>`).join('')
    + `<div class="card glass stat"><div class="k">Safety events logged</div><div class="v">${safetyCount}</div><div class="small muted">blocked injections, budget stops, grounding fixes</div></div>`
  if (!runs.length) {
    $('#runs-table').innerHTML = '<tr><td class="muted">No runs yet. Plan a day or shop to see real token counts here.</td></tr>'
    return
  }
  $('#runs-table').innerHTML = `<tr><th>When</th><th>Mode</th><th>Data</th><th>Status</th><th>Calls</th><th>Input</th><th>Cached</th><th>Output</th><th>Web</th><th>Cost</th><th>Time</th><th>⛨</th></tr>`
    + runs.map((r, i) => {
      const t = r.totals
      return `<tr class="clickable" data-run="${i}"><td>${new Date(r.started_at).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}</td>
      <td>${esc(labels[r.mode] || r.mode)}</td><td>${esc(r.dataset)}</td><td class="st-${esc(r.status)}">${esc(r.status.replace('_', ' '))}</td><td>${t.calls}</td>
      <td>${t.input_tokens.toLocaleString()}</td><td>${t.cached_tokens.toLocaleString()}</td><td>${t.output_tokens.toLocaleString()}</td><td>${t.web_searches}</td>
      <td>${usd(t.cost_usd)}</td><td>${t.seconds}s</td><td>${(r.safety_events || []).length || ''}</td></tr>`
    }).join('')
  $$('#runs-table tr.clickable').forEach((tr) => tr.addEventListener('click', () => {
    $$('#runs-table tr').forEach((x) => x.classList.remove('selected'))
    tr.classList.add('selected')
    const r = runs[+tr.dataset.run]
    const se = (r.safety_events || []).map((e) => `<li class="safety"><span class="t"></span>${agentPill(e.agent)}<span class="msg">[${esc(e.kind)}] ${esc(e.message)}</span></li>`).join('')
    $('#run-detail').innerHTML = (se ? `<div class="card glass" style="margin-bottom:12px"><h3>⛨ Safety events in this run</h3><ul class="trace-list">${se}</ul></div>` : '') + traceHTML(r, true)
    $('#run-detail').scrollIntoView({ behavior: 'smooth', block: 'start' })
  }))
}

// ------------------------------------------------------------------ boot
async function loadAll() {
  loadDay()
  loadCloset()
  try {
    state.profile = await api(`/api/profile?${q()}`)
  } catch {
    state.profile = {}
  }
  renderProfile()
  renderColorStyle()
  await loadStylist()
  renderOutfit()
}

// ------------------------------------------------------------------ PHOTO TRY-ON (own OpenAI key)
const SCENE_NAMES = { studio: 'boutique', classroom: 'classroom', office: 'office', gym: 'gym', coffee: 'coffee shop', street: 'campus walk', dinner: 'dinner' }

async function refreshPhotoStatus() {
  let st
  try { st = await api('/api/photo-tryon/status?' + q()) } catch { return }
  state.photo = st
  if (state.dataset !== 'user') {
    // photos are personal: the Sample set never shows them
    $('#me-photo-preview').innerHTML = '<div class="muted small sample-note">Photos live in My closet only.</div>'
    $('#face-thumb').innerHTML = 'Face'
    $('#place-status').textContent = ''
    renderSetup()
    return
  }
  $('#me-photo-preview').innerHTML = st.has_photo
    ? `<img src="/api/me/photo/user?t=${Date.now()}" alt="your photo" />`
    : '<div class="muted small">No photo yet</div>'
  $('#me-photo-consent').checked = !!st.consent
  $('#closeup-consent').checked = !!st.consent
  $('#face-thumb').innerHTML = st.has_face ? `<img src="/api/me/photo/user?kind=face&t=${Date.now()}" alt="face close-up" />` : 'Face'
  $('#place-status').textContent = st.places.length ? `Saved places: ${st.places.map((p) => SCENE_NAMES[p] || p).join(', ')}` : ''
  renderSetup()
  renderDrapeTest(true)
}

async function uploadMePhoto(ev, blob) {
  ev?.preventDefault()
  ensureMyCloset()
  const f = blob || $('#me-photo-file').files[0]
  if (!f) return toast('Choose a photo first')
  if (!$('#me-photo-consent').checked) return toast('Tick the consent box first')
  const fd = new FormData()
  fd.append('file', f, blob ? 'camera.jpg' : f.name); fd.append('dataset', state.dataset); fd.append('consent', 'true')
  try {
    await api('/api/me/photo', { method: 'POST', body: fd })
    toast('Photo saved for photo try-on. For your color season, take a face close-up above.')
    await refreshPhotoStatus()
    return
  } catch (e) { toast(e.message) }
  refreshPhotoStatus()
}

async function deleteMePhoto() {
  try { await api('/api/me/photo?' + q(), { method: 'DELETE' }); toast('Photo removed') } catch (e) { toast(e.message) }
  refreshPhotoStatus()
}

async function uploadPlace(ev) {
  ev.preventDefault()
  const f = $('#place-file').files[0]
  if (!f) return toast('Choose a photo of the place first')
  const fd = new FormData()
  fd.append('file', f); fd.append('scene', $('#place-scene').value); fd.append('dataset', state.dataset)
  try { await api('/api/places/photo', { method: 'POST', body: fd }); toast('Place saved') } catch (e) { toast(e.message) }
  refreshPhotoStatus()
}

// ------------------------------------------------------------------ COLOR SEASON & ARCHETYPE
async function initColorStyle() {
  try { state.styleMeta = await api('/api/style/meta') } catch { return }
  const m = state.styleMeta
  renderStylistCard()
  $('#season-override').innerHTML = '<option value="">Know your season? Choose it</option>' + Object.keys(m.seasons).map((k) => `<option>${esc(k)}</option>`).join('')
  renderColorStyle()
}

function renderColorStyle() {
  const m = state.styleMeta, p = state.profile || {}
  if (!m) return
  const cs = p.color_season
  if (cs && m.seasons[cs.season]) {
    const s = m.seasons[cs.season]
    const sw = (arr) => arr.map(([n, h]) => `<span class="swatch-lg" title="${esc(n)}" style="background:${esc(h)}"></span>`).join('')
    $('#season-out').innerHTML = `<div class="season-name">${esc(cs.season)}</div>
      <div class="muted small">${esc(s.traits)}${cs.confidence ? ` · confidence ${esc(cs.confidence)}` : ''}${cs.source === 'manual' ? ' · chosen by you' : ''}</div>
      <div class="swatches">${sw(s.palette)}</div>
      <div class="small"><b>Neutrals:</b> ${esc(s.neutrals.join(', '))} · <b>Metals:</b> ${esc(s.metals)}</div>
      <div class="small"><b>Skip near your face:</b> ${esc(s.avoid.join(', '))}</div>
      ${cs.why ? `<details class="more small"><summary>Why this season</summary><div class="muted">${esc(cs.why)}</div></details>` : ''}
      ${cs.top3?.length > 1 ? `<div class="small" style="margin-top:6px">Not quite you? Try: ${cs.top3.filter((x) => x !== cs.season).map((x) => `<button class="chip" type="button" data-season="${esc(x)}">${esc(x)}</button>`).join(' ')}</div>` : ''}`
    $$('#season-out [data-season]').forEach((b) => b.addEventListener('click', () => { $('#season-override').value = b.dataset.season; overrideSeason() }))
    $('#season-override').value = cs.season
  }
  const pal = cs && m.seasons[cs.season] ? m.seasons[cs.season].palette.filter(([n]) => !m.seasons[cs.season].neutrals.some((x) => x.toLowerCase() === n.toLowerCase()) && !/white|black/i.test(n)) : []
  $('#color-use').innerHTML = pal.length ? `<p style="margin:0 0 6px">Your signature colors: ${pal.map(([n, h]) => `<span class="chip static"><span class="swatch" style="background:${esc(h)}"></span>${esc(n)}</span>`).join(' ')}</p>
      <details class="more" style="margin-top:8px"><summary>How I use them</summary><ul style="margin:0;padding-left:18px"><li>Most looks carry one of these, as a piece or an accessory (the 10% accent at least).</li>
      <li>Your neutrals (${esc(m.seasons[cs.season].neutrals.join(', '))}) are the base, not the whole outfit.</li>
      <li>Every look follows color theory: one scheme on purpose, about 60/30/10, warm with warm and cool with cool.</li>
      <li>If your closet is short on these colors, your next pieces bring them in.</li></ul></details>`
    : '<p class="muted">Take a close-up to find your season. Your stylist then builds every look’s colors on it.</p>'
  renderDrapeTest(false)
}

async function runAnalysis(kind) {
  const btn = kind === 'color' ? $('#analyze-color-btn') : $('#analyze-style-btn')
  const body = { dataset: state.dataset }
  if (kind === 'style') body.answers = [0, 1, 2].map((i) => $(`#quiz-form input[name=q${i}]:checked`)?.value).filter(Boolean)
  btn.disabled = true
  const status = kind === 'style' ? $('#arch-status') : $('#analysis-status')
  status.innerHTML = `<div class="status"><div class="spinner"></div><div class="small">${kind === 'color' ? 'Your stylist is reading your coloring…' : 'Your stylist is reading your quiz, closet and feedback…'}</div></div>`
  try {
    const r = await postJSON(`/api/analyze/${kind}`, body)
    updateMeter(r.run)
    state.profile = await api('/api/profile?' + q())
    renderColorStyle()
    if (kind === 'style') loadStylist()
    status.innerHTML = ''
    toast(kind === 'color' ? `You're a ${r.result.season}` : `Your archetype: ${r.result.primary}`)
  } catch (e) {
    status.innerHTML = `<div class="status error small"><div style="font-size:18px;color:var(--burgundy)">!</div><div>${esc(e.message)}</div></div>`
  } finally { btn.disabled = false }
}

async function overrideSeason(ds = state.dataset) {
  // ds is 'user' when the choice comes from the drape test on the user's own photo
  const season = $('#season-override').value
  if (!season) return
  const qs = new URLSearchParams({ dataset: ds }).toString()
  const p = await api('/api/profile?' + qs)
  p.color_season = { ...(p.color_season || {}), season, source: 'manual', why: 'chosen by you', confidence: '' }
  await api('/api/profile?' + qs, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(p) })
  if (ds === state.dataset) state.profile = p
  renderColorStyle()
  toast(`Season set to ${season}${ds !== state.dataset ? ' (in My closet)' : ''}`)
}

// ------------------------------------------------------------------ LIVE CAMERA
// Works on http://localhost / 127.0.0.1 (a secure context). The stream stops as soon as the dialog closes.
const cam = { stream: null, facing: 'user', blob: null, resolve: null, timer: null }

async function startStream() {
  stopStream()
  cam.stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: cam.facing, width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false })
  const v = $('#cam-video')
  v.srcObject = cam.stream
  v.classList.toggle('mirror', cam.facing === 'user')
  await v.play().catch(() => {})
}

function stopStream() {
  if (cam.stream) cam.stream.getTracks().forEach((t) => t.stop())
  cam.stream = null
}

function camMode(preview) {
  $('#cam-video').classList.toggle('hidden', !preview)
  $('#cam-shot').classList.toggle('hidden', preview)
  for (const id of ['cam-snap', 'cam-timer', 'cam-flip']) $('#' + id).classList.toggle('hidden', !preview)
  for (const id of ['cam-use', 'cam-retake']) $('#' + id).classList.toggle('hidden', preview)
}

function snap() {
  const v = $('#cam-video')
  if (!v.videoWidth) return toast('The camera is still starting')
  const c = document.createElement('canvas')
  c.width = v.videoWidth; c.height = v.videoHeight
  c.getContext('2d').drawImage(v, 0, 0)  // saved un-mirrored, the way others see you
  c.toBlob((b) => {
    cam.blob = b
    $('#cam-shot').src = URL.createObjectURL(b)
    camMode(false)
  }, 'image/jpeg', 0.92)
}

function countdown(n) {
  const el = $('#cam-count')
  clearInterval(cam.timer)
  el.classList.remove('hidden'); el.textContent = n
  cam.timer = setInterval(() => {
    n -= 1
    if (n <= 0) { clearInterval(cam.timer); el.classList.add('hidden'); snap() } else el.textContent = n
  }, 1000)
}

function closeCamera(result) {
  clearInterval(cam.timer)
  $('#cam-count').classList.add('hidden')
  stopStream()
  $('#camera-modal').classList.add('hidden')
  if (cam.resolve) cam.resolve(result)
  cam.resolve = null
}

async function openCamera({ title, hint, facing = 'user' }) {
  if (!navigator.mediaDevices?.getUserMedia) { toast('This browser cannot use the camera here. Open http://127.0.0.1:8000 in Chrome or Safari.'); return null }
  $('#cam-title').textContent = title
  $('#cam-hint').textContent = hint
  cam.facing = facing; cam.blob = null
  camMode(true)
  $('#camera-modal').classList.remove('hidden')
  try { await startStream() } catch (e) {
    closeCamera(null)
    toast(e.name === 'NotAllowedError' ? 'Camera permission was blocked. Allow the camera for this site and try again.' : `Couldn't start the camera (${e.name}).`)
    return null
  }
  return new Promise((resolve) => { cam.resolve = resolve })
}

function initCamera() {
  $('#cam-snap').addEventListener('click', snap)
  $('#cam-timer').addEventListener('click', () => countdown(5))
  $('#cam-retake').addEventListener('click', () => { cam.blob = null; camMode(true) })
  $('#cam-use').addEventListener('click', () => closeCamera(cam.blob))
  $('#cam-cancel').addEventListener('click', () => closeCamera(null))
  $('#cam-flip').addEventListener('click', async () => { cam.facing = cam.facing === 'user' ? 'environment' : 'user'; try { await startStream() } catch { toast('No other camera found') } })
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !$('#camera-modal').classList.contains('hidden')) closeCamera(null) })
  $('#me-photo-camera').addEventListener('click', async () => {
    if (!$('#me-photo-consent').checked) return toast('Tick the consent box first')
    const blob = await openCamera({ title: 'Your full-body photo', hint: 'Prop your laptop up, press the 5-second timer, step back until your whole body is in the frame, and stand straight facing the camera. Daylight from a window is best.' })
    if (blob) uploadMePhoto(null, blob)
  })
  $('#closet-camera').addEventListener('click', async () => {
    const blob = await openCamera({ title: 'Photograph an item', hint: 'Hold the piece up flat (or lay it on the floor) against a plain background, with the whole item in the frame.', facing: 'environment' })
    if (blob) addPhoto(null, blob)
  })
}

function ensureMyCloset() {
  // photos of you always live in your own closet, never the sample
  if (state.dataset !== 'user') { setDataset('user'); toast('Switched to My closet: your photos are saved there') }
}

async function analyzeCloseup(blob) {
  if (!$('#closeup-consent').checked) return toast('Tick the consent box first')
  ensureMyCloset()
  const out = $('#season-out')
  const step = (msg) => { out.innerHTML = `<div class="status"><div class="spinner"></div><div class="small">${msg}</div></div>` }
  try {
    step('Saving your close-up…')
    const fd = new FormData()
    fd.append('file', blob, 'face.jpg'); fd.append('kind', 'face'); fd.append('dataset', state.dataset); fd.append('consent', 'true')
    await api('/api/me/closeup', { method: 'POST', body: fd })
    refreshPhotoStatus()
    // measure the server's JPEG copy, so iPhone HEIC photos work too
    const jpeg = await (await fetch(`/api/me/photo/user?kind=face&t=${Date.now()}`)).blob()
    step('Finding your face and measuring skin, brows, eyes and lips…')
    const { measureFace } = await import('./face_measure.js')
    const measured = await measureFace(jpeg)
    step('Your stylist is checking the measurements against your photo…')
    const r = await postJSON('/api/analyze/color', { dataset: state.dataset, measured })
    updateMeter(r.run)
    state.profile = await api('/api/profile?' + q())
    renderColorStyle()
    toast(`Your season: ${r.result.season}`)
  } catch (e) {
    out.innerHTML = `<div class="status error small"><div style="font-size:18px;color:var(--burgundy)">!</div><div>${esc(e.message)}</div></div>`
  }
}

function initCloseups() {
  $('#face-camera').addEventListener('click', async () => {
    if (!$('#closeup-consent').checked) return toast('Tick the consent box first')
    const b = await openCamera({ title: 'Face close-up for color analysis', hint: 'Face a window in daylight. Hair back, little makeup, fill most of the frame with your face. Turn off warm lamps.' })
    if (b) analyzeCloseup(b)
  })
  $('#face-file').addEventListener('change', (e) => { const f = e.target.files[0]; if (f) analyzeCloseup(f); e.target.value = '' })
}

// ------------------------------------------------------------------ DRAPE TEST (virtual draping)
// Real color analysts hold fabric under the face and compare. We draw the face close-up with
// each candidate season's colors as a cape, so the user can judge which one makes them glow.
const DRAPE_EXTRAS = ['Deep Winter', 'Deep Autumn', 'True Autumn']
const drape = { img: null, imgKey: '', oval: null, seasons: [], a: 0, b: 1, busy: false }

function loadImage(src) {
  return new Promise((resolve, reject) => {
    const im = new Image()
    im.onload = () => resolve(im)
    im.onerror = () => reject(new Error('Could not load the close-up'))
    im.src = src
  })
}

function drawDrape(canvas, img, palette, oval) {
  const S = canvas.width
  const ctx = canvas.getContext('2d')
  const W = img.naturalWidth, H = img.naturalHeight
  ctx.clearRect(0, 0, S, S)
  let pts = null
  if (oval) {
    // crop around the face: face height ~58% of the square, chin just above the cape
    const xs = oval.map((p) => p[0] * W), ys = oval.map((p) => p[1] * H)
    const fx0 = Math.min(...xs), fx1 = Math.max(...xs), fy0 = Math.min(...ys), fy1 = Math.max(...ys)
    const side = (fy1 - fy0) / 0.58
    const sx = (fx0 + fx1) / 2 - side / 2, sy = fy1 - side * 0.74
    ctx.drawImage(img, sx, sy, side, side, 0, 0, S, S)
    pts = oval.map((p) => [((p[0] * W) - sx) / side * S, ((p[1] * H) - sy) / side * S])
    // neutral cap: cover hair and background so only the face meets the drape color
    const cap = new Path2D()
    cap.rect(0, 0, S, S)
    pts.forEach(([x, y], i) => (i ? cap.lineTo(x, y) : cap.moveTo(x, y)))
    cap.closePath()
    ctx.save()
    const cg = ctx.createRadialGradient(S / 2, S * 0.35, S * 0.1, S / 2, S * 0.4, S * 0.75)
    cg.addColorStop(0, '#f4f1ec'); cg.addColorStop(1, '#dcd7cf')
    ctx.fillStyle = cg
    ctx.fill(cap, 'evenodd')
    ctx.strokeStyle = 'rgba(0,0,0,0.06)'; ctx.lineWidth = Math.max(1, S / 300)
    ctx.beginPath(); pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); ctx.closePath(); ctx.stroke()
    ctx.restore()
  } else {
    // fallback: square crop biased toward the upper part where the face is
    const side = Math.min(W, H)
    ctx.drawImage(img, (W - side) / 2, Math.max(0, (H - side) * 0.3), side, side, 0, 0, S, S)
  }

  // cape: shoulders at ~70% height, a soft neckline dipping to ~84% in the middle
  const top = S * 0.7, dip = S * 0.85
  const cape = new Path2D()
  cape.moveTo(0, top + S * 0.03)
  cape.bezierCurveTo(S * 0.18, top - S * 0.02, S * 0.32, top, S * 0.4, dip - S * 0.04)
  cape.quadraticCurveTo(S * 0.5, dip + S * 0.02, S * 0.6, dip - S * 0.04)
  cape.bezierCurveTo(S * 0.68, top, S * 0.82, top - S * 0.02, S, top + S * 0.03)
  cape.lineTo(S, S)
  cape.lineTo(0, S)
  cape.closePath()

  const colors = (palette || []).slice(0, 4).map((c) => c[1])
  ctx.save()
  ctx.clip(cape)
  const band = S / colors.length
  colors.forEach((hex, i) => {
    ctx.fillStyle = hex
    ctx.fillRect(i * band, top - S * 0.05, band + 1, S)
  })
  // gentle fabric shading
  const g = ctx.createLinearGradient(0, top, 0, S)
  g.addColorStop(0, 'rgba(255,255,255,0.18)')
  g.addColorStop(0.35, 'rgba(255,255,255,0)')
  g.addColorStop(1, 'rgba(0,0,0,0.22)')
  ctx.fillStyle = g
  ctx.fillRect(0, top - S * 0.05, S, S)
  ctx.restore()
  // gold piping along the neckline
  ctx.save()
  ctx.strokeStyle = 'rgba(184,150,78,0.9)'
  ctx.lineWidth = Math.max(2, S / 140)
  const edge = new Path2D()
  edge.moveTo(0, top + S * 0.03)
  edge.bezierCurveTo(S * 0.18, top - S * 0.02, S * 0.32, top, S * 0.4, dip - S * 0.04)
  edge.quadraticCurveTo(S * 0.5, dip + S * 0.02, S * 0.6, dip - S * 0.04)
  edge.bezierCurveTo(S * 0.68, top, S * 0.82, top - S * 0.02, S, top + S * 0.03)
  ctx.stroke(edge)
  ctx.restore()
}

async function renderDrapeTest(reloadImage) {
  const box = $('#drape-test')
  const m = state.styleMeta
  if (!box || !m) return
  if (!state.photo?.has_face || state.dataset !== 'user') { box.classList.add('hidden'); return }
  if (drape.busy) return
  drape.busy = true
  try {
    if (reloadImage || !drape.img) {
      const key = String(Date.now())
      drape.img = await loadImage(`/api/me/photo/user?kind=face&t=${key}`)
      drape.imgKey = key
      try {
        const { faceOutline } = await import('./face_measure.js')
        drape.oval = await faceOutline(drape.img)
      } catch { drape.oval = null }
    }
    let prof = {}
    try { prof = await api('/api/profile?dataset=user') } catch { /* show the extras only */ }
    const cs = prof.color_season || {}
    const list = [...(cs.top3 || []), ...(cs.season ? [cs.season] : []), ...DRAPE_EXTRAS]
    drape.seasons = [...new Set(list)].filter((n) => m.seasons[n]).slice(0, 6)
    const chosen = cs.source === 'manual' ? cs.season : ''
    const grid = $('#drape-grid')
    grid.innerHTML = drape.seasons.map((n, i) => `<button class="drape-item${n === chosen ? ' chosen' : ''}" type="button" data-drape="${i}" aria-label="Compare ${esc(n)} drape">
        <canvas width="300" height="300"></canvas>
        <span class="drape-name">${esc(n)}</span>
        ${(cs.top3 || []).includes(n) ? '<span class="drape-tag">measured</span>' : ''}${n === chosen ? '<span class="drape-tag gold">your pick</span>' : ''}
      </button>`).join('')
    $$('.drape-item', grid).forEach((el) => {
      const name = drape.seasons[+el.dataset.drape]
      drawDrape($('canvas', el), drape.img, m.seasons[name].palette, drape.oval)
      el.addEventListener('click', () => openDrapeCompare(+el.dataset.drape))
    })
    box.classList.remove('hidden')
  } catch (e) {
    box.classList.add('hidden')
  } finally {
    drape.busy = false
  }
}

function paintCompare() {
  const m = state.styleMeta
  for (const side of ['a', 'b']) {
    const name = drape.seasons[drape[side]]
    drawDrape($(`#drape-${side}`), drape.img, m.seasons[name].palette, drape.oval)
    $(`#drape-${side}-name`).textContent = name
  }
}

function openDrapeCompare(i) {
  if (!drape.img || drape.seasons.length < 2) return
  drape.a = i
  drape.b = (i + 1) % drape.seasons.length
  paintCompare()
  $('#drape-modal').classList.remove('hidden')
}

function closeDrapeCompare() {
  $('#drape-modal').classList.add('hidden')
}

function initDrapeTest() {
  $('#drape-close').addEventListener('click', closeDrapeCompare)
  $('#drape-modal').addEventListener('click', (e) => { if (e.target.id === 'drape-modal') closeDrapeCompare() })
  document.addEventListener('keydown', (e) => {
    if ($('#drape-modal').classList.contains('hidden')) return
    if (e.key === 'Escape') closeDrapeCompare()
    if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
      const n = drape.seasons.length
      drape.b = (drape.b + (e.key === 'ArrowRight' ? 1 : -1) + n) % n
      if (drape.b === drape.a) drape.b = (drape.b + (e.key === 'ArrowRight' ? 1 : -1) + n) % n
      paintCompare()
    }
  })
  $$('#drape-modal [data-nav]').forEach((b) => b.addEventListener('click', () => {
    const side = b.dataset.nav, other = side === 'a' ? 'b' : 'a', n = drape.seasons.length
    let next = (drape[side] + Number(b.dataset.dir) + n) % n
    if (next === drape[other]) next = (next + Number(b.dataset.dir) + n) % n
    drape[side] = next
    paintCompare()
  }))
  $$('#drape-modal [data-choose]').forEach((b) => b.addEventListener('click', async () => {
    const season = drape.seasons[drape[b.dataset.choose]]
    closeDrapeCompare()
    $('#season-override').value = season
    await overrideSeason('user')
  }))
}

async function refreshCalendarStatus() {
  try {
    const st = await api('/api/calendar/status?' + q())
    if (st.sample) { $('#cal-link-status').textContent = 'The sample data set uses an example day. Switch to My closet to connect your calendar.'; return }
    $('#cal-link-status').innerHTML = st.connected ? '✓ Live calendar connected' + (st.timezone ? ` · ${esc(st.timezone)}` : '') : (st.uploaded ? 'Using your uploaded .ics file.' : 'No calendar yet.')
    if (st.timezone) $('#cal-tz').value = st.timezone
  } catch { /* status is optional */ }
}

async function connectCalendar(ev) {
  ev.preventDefault()
  const url = $('#cal-link').value.trim()
  if (!url) return toast('Paste your private iCal link first')
  const tz = $('#cal-tz').value.trim() || Intl.DateTimeFormat().resolvedOptions().timeZone
  $('#cal-link-status').textContent = 'Checking the link…'
  try {
    const r = await postJSON('/api/calendar/link', { dataset: state.dataset, url, timezone: tz })
    $('#cal-link').value = ''
    toast(`Calendar connected (${r.events_in_feed} events found)`)
    refreshCalendarStatus(); loadDay()
  } catch (e) { $('#cal-link-status').textContent = e.message }
}

async function disconnectCalendar() {
  try { await postJSON('/api/calendar/link', { dataset: state.dataset, url: '' }); toast('Calendar disconnected') } catch (e) { toast(e.message) }
  refreshCalendarStatus(); loadDay()
}

// ------------------------------------------------------------------ STYLIST RECOMMENDS
function syncShopDefaults() {
  // real stores by default for your own closet; the sample uses the practice catalog
  $('#live-web').checked = state.dataset === 'user'
}

async function runRecommend(shopTop, fresh = false) {
  const out = $('#recs-out')
  const btns = [$('#recs-btn'), $('#recs-shop-btn')]
  btns.forEach((b) => { b.disabled = true })
  out.innerHTML = ''
  const stop = working($('#recs-status'), shopTop ? 'Finding your gaps, then shopping the top one… (about a minute)' : 'Reading your closet, colors and week…',
    ['Finding the gaps in your closet', ...(shopTop ? ['Searching in your size', 'Checking the fit', 'Double-checking the picks'] : [])])
  try {
    const r = await postJSON('/api/recommend', { dataset: state.dataset, shop: shopTop, look: $('#recs-look').value.trim(), fresh })
    $('#recs-status').innerHTML = ''
    showRecs(r.result, r.run)
    updateMeter(r.run)
  } catch (e) {
    showError($('#recs-status'), e)
  } finally {
    stop()
    btns.forEach((b) => { b.disabled = false })
  }
}

// saved picks keep their pictures; fresh or saved picks without pictures wait for her tap
// (6 images cost about $0.19, so neither a new run nor opening the page draws them by itself)
function showRecs(res, run) {
  renderRecs(res, run)
  const gaps = res.recommendations?.gaps || []
  if (state.dataset !== 'user' || !gaps.length) return
  if (res.mockups) return fillMockups(gaps, res.mockups)
  $$('[data-mock-piece], [data-mock-board]').forEach((el) => { el.innerHTML = '' })
  $('#recs-out .rec-gaps')?.insertAdjacentHTML('beforebegin', `<div class="kept-note small" id="mock-ask"><span>No pictures yet for these picks.</span>
    <button class="btn small ghost" type="button" data-draw-mocks>Draw them (about $${(gaps.length * 0.062).toFixed(2)})</button></div>`)
  $('[data-draw-mocks]')?.addEventListener('click', () => {
    $('#mock-ask')?.remove()
    $$('[data-mock-piece]').forEach((el) => { el.innerHTML = '<div class="spinner sm"></div>' })
    $$('[data-mock-board]').forEach((el) => { el.innerHTML = '<div class="status"><div class="spinner sm"></div><span class="small muted">Drawing the outfit…</span></div>' })
    drawMockups(res)
  })
}

function renderRecs(res, run) {
  const rec = res.recommendations || {}
  const gaps = rec.gaps || []
  const empty = res.closet_size === 0 ? `<p class="muted small">Your closet is empty, so these are foundation pieces for your archetype and season. Add clothes in the Closet tab for sharper picks.</p>` : ''
  const mock = state.dataset === 'user'
  const gapHTML = gaps.map((g, i) => `<div class="rec-gap">
      <div class="rec-num">${i + 1}</div>
      ${mock ? `<div class="rec-piece-img" data-mock-piece="${i}"><div class="spinner sm"></div></div>` : ''}
      <div style="flex:1">
        <div class="row between wrap"><b class="rec-piece">${esc(g.piece)}</b>
          <span class="swatches">${(g.colors || []).map((c) => `<span class="swatch-lg sm" title="${esc(c.name)}" style="background:${esc(c.hex)}"></span>`).join('')}</span></div>
        <p class="small">${esc(g.why)}</p>
        ${g.events?.length ? `<div class="small muted">For: ${g.events.map(esc).join(' · ')}</div>` : ''}
        ${g.pairs_with?.length && !g.outfit?.length ? `<div class="chips small" style="margin-top:4px">Pairs with: ${g.pairs_with.map((p) => `<span class="chip static"><span class="swatch" style="background:${esc(p.hex)}"></span>${esc(p.name)}</span>`).join('')}</div>` : ''}
        ${g.outfit?.length ? `<div class="rec-outfit"><div class="kicker-sm">The outfit${g.outfit_title ? `: ${esc(g.outfit_title)}` : ''}</div>
          <div class="small muted">${esc(g.piece)} (new) + ${g.outfit.map((o) => esc(o.name)).join(' + ')}</div>
          ${mock ? `<div class="rec-board" data-mock-board="${i}"><div class="status"><div class="spinner sm"></div><span class="small muted">Drawing the outfit…</span></div></div>` : ''}</div>` : ''}
        <div class="row gap wrap" style="margin-top:6px"><button class="btn small ghost" type="button" data-shopgap="${i}">Shop this in my size →</button>
          ${mock && g.outfit?.length ? `<button class="btn small ghost" type="button" data-onme="${i}">See it on me</button>` : ''}</div>
        ${fbHTML('recommendation', [], `Next piece: ${g.piece}`)}
      </div></div>`).join('')
  const why = res.kept ? `Your stylist's picks${res.look ? ` for “${esc(res.look)}”` : ''}: same closet, week and look as before, so they stand.`
    : res.changed?.length ? `New picks because ${esc(res.changed.join(' and '))} changed.` : ''
  $('#recs-out').innerHTML = `${why ? `<div class="kept-note small"><span>${why}</span><button class="btn small ghost" type="button" data-recs-fresh>↻ Fresh take</button></div>` : ''}
    ${noteCard(rec.stylist_take, true)}${listenedHTML(res.blocked)}${empty}<div class="rec-gaps">${gapHTML}</div>
    ${tellHTML('recommendations', res.look ? `Recommendations for “${res.look}”` : 'Recommendations')}
    ${res.shop ? `<h4 style="margin-top:14px">Found for #${(res.shop.for_gap || 0) + 1}: ${esc(gaps[res.shop.for_gap || 0]?.piece || '')}${res.shop.live_web ? ' <span class="tag">real stores, your size</span>' : ' <span class="tag">practice catalog</span>'}</h4><div id="recs-shop-out"></div>` : ''}
    ${run ? traceHTML(run) : ''}`
  $$('[data-shopgap]').forEach((b) => b.addEventListener('click', () => {
    const g = gaps[+b.dataset.shopgap]
    showTab('shop')
    $('#shop-q').value = g.search_request || g.piece
    syncShopDefaults()
    if (!$('#live-web').checked) return shop()
    // a live search costs money and takes a minute, so it waits for her "Find it"
    $('#shop-out').innerHTML = `<div class="kept-note small"><span>Ready to search real stores in your size for <b>${esc(g.piece)}</b> (about a minute, about $0.07). Press <b>Find it</b> when you're ready.</span></div>`
    $('#shop-form button[type=submit]').focus()
  }))
  $('#recs-out [data-recs-fresh]')?.addEventListener('click', () => runRecommend(false, true))
  $$('[data-onme]').forEach((b) => b.addEventListener('click', () => {
    // the new piece goes on as a description (it isn't in the closet yet); the rest are her own clothes
    const g = gaps[+b.dataset.onme]
    const own = g.outfit.map((o) => state.closet.find((x) => x.id === o.id)).filter(Boolean)
    state.outfit = [{ id: `new-${i18nSafe(g.piece)}`, name: g.piece, category: g.category, color: (g.colors || []).map((c) => c.name).join('/'), mockup: g.mockup || '' }, ...own]
    state.zones = {}
    openFitting('studio')
    toast('In the Fitting Room: tap “Make it real” to see this outfit on you.')
  }))
  if (res.shop) {
    // reuse the Shop tab's renderer, then move its output under the recommendation
    const keep = $('#shop-out').innerHTML
    renderShop(res.shop, null)
    $('#recs-shop-out').innerHTML = $('#shop-out').innerHTML
    $('#shop-out').innerHTML = keep
  }
}

const i18nSafe = (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 40)

function fillMockups(gaps, made) {
  made.forEach((m, i) => {
    if (gaps[i] && m.image) gaps[i].mockup = m.image  // "See it on me" hands the try-on this picture
    const p = $(`[data-mock-piece="${i}"]`), b = $(`[data-mock-board="${i}"]`)
    if (p) p.innerHTML = m.image ? `<img src="/api/mockups/${esc(m.image)}" alt="${esc(m.piece)}" />` : ''
    if (b) b.innerHTML = m.board ? `<img src="/api/mockups/${esc(m.board)}" alt="The outfit with ${esc(m.piece)}" />` : ''
  })
}

// pictures of the 3 pieces and their outfits (image model, own key); the text shows first, pictures fill in
async function drawMockups(res) {
  const gaps = res.recommendations.gaps
  try {
    const r = await postJSON('/api/recommend/mockups', { look: res.look || '', gaps })
    updateMeter(r.run)
    fillMockups(gaps, r.result)
  } catch (e) {
    $$('[data-mock-piece], [data-mock-board]').forEach((el) => { el.innerHTML = '' })
    const msg = /OPENAI_API_KEY/.test(e.message) ? 'Pictures need your own OpenAI key in .env.' : `Couldn't draw the pictures: ${e.message}`
    $('#recs-out .rec-gaps')?.insertAdjacentHTML('beforebegin', `<p class="muted small">${esc(msg)}</p>`)
  }
}

function initStylistRecs() {
  $('#recs-btn').addEventListener('click', () => runRecommend(false))
  $('#recs-shop-btn').addEventListener('click', () => runRecommend(true))
  // the last picks stay on the page across refreshes and data-set switches, like the day's plan
  let ask = 0  // only the newest load renders, so quick toggles can't show the picks twice
  const loadSaved = () => {
    const n = ++ask
    if (state.dataset === 'user') api('/api/recommend/saved').then((r) => {
      if (n === ask && state.dataset === 'user' && r?.result && !$('#recs-out').innerHTML.trim()) { $('#recs-look').value = r.result.look || ''; showRecs(r.result, null) }
    }).catch(() => {})
  }
  loadSaved()
  syncShopDefaults()
  $$('.dataset-toggle button').forEach((b) => b.addEventListener('click', () => setTimeout(() => { syncShopDefaults(); $('#recs-out').innerHTML = ''; $('#recs-status').innerHTML = ''; loadSaved() }, 0)))
}

function init() {
  const today = new Date()
  $('#day').value = new Date(today.getTime() - today.getTimezoneOffset() * 60000).toISOString().slice(0, 10)
  $$('.dataset-toggle button').forEach((b) => {
    b.classList.toggle('active', b.dataset.ds === state.dataset)
    b.addEventListener('click', () => setDataset(b.dataset.ds))
  })
  $$('#tabs button').forEach((b) => b.addEventListener('click', () => showTab(b.dataset.tab)))
  $('#day').addEventListener('change', loadDay)
  $('#plan-btn').addEventListener('click', () => planDay(false))
  $('#photo-form').addEventListener('submit', addPhoto)
  $('#photo-file').addEventListener('change', (e) => { if (e.target.files.length) addPhoto() })
  $('#shop-form').addEventListener('submit', shop)
  initStylistRecs()
  $('#shop-examples').innerHTML = EXAMPLES.map((e) => `<button class="chip" type="button">${esc(e)}</button>`).join('')
  $$('#shop-examples .chip').forEach((c) => c.addEventListener('click', () => { $('#shop-q').value = c.textContent; $('#shop-q').focus() }))
  $('#save-profile').addEventListener('click', saveProfile)
  $('#ics-form').addEventListener('submit', uploadICS)
  $('#cal-link-form').addEventListener('submit', connectCalendar)
  $('#cal-unlink').addEventListener('click', disconnectCalendar)
  refreshCalendarStatus()
  $('#refresh-runs').addEventListener('click', loadRuns)
  initDrapeTest()
  $('#me-photo-form').addEventListener('submit', uploadMePhoto)
  $('#me-photo-delete').addEventListener('click', deleteMePhoto)
  $('#place-form').addEventListener('submit', uploadPlace)
  initCamera()
  initCloseups()
  refreshPhotoStatus()
  document.addEventListener('click', (e) => { if (e.target.closest('#analyze-style-btn')) runAnalysis('style') })
  $('#season-override').addEventListener('change', () => overrideSeason())
  initColorStyle()
  restoreOutfit()
  initFittingControls()
  refreshStatus()
  api('/api/runs?limit=1').then((r) => r[0] && updateMeter(r[0])).catch(() => {})
  loadAll()
  const hash = location.hash.replace('#', '')
  if (hash) showTab(hash)
}

init()
// handy for debugging and for grabbing report screenshots
window.closetTwin = state
window.closetTwinApi = { addToOutfit, openFitting, renderOutfit, setScene, setMove, api, postJSON, q, esc, toast, updateMeter, itemImg, renderPlan, renderRecs, renderShop, listenedHTML, loadCloset, renderCloset, showTab, shop, syncShopDefaults, working, showError, noteCard }
