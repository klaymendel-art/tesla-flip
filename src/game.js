/* Tesla Flip — src/game.js
 * Vanilla Canvas 2D, no build step. Contract: docs/DESIGN.md.
 *
 * Sections: 1 config · 2 assets/loader · 3 layout & pre-scaled sprites · 4 world state
 *           5 gameplay (flip, obstacles, crash) · 6 update · 7 render · 8 input & boot.
 * Units: all gameplay distances are in CSS px, tuned as multiples of carW (the Roadster's
 * on-screen length), so the game plays identically on every screen size.
 * Audio lives in src/audio.js (global `Snd`).
 */
'use strict';

/* ───────────────────────────── 1. Config ───────────────────────────── */
const CFG = {
  DPR_MAX: 2,
  FIXED_DT: 1 / 120,            // physics step, s
  MAX_FRAME_DT: 0.1,            // clamp after tab switches
  SCROLL_SPEED: 3.0,            // road speed, carW per second (base)
  SPEED_RAMP: 0.04, SPEED_STEP: 5, SPEED_CAP: 1.6,   // +4 % every 5 points, capped at 1.6×
  PARALLAX: { bg_far: 0.15, bg_mid: 0.4, bg_near: 0.8, clouds: 0.05 },
  LAYER_REF_H: 1920,            // bg layers are authored for a 1920 px-tall portrait frame
  NEAR_FIT: [0.9, 1.6],         // bg_near is stretched to fill horizon→kerb, within these × of layer scale
  LAYOUT: {                     // fractions of screen height / width
    portrait: { horizon: 0.66, ground: 0.80, carWFrac: 0.27, playerX: 0.24 },
    landscape: { horizon: 0.62, ground: 0.82, carWFrac: 0.20, playerX: 0.28 },
    curb: 0.025, dash: 0.38, farLift: 0.07,       // kerb height, dash row inside the road, bg_far raised above horizon
    sun: { x: 0.72, up: 0.16, r: 0.07 },          // r × min(W,H); up × H above the horizon
    hudTop: 0.10, stars: 48, clouds: 3,
  },
  STACK_FIT: 2.8,               // car + rider + double-flip apex, in carW (keeps it on screen)
  MUSK_H: 0.95,                 // rider height in carW
  MUSK_FOOT_X: 430 / 900,       // feet centre along the car (artist pivot)
  MUSK_SINK: 6 / 900,           // soles sink into the roof, in carW
  // Flips. carPeak = Roadster apex (in carW); the rider is glued to the board. The car lags takeoff by carDelay.
  // Durations are at 1.0× road speed. Flight time scales with speed^-SPEED_TIME_EXP: at 1.0 the jump LENGTH
  // would be constant and tap windows shrink 1:1 with speed; 0.75 lets the jump grow ~12 % at the 1.6× cap so
  // the tightest windows (pickup, pair doubles) stay playable while pairs remain double-only.
  FLIP:   { dur: 1.0, turns: 1, carPeak: 0.90, carDelay: 0.03 },
  DOUBLE: { dur: 1.35, turns: 2, carPeak: 1.05 },             // shorter hang than before: the double is a commitment
  DOUBLE_TAP_MS: 200,
  QUEUE_WINDOW_S: 0.15,         // a mid-air tap only queues a flip this close to landing
  SPIN_FRAC: 0.94,              // rotation completes at this fraction of the flight
  SPEED_TIME_EXP: 0.75,
  FLIP_SFX_RATE_MAX: 1.3,       // flip whoosh speeds up with the shorter flight, capped
  // Kickflip rendering: 8 pre-rendered roll keyframes at 45° (000 = side, 090 = belly, 180 = side flipped,
  // 270 = top, plus the artist's 045/135/225/315). Between keyframes a small vertical squash + cross-fade hides the steps.
  ROLL: { squash: 0.92, blend: 0.15 },   // frames are 3/4 views: keep the smoothing squash <= 8 %
  RIDER_GAP: 0.12,              // rider lift above the car's top edge at the apex, × carH (0 at takeoff/landing)
  IDLE: { hz: 1.6, knees: 0.02 },   // riding idle: knee bob (rider squash) at 1.6 Hz, ~±2 px of head travel
  WHEELS: [{ x: 142, y: 201, r: 80 }, { x: 716, y: 201, r: 80 }],  // tyre centres/radii in tesla_side px (measured; wheel bottom row 281)
  WHEEL_AIR_SPIN: 0.6,          // wheels keep spinning a bit slower in the air
  TILT_Z: 8 * Math.PI / 180,
  LEAN: 9 * Math.PI / 180,
  SQUASH: { ms: 80, x: 1.12, y: 0.9 },
  SHAKE: { px: 2, ms: 130 },
  BOB: { hz: 2.1, px: 2.5 },
  // Obstacles. Hitboxes are 1–3 boxes per kind (hood / cab / bed), as fractions of the sprite
  // (x from the nose, top = height from the ground), already shrunk ≈6 %/side; the right 10 % is
  // left out because the exhaust puff is baked into the sprites.
  OBST_KINDS: ['obst_muscle', 'obst_pickup', 'obst_sedan'],
  HITBOX: {
    obst_muscle: [{ x1: 0.06, x2: 0.35, top: 0.70 }, { x1: 0.35, x2: 0.75, top: 0.94 }, { x1: 0.75, x2: 0.90, top: 0.70 }],
    obst_pickup: [{ x1: 0.06, x2: 0.25, top: 0.64 }, { x1: 0.25, x2: 0.55, top: 0.88 }, { x1: 0.55, x2: 0.90, top: 0.74 }],
    obst_sedan:  [{ x1: 0.06, x2: 0.30, top: 0.60 }, { x1: 0.30, x2: 0.75, top: 0.94 }, { x1: 0.75, x2: 0.90, top: 0.64 }],
  },
  PLAYER_SHRINK: 0.15, PLAYER_LENIENCY: 0.08,  // AABB inset; leniency lifts the player's bottom (in carW)
  GAP_SLACK: 1.05,              // carW added to the single-flip length for the minimum gap (distance, not time)
  GAP_RAND: [1.3, 0.4], GAP_RAND_SCORE: 40,   // max extra gap (× min gap) shrinks from [0] to [1] by this score
  PAIR_CHANCE: [0.2, 0.4], PAIR_CHANCE_SCORE: 60, PAIR_MIN_SCORE: 4, PAIR_GAP: [0.33, 0.45],  // pairs (gap in carW) need the double; chance ramps with score
  FIRST_SPAWN_S: 1.6,
  PUFF_EVERY: [0.7, 1.8], PUFF_AT: { x: 0.93, y: 0.12 },
  CRASH_S: 0.8,
  POOL: { particles: 96, lines: 12, pops: 4, obstacles: 6 },
  KEY_BEST: 'teslaflip.best',
};

