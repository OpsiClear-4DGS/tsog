// SPDX-License-Identifier: Apache-2.0
// Independent compact reference decoder; no renderer or player dependency.
import { readZIP, entryName } from "./zip.js";
import { createWebPDecoder } from "./webp.js";
const MAX = 3.4028234663852886e38;
const SQRT2 = Math.sqrt(2);
const MIME = { mp3: "audio/mpeg", m4a: "audio/mp4", aac: "audio/aac", ogg: "audio/ogg", oga: "audio/ogg", opus: "audio/ogg", wav: "audio/wav", flac: "audio/flac", webm: "audio/webm" };
const fail = message => { throw new Error(`TSOG: ${message}`); };
const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
function number(value, label, min = -Infinity, max = Infinity, integer = false) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < min || value > max || integer && !Number.isSafeInteger(value)) fail(`invalid ${label}`);
  return value;
}
function vector(value, length) {
  if (!Array.isArray(value) || value.length !== length) fail("range shape");
  value.forEach(n => number(n, "range", -MAX, MAX));
}
function group(meta, key, minimum, maximum = minimum, axes, book = false) {
  const g = meta[key];
  if (!object(g) || !Array.isArray(g.files) || g.files.length < minimum || g.files.length > maximum) fail(`invalid ${key} group`);
  if (new Set(g.files).size !== g.files.length) fail("duplicate image reference");
  g.files.forEach(name => { entryName(name); if (name === "meta.json") fail("attribute refers to metadata"); });
  if (axes !== undefined) {
    vector(g.mins, axes); vector(g.maxs, axes);
    if (g.mins.some((n, a) => n > g.maxs[a])) fail("reversed range");
  }
  if (book) {
    if (!Array.isArray(g.codebook) || g.codebook.length < 1 || g.codebook.length > 256) fail("codebook length");
    g.codebook.forEach(n => number(n, "codebook", -MAX, MAX));
  }
  return g;
}
export function mediaTiming(meta) {
  const p = meta.playback ?? {}, timeline = meta.timeline;
  let fps = p.fps ?? meta.fps ?? 30, duration = p.duration, frames = 1;
  if (timeline?.type === 0) {
    frames = timeline.N;
    if (duration !== undefined) {
      if (p.fps !== undefined && Math.abs(duration * fps - frames) > 1e-6 * frames) fail("discrete FPS/duration mismatch");
      fps = frames / duration;
    } else duration = frames / fps;
  } else if (timeline?.type === 1) {
    if (duration !== undefined) number(duration * fps, "duration*FPS", 0, Number.MAX_SAFE_INTEGER - 1);
    frames = duration !== undefined ? Math.max(2, Math.floor(duration * fps + .5) + 1) : 300;
    if (duration === undefined) duration = (frames - 1) / fps;
  }
  number(frames, "derived frame count", 1, Number.MAX_SAFE_INTEGER, true);
  if (duration !== undefined && number(duration, "duration", 0) === 0) fail("zero duration");
  if (number(fps, "FPS", 0) === 0) fail("zero FPS");
  return { frames, fps, duration: duration ?? null, rate: p.rate ?? 1, loop: p.loop ?? true };
}
function audioMime(audio) {
  if (audio.mimeType !== undefined) {
    if (typeof audio.mimeType !== "string" || !/^audio\/[a-z0-9.+-]+$/i.test(audio.mimeType)) fail("invalid audio MIME");
    return audio.mimeType;
  }
  const mime = MIME[audio.file.split(".").at(-1).toLowerCase()];
  if (!mime) fail("unknown audio extension requires MIME");
  return mime;
}
export function validateMetadata(meta, { requireProfile = false } = {}) {
  if (!object(meta) || ![1, 4].includes(meta.version)) fail("unsupported format version");
  if (meta.profile !== undefined) {
    if (!object(meta.profile) || meta.profile.id !== "org.opsiclear.tsog-playback" || meta.profile.version !== 1) fail("unsupported profile");
  } else if (requireProfile || meta.version === 1) fail("missing explicit profile");
  number(meta.count, "point count", 1, Number.MAX_SAFE_INTEGER, true);
  group(meta, "means", 2, 2, 3);
  group(meta, "scales", 1, 1, undefined, true);
  group(meta, "quats", 1);
  group(meta, "sh0", 1, 1, undefined, true);
  if (meta.shN !== undefined) {
    const g = group(meta, "shN", 2, 2, undefined, true);
    number(g.bands, "SH degree", 1, 3, true);
    number(g.count, "SH palette count", 1, 65536, true);
  }
  if (meta.timeline !== undefined) {
    const g = meta.timeline;
    if (!object(g) || ![0, 1].includes(g.type)) fail("unsupported timeline");
    group(meta, "timeline", 2, 2, g.type === 1 ? 2 : undefined);
    if (g.type === 0) {
      number(g.N, "frame count", 1, 65536, true);
      if (g.delta !== Math.floor(65536 / g.N)) fail("discrete delta");
    } else if (!(Math.fround(g.mins[1]) > 0)) fail("sigma must remain positive in float32");
  }
  if (meta.temporal !== undefined) {
    if (!meta.timeline || !object(meta.temporal) || Object.keys(meta.temporal).join(",") !== "means") fail("unsupported temporal attribute");
    const g = group(meta.temporal, "means", 1, 2);
    if (!Array.isArray(g.mins) || g.mins.length !== 1 || !Array.isArray(g.maxs) || g.maxs.length !== 1) fail("motion shape");
    group({ motion: { ...g, mins: g.mins[0], maxs: g.maxs[0] } }, "motion", 1, 2, 3);
  }
  if (meta.fps !== undefined && number(meta.fps, "legacy FPS", 0) === 0) fail("zero FPS");
  if (meta.playback !== undefined) {
    if (!object(meta.playback)) fail("playback object");
    for (const key of ["fps", "duration"]) if (meta.playback[key] !== undefined && number(meta.playback[key], key, 0) === 0) fail(`zero ${key}`);
    if (meta.playback.rate !== undefined) number(meta.playback.rate, "rate", .25, 4);
    if (meta.playback.loop !== undefined && typeof meta.playback.loop !== "boolean") fail("loop boolean");
  }
  mediaTiming(meta);
  if (meta.audio !== undefined) {
    if (!object(meta.audio)) fail("audio object");
    entryName(meta.audio.file);
    const names = ["means", "scales", "quats", "sh0", "shN", "timeline"].flatMap(k => meta[k]?.files ?? []);
    names.push(...(meta.temporal?.means.files ?? []));
    if (meta.audio.file === "meta.json" || names.includes(meta.audio.file)) fail("audio reference collision");
    audioMime(meta.audio);
    if (meta.audio.volume !== undefined) number(meta.audio.volume, "volume", 0, 1);
    if (!meta.timeline && meta.playback?.duration === undefined) fail("static audio requires duration");
  }
  return meta;
}
const f32 = n => { const value = Math.fround(n); if (!Number.isFinite(value)) fail("non-finite decoded attribute"); return value; };
function covarianceFinite(scale, q) {
  if (Math.max(...scale) <= Math.sqrt(MAX / 4)) return;
  const [w, x, y, z] = q;
  const r = [[1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)], [2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)], [2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)]];
  for (let a = 0; a < 3; a++) for (let b = a; b < 3; b++) f32(r[a].reduce((sum, value, c) => sum + value * r[b][c] * scale[c] ** 2, 0));
}
export async function decodeAttributes(meta, loadImage, { maxPoints = 10000000, onProgress = () => {}, signal } = {}) {
  validateMetadata(meta);
  const n = meta.count;
  if (n > maxPoints) fail("device/resource limit: point count");
  let dimensions;
  const image = async (name, perPoint = true) => {
    signal?.throwIfAborted();
    onProgress({ stage: "attribute", name });
    const result = await loadImage(name);
    const { width, height, pixels } = result;
    if (!Number.isInteger(width) || !Number.isInteger(height) || width < 1 || height < 1 || width > 16384 || height > 16384 || !(pixels instanceof Uint8Array) || pixels.length !== width * height * 4) fail("invalid decoded image");
    if (perPoint) {
      if (width * height < n || dimensions && (dimensions[0] !== width || dimensions[1] !== height)) fail("per-point dimensions mismatch");
      dimensions = [width, height];
    }
    return result;
  };
  const pair = async g => [await image(g.files[0]), g.files.length === 2 ? await image(g.files[1]) : null];
  const code = (low, high, at) => low[at] + (high ? 256 * high[at] : 0);
  const book = (values, index) => { if (index >= values.length) fail("codebook index out of bounds"); return f32(values[index]); };
  const model = { metadata: meta, positions: new Float32Array(n * 3), scales: new Float32Array(n * 3),
    quaternions: new Float32Array(n * 4), dc: new Float32Array(n * 3), opacity: new Float32Array(n) };
  {
    const [low, high] = await pair(meta.means), table = new Float64Array(65536);
    for (let axis = 0; axis < 3; axis++) {
      const lo = meta.means.mins[axis], span = meta.means.maxs[axis] - lo;
      for (let q = 0; q < 65536; q++) { const value = lo + span * (q / 65535); table[q] = Math.sign(value) * Math.expm1(Math.abs(value)); }
      for (let i = 0; i < n; i++) model.positions[i * 3 + axis] = f32(table[code(low.pixels, high.pixels, i * 4 + axis)]);
    }
  }
  {
    const { pixels } = await image(meta.scales.files[0]);
    const values = meta.scales.codebook.map(v => Math.exp(v));
    for (let i = 0; i < n; i++) for (let a = 0; a < 3; a++) {
      const value = book(values, pixels[i * 4 + a]);
      if (value <= 0) fail("non-positive decoded scale");
      model.scales[i * 3 + a] = value;
    }
  }
  {
    const { pixels } = await image(meta.quats.files[0]), q = new Float64Array(4);
    for (let i = 0; i < n; i++) {
      const p = i * 4, missing = pixels[p + 3] - 252;
      if (missing < 0) fail("quaternion tag");
      let square = 0, channel = 0;
      for (let a = 0; a < 4; a++) if (a !== missing) { q[a] = (2 * pixels[p + channel++] / 255 - 1) / SQRT2; square += q[a] * q[a]; }
      q[missing] = Math.sqrt(Math.max(0, 1 - square));
      const length = Math.hypot(...q);
      for (let a = 0; a < 4; a++) model.quaternions[p + a] = f32(q[a] / length);
      if (Math.max(model.scales[i * 3], model.scales[i * 3 + 1], model.scales[i * 3 + 2]) > Math.sqrt(MAX / 4)) covarianceFinite(model.scales.subarray(i * 3, i * 3 + 3), model.quaternions.subarray(p, p + 4));
    }
  }
  {
    const { pixels } = await image(meta.sh0.files[0]);
    for (let i = 0; i < n; i++) {
      for (let a = 0; a < 3; a++) model.dc[i * 3 + a] = book(meta.sh0.codebook, pixels[i * 4 + a]);
      model.opacity[i] = pixels[i * 4 + 3] / 255;
    }
  }
  if (meta.timeline) {
    const g = meta.timeline, [low, high] = await pair(g);
    if (g.type === 0) {
      model.frame_ids = new Uint16Array(n);
      for (let i = 0; i < n; i++) model.frame_ids[i] = Math.min(g.N - 1, Math.floor(code(low.pixels, high.pixels, i * 4) / g.delta));
    } else {
      model.centers = new Float32Array(n); model.sigmas = new Float32Array(n);
      for (let i = 0; i < n; i++) {
        model.centers[i] = f32(g.mins[0] + (g.maxs[0] - g.mins[0]) * (code(low.pixels, high.pixels, i * 4) / 65535));
        model.sigmas[i] = f32(g.mins[1] + (g.maxs[1] - g.mins[1]) * (code(low.pixels, high.pixels, i * 4 + 1) / 65535));
        if (model.sigmas[i] <= 0) fail("non-positive temporal sigma");
      }
    }
  }
  if (meta.temporal) {
    const g = meta.temporal.means, [low, high] = await pair(g), maximum = high ? 65535 : 255;
    const velocity = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) for (let a = 0; a < 3; a++) velocity[i * 3 + a] = f32(g.mins[0][a] + (g.maxs[0][a] - g.mins[0][a]) * (code(low.pixels, high?.pixels, i * 4 + a) / maximum));
    if (model.centers) model.velocities = velocity;
  }
  if (meta.shN) {
    const g = meta.shN, k = (g.bands + 1) ** 2 - 1, palette = await image(g.files[0], false);
    if (palette.width !== 64 * k || palette.height !== Math.ceil(g.count / 64)) fail("SH palette dimensions");
    model.sh_palette = new Float32Array(g.count * k * 3);
    for (let i = 0; i < g.count * k; i++) for (let a = 0; a < 3; a++) model.sh_palette[i * 3 + a] = book(g.codebook, palette.pixels[i * 4 + a]);
    const { pixels } = await image(g.files[1]);
    model.sh_labels = new Uint16Array(n);
    for (let i = 0; i < n; i++) {
      const label = pixels[i * 4] + 256 * pixels[i * 4 + 1];
      if (label >= g.count) fail("SH palette label");
      model.sh_labels[i] = label;
    }
  }
  signal?.throwIfAborted();
  return model;
}
export async function decodeTSOG(blob, options = {}) {
  const archive = await readZIP(blob, options);
  const metadata = validateMetadata(JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(await archive.read("meta.json", 4 * 1048576))), options);
  const webp = createWebPDecoder();
  try {
    const model = await decodeAttributes(metadata, async name => webp.decode(await archive.read(name)), options);
    if (metadata.audio) {
      const bytes = await archive.read(metadata.audio.file, 128 * 1048576);
      if (!bytes.length) fail("empty audio");
      model.audio = new Blob([bytes], { type: audioMime(metadata.audio) });
    }
    return model;
  } finally { webp.close(); }
}
