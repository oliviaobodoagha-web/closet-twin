// Today extras: quick-tap outfit check-ins on each plan block, "show me another option",
// the saved plan for the selected day, yesterday's check-in banner, and today's look on the real you.
const $ = (s, el = document) => el.querySelector(s)
const $$ = (s, el = document) => [...el.querySelectorAll(s)]
const S = () => window.closetTwin
const A = () => window.closetTwinApi
const TAGS = [['wore_it', 'Wore it'], ['banger', 'Banger 🔥'], ['compliments', 'Got compliments ✨'], ['comfy', 'So comfy'], ['not_me', 'Not me'], ['uncomfortable', 'Uncomfortable'], ['too_warm', 'Too warm'], ['too_cold', 'Too cold']]
const day = () => $('#day').value
const realToday = () => { const d = new Date(); return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10) }

function quickTapHTML(extra = '') {
  return `<div class="quicktap">
    <div class="chips">${TAGS.map(([k, l]) => `<button type="button" class="chip" data-qt="${k}">${l}</button>`).join('')}</div>
    <div class="row gap wrap qt-row"><input type="text" class="qt-note" maxlength="160" placeholder="Note (optional)" />
      <button type="button" class="btn small primary" data-qtsave>Save</button>${extra}</div></div>`
}

async function sendCheckin(box, { dayStr, label, ids }) {
  const tags = $$('[data-qt].active', box).map((b) => b.dataset.qt)
  const note = $('.qt-note', box).value.trim()
  if (!tags.length && !note) { A().toast('Tap how it went first'); return null }
  try {
    const r = await A().postJSON('/api/outfit/feedback', { dataset: S().dataset, day: dayStr, block_label: label, item_ids: ids, tags, note })
    A().toast(r.learned?.length ? `Learned: ${r.learned.join(' · ')}` : 'Noted. Thank you!')
    window.ctLoadMemory?.(true)
    return { tags, note }
  } catch (e) { A().toast(`Couldn't save that: ${e.message}`); return null }
}

const blockIds = (b) => b.item_ids || (b.items || []).map((it) => it.id)

// ---- plan blocks
function decoratePlan() {
  const res = S().lastPlanRes
  if (!res) return
  $$('#plan-out .block[data-bi]').forEach((card) => {
    if (card.querySelector('.quicktap')) return
    card.insertAdjacentHTML('beforeend', quickTapHTML('<button type="button" class="btn small ghost" data-swap>↻ Show another option</button>'))
  })
  showRealYou()
}