const IMG_FILES = {
  musk_ride: 'assets/img/musk_ride.png', musk_air: 'assets/img/musk_air.png',
  tesla_side: 'assets/img/tesla_side.png', tesla_bottom: 'assets/img/tesla_bottom.png', tesla_top: 'assets/img/tesla_top.png',
  tesla_roll_045: 'assets/img/tesla_roll_045.png', tesla_roll_135: 'assets/img/tesla_roll_135.png',
  tesla_roll_225: 'assets/img/tesla_roll_225.png', tesla_roll_315: 'assets/img/tesla_roll_315.png',
  bg_far: 'assets/img/bg_far.png', bg_mid: 'assets/img/bg_mid.png', bg_near: 'assets/img/bg_near.png',
  obst_muscle: 'assets/img/obst_muscle.png', obst_pickup: 'assets/img/obst_pickup.png', obst_sedan: 'assets/img/obst_sedan.png',
};
// Natural sizes used for placeholders when a file is missing (from the art contract).
const IMG_FALLBACK = {
  musk_ride: [430, 900], musk_air: [519, 817], tesla_side: [900, 282], tesla_bottom: [900, 434], tesla_top: [900, 434],
  tesla_roll_045: [900, 421], tesla_roll_135: [900, 421], tesla_roll_225: [900, 441], tesla_roll_315: [900, 441],
  bg_far: [2048, 379], bg_mid: [2048, 417], bg_near: [2048, 211],
  obst_muscle: [940, 316], obst_pickup: [1000, 470], obst_sedan: [900, 327],
};
const PLACEHOLDER_COLOR = {
  musk_ride: '#5aa0e6', musk_air: '#7cc1ff', tesla_side: '#e9e9e4', tesla_bottom: '#3a3a48', tesla_top: '#d9d9d4',
  bg_far: '#6b5fa8', bg_mid: '#4e4178', bg_near: '#7a7490',
  obst_muscle: '#f08a2a', obst_pickup: '#6e7d55', obst_sedan: '#b0966e',
};
const COLORS = {
  ink: '#1b1430', red: '#e82127', gold: '#ffe27a', lilac: '#e8e0ff',
  sky: ['#241a4d', '#6a3a8c', '#d9603f', '#ffb46a'], sun: '#ffd27a', sunGlow: '#ffe0a0',
  bandTop: '#4a4668', bandBottom: '#58577e',   // bandBottom = bg_near pavement colour
  road: '#2f2d3a', curb: '#8f889f', dash: 'rgba(231,217,160,0.8)', dust: '#cdbfaa', smoke: '#2b2733',
};
const FONT_FAMILY = '"Arial Rounded MT Bold", "Trebuchet MS", "Segoe UI", system-ui, sans-serif';
const TAU = Math.PI * 2;
const DEBUG = /[?&]debug=1/.test(location.search);

/* ───────────────────────────── 2. Assets ───────────────────────────── */
const images = {};   // name → HTMLImageElement | null (null = missing → placeholder)

function loadImages(onProgress) {
  const names = Object.keys(IMG_FILES);
  let done = 0;
  return Promise.all(names.map((n) => new Promise((resolve) => {
    const img = new Image();
    const finish = (ok) => { images[n] = ok ? img : null; onProgress(++done / names.length); resolve(); };
    img.onload = () => finish(true);
    img.onerror = () => { console.warn('[TeslaFlip] image missing (fallback in use): ' + IMG_FILES[n]); finish(false); };
    img.src = IMG_FILES[n];
  })));
}
function natSize(name) {
  const img = images[name];
  return img ? [img.naturalWidth, img.naturalHeight] : IMG_FALLBACK[name];
}

/* ─────────────────── 3. Layout & pre-scaled sprites ─────────────────── */
const canvas = document.getElementById('game');
const ctx = canvas.getContext('2d', { alpha: false });

const L = {    // everything derived from the viewport; rebuilt on resize
  W: 1, H: 1, dpr: 1, portrait: true, safe: { t: 0, r: 0, b: 0, l: 0 },
  horizonY: 0, groundY: 0, roadTop: 0, dashY: 0, playerX: 0,
  carW: 100, carH: 32, px: 0.1, muskS: 0.1, muskFootX: 0,
  layerS: 1, btn: { x: 0, y: 0, r: 40 }, showBtn: true, mute: { x: 0, y: 0, s: 44 },
  fonts: {}, sky: null, band: null, sun: { x: 0, y: 0, r: 0 },
  stars: [], clouds: [],
};
for (let i = 0; i < CFG.LAYOUT.stars; i++) L.stars.push({ x: 0, y: 0, r: 1, a: 0.5 });
for (let i = 0; i < CFG.LAYOUT.clouds; i++) L.clouds.push({ x: 0, y: 0, w: 0, h: 0 });
const SPR = {};   // name → { cv, w, h } pre-scaled to device pixels; w/h in CSS px

function readSafeInset(cs, v) { return parseFloat(cs.getPropertyValue(v)) || 0; }
/** Small deterministic PRNG so stars/clouds don't reshuffle on every resize. */
function seeded(seed) { let s = seed >>> 0; return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; }; }

function layout() {
  const W = Math.max(1, window.innerWidth), H = Math.max(1, window.innerHeight);
  const dpr = Math.min(CFG.DPR_MAX, window.devicePixelRatio || 1);
  canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
  canvas.style.width = W + 'px'; canvas.style.height = H + 'px';
  L.W = W; L.H = H; L.dpr = dpr; L.portrait = H >= W;
  const LY = CFG.LAYOUT, mode = LY[L.portrait ? 'portrait' : 'landscape'];
  const cs = getComputedStyle(document.documentElement);
  L.safe = { t: readSafeInset(cs, '--sat'), r: readSafeInset(cs, '--sar'), b: readSafeInset(cs, '--sab'), l: readSafeInset(cs, '--sal') };

  L.horizonY = Math.round(H * mode.horizon);
  L.groundY = Math.round(H * mode.ground);
  L.roadTop = L.groundY - Math.round(H * LY.curb);
  L.dashY = L.groundY + (H - L.groundY) * LY.dash;
  L.playerX = Math.round(W * mode.playerX);

  const topSafe = L.safe.t + H * LY.hudTop;
  L.carW = Math.min(W * mode.carWFrac, (L.groundY - topSafe) / CFG.STACK_FIT);
  const [cw0, ch0] = natSize('tesla_side');
  L.px = L.carW / cw0;                       // world pixel scale: 900 sprite px ≈ one car length
  L.carH = ch0 * L.px;
  const [, mh0] = natSize('musk_ride');
  L.muskS = CFG.MUSK_H * L.carW / mh0;       // same scale for both rider frames
  L.muskFootX = L.playerX + (CFG.MUSK_FOOT_X - 0.5) * L.carW;
  L.layerS = H / CFG.LAYER_REF_H;

  const m = Math.min(W, H);
  L.btn.r = clamp(m * 0.11, 34, 60);
  L.btn.y = H - L.safe.b - L.btn.r - m * 0.04;
  L.btn.x = W / 2;
  L.showBtn = L.portrait;   // landscape has no room below the lane (cars would pass behind it): tap anywhere / keys
  L.mute.s = 44; L.mute.x = W - L.safe.r - 12 - 44; L.mute.y = L.safe.t + 12;
  L.sun.x = W * LY.sun.x; L.sun.y = L.horizonY - H * LY.sun.up; L.sun.r = m * LY.sun.r;

  const rnd = seeded(7);
  for (const s of L.stars) { s.x = rnd() * W; s.y = rnd() * L.sun.y * 0.9; s.r = 0.7 + rnd() * 1.1; s.a = 0.25 + rnd() * 0.55; }
  for (const c of L.clouds) { c.x = rnd() * W; c.y = L.horizonY * (0.35 + rnd() * 0.3); c.w = m * (0.18 + rnd() * 0.14); c.h = c.w * 0.3; }

  const fs = (key, size) => { L.fonts[key] = { str: '900 ' + size + 'px ' + FONT_FAMILY, size }; return size; };
  const hud = fs('hud', clamp(m * 0.13, 28, 72));
  fs('best', hud * 0.38);
  const title = fs('title', clamp(m * 0.17, 36, 110));
  fs('tap', clamp(m * 0.07, 18, 44)); fs('hint', clamp(m * 0.032, 11, 20));
  fs('btn', L.btn.r * 0.5); fs('pop', clamp(m * 0.08, 20, 44));
  const panel = clamp(m * 0.11, 26, 64);
  fs('panel', panel * 0.8); fs('panelS', panel * 0.45); fs('panelTap', panel * 0.52);
  L.panelUnit = panel; L.titleSize = title;

  L.sky = ctx.createLinearGradient(0, 0, 0, L.horizonY);
  COLORS.sky.forEach((c, i) => L.sky.addColorStop([0, 0.45, 0.8, 1][i], c));
  L.band = ctx.createLinearGradient(0, L.horizonY, 0, L.roadTop);   // far plaza, blends into the bg_near pavement
  L.band.addColorStop(0, COLORS.bandTop); L.band.addColorStop(1, COLORS.bandBottom);

  buildSprites();
  for (const o of G.obstacles) if (o.alive) sizeObstacle(o);
}

