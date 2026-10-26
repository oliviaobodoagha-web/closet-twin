// Closet extras: the "+ Add to my wardrobe" card (one or many photos or product links), the size/fit
// follow-up after items are added (prefilled with your guessed size), wear memory on closet cards (worn N×, resting), and "Returned".
const $ = (s, el = document) => el.querySelector(s)
const $$ = (s, el = document) => [...el.querySelectorAll(s)]
const S = () => window.closetTwin
const A = () => window.closetTwinApi
const RETURN_REASONS = [['too_small', 'Too small'], ['too_big', 'Too big'], ['wrong_length', 'Wrong length'], ['uncomfortable', 'Uncomfortable'], ['color', 'Color'], ['quality', 'Quality'], ['not_my_style', 'Not my style']]
const FITS = ['perfect', 'snug', 'tight', 'loose']
const BULK = 16  // per run, matches MAX_BULK_ADD on the server
const ROUNDS_AT_ONCE = 2  // rounds uploading at the same time (each tags 8 photos at once on the server)

// wear memory is shared with the Today tab (pending check-in)
let memo = null
window.ctLoadMemory = async (force = false) => {
  if (memo && !force && memo.ds === S().dataset) return memo.data
  try {
    const data = await A().api(`/api/wardrobe/memory?${A().q()}`)
    memo = { ds: S().dataset, data }
  } catch { memo = { ds: S().dataset, data: null } }
  return memo.data
}

function sizeLine(it) {
  const { esc } = A()
  if (it.size_label) return `<div class="size-line">Size ${esc(it.size_label)}${it.fit_verdict ? ` · fits ${esc(it.fit_verdict)}` : ''}</div>`
  const g = it.size_guess
  return g ? `<div class="size-line guess" title="Guessed from ${esc(g.why)}">Your size: likely ${esc(g.size)}</div>` : ''
}

const fmtDate = (d) => { try { return new Date(d.length === 10 ? d + 'T12:00' : d).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) } catch { return d } }

async function decorateCloset() {
  const { esc } = A()
  const mem = await window.ctLoadMemory()
  const today = new Date().toISOString().slice(0, 10)
  $$('#closet-grid .card.item[data-id]').forEach((card) => {
    const it = S().closet.find((x) => x.id === card.dataset.id)
    if (!it || card.querySelector('.wear-line')) return
    const w = mem?.wear?.[it.id]
    const returned = it.returned || it.status === 'returned'
    const resting = w?.resting_until && w.resting_until.slice(0, 10) > today
    const brandFit = it.brand && mem?.brand_fit?.[it.brand]
    const bits = [w?.wears ? `worn ${w.wears}×` : 'not worn yet', w?.last_worn ? `last worn ${fmtDate(w.last_worn)}` : ''].filter(Boolean)
    card.querySelector('.name').insertAdjacentHTML('afterend', `<div class="wear-line small muted">${esc(bits.join(' · '))}
      ${resting ? `<span class="tag rest" title="Resting until ${esc(fmtDate(w.resting_until))}">resting</span>` : ''}
      ${returned ? '<span class="tag returned-tag">returned</span>' : ''}
      ${sizeLine(it)}
      ${brandFit ? `<div class="brand-fit">${esc(it.brand)}: ${esc(brandFit)}</div>` : ''}</div>`)
    card.classList.toggle('returned', !!returned)
  })
}

document.addEventListener('change', async (e) => {
  const sel = e.target.closest('[data-return]')
  if (!sel || !sel.value) return
  const it = S().closet.find((x) => x.id === sel.dataset.return)
  const reason = sel.value
  try {
    const r = await A().postJSON(`/api/closet/${encodeURIComponent(it.id)}/return`, { dataset: S().dataset, reason, note: '' })
    Object.assign(it, r.item || {}, { returned: true })
    A().toast(r.learned?.length ? `Returned. Learned: ${r.learned.join(' · ')}` : `Marked ${it.name} as returned.`)
    window.ctLoadMemory(true)
    A().renderCloset()
  } catch (err) {
    sel.value = ''
    A().toast(`Couldn't mark it returned: ${err.message}`)
  }
})

// ---- edit: fix what the cataloger got wrong (and turn a sideways photo)
const SECTIONS = [['tops', 'Tops & blouses'], ['layers', 'Tanks & camis'], ['pants', 'Pants & shorts'], ['skirts', 'Skirts'], ['dresses', 'Dresses'],
  ['blazers', 'Blazers'], ['jackets', 'Jackets & coats'], ['activewear', 'Activewear'], ['swim', 'Swim'], ['shoes', 'Shoes'], ['accessories', 'Accessories']]

// "What's wrong?" for a product shot: her answers fix the piece and go into every redraw of it
const REDO_ISSUES = [['color', 'Color'], ['type', 'Product type'], ['neckline', 'Neckline / collar'], ['sleeves', 'Sleeves'],
  ['shape', 'Length / shape'], ['pattern', 'Pattern / texture'], ['details', 'Buttons, zips, logos'], ['wrinkles', 'Wrinkled'],
  ['extra', 'Added / missing parts'], ['angle', 'Not upright / cut off']]