async function swapBlock(card, reason) {
  const i = +card.dataset.bi
  const res = S().lastPlanRes
  const btn = $('[data-swap]', card)
  btn.disabled = true
  btn.textContent = 'Finding another…'
  try {
    const r = await A().postJSON('/api/outfit/swap', { dataset: S().dataset, day: day(), block_index: i, block: res.plan.blocks[i], reason })
    res.plan.blocks[i] = r.result.block
    A().updateMeter(r.run)
    A().renderPlan(res, S().lastPlanRun)
    $(`#plan-out .block[data-bi="${i}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    A().toast('Here is another option.')
  } catch (e) {
    A().toast(`Couldn't find another option: ${e.message}`)
    btn.disabled = false
    btn.textContent = '↻ Show another option'
  }
}

document.addEventListener('click', async (e) => {
  const chip = e.target.closest('[data-qt]')
  if (chip) {
    chip.classList.toggle('active')
    const card = chip.closest('#plan-out .block[data-bi]')
    // "Not me" on a plan block: log it and show another option right away
    if (card && chip.dataset.qt === 'not_me' && chip.classList.contains('active')) {
      const b = S().lastPlanRes.plan.blocks[+card.dataset.bi]
      const sent = await sendCheckin($('.quicktap', card), { dayStr: day(), label: b.label, ids: blockIds(b) })
      swapBlock(card, ['not_me', ...(sent?.tags || [])].join(', ') + (sent?.note ? `: ${sent.note}` : ''))
    }
    return
  }
  const save = e.target.closest('[data-qtsave]')
  if (save) {
    const card = save.closest('#plan-out .block[data-bi]')
    if (card) {
      const b = S().lastPlanRes.plan.blocks[+card.dataset.bi]
      if (await sendCheckin($('.quicktap', card), { dayStr: day(), label: b.label, ids: blockIds(b) })) save.textContent = 'Saved ✓'
      return
    }
    const banner = save.closest('.checkin')
    if (banner) {
      const p = banner._pending
      if (await sendCheckin(banner, { dayStr: p.day, label: p.block_label, ids: p.item_ids || [] })) $('#checkin-banner').innerHTML = ''
    }
    return
  }
  const sw = e.target.closest('[data-swap]')
  if (sw) {
    const card = sw.closest('.block[data-bi]')
    const tags = $$('[data-qt].active', card).map((b) => b.dataset.qt)
    swapBlock(card, [tags.join(', '), $('.qt-note', card).value.trim()].filter(Boolean).join(': ') || 'show me another option')
  }
  if (e.target.closest('.checkin-x')) $('#checkin-banner').innerHTML = ''
})

// ---- saved plan for the selected day (so Today doesn't re-plan every visit)
let loadedFor = ''
async function loadSaved() {
  const key = `${S().dataset}|${day()}`
  if (loadedFor !== key) { $('#plan-out').innerHTML = ''; $('#today-real').innerHTML = ''; S().lastPlanRes = null }
  loadedFor = key
  try {
    const r = await A().api(`/api/plan/saved?${A().q({ day: day() })}`)
    if (r?.plan && loadedFor === key && !$('#plan-out').innerHTML.trim()) A().renderPlan(r.plan, null)
  } catch { /* not available yet: just plan as usual */ }
}

// ---- yesterday's check-in
async function loadCheckin() {
  const el = $('#checkin-banner')
  el.innerHTML = ''
  const mem = await window.ctLoadMemory?.(true)
  const p = mem?.pending_checkin
  if (!p) return
  const { esc } = A()
  const names = (p.item_ids || []).map((id) => S().closet.find((x) => x.id === id)?.name).filter(Boolean)
  el.innerHTML = `<div class="card glass checkin"><div class="row between"><div class="kicker-sm">Quick check-in</div><button type="button" class="x checkin-x" title="Later">✕</button></div>
    <h3>How was yesterday's ${esc(p.block_label || '')} outfit?</h3>
    ${names.length ? `<p class="muted small" style="margin:0 0 6px">${names.map(esc).join(' · ')}</p>` : ''}
    ${quickTapHTML()}</div>`
  $('.checkin', el)._pending = p
}

// ---- today's look on the real you
const real = { busy: false, key: '' }
async function showRealYou() {
  const el = $('#today-real')
  const plan = S().lastPlanRes?.plan
  if (S().dataset !== 'user' || !plan) { el.innerHTML = ''; return }
  const b = plan.blocks.find((x) => x.scene !== 'gym' && !/gym|workout|spin/i.test(x.label || '')) || null
  if (!b || !(b.items || []).length) { el.innerHTML = ''; return }
  const key = b.items.map((i) => String(i.id || i.name || '')).sort().join('|') + `@${b.scene}#standing`
  if (real.busy || (real.key === key && el.innerHTML)) return
  real.key = key
  const { esc } = A()
  let st, gal
  try {
    [st, gal] = await Promise.all([A().api('/api/photo-tryon/status'), A().api('/api/tryons')])
  } catch { el.innerHTML = ''; return }
  if (!(st.key_set && st.has_photo && st.consent)) { el.innerHTML = ''; return }
  const head = `<div class="kicker-sm">On the real you</div><h3>${esc(b.label)}</h3>`
  const show = (img) => {
    el.innerHTML = `<div class="card glass real-today">${head}<button type="button" class="real-img" title="Open in the Fitting Room"><img src="/api/tryons/user/${esc(img)}" alt="You in today's ${esc(b.label)} outfit" /></button>
      <p class="muted small">${b.items.map((i) => esc(i.name)).join(' · ')} · tap to open the Fitting Room (not right? “Tell me” there and I'll redo it)</p></div>`
    $('.real-img', el).addEventListener('click', () => { S().outfit = [...b.items]; S().zones = {}; A().openFitting(b.scene) })
  }
  const hit = (Array.isArray(gal) ? gal : []).find((g) => g.key === key)
  if (hit) return show(hit.image)
  const flag = `ct-daily-photo-${realToday()}`
  let made = false
  try { made = !!localStorage.getItem(flag) } catch { /* storage off */ }
  if (made) { el.innerHTML = ''; return }  // one automatic photo per day; more from the Fitting Room
  try { localStorage.setItem(flag, key) } catch { /* storage off */ }
  real.busy = true
  el.innerHTML = `<div class="card glass real-today">${head}<div class="status"><div class="spinner"></div><div class="small">Dressing the real you in today's ${esc(b.label)} outfit… about 15–30 s</div></div></div>`
  try {
    const r = await A().postJSON('/api/photo-tryon', { dataset: 'user', items: b.items, scene: b.scene, pose: 'standing' })
    const g2 = await A().api('/api/tryons')
    const img = (Array.isArray(g2) ? g2 : []).find((g) => g.key === key)?.image || r.image || r.result?.image
    if (img) show(img); else el.innerHTML = ''
  } catch (e) {
    el.innerHTML = `<div class="card glass real-today">${head}<p class="muted small">Couldn't make today's photo: ${esc(e.message)}</p></div>`
  } finally { real.busy = false }
}

function init() {
  if (!window.closetTwinApi || !window.ctLoadMemory) return setTimeout(init, 200)
  document.addEventListener('ct:plan-rendered', decoratePlan)
  document.addEventListener('ct:dataset', () => { real.key = ''; loadSaved(); loadCheckin() })
  $('#day').addEventListener('change', loadSaved)
  loadSaved()
  // wait a beat so the closet is loaded for item names in the banner
  setTimeout(loadCheckin, 600)
}

init()