function buildSprites() {
  const s = L.px;
  for (const n of ['musk_ride', 'musk_air']) { const [w, h] = natSize(n); sprite(n, w * L.muskS, h * L.muskS); }
  for (const n of ['tesla_side', 'tesla_bottom', ...CFG.OBST_KINDS]) { const [w, h] = natSize(n); sprite(n, w * s, h * s); }
  buildRollFrames();
  buildWheels();
  for (const n of ['bg_far', 'bg_mid']) { const [w, h] = natSize(n); sprite(n, w * L.layerS, h * L.layerS); }
  // bg_near is the kerb: stretch it (within limits) so it exactly fills horizon → kerb and no flat band shows.
  const [nw, nh] = natSize('bg_near');
  const want = (L.roadTop - 2 - L.horizonY) / nh;
  const k = clamp(want, L.layerS * CFG.NEAR_FIT[0], L.layerS * CFG.NEAR_FIT[1]);
  sprite('bg_near', nw * k, nh * k);
}

/** (Re)build one pre-scaled sprite canvas; reuses the canvas element across resizes. */
function sprite(name, w, h) {
  let sp = SPR[name];
  if (!sp) sp = SPR[name] = { cv: document.createElement('canvas'), w: 0, h: 0 };
  const pw = Math.max(1, Math.round(w * L.dpr)), ph = Math.max(1, Math.round(h * L.dpr));
  sp.cv.width = pw; sp.cv.height = ph; sp.w = w; sp.h = h;
  const c = sp.cv.getContext('2d');
  c.imageSmoothingEnabled = true; c.imageSmoothingQuality = 'high';
  const img = images[name];
  if (img) {
    c.drawImage(img, 0, 0, pw, ph);
  } else if (name === 'tesla_bottom' && images.tesla_side) {
    // Contract fallback: no belly sprite → darkened side view.
    c.drawImage(images.tesla_side, 0, 0, pw, ph);
    c.globalCompositeOperation = 'source-atop';
    c.fillStyle = 'rgba(25,22,40,0.7)'; c.fillRect(0, 0, pw, ph);
  } else {
    c.fillStyle = PLACEHOLDER_COLOR[name] || '#888'; c.fillRect(0, 0, pw, ph);
    c.lineWidth = Math.max(2, 4 * L.dpr); c.strokeStyle = COLORS.ink; c.strokeRect(0, 0, pw, ph);
    c.fillStyle = COLORS.ink; c.textAlign = 'center'; c.textBaseline = 'middle';
    c.font = 'bold ' + Math.max(10, Math.min(ph * 0.3, pw * 0.09)) + 'px ' + FONT_FAMILY;
    c.fillText(name, pw / 2, ph / 2);
  }
  return sp;
}

/** Vertically flipped copy of a sprite (the 180° roll keyframe). */
function flipCopy(name, src) {
  let sp = SPR[name];
  if (!sp) sp = SPR[name] = { cv: document.createElement('canvas'), w: 0, h: 0 };
  sp.cv.width = src.cv.width; sp.cv.height = src.cv.height; sp.w = src.w; sp.h = src.h;
  const c = sp.cv.getContext('2d');
  c.translate(0, sp.cv.height); c.scale(1, -1); c.drawImage(src.cv, 0, 0);
  return sp;
}

/** Opaque row range of an image as fractions of its height (alpha ≥ 128; quantised art has interior alpha 250–254).
 *  Computed once per image on a 64 px thumbnail; falls back to the full height if pixels are unreadable (file://). */
const alphaBoundsCache = {};
function alphaBounds(name) {
  if (alphaBoundsCache[name]) return alphaBoundsCache[name];
  let top = 0, bottom = 1;
  const img = images[name];
  if (img) {
    try {
      const cv = document.createElement('canvas'); cv.width = 64; cv.height = 64;
      const c = cv.getContext('2d'); c.drawImage(img, 0, 0, 64, 64);
      const d = c.getImageData(0, 0, 64, 64).data;
      let first = -1, last = -1;
      for (let y = 0; y < 64; y++) for (let x = 0; x < 64; x++) if (d[(y * 64 + x) * 4 + 3] >= 128) { if (first < 0) first = y; last = y; break; }
      if (first >= 0) { top = first / 64; bottom = (last + 1) / 64; }
    } catch (e) { /* tainted canvas → keep full height */ }
  }
  return (alphaBoundsCache[name] = { top, bottom });
}

/** The 8 roll keyframes (45° apart). Missing files fall back to the nearest existing keyframe — never a blank. */
const ROLL_KEYS = ['tesla_side', 'tesla_roll_045', 'tesla_bottom', 'tesla_roll_135', 'tesla_side_flip', 'tesla_roll_225', 'tesla_top', 'tesla_roll_315'];
const ROLL = ROLL_KEYS.map(() => ({ sp: null, top: 0, mid: 0, flipped: false, side: false }));
function buildRollFrames() {
  flipCopy('tesla_side_flip', SPR.tesla_side);
  const have = {};
  for (const n of ['tesla_roll_045', 'tesla_roll_135', 'tesla_roll_225', 'tesla_top']) {
    if (images[n]) { const [w, h] = natSize(n); sprite(n, w * L.px, h * L.px); have[n] = true; }
  }
  have.tesla_side = have.tesla_side_flip = have.tesla_bottom = true;   // always available (bottom has its own fallback)
  for (let k = 0; k < 8; k++) {
    let src = k;
    for (let d = 0; d < 8 && !have[ROLL_KEYS[src]]; d++) src = (k + [-1, 1, -2, 2, -3, 3, 4][d] + 8) % 8;   // nearest existing
    const name = ROLL_KEYS[src], sp = SPR[name], fr = ROLL[k];
    const base = name === 'tesla_side_flip' ? alphaBounds('tesla_side') : alphaBounds(name === 'tesla_bottom' && !images.tesla_bottom ? 'tesla_side' : name);
    const b = name === 'tesla_side_flip' ? { top: 1 - base.bottom, bottom: 1 - base.top } : base;
    fr.sp = sp; fr.top = b.top * sp.h; fr.mid = (b.top + b.bottom) * 0.5 * sp.h;
    fr.side = src === 0 || src === 4; fr.flipped = src === 4;
  }
}

/** Circular cut-outs of the two tyres from the side sprite, rotated at run time so the wheels spin. */
const WHEELS = CFG.WHEELS.map(() => ({ cv: document.createElement('canvas'), x: 0, y: 0, r: 0 }));
function buildWheels() {
  const img = images.tesla_side;
  CFG.WHEELS.forEach((w, i) => {
    const W = WHEELS[i];
    W.r = w.r * L.px; W.x = w.x * L.px; W.y = w.y * L.px;
    const d = Math.max(2, Math.round(W.r * 2 * L.dpr));
    W.cv.width = d; W.cv.height = d;
    if (!img) return;
    const c = W.cv.getContext('2d');
    c.beginPath(); c.arc(d / 2, d / 2, d / 2 - 0.5, 0, TAU); c.clip();
    const k = L.px * L.dpr;    // sprite px → device px
    c.drawImage(img, d / 2 - w.x * k, d / 2 - w.y * k, img.naturalWidth * k, img.naturalHeight * k);
  });
}

