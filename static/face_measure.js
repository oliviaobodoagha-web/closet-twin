// Measures face colors in the browser for seasonal color analysis.
// MediaPipe Face Landmarker (Apache-2.0) finds 478 face landmarks; we sample median
// colors at the same landmark points as tkamali2020/Seasonal-Color-Analysis (Apache-2.0):
// skin (cheeks, forehead, chin), eyebrows, irises and lips. Nothing leaves the page here.
import { FaceLandmarker, FilesetResolver } from 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14'

const WASM = 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm'
const MODEL = 'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task'

const SKIN = [50, 280, 117, 346, 118, 347, 10, 152]
const BROWS = [70, 63, 105, 66, 107, 336, 296, 334, 293, 300]
const LIPS = [13, 14, 0, 17, 78, 308, 82, 312, 87, 317]
const IRIS_R = [469, 470, 471, 472], IRIS_L = [474, 475, 476, 477]
const IRIS_C = { r: 468, l: 473 }

let landmarker = null
async function getLandmarker() {
  if (landmarker) return landmarker
  const files = await FilesetResolver.forVisionTasks(WASM)
  landmarker = await FaceLandmarker.createFromOptions(files, {
    baseOptions: { modelAssetPath: MODEL },
    runningMode: 'IMAGE',
    numFaces: 1,
  })
  return landmarker
}

function rgbToHsv(r, g, b) { // h 0-360, s/v 0-255 (OpenCV-style scale for s, v)
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn
  let h = 0
  if (d) h = mx === r ? ((g - b) / d) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4
  h = (h * 60 + 360) % 360
  return [h, mx ? (d / mx) * 255 : 0, mx]
}

const median = (arr) => { const s = [...arr].sort((a, b) => a - b); return s.length ? s[Math.floor(s.length / 2)] : 0 }
const pct = (arr, p) => { const s = [...arr].sort((a, b) => a - b); return s[Math.min(s.length - 1, Math.floor(p * s.length))] }

function patch(ctx, w, h, x, y, size) {
  const x0 = Math.max(0, Math.round(x - size / 2)), y0 = Math.max(0, Math.round(y - size / 2))
  const pw = Math.min(size, w - x0), ph = Math.min(size, h - y0)
  if (pw <= 0 || ph <= 0) return []
  const d = ctx.getImageData(x0, y0, pw, ph).data, out = []
  for (let i = 0; i < d.length; i += 4) out.push([d[i], d[i + 1], d[i + 2]])
  return out
}

function medianRGB(px) {
  return [0, 1, 2].map((c) => Math.round(median(px.map((p) => p[c]))))
}

export async function measureFace(blob) {
  const lm = await getLandmarker()
  const bmp = await createImageBitmap(blob)
  const scale = Math.min(1, 1280 / Math.max(bmp.width, bmp.height))
  const w = Math.round(bmp.width * scale), h = Math.round(bmp.height * scale)
  const canvas = document.createElement('canvas')
  canvas.width = w; canvas.height = h
  const ctx = canvas.getContext('2d', { willReadFrequently: true })
  ctx.drawImage(bmp, 0, 0, w, h)
  const res = lm.detect(canvas)
  if (!res.faceLandmarks?.length) throw new Error("I couldn't find a face in that photo. Try a closer, well-lit, straight-on close-up.")
  const pts = res.faceLandmarks[0].map((p) => [p.x * w, p.y * h])

  // face size check: the face should fill a good part of the frame
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1])
  const faceFrac = ((Math.max(...xs) - Math.min(...xs)) * (Math.max(...ys) - Math.min(...ys))) / (w * h)
  const sz = Math.max(8, Math.round((Math.max(...xs) - Math.min(...xs)) / 25))

  // skin: drop shadows/highlights, then 5th-95th percentile per channel, then median
  let skin = []
  for (const i of SKIN) for (const p of patch(ctx, w, h, pts[i][0], pts[i][1], sz * 2)) {
    const [, s, v] = rgbToHsv(...p)
    if (v > 45 && v < 245 && s > 20 && s < 180) skin.push(p)
  }
  if (skin.length < 20) throw new Error('The skin areas are too dark, bright or shadowed. Face a window in daylight and try again.')
  for (const c of [0, 1, 2]) {
    const ch = skin.map((p) => p[c]), lo = pct(ch, 0.05), hi = pct(ch, 0.95)
    skin = skin.filter((p) => p[c] >= lo && p[c] <= hi)
  }

  // brows: only pixels clearly darker than the skin, then the darker half. Without this, skin next to the
  // brow gets counted as brow on deeper skin tones and contrast reads too low.
  const skinV = median(skin.map((p) => rgbToHsv(...p)[2]))
  let brow = []
  for (const i of BROWS) for (const p of patch(ctx, w, h, pts[i][0], pts[i][1], sz)) {
    const [, s, v] = rgbToHsv(...p)
    if (v < 170 && v < skinV * 0.85 && s > 10) brow.push(p)
  }
  if (brow.length) {
    const bv = brow.map((p) => rgbToHsv(...p)[2]), cut = median(bv)
    brow = brow.filter((p, i) => bv[i] <= cut)
  }
  let lips = []
  for (const i of LIPS) for (const p of patch(ctx, w, h, pts[i][0], pts[i][1], sz)) {
    const [, s, v] = rgbToHsv(...p)
    if (v > 40 && v < 245 && s > 25) lips.push(p)
  }

  // iris: sample between each iris edge point and the center, skip pupil and glints, keep the brighter half
  const eye = []
  for (const [ring, ci] of [[IRIS_R, IRIS_C.r], [IRIS_L, IRIS_C.l]]) {
    const [cx, cy] = pts[ci]
    for (const i of ring) for (const t of [0.35, 0.55, 0.7]) {
      const sx = pts[i][0] + t * (cx - pts[i][0]), sy = pts[i][1] + t * (cy - pts[i][1])
      for (const p of patch(ctx, w, h, sx, sy, 5)) {
        const [, s, v] = rgbToHsv(...p)
        if (v > 30 && v < 235 && !(v > 210 && s < 35)) eye.push(p)
      }
    }
  }
  const eyeV = eye.map((p) => rgbToHsv(...p)[2]), vMed = median(eyeV)
  const eyeBright = eye.filter((p, i) => eyeV[i] >= vMed)
  const eyeRGB = eyeBright.length ? medianRGB(eyeBright) : [60, 50, 40]

  return {
    skin_rgb: medianRGB(skin),
    brow_rgb: brow.length ? medianRGB(brow) : [60, 50, 40],
    eye_rgb: eyeRGB,
    eye_hsv: rgbToHsv(...eyeRGB),
    lip_rgb: lips.length ? medianRGB(lips) : [150, 90, 90],
    face_fraction: Math.round(faceFrac * 100) / 100,
    samples: { skin: skin.length, brow: brow.length, eye: eyeBright.length, lips: lips.length },
  }
}

// Face outline (MediaPipe's face-oval landmarks) for the drape test's neutral cap.
const FACE_OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148,
  176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109]

export async function faceOutline(img) {
  const lm = await getLandmarker()
  const res = lm.detect(img)
  if (!res.faceLandmarks?.length) return null
  const f = res.faceLandmarks[0]
  return FACE_OVAL.map((i) => [f[i].x, f[i].y])  // normalized 0-1
}