function redoBox(it) {
  const { esc } = A()
  const fix = { color: `<input class="hidden" data-fix="color" maxlength="30" placeholder="What color is it? e.g. burgundy" value="" />`,
    type: `<input class="hidden" data-fix="type" maxlength="30" placeholder="What is it? e.g. blouse, quarter-zip" value="" />` }
  return `<div class="redo-box stack gap">
    <div class="small"><b>What's wrong with the product shot?</b> <span class="muted">Your answers stay with ${esc(it.name)} for every redo.</span></div>
    <div class="redo-grid">${REDO_ISSUES.map(([k, l]) => `<label class="redo-opt"><input type="checkbox" name="issue" value="${k}" /> ${l}</label>${fix[k] || ''}`).join('')}</div>
    <label class="redo-opt"><input type="checkbox" data-more /> Other / add detail</label>
    <textarea class="hidden" data-detail maxlength="300" rows="2" placeholder="e.g. the collar has lace trim and the cuffs are ruffled"></textarea>
    <div><button type="button" class="btn small primary" data-redo-go>✦ Redo with these fixes</button></div>
  </div>`
}

function openEdit(card, it) {
  const { esc, itemImg } = A()
  card.querySelector('.edit-box')?.remove()
  card.insertAdjacentHTML('beforeend', `<form class="edit-box stack gap" data-eid="${esc(it.id)}">
    <label class="small">Name<input name="name" value="${esc(it.name)}" maxlength="80" /></label>
    <div class="row gap wrap">
      <label class="small">Section<select name="section">${SECTIONS.map(([k, l]) => `<option value="${k}" ${k === (it.section || it.category) ? 'selected' : ''}>${l}</option>`).join('')}</select></label>
      <label class="small">Kind<input name="subtype" value="${esc(it.subtype || '')}" maxlength="30" placeholder="sweater, jacket…" /></label>
      <label class="small">Color<input name="color" value="${esc(it.colors?.[0]?.name || '')}" maxlength="30" /></label>
    </div>
    ${!it.image ? `<div class="link-paste" data-addphoto tabindex="0"><b>Add photo:</b> copy the product image on the store's page (right-click → Copy Image), click here and press ⌘V, drag it in, or <label class="linklike">choose a file<input type="file" accept="image/*" hidden data-addphoto-file /></label>.</div>` : ''}
    ${it.image ? `<div class="row gap wrap"><button type="button" class="btn small ghost" data-rot="270">↺ Turn left</button><button type="button" class="btn small ghost" data-rot="90">↻ Turn right</button>
      <button type="button" class="btn small ghost" data-reshot>✦ ${it.shot ? 'Redo' : 'Make'} product shot</button><span class="small muted" data-rotnote></span></div>` : ''}
    ${it.status === 'returned' || it.returned ? '' : `<label class="small">I returned it<select data-return="${esc(it.id)}"><option value="">No</option>${RETURN_REASONS.map(([k, l]) => `<option value="${k}">Yes: ${l.toLowerCase()}</option>`).join('')}</select></label>`}
    <div class="row gap"><button class="btn small primary" type="submit">Save</button><button class="btn small ghost" type="button" data-cancel>Cancel</button></div>
  </form>`)
  const box = card.querySelector('.edit-box')
  let rotate = 0
  box.addEventListener('click', (e) => {
    const r = e.target.closest('[data-rot]')
    if (r) {
      rotate = (rotate + Number(r.dataset.rot)) % 360
      card.querySelector('.img img')?.style.setProperty('transform', `rotate(${rotate}deg)`)
      box.querySelector('[data-rotnote]').textContent = rotate ? 'saves on Save' : ''
    }
    if (e.target.closest('[data-reshot]') && !it.shot) {
      const b = e.target.closest('[data-reshot]')  // no shot yet: just make one
      b.disabled = true; b.textContent = 'Making it… about 20 s'
      A().postJSON('/api/closet/shots', { dataset: S().dataset, ids: [it.id] })
        .then(async (r) => { A().updateMeter(r.run); A().toast('Product shot ready'); await A().loadCloset(); A().renderCloset(it.id) })
        .catch((err) => { b.disabled = false; b.textContent = '✦ Make product shot'; A().toast(`Couldn't make it: ${err.message}`) })
    } else if (e.target.closest('[data-reshot]')) {
      const open = box.querySelector('.redo-box')
      if (open) open.remove()
      else box.querySelector('[data-reshot]').closest('.row').insertAdjacentHTML('afterend', redoBox(it))
    }
    const go = e.target.closest('[data-redo-go]')
    if (go) {
      const rb = box.querySelector('.redo-box')
      const issues = [...rb.querySelectorAll('input[name=issue]:checked')].map((x) => x.value)
      const val = (n) => (issues.includes(n) ? rb.querySelector(`[data-fix=${n}]`).value.trim() : '')
      const detail = rb.querySelector('[data-more]').checked ? rb.querySelector('[data-detail]').value.trim() : ''
      if (!issues.length && !detail) { A().toast('Tick what looks wrong first.'); return }
      go.disabled = true; go.textContent = 'Redrawing… about 20 s'
      A().postJSON(`/api/closet/${encodeURIComponent(it.id)}/reshoot`, { dataset: S().dataset, issues, color: val('color'), kind: val('type'), detail })
        .then(async (r) => { A().updateMeter(r.run); A().toast(`New product shot of ${r.result.item.name} ready`); await A().loadCloset(); A().renderCloset(it.id) })
        .catch((err) => { go.disabled = false; go.textContent = '✦ Redo with these fixes'; A().toast(`Couldn't redo it: ${err.message}`) })
    }
    if (e.target.closest('[data-cancel]')) { card.querySelector('.img img')?.style.removeProperty('transform'); box.remove() }
  })
  const zone = box.querySelector('[data-addphoto]')
  if (zone) {
    const send = async (file) => {
      if (!file || !/^image\//.test(file.type)) return A().toast('That isn’t an image.')
      zone.innerHTML = '<b>Adding the photo…</b>'
      try {
        const fd = new FormData()
        fd.append('file', file, 'photo'); fd.append('dataset', S().dataset)
        const res = await fetch(`/api/closet/${encodeURIComponent(it.id)}/photo`, { method: 'POST', body: fd })
        const r = await res.json()
        if (!res.ok || r.ok === false) throw new Error(r.detail || r.error || `HTTP ${res.status}`)
        A().toast(`Photo added to ${it.name}`)
        await A().loadCloset(); A().renderCloset(it.id)
      } catch (err) { zone.innerHTML = `<b>Couldn't add it:</b> ${A().esc(err.message)}` }
    }
    zone.addEventListener('paste', (e) => { const f = imageFrom(e.clipboardData?.items); if (f) { e.preventDefault(); send(f) } })
    zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('over') })
    zone.addEventListener('dragleave', () => zone.classList.remove('over'))
    zone.addEventListener('drop', (e) => { e.preventDefault(); zone.classList.remove('over'); send(imageFrom(e.dataTransfer.files)) })
    zone.querySelector('[data-addphoto-file]').addEventListener('change', (e) => send(e.target.files[0]))
  }
  box.addEventListener('change', (e) => {
    // ticking Color / Product type opens its "what is it really?" field; "Add detail" opens the note
    const c = e.target.closest('input[name=issue], [data-more]')
    if (!c) return
    const f = box.querySelector(c.dataset.more !== undefined ? '[data-detail]' : `[data-fix=${c.value}]`)
    if (f) { f.classList.toggle('hidden', !c.checked); if (c.checked) f.focus() }
  })
  box.addEventListener('submit', async (e) => {
    e.preventDefault()
    const f = new FormData(box)
    try {
      const r = await A().postJSON(`/api/closet/${encodeURIComponent(it.id)}/edit`, {
        dataset: S().dataset, name: f.get('name'), section: f.get('section') === (it.section || it.category) ? null : f.get('section'), subtype: f.get('subtype'), color: f.get('color'), rotate,
      })
      Object.assign(it, r.item, { v: Date.now() })
      A().toast(`Saved ${it.name}.${r.cleared_tryons ? ' Old try-ons of it cleared, so the next one uses the fix.' : ''}`)
      A().renderCloset(it.id)
    } catch (err) { A().toast(`Couldn't save: ${err.message}`) }
  })
}