/* ───────────────────────────── 4. State ───────────────────────────── */
const G = {
  state: 'boot',                 // boot → title → play → crash → over → play …
  progress: 0, time: 0, scroll: 0,
  speedMul: 1,                   // ramps with score
  roadK: 1,                      // 0..1, road motion factor (eases to 0 during a crash)
  score: 0, best: 0, scoreStr: '0', bestStr: 'BEST 0', newBest: false,
  flip: { active: false, t: 0, dur: 1, turns: 1, cy: 0, cvy: 0, cg: 0, carDelay: 0, theta: 0, omega: 0, thetaMax: 0 },
  wheelA: 0,                     // wheel spin angle
  queued: false,
  squashT: 0, shakeT: 0, btnT: 0,  // ms timers
  dustTimer: 0,
  spawnDist: 0, nextKind: 'obst_sedan', nextPair: false,
  crash: { t: 0, mx: 0, my: 0, mvx: 0, mvy: 0, ma: 0, mav: 0, cx: 0, cy: 0, cvx: 0, cvy: 0, ca: 0, cav: 0 },
  particles: [], lines: [], pops: [], obstacles: [],
  paused: false,                 // QA hook: freezes the rAF physics so TF.step() can drive it
};
for (let i = 0; i < CFG.POOL.particles; i++) G.particles.push({ life: 0, max: 1, x: 0, y: 0, vx: 0, vy: 0, r: 1, smoke: false });
for (let i = 0; i < CFG.POOL.lines; i++) G.lines.push({ x: 0, y: 0, len: 0, spd: 1, a: 0.2 });
for (let i = 0; i < CFG.POOL.pops; i++) G.pops.push({ alive: false, x: 0, y: 0, t: 0, text: '' });
for (let i = 0; i < CFG.POOL.obstacles; i++) G.obstacles.push({ alive: false, kind: 'obst_sedan', x: 0, w: 0, h: 0, scored: false, puffT: 0 });

try { G.best = parseInt(localStorage.getItem(CFG.KEY_BEST), 10) || 0; } catch (e) { /* storage blocked */ }
G.bestStr = 'BEST ' + G.best;

function clamp(v, a, b) { return v < a ? a : v > b ? b : v; }
function rand(a, b) { return a + Math.random() * (b - a); }
function roadSpeed() { return CFG.SCROLL_SPEED * L.carW * G.speedMul * G.roadK; }  // px/s
function squashK() { return G.squashT > 0 ? G.squashT / CFG.SQUASH.ms : 0; }
function muskH() { return SPR.musk_ride.h; }

/* ───────────────────────────── 5. Gameplay ───────────────────────────── */
function startFlip(kind) {
  const f = G.flip, cw = L.carW, sm = Math.pow(G.speedMul, CFG.SPEED_TIME_EXP);
  const dur = kind.dur / sm, cd = CFG.FLIP.carDelay / sm, cdur = dur - cd;   // ~same length over the road at any speed
  const hc = kind.carPeak * cw;
  f.active = true; f.t = 0; f.dur = dur; f.turns = kind.turns;
  // Parabola with explicit velocity/gravity so a mid-air upgrade to a double stays continuous.
  f.cy = 0; f.cvy = 4 * hc / cdur; f.cg = 8 * hc / (cdur * cdur); f.carDelay = cd;
  f.theta = 0; f.thetaMax = TAU * kind.turns; f.omega = f.thetaMax / (dur * CFG.SPIN_FRAC);
  G.squashT = 0;
  spawnDust(L.playerX - cw * 0.3, L.groundY, 6, 1);
  Snd.play('pop'); Snd.play('flip', Math.min(CFG.FLIP_SFX_RATE_MAX, sm), 0.05);   // whoosh keeps pace with the flight
}

/** Second tap within DOUBLE_TAP_MS of takeoff: re-solve gravity so the current height/velocity
 *  flow into a longer, higher flight that touches down exactly at DOUBLE.dur. */
function upgradeToDouble() {
  const f = G.flip, K = CFG.DOUBLE, dur = K.dur / Math.pow(G.speedMul, CFG.SPEED_TIME_EXP), tau = dur - f.t;
  f.turns = 2; f.dur = dur;
  if (f.t >= f.carDelay) f.cg = 2 * (f.cy + f.cvy * tau) / (tau * tau);
  else { const hc = K.carPeak * L.carW, cdur = dur - f.carDelay; f.cvy = 4 * hc / cdur; f.cg = 8 * hc / (cdur * cdur); }
  f.thetaMax = TAU * 2; f.omega = (f.thetaMax - f.theta) / (tau * CFG.SPIN_FRAC);
  Snd.play('flip', Math.min(CFG.FLIP_SFX_RATE_MAX, 1.2 * G.speedMul));
}

function land() {
  const f = G.flip;
  f.active = false; f.cy = 0; f.theta = 0;
  G.squashT = CFG.SQUASH.ms; G.shakeT = CFG.SHAKE.ms;
  spawnDust(L.playerX - L.carW * 0.33, L.groundY, 7, 1.2);
  spawnDust(L.playerX + L.carW * 0.33, L.groundY, 7, 1.2);
  Snd.play('land');
  if (f.turns > 1) Snd.play('combo', 1, 0.08);
}

function tryFlip() {
  const f = G.flip;
  if (!f.active) { startFlip(CFG.FLIP); return; }
  if (f.turns === 1 && f.t * 1000 <= CFG.DOUBLE_TAP_MS) upgradeToDouble();
  else if (f.dur - f.t <= CFG.QUEUE_WINDOW_S) G.queued = true;   // late tap: one flip right after landing
}

/* Obstacles --------------------------------------------------------------- */
function sizeObstacle(o) { const sp = SPR[o.kind]; o.w = sp.w; o.h = sp.h; }
function spawnObstacle(kind, x) {
  for (const o of G.obstacles) {
    if (o.alive) continue;
    o.alive = true; o.kind = kind; sizeObstacle(o);
    o.x = x === undefined ? L.W + L.carW * 0.15 : x;
    o.scored = false; o.puffT = rand(CFG.PUFF_EVERY[0], CFG.PUFF_EVERY[1]);
    return o;
  }
  return null;
}
function lowKind() { return Math.random() < 0.5 ? 'obst_muscle' : 'obst_sedan'; }

/** Spawns the next obstacle — or a close pair (both cars at once, so the pair is readable the
 *  moment it enters the screen; it needs the double flip) — and schedules the one after it. */
function spawnNext() {
  const first = spawnObstacle(G.nextKind);
  if (!first) return;
  let span = first.w, wasPair = false;
  if (G.nextPair) {
    const partner = spawnObstacle(lowKind(), first.x + first.w + rand(CFG.PAIR_GAP[0], CFG.PAIR_GAP[1]) * L.carW);
    if (partner) { span = partner.x + partner.w - first.x; wasPair = true; }
  }
  // Minimum gap is a distance (flip length at 1.0× + slack), so it stays fair at any speed.
  const flipDur = wasPair ? CFG.DOUBLE.dur : CFG.FLIP.dur;     // recovering from a double takes longer
  const minGap = (CFG.SCROLL_SPEED * flipDur + CFG.GAP_SLACK) * L.carW;
  const k = Math.min(1, G.score / CFG.GAP_RAND_SCORE);          // gaps tighten as the score climbs
  const gapRand = CFG.GAP_RAND[0] + (CFG.GAP_RAND[1] - CFG.GAP_RAND[0]) * k;
  G.spawnDist = span + minGap * (1 + Math.random() * gapRand);
  const pairChance = CFG.PAIR_CHANCE[0] + (CFG.PAIR_CHANCE[1] - CFG.PAIR_CHANCE[0]) * Math.min(1, G.score / CFG.PAIR_CHANCE_SCORE);
  G.nextPair = G.score >= CFG.PAIR_MIN_SCORE && Math.random() < pairChance;
  G.nextKind = G.nextPair ? lowKind() : CFG.OBST_KINDS[(Math.random() * CFG.OBST_KINDS.length) | 0];
}

/** Player hitbox bottom (screen y). Follows the Roadster; mid-flip the car is edge-on, so its
 *  real underside sits higher — credit that so visible clears are clears. */
function playerBottom() {
  const f = G.flip;
  const edgeOn = f.active ? (1 - Math.abs(Math.cos(f.theta))) * L.carH * 0.5 : 0;
  return L.groundY - f.cy - edgeOn - L.carW * CFG.PLAYER_LENIENCY;
}

