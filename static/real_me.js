// Fitting room: a photorealistic image of the user in the current outfit, scene and pose
// (photo try-on on their own OpenAI key), plus a 360° turntable you can drag to turn around.
// Images are reused from the gallery when the same look was made before, so switching
// scenes back and forth doesn't pay twice.
const $ = (s, el = document) => el.querySelector(s)
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))
const POSE_FOR_MOVE = { idle: 'standing', turn: 'turn', sit: 'sitting', walk: 'walking' }
const SCENE_NAMES = { studio: 'boutique', classroom: 'classroom', office: 'office', gym: 'gym', coffee: 'coffee shop', street: 'campus walk', dinner: 'dinner' }

const rm = { mode: null, gallery: [], status: null, busy: false }

// Your real avatar: you, from your photo, in a plain minimalist outfit in the boutique. Made once (about $0.02)
// and shown whenever no outfit is on, so the fitting room always opens on you, not a mannequin.
const BASE_OUTFIT = [
  { id: 'base-tee', name: 'Fitted ivory crewneck tee', category: 'top', color: 'ivory', fit: 'fitted' },
  { id: 'base-trouser', name: 'Navy straight-leg trousers', category: 'bottom', color: 'navy', fit: 'regular' },
  { id: 'base-loafer', name: 'Ivory leather loafers', category: 'shoes', color: 'ivory' },
]
const BASE_KEY = BASE_OUTFIT.map((i) => i.id).sort().join('|') + '@studio#standing'

function state() { return window.closetTwin }

function lookKey() {
  const s = state()
  if (!(s.outfit || []).length) return BASE_KEY
  const ids = (s.outfit || []).map((i) => String(i.id || i.name || '')).sort()
  return ids.join('|') + `@${s.scene}#${POSE_FOR_MOVE[s.move] || 'standing'}`
}

async function refresh() {
  try {
    const [st, gal] = await Promise.all([fetch('/api/photo-tryon/status').then((r) => r.json()), fetch('/api/tryons').then((r) => r.json())])
    rm.status = st
    const all = Array.isArray(gal) ? gal : []
    rm.gallery = all.filter((g) => g.type !== 'turntable')
    rm.spins = Object.fromEntries(all.filter((g) => g.type === 'turntable').map((g) => [g.image, g]))
  } catch { /* offline: stay in 3D */ }
}

function ready() { return rm.status && rm.status.key_set && rm.status.has_photo && rm.status.consent }