document.addEventListener('click', (e) => {
  const b = e.target.closest('[data-edit]')
  if (!b) return
  openEdit(b.closest('.card.item'), S().closet.find((x) => x.id === b.dataset.edit))
})

// ---- add card: Photo | Paste a link
function setMode(mode) {
  $$('#add-modes .chip').forEach((b) => b.classList.toggle('active', b.dataset.addmode === mode))
  $('#photo-form').classList.toggle('hidden', mode !== 'photo')
  $('#link-form').classList.toggle('hidden', mode !== 'link')
  $('#receipt-form').classList.toggle('hidden', mode !== 'receipt')
  if (mode === 'link') $('#link-url').focus()
}

// ---- a product photo she copied from the store page (for stores that don't let apps read their pages)
let pastedPhoto = null

function setPasted(file) {
  pastedPhoto = file
  const box = $('#link-paste')
  box.querySelector('.lp-empty').classList.toggle('hidden', !!file)
  box.querySelector('.lp-full').classList.toggle('hidden', !file)
  box.classList.toggle('has-photo', !!file)
  if (file) box.querySelector('.lp-full img').src = URL.createObjectURL(file)
}

function imageFrom(items) {
  for (const it of items || []) {
    const f = it.kind === 'file' ? it.getAsFile() : it
    if (f && /^image\//.test(f.type)) return f
  }
  return null
}

document.addEventListener('paste', (e) => {
  if (document.activeElement?.closest?.('[data-addphoto]')) return  // pasting a photo into a piece's Edit box
  if (!$('#receipt-form').classList.contains('hidden')) {  // Receipt card: a pasted screenshot is the receipt
    const r = imageFrom(e.clipboardData?.items)
    if (r) { e.preventDefault(); readReceipt(r) }
    return
  }
  if ($('#link-form').classList.contains('hidden')) return  // only while the Link card is open
  const f = imageFrom(e.clipboardData?.items)
  if (!f) return  // plain text (a link) pastes as usual
  e.preventDefault()
  setPasted(f)
  A().toast('Product photo added. Paste the link too, then press Add.')
})
$('#link-paste').addEventListener('dragover', (e) => { e.preventDefault(); e.currentTarget.classList.add('over') })
$('#link-paste').addEventListener('dragleave', (e) => e.currentTarget.classList.remove('over'))
$('#link-paste').addEventListener('drop', async (e) => {
  e.preventDefault()
  e.currentTarget.classList.remove('over')
  let f = imageFrom(e.dataTransfer.files)
  const src = !f && (e.dataTransfer.getData('text/uri-list') || '').split('\n').find((u) => /^https?:/.test(u))
  if (src) {
    // a photo dragged from another tab arrives as its address; the browser can fetch it if the store allows
    try { const b = await (await fetch(src)).blob(); if (/^image\//.test(b.type)) f = new File([b], 'product', { type: b.type }) } catch {}
    if (!f) return A().toast("That store won't hand the photo over by dragging. Right-click it → Copy Image, then ⌘V here.")
  }
  if (f) setPasted(f)
})
$('#link-paste').addEventListener('click', (e) => { if (e.target.closest('[data-lp-clear]')) setPasted(null) })

async function addLinkWithPhoto(url) {
  const stop = A().working($('#photo-status'), 'Adding the product photo…', ['Tagging the photo you pasted'])
  try {
    const fd = new FormData()
    fd.append('file', pastedPhoto, 'product.png')
    fd.append('url', url || '')
    fd.append('dataset', S().dataset)
    const res = await fetch('/api/closet/link-photo', { method: 'POST', body: fd })
    const r = await res.json()
    if (!res.ok || r.ok === false) throw new Error(r.detail || r.error || `HTTP ${res.status}`)
    stop()
    return r
  } catch (e) { stop(); throw e }
}

async function addLink(ev) {
  ev.preventDefault()
  const urls = $('#link-url').value.split(/\s+/).map((u) => u.trim()).filter((u) => /^https?:\/\//i.test(u))
  if (!urls.length && !pastedPhoto) return A().toast('Paste a product link (or a product photo) first')
  if (S().dataset === 'sample') return A().toast('Switch to My closet first; the Sample closet is for practice.')
  const btn = $('#link-form button[type=submit]')
  btn.disabled = true
  try {
    if (urls.length > 1 && !pastedPhoto) return await bulkAdd(urls.map((u) => ({ url: u })), 'links')
    if (urls.length > 1) return A().toast('A pasted photo goes with one link: keep just its link in the box.')
    const stop = A().working($('#photo-status'), 'Reading the product page…', ['Reading the link'])
    try {
      const r = pastedPhoto ? (stop(), await addLinkWithPhoto(urls[0])) : await A().postJSON('/api/closet/link', { dataset: S().dataset, url: urls[0] })
      setPasted(null)
      if (r.result.photo_from === 'pasted') {  // a pasted store photo may show a model: redraw just the piece
        A().postJSON('/api/closet/shots', { dataset: S().dataset, ids: [r.result.id] })
          .then(async (x) => { A().updateMeter(x.run); await A().loadCloset(); A().renderCloset(r.result.id) })
          .catch((err) => A().toast(`Product shot didn't finish: ${err.message}`))
      }
      stop()
      $('#photo-status').innerHTML = `<div class="status"><div style="font-size:22px;color:var(--green)">✓</div><div><b>Added: ${A().esc(r.result.name)}</b><div class="muted small">${A().esc(r.result.category || '')} · ${A().esc(r.result.subtype || '')}</div></div></div>`
      A().updateMeter(r.run)
      $('#link-url').value = ''
      S().filter = 'all'
      await A().loadCloset()
      A().renderCloset(r.result.id)
      showFollowup([S().closet.find((x) => x.id === r.result.id) || r.result])
    } catch (e) {
      stop()
      A().showError($('#photo-status'), e)
      if (/Copy Image/.test(e.message)) { $('#link-paste').classList.add('nudge'); $('#link-paste').focus() }
    }
  } finally { btn.disabled = false }
}

// ---- receipt: read it, tick what to add, each piece arrives with its printed size and price
let receiptRead = null

async function readReceipt(file) {
  if (S().dataset === 'sample') return A().toast('Switch to My closet first; the Sample closet is for practice.')
  const { esc } = A()
  const stop = A().working($('#photo-status'), 'Reading the receipt…', ['Receipt Reader: finding what you bought'])
  $('#receipt-lines').innerHTML = ''
  try {
    const fd = new FormData()
    fd.append('file', file, file.name || 'receipt')
    fd.append('dataset', S().dataset)
    const res = await fetch('/api/closet/receipt', { method: 'POST', body: fd })
    const r = await res.json()
    stop()
    if (!res.ok || r.ok === false) throw new Error(r.detail || r.error || `HTTP ${res.status}`)
    A().updateMeter(r.run)
    $('#photo-status').innerHTML = ''
    receiptRead = r.result
    const lines = receiptRead.lines
    if (!lines.length) return A().toast("I couldn't find any items on that receipt.")
    $('#receipt-lines').innerHTML = (receiptRead.incomplete ? `<div class="rc-warn small"><b>Some of this receipt may be missing:</b> ${esc(receiptRead.incomplete)} If you saved it as a PDF, save it again with <b>all pages</b>.</div>` : '')
      + `<div class="rc-head small"><b>${esc(receiptRead.store || 'Receipt')}</b>${receiptRead.date ? ` · ${esc(receiptRead.date)}` : ''} · tick what to add</div>
      ${lines.map((ln, i) => `<label class="rc-line ${ln.is_clothing ? '' : 'other'}"><input type="checkbox" data-rc="${i}" ${ln.is_clothing ? 'checked' : ''} />
        <span class="rc-name">${esc(ln.name)}${ln.confidence === 'low' ? ' <span class="muted">(check the name)</span>' : ''}</span>
        <span class="rc-meta small muted">${[ln.size && `size ${esc(ln.size)}`, ln.quantity > 1 && `×${ln.quantity}`, ln.price && `$${Number(ln.price).toFixed(2)}`, !ln.is_clothing && 'not clothing'].filter(Boolean).join(' · ')}</span></label>`).join('')}
      <div class="row gap"><button type="button" class="btn small primary" data-rc-add>Add to my closet</button></div>`
  } catch (e) { stop(); A().showError($('#photo-status'), e) }
}

async function addReceiptLines() {
  const picked = $$('#receipt-lines [data-rc]:checked').map((c) => receiptRead.lines[Number(c.dataset.rc)])
  if (!picked.length) return A().toast('Tick at least one item.')
  try {
    const r = await A().postJSON('/api/closet/receipt/add', { dataset: S().dataset, token: receiptRead.token || '', store: receiptRead.store, date: receiptRead.date, lines: picked })
    const filled = r.filled || []
    const withPhoto = r.added.filter((a) => a.image).concat(filled)
    const without = r.added.filter((a) => !a.image).length
    const s = (n) => (n === 1 ? '' : 's')
    $('#receipt-lines').innerHTML = `<div class="small">✓ ${[
      r.added.length && `Added ${r.added.length} piece${s(r.added.length)} with their sizes`,
      filled.length && `gave ${filled.length} piece${s(filled.length)} you'd already added ${filled.length === 1 ? 'its' : 'their'} photo`,
      r.skipped?.length && `${r.skipped.length} already in your closet`,
    ].filter(Boolean).join('; ')}${withPhoto.length ? `. ${withPhoto.length} photo${s(withPhoto.length)} cut from the receipt, product shots on the way` : ''}.${without ? ` ${without} had no photo on the receipt: give ${without === 1 ? 'it' : 'each'} one in <b>Edit → Add photo</b>.` : ''}</div>`
    if (withPhoto.length) {  // receipt thumbnails are small: redraw them as full product shots
      A().postJSON('/api/closet/shots', { dataset: S().dataset, ids: withPhoto.map((a) => a.id) })
        .then(async (x) => { A().updateMeter(x.run); await A().loadCloset(); A().renderCloset(); A().toast('Product shots ready') })
        .catch((err) => A().toast(`Product shots didn't finish: ${err.message}`))
    }
    S().filter = 'all'
    await A().loadCloset()
    A().renderCloset(r.added[0]?.id)
    if (r.added.length) showFollowup(r.added.map((a) => S().closet.find((x) => x.id === a.id) || a))
  } catch (e) { A().toast(`Couldn't add them: ${e.message}`) }
}

// ---- bulk add: photos or links in batches of 8, each batch one run (4 tagged at a time)
window.ctBulkPhotos = (files) => bulkAdd(files.map((f) => ({ file: f })), 'photos')

// one upload at a time: photos picked while one is running wait their turn (no tangled progress, no doubles)
const queue = []
let uploading = false

async function bulkAdd(jobs, kind) {
  if (S().dataset === 'sample') return A().toast('Switch to My closet first; the Sample closet is for practice.')
  queue.push([jobs, kind])
  if (uploading) {
    $('#photo-file').value = ''
    return A().toast(`Queued ${jobs.length} more; they start when this batch is done.`)
  }
  uploading = true
  try {
    while (queue.length) await runUpload(...queue.shift())
  } finally { uploading = false }
}

async function runUpload(jobs, kind) {
  const { esc } = A()
  const box = $('#photo-status')
  const label = (j) => j.file ? j.file.name : (() => { try { return new URL(j.url).hostname.replace(/^www\./, '') } catch { return j.url } })()
  jobs.forEach((j) => { if (j.file) j.thumb = URL.createObjectURL(j.file) })
  box.innerHTML = `<div class="up-panel">
    <div class="up-head"><b data-uptitle>Adding ${jobs.length} piece${jobs.length === 1 ? '' : 's'}…${queue.length ? ` (${queue.reduce((n, [j]) => n + j.length, 0)} more queued)` : ''}</b><span class="small muted" data-upcount>0 of ${jobs.length} done</span></div>
    <div class="up-bar"><span data-upbar style="width:3%"></span></div>
    <div class="up-list">${jobs.map((j, n) => `<div class="up-row" data-up="${n}">
      <div class="up-thumb">${j.thumb ? `<img src="${j.thumb}" alt="" />` : '🔗'}</div>
      <div class="up-text"><div class="small">${esc(label(j)).slice(0, 48)}</div><div class="small muted" data-upstate>waiting</div></div>
      <div class="up-icon" data-upicon></div></div>`).join('')}</div></div>`
  box.scrollIntoView({ behavior: 'smooth', block: 'center' })
  const row = (n) => box.querySelector(`[data-up="${n}"]`)
  const set = (n, state, icon, cls) => {
    const r = row(n)
    r.querySelector('[data-upstate]').innerHTML = state
    r.querySelector('[data-upicon]').innerHTML = icon
    r.className = `up-row ${cls || ''}`
  }
  let done = 0
  const tick = () => {
    box.querySelector('[data-upcount]').textContent = `${done} of ${jobs.length} done`
    box.querySelector('[data-upbar]').style.width = `${Math.max(3, (100 * done) / jobs.length)}%`
  }
  const added = [], skipped = [], shots = []
  let stop = false
  const sectionName = (it) => (SECTIONS.find(([k]) => k === it.section) || [, it.category])[1]

  // one round: tag its photos, then start their product shots right away while other rounds keep tagging
  async function round(i) {
    const batch = jobs.slice(i, i + BULK)
    batch.forEach((_, k) => set(i + k, 'Your stylist is tagging it…', '<div class="spinner sm"></div>', 'busy'))
    try {
      let r
      if (kind === 'photos') {
        const fd = new FormData()
        batch.forEach((j) => fd.append('files', j.file, j.file.name))
        fd.append('dataset', S().dataset)
        r = await A().api('/api/closet/bulk', { method: 'POST', body: fd })
      } else {
        r = await A().postJSON('/api/closet/links', { dataset: S().dataset, urls: batch.map((j) => j.url) })
      }
      A().updateMeter(r.run)
      const flat = []
      r.result.results.forEach((res) => {
        const n = i + res.index
        if (res.ok) {
          added.push(res.item)
          const shot = res.item.image && res.item.source !== 'link'
          if (shot) flat.push([n, res.item])
          set(n, `<b>${esc(res.item.name)}</b> · filed under ${esc(sectionName(res.item))}${shot ? ' · <span class="muted">standing it up…</span>' : ''}`, shot ? '<div class="spinner sm"></div>' : '✓', shot ? 'busy' : 'ok')
        } else {
          skipped.push({ name: res.name, error: res.error })
          set(n, esc(res.error), '✕', 'bad')
        }
      })
      await A().loadCloset()
      A().renderCloset(added.map((a) => a.id))  // pieces appear as each round lands
      if (flat.length) shots.push(makeShots(flat, set))
    } catch (e) {
      batch.forEach((j, k) => { skipped.push({ name: j.file?.name || j.url, error: e.message }); set(i + k, esc(e.message), '✕', 'bad') })
      if (/budget|cap|limit/i.test(e.message)) stop = true
    } finally {
      done += batch.length
      tick()
    }
  }

  const starts = []
  for (let i = 0; i < jobs.length; i += BULK) starts.push(i)
  const lanes = Array.from({ length: Math.min(ROUNDS_AT_ONCE, starts.length) }, async () => {
    while (starts.length && !stop) await round(starts.shift())
  })
  await Promise.all(lanes)
  jobs.forEach((j) => j.thumb && setTimeout(() => URL.revokeObjectURL(j.thumb), 60000))
  $('#photo-file').value = ''
  if (kind === 'links') $('#link-url').value = skipped.map((x) => x.name).filter((n) => /^https?:/.test(n)).join('\n')
  const title = `Added ${added.length} piece${added.length === 1 ? '' : 's'} to your closet` + (skipped.length ? ` · ${skipped.length} skipped` : '')
  box.querySelector('[data-uptitle]').textContent = shots.length ? `${title} · finishing product shots…` : title
  S().filter = 'all'
  showFollowup(added.map((a) => S().closet.find((x) => x.id === a.id) || a))
  await Promise.all(shots)
  box.querySelector('[data-uptitle]').textContent = title
  await A().loadCloset()
  A().renderCloset(added.map((a) => a.id))
}

// upright store-style product shots (image model on your own key; skipped without one), 8 drawn at once
async function makeShots(pairs, set) {
  const ids = pairs.map(([, it]) => it.id)
  const mark = (fn) => pairs.forEach(([n, it]) => fn(n, it))
  const { esc } = A()
  try {
    const r = await A().postJSON('/api/closet/shots', { dataset: S().dataset, ids })
    A().updateMeter(r.run)
    const failed = new Set((r.result.failed || []).map((f) => f.id))
    mark((n, it) => set(n, `<b>${esc(it.name)}</b> · ${failed.has(it.id) ? 'product shot failed (Edit → Redo product shot)' : 'product shot ready'}`, failed.has(it.id) ? '!' : '✓', failed.has(it.id) ? 'bad' : 'ok'))
  } catch (e) {
    const why = /OPENAI_API_KEY/.test(e.message) ? 'showing the cutout (product shots need your own OpenAI key)' : `product shot skipped: ${esc(e.message)}`
    mark((n, it) => set(n, `<b>${esc(it.name)}</b> · ${why}`, '✓', 'ok'))
  }
}

// ---- size & fit follow-up: your size is guessed; tap how it fits (or fix the size first)
// bags, hats, jewelry, sunglasses etc. have no size or fit to ask about; belts do
const NO_SIZE = /\b(bags?|backpacks?|totes?|purses?|clutch(es)?|handbags?|crossbody|hats?|baseball caps?|beanies?|berets?|fedoras?|jewel(le)?ry|necklaces?|earrings?|bracelets?|rings?|anklets?|brooch(es)?|watch(es)?|sunglasses|scarf|scarves|hair)\b/i
const hasSize = (it) => /belt/i.test(it.subtype || '') ||
  (it.category !== 'accessory' && !NO_SIZE.test(`${it.subtype || ''} ${it.name || ''}`))

function showFollowup(items) {
  const open = new Set($$('#add-followup .followup').map((b) => b.dataset.fid))
  items = (items || []).filter((x) => x?.id && !open.has(x.id) && hasSize(x))
  if (!items.length) return
  const rows = items.map(fuRow).join('')
  if (open.size) return $('#add-followup').insertAdjacentHTML('beforeend', rows)  // keep cards you haven't answered yet
  $('#add-followup').innerHTML = `<div class="fu-head small"><b>How do they fit?</b> Your size is guessed from your measurements; fix it if the label says otherwise, then tap a fit. Every answer sharpens the next guess.
    <button type="button" class="btn small ghost fu-close-all">Skip all</button></div>` + rows
}

function fuRow(item) {
  const { esc, itemImg } = A()
  const g = item.size_guess
    return `<div class="followup" data-fid="${esc(item.id)}">
    <div class="fu-img">${itemImg(item)}</div>
    <div class="fu-body"><b>${esc(item.name)}</b>
      <div class="row gap wrap fu-row"><label class="small">Size</label><input class="fu-size" type="text" maxlength="20" placeholder="e.g. M, 8, 28x32" value="${esc(item.size_label || g?.size || '')}" />
        ${g && !item.size_label ? `<span class="small muted" title="From ${esc(g.why)}">our guess${g.confidence ? ` · ${esc(g.confidence)} confidence` : ''}</span>` : ''}</div>
      <div class="row gap wrap fu-row"><span class="small">How does it fit?</span>${FITS.map((f) => `<button type="button" class="chip" data-fit="${f}">${f[0].toUpperCase() + f.slice(1)}</button>`).join('')}</div>
    </div>
    <button type="button" class="x fu-close" title="Skip">✕</button></div>`
}

function dropRow(box) {
  box.remove()
  if (!$('#add-followup .followup')) $('#add-followup').innerHTML = ''
}

async function sendFit(btn) {
  const box = btn.closest('.followup')
  const size = $('.fu-size', box).value.trim()
  if (!size) { $('.fu-size', box).focus(); return A().toast('Add the size on the label first') }
  const old = S().profile?.sizes || {}
  if (!S().closet.some((x) => x.id === box.dataset.fid)) { dropRow(box); return A().toast('That piece was removed from your closet, so there’s no fit to save.') }
  try {
    const r = await A().postJSON(`/api/closet/${encodeURIComponent(box.dataset.fid)}/fit`, { dataset: S().dataset, size_label: size, fit: btn.dataset.fit })
    if (S().profile) { S().profile.sizes = r.sizes; S().profile.measurements_in = r.measurements_in }
    const changed = Object.entries(r.sizes || {}).filter(([k, v]) => JSON.stringify(old[k]) !== JSON.stringify(v))
    const fmt = (v) => (typeof v === 'object' && v ? Object.values(v).join('/') : v)
    A().toast(changed.length
      ? `Thanks! Updated your sizes: ${changed.slice(0, 4).map(([k, v]) => `${k} ${fmt(v)}`).join(' · ')}`
      : 'Thanks! Noted. Your sizes held steady.')
    const it = S().closet.find((x) => x.id === box.dataset.fid)
    if (it) Object.assign(it, { size_label: size, fit_verdict: btn.dataset.fit })
    dropRow(box)
  } catch (e) {
    if (/isn't in your closet/.test(e.message)) dropRow(box)
    A().toast(`Couldn't save the fit: ${e.message}`)
  }
}

// ---- possible duplicates: the same photo twice, or same kind + color; she decides, nothing is removed on its own
let seenPairs = null  // pairs already shown, so only a new one (just added) gets a toast

async function checkDupes() {
  const { esc, itemImg } = A()
  let pairs = []
  try { pairs = (await A().api(`/api/closet/dupes?${A().q()}`)).pairs } catch { return }
  const byId = (id) => S().closet.find((x) => x.id === id)
  pairs = pairs.filter((p) => byId(p.a) && byId(p.b))
  let box = $('#dupes')
  if (!box) { $('#closet-grid').insertAdjacentHTML('beforebegin', '<div id="dupes"></div>'); box = $('#dupes') }
  const key = (p) => `${p.a}|${p.b}`
  const fresh = seenPairs ? pairs.filter((p) => !seenPairs.has(key(p))) : []
  seenPairs = new Set(pairs.map(key))
  if (!pairs.length || (dupesHidden && !fresh.length)) { box.innerHTML = ''; return }
  if (fresh.length) dupesHidden = false
  // one slim line until she opens it; nothing scrolls or covers the closet
  const open = box.querySelector('.dupes-card.open') && !fresh.length ? ' open' : ''
  const side = (it) => `<div class="dp-side"><div class="dp-img">${itemImg(it)}</div><div class="small"><b>${esc(it.name)}</b></div>
    <button type="button" class="btn small ghost" data-dp-remove="${esc(it.id)}">Remove this one</button></div>`
  const first = pairs[0]
  box.innerHTML = `<div class="dupes-card${open}"><div class="dp-bar small"><span>⚠ <b>${pairs.length} possible duplicate${pairs.length === 1 ? '' : 's'}</b>
    <span class="muted">· ${esc(byId(first.a).name)} &amp; ${esc(byId(first.b).name)}${pairs.length > 1 ? ` + ${pairs.length - 1} more` : ''}</span></span>
    <span class="row gap"><button type="button" class="btn small ghost" data-dp-toggle>${open ? 'Hide' : 'Review'}</button>
    <button type="button" class="x" data-dp-later title="Hide for now">✕</button></span></div>
    <div class="dp-pairs">${pairs.map((p) => `<div class="dp-pair" data-a="${esc(p.a)}" data-b="${esc(p.b)}">${side(byId(p.a))}
      <div class="dp-mid small muted">${esc(p.why)}<button type="button" class="btn small ghost" data-dp-keep>Not duplicates</button></div>${side(byId(p.b))}</div>`).join('')}</div></div>`
  if (fresh.length) A().toast(`${byId(fresh[0].b).name} may be a duplicate of ${byId(fresh[0].a).name} (${fresh[0].why}). Review it at the top of your closet.`)
}
let dupesHidden = false  // ✕ hides the notice until a new duplicate turns up

document.addEventListener('click', (e) => {
  const card = e.target.closest('.dupes-card')
  if (!card) return
  if (e.target.closest('[data-dp-toggle]')) {
    card.classList.toggle('open')
    e.target.closest('[data-dp-toggle]').textContent = card.classList.contains('open') ? 'Hide' : 'Review'
  }
  if (e.target.closest('[data-dp-later]')) { dupesHidden = true; $('#dupes').innerHTML = '' }
})

document.addEventListener('click', async (e) => {
  const rm = e.target.closest('[data-dp-remove]')
  const keep = e.target.closest('[data-dp-keep]')
  if (!rm && !keep) return
  const pair = e.target.closest('.dp-pair')
  try {
    if (rm) {
      const it = S().closet.find((x) => x.id === rm.dataset.dpRemove)
      await A().api(`/api/closet/${encodeURIComponent(it.id)}?${A().q()}`, { method: 'DELETE' })
      A().toast(`Removed the extra ${it.name}.`)
    } else {
      await A().postJSON('/api/closet/not-dupes', { dataset: S().dataset, a: pair.dataset.a, b: pair.dataset.b })
      A().toast("Got it, they're different pieces. I won't flag them again.")
    }
    await A().loadCloset()
    A().renderCloset()
  } catch (err) { A().toast(`Couldn't do that: ${err.message}`) }
})

// adding in Sample mode would put your clothes in the practice closet, so the add forms wait for My closet
function guard() {
  const sample = S().dataset === 'sample'
  $('#sample-guard').classList.toggle('hidden', !sample)
  $$('#photo-form, #link-form, #receipt-form').forEach((f) => f.classList.toggle('locked', sample))
}

// ---- section rail: a vertical strip on the right to jump between closet sections or back to the top
const short = (title) => ({ 'Out of season · packed away': 'Packed', Accessories: 'Acc.', Activewear: 'Active' }[title] || title.split(/[\s&·]+/)[0])

function buildRail() {
  const { esc } = A()
  const heads = $$('#closet-grid h3.closet-group')
  heads.forEach((h, n) => { h.id = `sec-${n}` })
  $('#sec-rail').innerHTML = `<button type="button" class="rail-top" data-rail="top" title="Back to top">↑<span>Top</span></button>`
    + `<button type="button" class="rail-more" data-rail-more title="Sections">☰</button>`  // phone width: sections fold away
    + heads.map((h, n) => { const t = h.firstChild.textContent.trim(); return `<button type="button" data-rail="sec-${n}" title="${esc(t)}">${esc(short(t))}</button>` }).join('')
  railState()
}

function railState() {
  const rail = $('#sec-rail')
  rail.classList.toggle('shown', $('#tab-closet').classList.contains('active') && !!$('#closet-grid h3.closet-group'))
  // centered on screen, but never over the header or the tab bar
  const below = $('#tabs').getBoundingClientRect().bottom + 12
  rail.style.top = `${Math.max(below, (window.innerHeight - rail.offsetHeight) / 2)}px`
  const heads = $$('#closet-grid h3.closet-group')
  const cur = heads.filter((h) => h.getBoundingClientRect().top < window.innerHeight * 0.35).pop()
  $$('[data-rail]', rail).forEach((b) => b.classList.toggle('here', !!cur && b.dataset.rail === cur.id))
}

function topButton() {
  window.addEventListener('scroll', railState, { passive: true })
  document.addEventListener('click', (e) => { if (e.target.closest('#tabs button')) setTimeout(railState, 0) })
  window.addEventListener('resize', railState)
  $('#sec-rail').addEventListener('click', (e) => {
    const rail = $('#sec-rail')
    if (e.target.closest('[data-rail-more]')) { rail.classList.toggle('open'); return railState() }
    const b = e.target.closest('[data-rail]')
    if (!b) return
    rail.classList.remove('open')
    if (b.dataset.rail === 'top') window.scrollTo({ top: 0, behavior: 'smooth' })
    else document.getElementById(b.dataset.rail)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}

function init() {
  if (!window.closetTwinApi) return setTimeout(init, 200)
  topButton()
  guard()
  $('#guard-switch').addEventListener('click', () => document.querySelector('.dataset-toggle button[data-ds="user"]').click())
  $$('#add-modes .chip').forEach((b) => b.addEventListener('click', () => setMode(b.dataset.addmode)))
  $('#link-form').addEventListener('submit', addLink)
  $('#receipt-form').addEventListener('submit', (e) => e.preventDefault())
  $('#link-receipt-file').addEventListener('change', (e) => { const f = e.target.files[0]; e.target.value = ''; if (f) { setMode('receipt'); readReceipt(f) } })
  $('#receipt-file').addEventListener('change', (e) => { const f = e.target.files[0]; e.target.value = ''; if (f) readReceipt(f) })
  $('#receipt-lines').addEventListener('click', (e) => { if (e.target.closest('[data-rc-add]')) addReceiptLines() })
  $('#add-followup').addEventListener('click', (e) => {
    const f = e.target.closest('[data-fit]')
    if (f) return sendFit(f)
    if (e.target.closest('.fu-close')) dropRow(e.target.closest('.followup'))
    if (e.target.closest('.fu-close-all')) $('#add-followup').innerHTML = ''
  })
  document.addEventListener('ct:item-added', async (e) => {
    await A().loadCloset()
    showFollowup([S().closet.find((x) => x.id === e.detail?.id) || e.detail])
  })
  document.addEventListener('ct:closet-rendered', () => { decorateCloset(); checkDupes(); buildRail() })
  document.addEventListener('ct:dataset', () => { memo = null; seenPairs = null; $('#add-followup').innerHTML = ''; guard() })
  decorateCloset()
  checkDupes()
  buildRail()
}

init()