function updateObstacles(dt) {
  const v = roadSpeed();
  if (G.state === 'play') {
    G.spawnDist -= v * dt;
    if (G.spawnDist <= 0) spawnNext();
  }
  const cw = L.carW, half = cw * 0.5 * (1 - CFG.PLAYER_SHRINK);
  const px1 = L.playerX - half, px2 = L.playerX + half, pBottom = playerBottom();
  for (const o of G.obstacles) {
    if (!o.alive) continue;
    o.x -= v * dt;
    if (o.x + o.w < -cw) { o.alive = false; continue; }
    o.puffT -= dt;
    if (o.puffT <= 0) { o.puffT = rand(CFG.PUFF_EVERY[0], CFG.PUFF_EVERY[1]); spawnSmoke(o.x + o.w * CFG.PUFF_AT.x, L.groundY - o.h * CFG.PUFF_AT.y); }
    if (G.state !== 'play') continue;
    if (!o.scored && o.x + o.w < L.playerX) { o.scored = true; addScore(); }
    for (const b of CFG.HITBOX[o.kind]) {
      if (o.x + o.w * b.x1 < px2 && o.x + o.w * b.x2 > px1 && pBottom > L.groundY - o.h * b.top) { startCrash(); break; }
    }
  }
}

function addScore() {
  G.score++; G.scoreStr = String(G.score);
  if (G.score > G.best) {
    G.best = G.score; G.bestStr = 'BEST ' + G.best; G.newBest = true;
    try { localStorage.setItem(CFG.KEY_BEST, String(G.best)); } catch (e) { /* ignore */ }
  }
  G.speedMul = Math.min(CFG.SPEED_CAP, 1 + CFG.SPEED_RAMP * Math.floor(G.score / CFG.SPEED_STEP));
  spawnPop('+1');
  Snd.play('score');
}

/* Crash -------------------------------------------------------------------- */
function startCrash() {
  const c = G.crash, f = G.flip, cw = L.carW;
  G.state = 'crash'; c.t = 0;
  updateCarPose(); updateRiderPose();
  c.mx = L.muskFootX; c.my = RIDER.feetY - muskH() / 2;                 // rider centre
  c.mvx = cw * 1.3; c.mvy = -cw * 1.8; c.ma = 0; c.mav = 7;
  c.cx = L.playerX; c.cy = L.groundY - L.carH / 2 - f.cy;                 // car centre
  c.cvx = -cw * 0.7; c.cvy = -cw * 1.1; c.ca = 0; c.cav = -5;
  f.active = false; f.cy = 0; G.queued = false;
  G.shakeT = CFG.SHAKE.ms * 2.5;
  spawnDust(L.playerX, L.groundY - L.carH, 16, 2);
  Snd.play('crash');
  Snd.stopLoop('roll', 0.25);
  Snd.duckMusic(true);
}

function updateCrash(dt) {
  const c = G.crash, g = L.carW * 6;
  c.t += dt;
  G.roadK = Math.max(0, G.roadK - dt * 2.5);     // the world grinds to a halt
  c.mvy += g * dt; c.mx += c.mvx * dt; c.my += c.mvy * dt; c.ma += c.mav * dt;
  const mFloor = L.groundY - muskH() * 0.3;
  if (c.my > mFloor) { c.my = mFloor; c.mvy = 0; c.mvx *= 0.6; c.mav *= 0.5; }
  c.cvy += g * dt; c.cx += c.cvx * dt; c.cy += c.cvy * dt; c.ca += c.cav * dt;
  const cFloor = L.groundY - L.carH * 0.5;
  if (c.cy > cFloor) { c.cy = cFloor; c.cvy = 0; c.cvx *= 0.5; c.cav *= 0.4; }
  if (c.t >= CFG.CRASH_S) G.state = 'over';
}

function resetRun() {
  G.state = 'play'; G.score = 0; G.scoreStr = '0'; G.newBest = false; G.speedMul = 1; G.roadK = 1;
  G.queued = false; G.squashT = 0; G.flip.active = false; G.flip.cy = 0; G.flip.theta = 0;
  for (const o of G.obstacles) o.alive = false;
  for (const p of G.particles) p.life = 0;
  G.spawnDist = CFG.SCROLL_SPEED * L.carW * CFG.FIRST_SPAWN_S;
  G.nextPair = false; G.nextKind = lowKind();
  Snd.startLoop('roll');
  Snd.duckMusic(false);
}

/* Particles ---------------------------------------------------------------- */
function spawnDust(x, y, n, power) {
  const cw = L.carW;
  for (const p of G.particles) {
    if (n <= 0) break;
    if (p.life > 0) continue;
    n--;
    p.smoke = false; p.max = p.life = rand(0.3, 0.6);
    p.x = x + rand(-0.05, 0.05) * cw; p.y = y;
    p.vx = rand(-0.3, 0.6) * cw * power; p.vy = -rand(0.3, 1.0) * cw * power;
    p.r = rand(0.012, 0.03) * cw;
  }
}
function spawnSmoke(x, y) {
  let n = 3;
  for (const p of G.particles) {
    if (n <= 0) break;
    if (p.life > 0) continue;
    n--;
    p.smoke = true; p.max = p.life = rand(0.6, 1.1);
    p.x = x; p.y = y + rand(-0.02, 0.02) * L.carW;
    p.vx = rand(0.1, 0.3) * L.carW; p.vy = -rand(0.15, 0.3) * L.carW;
    p.r = rand(0.02, 0.035) * L.carW;
  }
}
function spawnPop(text) {
  for (const p of G.pops) {
    if (p.alive) continue;
    p.alive = true; p.t = 0; p.text = text;
    updateCarPose(); updateRiderPose();
    p.x = L.playerX + L.carW * 0.1; p.y = RIDER.feetY - muskH() - L.carW * 0.1;
    return;
  }
}
/** Speed lines: a few slow ones in the sky (far plane), faster ones on the asphalt (near plane). */
function resetLine(ln, offscreen) {
  ln.x = offscreen ? L.W + rand(0, L.W) : rand(0, L.W);
  const sky = Math.random() < 0.5;
  ln.y = sky ? rand(L.H * 0.04, L.horizonY * 0.9) : rand(L.groundY + 6, L.H - 6);
  ln.spd = sky ? 0.25 : rand(1.3, 1.7);
  ln.len = rand(0.3, 0.9) * L.carW; ln.a = sky ? rand(0.06, 0.12) : rand(0.1, 0.2);
}

/* ───────────────────────────── 6. Update ───────────────────────────── */
function update(dt) {
  G.time += dt;
  const v = roadSpeed();
  G.scroll += v * dt;
  if (G.scroll > 1e7) G.scroll -= 1e7;

  const f = G.flip;
  if (f.active) {
    f.t += dt;
    if (f.t >= f.carDelay) { f.cy += f.cvy * dt; f.cvy -= f.cg * dt; }
    f.theta = Math.min(f.thetaMax, f.theta + f.omega * dt);
    if (f.t >= f.dur) land();
  }
  if (G.squashT > 0) {
    G.squashT -= dt * 1000;
    if (G.squashT <= 0 && G.queued) { G.queued = false; if (G.state === 'play') startFlip(CFG.FLIP); }
  }
  if (G.shakeT > 0) G.shakeT -= dt * 1000;
  if (G.btnT > 0) G.btnT -= dt * 1000;
  if (G.state !== 'crash' && G.state !== 'over') {                     // wheels spin with the road, a bit slower in the air
    G.wheelA += (v / Math.max(1, WHEELS[0].r)) * (f.active ? CFG.WHEEL_AIR_SPIN : 1) * dt;
    if (G.wheelA > TAU) G.wheelA -= TAU;
  }

  if (G.state === 'crash') updateCrash(dt);
  if (G.state === 'play' || G.state === 'crash' || G.state === 'over') updateObstacles(dt);

  // rolling dust behind the rear wheel
  if (!f.active && (G.state === 'title' || G.state === 'play')) {
    G.dustTimer -= dt;
    if (G.dustTimer <= 0) { G.dustTimer = 0.07; spawnDust(L.playerX - L.carW * 0.42, L.groundY, 1, 0.5); }
  }

  const grav = L.carW * 3;
  for (const p of G.particles) {
    if (p.life <= 0) continue;
    p.life -= dt;
    if (p.smoke) { p.x += (p.vx - v) * dt; p.y += p.vy * dt; p.r += dt * L.carW * 0.03; }
    else { p.x += (p.vx - v * 0.9) * dt; p.y += p.vy * dt; p.vy += grav * dt; if (p.y > L.groundY) { p.y = L.groundY; p.vy *= -0.3; } }
  }
  for (const ln of G.lines) {
    ln.x -= v * ln.spd * dt;
    if (ln.x + ln.len < 0) resetLine(ln, true);
  }
  for (const p of G.pops) if (p.alive) { p.t += dt; p.y -= dt * L.carW * 0.6; if (p.t > 0.8) p.alive = false; }
}