function render() {
  if (rm.mode !== 'real') return
  const s = state(), view = $('#rm-view')
  const pose = POSE_FOR_MOVE[s.move]
  const outfit = (s.outfit || []).map((i) => i.name).filter(Boolean)
  const where = SCENE_NAMES[s.scene] || s.scene
  if (!ready()) {
    view.innerHTML = `<div class="rm-empty"><h3>See the real you</h3><p>${!rm.status?.key_set
      ? 'Seeing yourself needs your own <code>OPENAI_API_KEY</code> in <code>.env</code> (the stylist, planner and shopper work without it).'
      : 'Add one full-body photo (and tick consent) in <b>Me → Your photo</b>.'}</p></div>`
    return
  }
  const base = rm.gallery.find((g) => g.key === BASE_KEY)
  const hit = outfit.length ? rm.gallery.find((g) => g.key === lookKey()) : base
  const strip = rm.gallery.slice(0, 12).map((g) => `<button class="rm-thumb${hit && g.image === hit.image ? ' on' : ''}" type="button" data-img="${esc(g.image)}" title="${esc((g.items || []).join(', '))} · ${esc(SCENE_NAMES[g.scene] || g.scene)} · ${esc(g.pose)}"><img src="/api/tryons/user/${esc(g.image)}" alt="" /></button>`).join('')
  view.innerHTML = `
    <div class="rm-stage">
      ${hit
        ? spinStage(hit)
        : `<div class="rm-frame"><img class="rm-photo dim" src="${base ? `/api/tryons/user/${esc(base.image)}` : '/api/me/photo/user'}" alt="You" />
           <div class="rm-cta">
             <div class="rm-cta-card">
               <div class="rm-kicker">${outfit.length ? `${esc(where)} · ${esc(pose)}` : 'Your avatar'}</div>
               <h3>${outfit.length ? 'Dress me in this look' : 'Create my real avatar'}</h3>
               <p class="small">${outfit.length ? esc(outfit.join(' · ')) : 'You, from your photo, in a plain ivory tee and navy trousers. Made once, then the fitting room always opens on you.'}</p>
               <button class="btn primary" type="button" data-make>✦ ${outfit.length ? 'Make it real' : 'Create my avatar'} (about $0.02)</button>
               <div class="small muted" style="margin-top:6px">${rm.status.used_today}/${rm.status.max_per_day} used today</div>
             </div>
           </div></div>`}
      ${hit && !outfit.length ? '<div class="rm-caption">Your avatar · put a look on from Today, Closet or Shop to dress it</div>' : ''}
      ${rm.busy ? `<div class="rm-busy"><div class="spinner"></div><div>${rm.busy === 'spin' ? 'Turning you around: 7 angles at once… about 30–60 s' : 'Dressing the real you… about 15–30 s'}</div></div>` : ''}
    </div>
    ${strip ? `<div class="rm-strip">${strip}</div>` : ''}`
  view.querySelector('[data-make]')?.addEventListener('click', make)
  wireSpin(view, hit)
  view.querySelectorAll('[data-img]').forEach((b) => b.addEventListener('click', () => {
    const g = rm.gallery.find((x) => x.image === b.dataset.img)
    if (!g) return
    view.querySelector('.rm-stage').innerHTML = spinStage(g) + `<div class="rm-caption">${esc((g.items || []).join(' · '))} · ${esc(SCENE_NAMES[g.scene] || g.scene)} · ${esc(g.pose)}</div>`
    wireSpin(view, g)
  }))
}

// ---- 360° turntable: 8 photoreal angles of you; drag (or swipe) to turn yourself around
function spinStage(g) {
  const spin = rm.spins?.[g.image]
  if (spin) {
    return `<div class="rm-frame"><div class="rm-spin" data-spin>${spin.frames.map((f, i) => `<img class="rm-photo${i ? ' off' : ''}" src="/api/tryons/user/${esc(f)}" alt="${i * 45}°" draggable="false" />`).join('')}</div></div>
      <div class="rm-spin-bar"><button class="btn small ghost" type="button" data-step="-1">◀</button><span class="small">Drag to turn · <span data-deg>0°</span></span><button class="btn small ghost" type="button" data-step="1">▶</button><button class="btn small ghost" type="button" data-auto>↻ Spin</button></div>`
  }
  const canSpin = g.pose === 'standing'
  return `<div class="rm-frame"><img class="rm-photo" src="/api/tryons/user/${esc(g.image)}" alt="You in this look" /></div>
    <div class="rm-spin-bar">${canSpin ? '<button class="btn small primary" type="button" data-make-spin>↻ See me in 360° (about $0.25)</button>' : ''}
      <button class="btn small ghost" type="button" data-fix-open>✎ Not right? Tell me</button></div>
    ${fixBox(g)}`
}

// ---- "What's wrong with this photo?": her answers redo it and go into every try-on after it
const PHOTO_ISSUES = [['hair', 'Hair looks messy'], ['smile', 'Want a smile'], ['face', "Doesn't look like me"], ['body', 'Body shape changed'],
  ['clothes', 'Wrong / missing piece'], ['fit', 'Fit looks wrong'], ['coat', 'Coat on indoors'], ['pose', 'Awkward pose'],
  ['scene', 'Wrong place'], ['light', 'Light / colors off']]

function fixBox(g) {
  return `<div class="rm-fix hidden" data-fix="${esc(g.image)}">
    <div class="small"><b>What's wrong with this photo?</b> <span class="muted">I'll remember it for every photo of you.</span></div>
    <div class="rm-fix-grid">${PHOTO_ISSUES.map(([k, l]) => `<label class="redo-opt"><input type="checkbox" value="${k}" /> ${l}</label>`).join('')}</div>
    <textarea maxlength="300" rows="2" placeholder="Anything else? e.g. my hair is usually in a sleek low bun"></textarea>
    <div class="row gap"><button class="btn small primary" type="button" data-fix-go>✦ Redo with these fixes (about $0.02)</button>
      <button class="btn small ghost" type="button" data-fix-save>Just remember it</button></div></div>`
}

