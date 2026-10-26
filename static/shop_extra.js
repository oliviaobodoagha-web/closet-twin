// Shop extras: recreate an inspiration look (screenshots or a Pinterest board) and a price tracker.
const $ = (s, el = document) => el.querySelector(s)
const $$ = (s, el = document) => [...el.querySelectorAll(s)]
const S = () => window.closetTwin
const A = () => window.closetTwinApi

// ---- inspiration
let inspo = null
async function runInspo(makeRequest, label) {
  const stop = A().working($('#inspo-status'), label, ['Stylist: reading the look', 'Matching your closet'])
  $('#inspo-out').innerHTML = ''
  try {
    const r = await makeRequest()
    stop()
    $('#inspo-status').innerHTML = ''
    A().updateMeter(r.run)
    inspo = r.result
    renderInspo()
  } catch (e) {
    stop()
    A().showError($('#inspo-status'), e)
  }
}

function renderInspo() {
  const { esc, itemImg } = A()
  const look = inspo.look || {}
  const owned = (inspo.recreate?.item_ids || []).map((id) => S().closet.find((x) => x.id === id)).filter(Boolean)
  const missing = inspo.missing || []
  $('#inspo-out').innerHTML = `
    <p class="inspo-summary">${esc(look.summary || '')}</p>
    <div>${(look.vibe_words || []).map((w) => `<span class="tag pink">${esc(w)}</span>`).join('')}</div>
    <h4>From your closet</h4>
    ${owned.length ? `<div class="thumbs">${owned.map((it) => `<div class="thumb"><div class="img">${itemImg(it)}</div>${esc(it.name)}</div>`).join('')}</div>
      ${inspo.recreate?.how ? `<p class="small">${esc(inspo.recreate.how)}</p>` : ''}
      <button type="button" class="btn small primary" id="inspo-try">Try it on me</button>` : '<p class="muted small">Nothing in your closet matches yet.</p>'}
    ${missing.length ? `<h4>Missing pieces</h4><ul class="inspo-missing">${missing.map((m, i) => `<li><span><b>${esc(m.description)}</b> <span class="tag">${esc(m.category || '')}</span></span>
      <button type="button" class="btn small ghost" data-findmiss="${i}">Find it in my size →</button></li>`).join('')}</ul>` : ''}`
  $('#inspo-try')?.addEventListener('click', () => {
    S().outfit = []; S().zones = {}
    owned.forEach((it) => A().addToOutfit(it))
    A().openFitting()
  })
  $$('[data-findmiss]').forEach((b) => b.addEventListener('click', () => {
    const m = missing[+b.dataset.findmiss]
    A().showTab('shop')
    $('#shop-q').value = m.search_query || m.description
    $('#live-web').checked = true
    A().shop()
  }))
}

function initInspo() {
  $('#inspo-file').addEventListener('change', (e) => {
    const files = [...e.target.files]
    e.target.value = ''
    if (!files.length) return
    const fd = new FormData()
    fd.append('file', files[0], files[0].name)  // the server reads one screenshot per request
    if (files.length > 1) A().toast('Reading the first screenshot (one at a time for now)')
    fd.append('dataset', S().dataset)
    runInspo(() => A().api('/api/inspo/photo', { method: 'POST', body: fd }), 'Reading your screenshot…')
  })
  $('#inspo-form').addEventListener('submit', (e) => {
    e.preventDefault()
    const url = $('#inspo-url').value.trim()
    if (!url) return A().toast('Paste a Pinterest board link, or upload a screenshot')
    runInspo(() => A().postJSON('/api/inspo/pinterest', { dataset: S().dataset, url }), 'Reading your board…')
  })
}

// ---- price tracker
const pct = (n) => (n == null ? '' : `${n > 0 ? '+' : ''}${(+n).toFixed(1)}%`)
const money = (n) => (n == null ? '?' : `$${(+n).toFixed(2).replace(/\.00$/, '')}`)

function renderWatch(data) {
  const { esc } = A()
  const items = data?.items || []
  const trends = Object.entries(data?.trends || {})
  $('#watch-out').innerHTML = items.length ? `
    <ul class="watch-list">${items.map((w) => `<li>
      ${w.image ? `<img src="${esc(w.image)}" alt="" loading="lazy" />` : '<span class="w-ph">✦</span>'}
      <div class="w-main"><a href="${esc(w.url)}" target="_blank" rel="noopener noreferrer">${esc(w.name || w.url)}</a>
        <div class="small muted">${esc(w.store || '')}${w.lowest != null ? ` · lowest ${money(w.lowest)}` : ''}</div></div>
      <div class="w-price"><b>${money(w.current)}</b><div class="small ${w.change_pct < 0 ? 'down' : w.change_pct > 0 ? 'up' : 'muted'}">${pct(w.change_pct)}</div>
        ${w.dropped ? '<span class="tag drop">dropped</span>' : ''}</div>
      <button type="button" class="x" data-unwatch="${esc(w.id)}" title="Stop tracking">✕</button></li>`).join('')}</ul>
    ${trends.length ? `<div class="trends small">${trends.map(([store, t]) => `<div><b>${esc(store)}</b> · ${t.tracked} tracked · avg <span class="${t.avg_change_pct < 0 ? 'down' : t.avg_change_pct > 0 ? 'up' : ''}">${pct(t.avg_change_pct || 0)}</span>${t.dropped ? ` · ${t.dropped} dropped` : ''}</div>`).join('')}</div>` : ''}`
    : '<p class="muted small">Nothing tracked yet. Tap "☆ Track price" on any shop pick with a link.</p>'
}

async function loadWatch() {
  try { renderWatch(await A().api(`/api/watch?${A().q()}`)) } catch {
    $('#watch-out').innerHTML = '<p class="muted small">Price tracking isn\'t available on this server yet.</p>'
  }
}

async function checkPrices() {
  const btn = $('#watch-check')
  btn.disabled = true
  btn.textContent = 'Checking…'
  try {
    const r = await A().postJSON('/api/watch/check', { dataset: S().dataset })
    renderWatch(r.result)
    const drops = r.result?.drops || []
    A().toast(drops.length ? `Price drop on ${drops.length} item${drops.length > 1 ? 's' : ''}!` : 'No drops yet. I\'ll keep watching.')
  } catch (e) { A().toast(`Couldn't check prices: ${e.message}`) } finally {
    btn.disabled = false
    btn.textContent = '↻ Check prices'
  }
}

document.addEventListener('click', async (e) => {
  const t = e.target.closest('[data-track]')
  if (t) {
    t.disabled = true
    try {
      await A().postJSON('/api/watch', { dataset: S().dataset, ...JSON.parse(t.dataset.track) })
      t.textContent = '★ Tracking'
      A().toast('Tracking the price. Check it in the Price tracker below.')
      loadWatch()
    } catch (err) { t.disabled = false; A().toast(`Couldn't track it: ${err.message}`) }
    return
  }
  const u = e.target.closest('[data-unwatch]')
  if (u) {
    try {
      await A().api(`/api/watch/${encodeURIComponent(u.dataset.unwatch)}?${A().q()}`, { method: 'DELETE' })
      loadWatch()
    } catch (err) { A().toast(`Couldn't remove it: ${err.message}`) }
  }
})

function init() {
  if (!window.closetTwinApi) return setTimeout(init, 200)
  initInspo()
  $('#watch-check').addEventListener('click', checkPrices)
  document.addEventListener('ct:dataset', () => { $('#inspo-out').innerHTML = ''; loadWatch() })
  loadWatch()
}

init()