/* ───────────────────────────── 7. Render ───────────────────────────── */
function render() {
  const W = L.W, H = L.H;
  ctx.setTransform(L.dpr, 0, 0, L.dpr, 0, 0);
  if (G.state === 'boot') { drawBoot(); return; }

  if (G.shakeT > 0) {
    const k = CFG.SHAKE.px * Math.min(1, G.shakeT / CFG.SHAKE.ms);
    ctx.translate((Math.random() * 2 - 1) * k, (Math.random() * 2 - 1) * k);
  }
  drawSky();
  drawLayer('bg_far', L.horizonY - H * CFG.LAYOUT.farLift);   // raised so its roofline shows above bg_mid
  drawLayer('bg_mid', L.horizonY);
  ctx.fillStyle = L.band; ctx.fillRect(0, L.horizonY, W, L.roadTop - L.horizonY);
  drawLayer('bg_near', L.roadTop - 2);
  ctx.fillStyle = COLORS.road; ctx.fillRect(0, L.roadTop, W, H - L.roadTop);
  ctx.fillStyle = COLORS.curb; ctx.fillRect(0, L.roadTop, W, 3);
  drawDashes();
  drawSpeedLines();

  for (const o of G.obstacles) if (o.alive) { const sp = SPR[o.kind]; ctx.drawImage(sp.cv, o.x, L.groundY - o.h, o.w, o.h); }

  if (G.state === 'crash' || G.state === 'over') drawCrashed();
  else { updateCarPose(); updateRiderPose(); drawShadow(); drawCar(); drawMusk(); }
  drawParticles();
  drawPops();
  if (DEBUG) drawDebug();

  drawHUD();
  if (G.state === 'title') drawTitle();
  if (G.state === 'over') drawGameOver();
}

function drawBoot() {
  const W = L.W, H = L.H;
  ctx.fillStyle = COLORS.sky[0]; ctx.fillRect(0, 0, W, H);
  drawText('TESLA FLIP', W / 2, H * 0.42, 'tap', '#fff');
  const bw = Math.min(W * 0.6, 320), bh = 10, bx = (W - bw) / 2, by = H * 0.42 + L.fonts.tap.size * 1.8;
  ctx.fillStyle = 'rgba(255,255,255,0.15)'; ctx.fillRect(bx, by, bw, bh);
  ctx.fillStyle = COLORS.red; ctx.fillRect(bx, by, bw * G.progress, bh);
}

function drawSky() {
  const W = L.W;
  ctx.fillStyle = L.sky; ctx.fillRect(0, 0, W, L.horizonY + 2);
  ctx.fillStyle = '#fff';
  for (const s of L.stars) { ctx.globalAlpha = s.a; ctx.beginPath(); ctx.arc(s.x, s.y, s.r, 0, TAU); ctx.fill(); }
  ctx.globalAlpha = 0.25; ctx.fillStyle = COLORS.sunGlow;
  ctx.beginPath(); ctx.arc(L.sun.x, L.sun.y, L.sun.r * 1.7, 0, TAU); ctx.fill();
  ctx.globalAlpha = 1; ctx.fillStyle = COLORS.sun;
  ctx.beginPath(); ctx.arc(L.sun.x, L.sun.y, L.sun.r, 0, TAU); ctx.fill();
  ctx.globalAlpha = 0.14; ctx.fillStyle = '#ffd9c0';
  const drift = G.scroll * CFG.PARALLAX.clouds;
  for (const c of L.clouds) {
    const x = ((c.x - drift) % (W + c.w * 2) + W + c.w * 2) % (W + c.w * 2) - c.w;   // wraps across the width
    ctx.beginPath();
    ctx.ellipse(x, c.y, c.w * 0.5, c.h * 0.5, 0, 0, TAU);
    ctx.ellipse(x - c.w * 0.3, c.y + c.h * 0.15, c.w * 0.3, c.h * 0.4, 0, 0, TAU);
    ctx.ellipse(x + c.w * 0.3, c.y + c.h * 0.12, c.w * 0.32, c.h * 0.42, 0, 0, TAU);
    ctx.fill();
  }
  ctx.globalAlpha = 1;
}

function drawLayer(name, bottomY) {
  const sp = SPR[name], f = CFG.PARALLAX[name];
  const y = Math.round(bottomY - sp.h);
  let x = -((G.scroll * f) % sp.w);
  for (; x < L.W; x += sp.w) ctx.drawImage(sp.cv, Math.round(x), y, sp.w + 1, sp.h);  // +1 hides seams
}

function drawDashes() {
  const dash = L.carW * 0.35, gap = L.carW * 0.3, period = dash + gap, h = Math.max(2, L.H * 0.008);
  ctx.fillStyle = COLORS.dash;
  for (let x = -(G.scroll % period); x < L.W; x += period) ctx.fillRect(x, L.dashY, dash, h);
}

function drawSpeedLines() {
  ctx.strokeStyle = '#fff'; ctx.lineCap = 'round'; ctx.lineWidth = 2;
  for (const ln of G.lines) {
    ctx.globalAlpha = ln.a; ctx.beginPath(); ctx.moveTo(ln.x, ln.y); ctx.lineTo(ln.x + ln.len, ln.y); ctx.stroke();
  }
  ctx.globalAlpha = 1;
}

function drawShadow() {
  const f = G.flip, k = Math.min(1, f.cy / (L.carW * 0.5));
  ctx.globalAlpha = 0.35 * (1 - 0.55 * k); ctx.fillStyle = '#000';
  ctx.beginPath(); ctx.ellipse(L.playerX, L.groundY + 3, L.carW * 0.48 * (1 - 0.3 * k), L.carW * 0.035 * (1 - 0.3 * k), 0, 0, TAU); ctx.fill();
  ctx.globalAlpha = 1;
}

function roadBob() { return Math.sin(G.time * TAU * CFG.BOB.hz) * CFG.BOB.px * 0.4; }

/* Car pose, shared by drawCar / drawMusk / crash / pops. Filled in place (no allocations). */
const CAR = { cx: 0, cy: 0, topY: 0, tilt: 0, sy: 1, sx: 1, k: 0, kNext: 0, alphaNext: 0 };
const RIDER = { feetY: 0, lean: 0, sy: 1, air: false };