async function sendFix(box, redo) {
  const issues = [...box.querySelectorAll('input:checked')].map((x) => x.value)
  const detail = box.querySelector('textarea').value.trim()
  if (!issues.length && !detail) return alert('Tick what looks wrong first.')
  const res = await fetch('/api/photo-tryon/feedback', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image: box.dataset.fix, issues, detail }) })
  const data = await res.json()
  if (!res.ok || !data.ok) return alert(data.detail || data.error || 'Could not save that.')
  await refresh()
  if (redo) return make()
  render()
}

function wireSpin(view, g) {
  if (!g) return
  view.querySelector('[data-make-spin]')?.addEventListener('click', () => makeSpin(g.image))
  const fix = view.querySelector('[data-fix]')
  view.querySelector('[data-fix-open]')?.addEventListener('click', () => fix.classList.toggle('hidden'))
  fix?.querySelector('[data-fix-go]').addEventListener('click', () => sendFix(fix, true))
  fix?.querySelector('[data-fix-save]').addEventListener('click', () => sendFix(fix, false))
  const box = view.querySelector('[data-spin]')
  if (!box) return
  const frames = [...box.querySelectorAll('img')], deg = view.querySelector('[data-deg]')
  let i = 0, timer = null, startX = null, startI = 0
  const show = (k) => { i = ((k % frames.length) + frames.length) % frames.length; frames.forEach((f, n) => f.classList.toggle('off', n !== i)); deg.textContent = `${i * 45}°` }
  view.querySelectorAll('[data-step]').forEach((b) => b.addEventListener('click', () => show(i + Number(b.dataset.step))))
  view.querySelector('[data-auto]').addEventListener('click', () => { if (timer) { clearInterval(timer); timer = null } else timer = setInterval(() => show(i + 1), 450) })
  box.addEventListener('pointerdown', (e) => { startX = e.clientX; startI = i; box.setPointerCapture(e.pointerId); if (timer) { clearInterval(timer); timer = null } })
  box.addEventListener('pointermove', (e) => { if (startX !== null) show(startI + Math.round((startX - e.clientX) / 45)) })
  box.addEventListener('pointerup', () => { startX = null })
}

async function makeSpin(image) {
  if (rm.busy) return
  rm.busy = 'spin'; render()
  try {
    const res = await fetch('/api/photo-tryon/spin', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ image }) })
    const data = await res.json()
    if (!res.ok || !data.ok) throw new Error(data.error || data.detail || `Request failed (${res.status})`)
  } catch (e) {
    alert(e.message)
  } finally {
    rm.busy = false
    await refresh(); render()
  }
}

async function make() {
  if (rm.busy) return
  const s = state()
  rm.busy = true; render()
  try {
    const res = await fetch('/api/photo-tryon', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify((s.outfit || []).length
        ? { dataset: 'user', items: s.outfit, scene: s.scene, zones: s.zones, pose: POSE_FOR_MOVE[s.move] || 'standing' }
        : { dataset: 'user', items: BASE_OUTFIT, scene: 'studio', pose: 'standing' }),
    })
    const data = await res.json()
    if (!res.ok || !data.ok) throw new Error(data.error || data.detail || `Request failed (${res.status})`)
  } catch (e) {
    alert(e.message)
  } finally {
    rm.busy = false
    await refresh(); render()
  }
}

async function init() {
  const stage = $('#tab-fitting .stage')
  if (!stage || !window.closetTwin) return setTimeout(init, 300)
  stage.insertAdjacentHTML('beforeend', '<div id="rm-view" class="rm-view"></div>')
  // follow the existing scene / move chips and outfit changes
  const rerender = () => setTimeout(render, 50)
  $('#scene-btns').addEventListener('click', rerender)
  $('#move-btns').addEventListener('click', rerender)
  new MutationObserver(rerender).observe($('#outfit-list'), { childList: true, subtree: true })
  await refresh()
  rm.mode = 'real'
  render()
}

init()