function updateCarPose() {
  const f = G.flip, C = CAR, ch = L.carH;
  C.cx = L.playerX;
  if (!f.active) {
    const k = squashK();
    C.sx = 1 + (CFG.SQUASH.x - 1) * k; C.sy = 1 - (1 - CFG.SQUASH.y) * k;
    C.cy = L.groundY + roadBob(); C.tilt = 0; C.k = 0; C.alphaNext = 0;
    C.topY = C.cy - ch * C.sy;
    return;
  }
  const u = f.t / f.dur, step = TAU / 8;
  const th = f.theta % TAU;
  let k = Math.round(th / step) % 8;
  let d = th - k * step; if (d > step / 2) d -= TAU; if (d < -step / 2) d += TAU;   // offset from the keyframe, ±22.5°
  C.k = k; C.sx = 1;
  C.sy = CFG.ROLL.squash + (1 - CFG.ROLL.squash) * Math.abs(Math.cos(2 * d));   // equal at both sides of a boundary → no pop
  const edge = (step / 2) * (1 - CFG.ROLL.blend);
  if (Math.abs(d) > edge) { C.kNext = (k + (d > 0 ? 1 : 7)) % 8; C.alphaNext = 0.5 * (Math.abs(d) - edge) / (step / 2 - edge); }
  else C.alphaNext = 0;
  C.tilt = -CFG.TILT_Z * Math.sin(TAU * u);              // nose up on takeoff, down on landing
  C.cy = L.groundY - ch / 2 - f.cy;                      // car centre line
  const fr = ROLL[k];
  C.topY = C.cy - (fr.mid - fr.top) * C.sy;              // top edge of the drawn keyframe
}

function updateRiderPose() {
  const f = G.flip, R = RIDER, sink = CFG.MUSK_SINK * L.carW;
  if (f.active) {
    const u = f.t / f.dur, arc = Math.sin(Math.PI * u);
    R.feetY = CAR.topY - CFG.RIDER_GAP * L.carH * arc + sink;   // glued to the board, lifting ≤ 0.12 carH at the apex
    R.lean = CAR.tilt + 0.5 * CFG.LEAN * arc;
    R.sy = 1; R.air = u > 0.1 && u < 0.88;
  } else {
    const knees = CFG.IDLE.knees * (0.5 + 0.5 * Math.sin(G.time * TAU * CFG.IDLE.hz));
    R.feetY = CAR.topY + sink; R.lean = 0; R.air = false;
    R.sy = 1 - knees - 0.06 * squashK();
  }
}

function drawRollFrame(k, alpha) {
  const fr = ROLL[k], sp = fr.sp;
  ctx.globalAlpha = alpha;
  ctx.drawImage(sp.cv, -L.carW / 2, -fr.mid, sp.w, sp.h);
  if (fr.side) drawWheels(-L.carW / 2, -fr.mid, fr.flipped, sp.h);
  ctx.globalAlpha = 1;
}

/** Spinning tyres on top of the baked ones; (ox, oy) = top-left of the side sprite in the current transform. */
function drawWheels(ox, oy, flipped, spriteH) {
  for (const w of WHEELS) {
    ctx.save();
    ctx.translate(ox + w.x, oy + (flipped ? spriteH - w.y : w.y));
    ctx.rotate(flipped ? -G.wheelA : G.wheelA);
    ctx.drawImage(w.cv, -w.r, -w.r, w.r * 2, w.r * 2);
    ctx.restore();
  }
}

function drawCar() {
  const C = CAR, sp = SPR.tesla_side;
  ctx.save();
  ctx.translate(C.cx, C.cy);
  if (G.flip.active) {
    ctx.rotate(C.tilt);
    ctx.scale(1, C.sy);
    drawRollFrame(C.k, 1);
    if (C.alphaNext > 0) drawRollFrame(C.kNext, C.alphaNext);   // cross-fade near a keyframe boundary
  } else {
    ctx.scale(C.sx, C.sy);
    ctx.drawImage(sp.cv, -L.carW / 2, -L.carH, sp.w, sp.h);
    drawWheels(-L.carW / 2, -L.carH, false, sp.h);
  }
  ctx.restore();
}

function drawMusk() {
  const R = RIDER, frame = R.air ? SPR.musk_air : SPR.musk_ride;
  ctx.save();
  ctx.translate(L.muskFootX, R.feetY);
  ctx.rotate(R.lean); ctx.scale(1, R.sy);
  ctx.drawImage(frame.cv, -frame.w / 2, -frame.h, frame.w, frame.h);
  ctx.restore();
}

function drawCrashed() {
  const c = G.crash, m = SPR.musk_air, car = SPR.tesla_side;
  ctx.save(); ctx.translate(c.cx, c.cy); ctx.rotate(c.ca); ctx.drawImage(car.cv, -car.w / 2, -car.h / 2, car.w, car.h); ctx.restore();
  ctx.save(); ctx.translate(c.mx, c.my); ctx.rotate(c.ma); ctx.drawImage(m.cv, -m.w / 2, -m.h / 2, m.w, m.h); ctx.restore();
}

function drawParticles() {
  for (const p of G.particles) {
    if (p.life <= 0) continue;
    const k = p.life / p.max;
    ctx.globalAlpha = (p.smoke ? 0.45 : 0.7) * k;
    ctx.fillStyle = p.smoke ? COLORS.smoke : COLORS.dust;
    ctx.beginPath(); ctx.arc(p.x, p.y, p.r * (p.smoke ? 1 : 1.6 - 0.6 * k), 0, TAU); ctx.fill();
  }
  ctx.globalAlpha = 1;
}

function drawPops() {
  for (const p of G.pops) {
    if (!p.alive) continue;
    ctx.globalAlpha = p.t < 0.5 ? 1 : 1 - (p.t - 0.5) / 0.3;
    drawText(p.text, p.x, p.y, 'pop', COLORS.gold);
  }
  ctx.globalAlpha = 1;
}

/** Outlined cartoon text. `fontKey` names a size pre-built in layout() (no per-frame font strings). */
function drawText(str, x, y, fontKey, fill, align = 'center') {
  const f = L.fonts[fontKey];
  ctx.font = f.str;
  ctx.textAlign = align; ctx.textBaseline = 'top'; ctx.lineJoin = 'round';
  ctx.lineWidth = Math.max(2, f.size * 0.14); ctx.strokeStyle = COLORS.ink;
  ctx.strokeText(str, x, y); ctx.fillStyle = fill; ctx.fillText(str, x, y);
}

function drawHUD() {
  const s = L.safe, hud = L.fonts.hud.size;
  if (G.state !== 'title') {
    drawText(G.scoreStr, L.W / 2, s.t + 10, 'hud', '#fff');
    drawText(G.bestStr, L.W / 2, s.t + 10 + hud * 1.1, 'best', COLORS.gold);
  }
  // mute toggle
  const m = L.mute, cx = m.x + m.s / 2, cy = m.y + m.s / 2;
  ctx.fillStyle = 'rgba(27,20,48,0.55)'; roundRect(m.x, m.y, m.s, m.s, 10); ctx.fill();
  ctx.fillStyle = '#fff'; ctx.beginPath();
  ctx.moveTo(cx - 10, cy - 5); ctx.lineTo(cx - 4, cy - 5); ctx.lineTo(cx + 3, cy - 11); ctx.lineTo(cx + 3, cy + 11); ctx.lineTo(cx - 4, cy + 5); ctx.lineTo(cx - 10, cy + 5); ctx.closePath(); ctx.fill();
  ctx.lineWidth = 2.5; ctx.lineCap = 'round';
  if (Snd.muted) {
    ctx.strokeStyle = '#ff5a5a'; ctx.beginPath(); ctx.moveTo(cx + 7, cy - 6); ctx.lineTo(cx + 15, cy + 6); ctx.moveTo(cx + 15, cy - 6); ctx.lineTo(cx + 7, cy + 6); ctx.stroke();
  } else {
    ctx.strokeStyle = '#fff'; ctx.beginPath(); ctx.arc(cx + 4, cy, 8, -0.9, 0.9); ctx.stroke();
    ctx.beginPath(); ctx.arc(cx + 4, cy, 13, -0.9, 0.9); ctx.stroke();
  }
  // big FLIP button (the whole screen is the real tap target; this is affordance)
  if (L.showBtn && (G.state === 'play' || G.state === 'title')) {
    const b = L.btn, k = G.btnT > 0 ? G.btnT / 120 : 0, sc = 1 - 0.1 * k;
    const canFlip = !G.flip.active || (G.flip.turns === 1 && G.flip.t * 1000 <= CFG.DOUBLE_TAP_MS);
    ctx.save(); ctx.translate(b.x, b.y); ctx.scale(sc, sc); ctx.globalAlpha = canFlip ? 1 : 0.5;
    ctx.fillStyle = 'rgba(0,0,0,0.3)'; ctx.beginPath(); ctx.arc(0, 5, b.r, 0, TAU); ctx.fill();
    ctx.fillStyle = COLORS.red; ctx.beginPath(); ctx.arc(0, 0, b.r, 0, TAU); ctx.fill();
    ctx.lineWidth = 4; ctx.strokeStyle = COLORS.ink; ctx.stroke();
    ctx.strokeStyle = 'rgba(255,255,255,0.35)'; ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(0, 0, b.r * 0.78, -2.6, -0.6); ctx.stroke();
    drawText('FLIP', 0, -L.fonts.btn.size * 0.58, 'btn', '#fff');
    ctx.restore();
  }
}

function drawTitle() {
  const W = L.W, H = L.H, title = L.titleSize, tap = L.fonts.tap.size, hint = L.fonts.hint.size;
  const tx = L.portrait ? W / 2 : W * 0.66, ty = L.portrait ? H * 0.12 : L.safe.t + H * 0.08;
  drawText('TESLA', tx, ty, 'title', '#fff');
  drawText('FLIP', tx, ty + title * 0.95, 'title', COLORS.red);
  ctx.globalAlpha = 0.65 + 0.35 * Math.sin(G.time * 5);
  drawText('TAP TO FLIP', tx, ty + title * 2.15, 'tap', COLORS.gold);
  ctx.globalAlpha = 1;
  const hy = ty + title * 2.15 + tap * 1.6;
  if (!L.portrait) {   // hints sit over the buildings in landscape → translucent panel for legibility
    const pw = hint * 24, ph = hint * 3.6;
    ctx.fillStyle = 'rgba(27,20,48,0.6)'; roundRect(tx - pw / 2, hy - hint * 0.6, pw, ph, 12); ctx.fill();
  }
  drawText('TAP = KICKFLIP · DOUBLE TAP = DOUBLE FLIP', tx, hy, 'hint', COLORS.lilac);
  drawText("DON'T HIT THE V8s", tx, hy + hint * 1.5, 'hint', COLORS.lilac);
  if (G.best > 0) drawText(G.bestStr, W / 2, L.safe.t + 12, 'best', COLORS.gold);
}

function drawGameOver() {
  const W = L.W, H = L.H, u = L.panelUnit;
  const pw = Math.min(W * 0.84, 420), ph = u * 4.6, px = (W - pw) / 2, py = Math.max(L.safe.t + L.fonts.hud.size * 1.7, H * 0.5 - ph / 2 - H * 0.05);
  ctx.fillStyle = 'rgba(27,20,48,0.86)'; roundRect(px, py, pw, ph, 22); ctx.fill();
  ctx.lineWidth = 3; ctx.strokeStyle = COLORS.red; ctx.stroke();
  const cx = W / 2;
  drawText('GAME OVER', cx, py + u * 0.35, 'panel', '#fff');
  drawText('SCORE ' + G.scoreStr, cx, py + u * 1.45, 'panelS', COLORS.gold);
  drawText(G.newBest ? 'NEW BEST!' : G.bestStr, cx, py + u * 2.15, 'panelS', G.newBest ? '#7cff9a' : COLORS.lilac);
  ctx.globalAlpha = 0.65 + 0.35 * Math.sin(G.time * 5);
  drawText('TAP TO RETRY', cx, py + u * 3.2, 'panelTap', '#fff');
  ctx.globalAlpha = 1;
}

function drawDebug() {
  const half = L.carW * 0.5 * (1 - CFG.PLAYER_SHRINK), pb = playerBottom();
  ctx.lineWidth = 2; ctx.strokeStyle = '#00ff88';
  ctx.strokeRect(L.playerX - half, pb - muskH() - L.carH, half * 2, muskH() + L.carH);
  ctx.strokeStyle = '#ff3366';
  for (const o of G.obstacles) {
    if (!o.alive) continue;
    for (const b of CFG.HITBOX[o.kind]) ctx.strokeRect(o.x + o.w * b.x1, L.groundY - o.h * b.top, o.w * (b.x2 - b.x1), o.h * b.top);
  }
}

function roundRect(x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
}

/* ───────────────────────────── 8. Input & boot ───────────────────────────── */
function onTap(x, y) {
  Snd.unlock();
  if (G.state === 'boot') return;
  if (x >= 0 && x >= L.mute.x && x <= L.mute.x + L.mute.s && y >= L.mute.y && y <= L.mute.y + L.mute.s) { Snd.toggleMute(); return; }
  G.btnT = 120;
  if (G.state === 'title') { resetRun(); tryFlip(); return; }
  if (G.state === 'play') { tryFlip(); return; }
  if (G.state === 'over') resetRun();           // 'crash' ignores taps so the panel can't be skipped by accident
}

window.addEventListener('pointerdown', (e) => {
  if (e.pointerType === 'mouse' && e.button !== 0) return;
  if (e.cancelable) e.preventDefault();
  onTap(e.clientX, e.clientY);
}, { passive: false });
window.addEventListener('keydown', (e) => {
  if (e.repeat) return;
  if (e.code === 'Space' || e.code === 'ArrowUp' || e.code === 'Enter') { e.preventDefault(); onTap(-1, -1); }
  else if (e.code === 'KeyM') { Snd.unlock(); Snd.toggleMute(); }
});
// Kill every leftover browser gesture (double-tap zoom, pinch, long-press menu, scroll bounce).
for (const ev of ['touchstart', 'touchmove', 'touchend', 'gesturestart', 'contextmenu'])
  window.addEventListener(ev, (e) => { if (e.cancelable) e.preventDefault(); }, { passive: false });

let resizeTimer = 0;   // debounced: layout() re-rasterises every sprite, so don't run it per drag event
function onResize() { clearTimeout(resizeTimer); resizeTimer = setTimeout(layout, 80); }
window.addEventListener('resize', onResize);
window.addEventListener('orientationchange', onResize);
if (window.visualViewport) window.visualViewport.addEventListener('resize', onResize);

let lastTs = 0, acc = 0;
function frame(ts) {
  requestAnimationFrame(frame);
  if (!lastTs) lastTs = ts;
  let dt = (ts - lastTs) / 1000; lastTs = ts;
  if (dt > CFG.MAX_FRAME_DT) dt = CFG.MAX_FRAME_DT;
  if (!G.paused) {
    acc += dt;
    while (acc >= CFG.FIXED_DT) { update(CFG.FIXED_DT); acc -= CFG.FIXED_DT; }
  }
  render();
}
document.addEventListener('visibilitychange', () => {
  Snd.setSuspended(document.hidden);
  if (!document.hidden) lastTs = 0;
});

(function boot() {
  Snd.init();
  layout();
  requestAnimationFrame(frame);
  loadImages((p) => { G.progress = p; }).then(() => {
    layout();                                   // sprites now use real natural sizes
    for (const ln of G.lines) resetLine(ln, false);
    G.spawnDist = Infinity;                     // no obstacles on the title screen
    G.state = 'title';
  });
})();

// QA hook: state inspection, deterministic spawns and stepping (set TF.G.paused = true, then TF.step(n)).
window.TF = {
  G, L, CFG, SPR,
  tap: () => onTap(-1, -1), spawnObstacle, resetRun,
  step: (n = 1) => { for (let i = 0; i < n; i++) update(CFG.FIXED_DT); },
  pose: () => { updateCarPose(); updateRiderPose(); return { carTop: CAR.topY, feetY: RIDER.feetY, k: CAR.k, sy: CAR.sy }; },
};
