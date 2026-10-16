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
  SPEED_RAMP: 0.03,             // +3 % per 10 points …
  SPEED_CAP: 1.8,               // … capped at 1.8×
  PARALLAX: { bg_far: 0.15, bg_mid: 0.4, bg_near: 0.8 },
  LAYER_REF_H: 1920,            // bg layers are authored for a 1920 px-tall portrait frame
  NEAR_LAYER_SCALE: 0.6,        // bg_near is busy; artist suggests ≤ 60 %
  CAR_W_FRAC: { portrait: 0.27, landscape: 0.2 },  // carW vs screen width
  STACK_FIT: 2.8,               // car + rider + double-flip apex, in carW (keeps it on screen)
  MUSK_H: 0.95,                 // rider height in carW
  MUSK_FOOT_X: 430 / 900,       // feet centre along the car (artist pivot)
  MUSK_SINK: 6 / 900,           // soles sink into the roof, in carW
  PLAYER_X: { portrait: 0.24, landscape: 0.28 },
  // Flips. peak = rider apex, carPeak = Roadster apex (both in carW). The car lags takeoff by carDelay.
  FLIP:   { dur: 1.0,  turns: 1, peak: 0.95, carPeak: 0.85, carDelay: 0.04 },
  DOUBLE: { dur: 1.45, turns: 2, peak: 1.15, carPeak: 1.05 },
  DOUBLE_TAP_MS: 200,
  SPIN_FRAC: 0.94,              // rotation completes at this fraction of the flight
  TILT_Z: 12 * Math.PI / 180,
  LEAN: 9 * Math.PI / 180,
  SQUASH: { ms: 80, x: 1.12, y: 0.9 },
  SHAKE: { px: 2, ms: 130 },
  BOB: { hz: 2.1, px: 2.5 },
  // Obstacles
  OBST_KINDS: ['obst_muscle', 'obst_pickup', 'obst_sedan'],
  OBST_SHRINK: { side: 0.06, right: 0.10, top: 0.06 },  // hitbox inset, fraction of sprite
  PLAYER_SHRINK: 0.15,
  GAP_SLACK: 0.35,              // s added to the flip duration for the minimum gap
  GAP_RAND: 1.3,                // max extra gap, as a multiple of the minimum
  PAIR_CHANCE: 0.22, PAIR_MIN_SCORE: 4, PAIR_GAP: [0.3, 0.55],  // pairs (in carW) need the double flip
  FIRST_SPAWN_S: 1.6,
  PUFF_EVERY: [0.7, 1.8],
  CRASH_S: 0.8,
  POOL: { particles: 96, lines: 12, pops: 4, obstacles: 6 },
  KEY_BEST: 'teslaflip.best',
};

const IMG_FILES = {
  musk_ride: 'assets/img/musk_ride.png', musk_air: 'assets/img/musk_air.png',
  tesla_side: 'assets/img/tesla_side.png', tesla_bottom: 'assets/img/tesla_bottom.png',
  bg_far: 'assets/img/bg_far.png', bg_mid: 'assets/img/bg_mid.png', bg_near: 'assets/img/bg_near.png',
  obst_muscle: 'assets/img/obst_muscle.png', obst_pickup: 'assets/img/obst_pickup.png', obst_sedan: 'assets/img/obst_sedan.png',
};
// Natural sizes used for placeholders when a file is missing (from the art contract).
const IMG_FALLBACK = {
  musk_ride: [426, 900], musk_air: [708, 787], tesla_side: [900, 287], tesla_bottom: [900, 434],
  bg_far: [2048, 379], bg_mid: [2048, 417], bg_near: [2048, 211],
  obst_muscle: [940, 316], obst_pickup: [1000, 470], obst_sedan: [900, 327],
};
const PLACEHOLDER_COLOR = {
  musk_ride: '#5aa0e6', musk_air: '#7cc1ff', tesla_side: '#e9e9e4', tesla_bottom: '#3a3a48',
  bg_far: '#6b5fa8', bg_mid: '#4e4178', bg_near: '#7a7490',
  obst_muscle: '#f08a2a', obst_pickup: '#6e7d55', obst_sedan: '#b0966e',
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
    img.onerror = () => { console.warn('[TeslaFlip] image missing, using placeholder: ' + IMG_FILES[n]); finish(false); };
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
  layerS: 1, btn: { x: 0, y: 0, r: 40 }, mute: { x: 0, y: 0, s: 44 },
  font: {}, sky: null, band: null, sun: { x: 0, y: 0, r: 0 },
};
const SPR = {};   // name → { cv, w, h } pre-scaled to device pixels; w/h in CSS px

function readSafeInset(cs, v) { return parseFloat(cs.getPropertyValue(v)) || 0; }

function layout() {
  const W = Math.max(1, window.innerWidth), H = Math.max(1, window.innerHeight);
  const dpr = Math.min(CFG.DPR_MAX, window.devicePixelRatio || 1);
  canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
  canvas.style.width = W + 'px'; canvas.style.height = H + 'px';
  L.W = W; L.H = H; L.dpr = dpr; L.portrait = H >= W;
  const mode = L.portrait ? 'portrait' : 'landscape';
  const cs = getComputedStyle(document.documentElement);
  L.safe = { t: readSafeInset(cs, '--sat'), r: readSafeInset(cs, '--sar'), b: readSafeInset(cs, '--sab'), l: readSafeInset(cs, '--sal') };

  L.horizonY = Math.round(H * (L.portrait ? 0.62 : 0.60));
  L.groundY = Math.round(H * (L.portrait ? 0.78 : 0.82));
  L.roadTop = L.groundY - Math.round(H * 0.025);
  L.dashY = L.groundY + (H - L.groundY) * 0.38;
  L.playerX = Math.round(W * CFG.PLAYER_X[mode]);

  const topSafe = L.safe.t + H * 0.1;
  L.carW = Math.min(W * CFG.CAR_W_FRAC[mode], (L.groundY - topSafe) / CFG.STACK_FIT);
  const [cw0, ch0] = natSize('tesla_side');
  L.px = L.carW / cw0;                       // world pixel scale: 900 sprite px ≈ one car length
  L.carH = ch0 * L.px;
  const [, mh0] = natSize('musk_ride');
  L.muskS = CFG.MUSK_H * L.carW / mh0;       // same scale for both rider frames
  L.muskFootX = L.playerX + (CFG.MUSK_FOOT_X - 0.5) * L.carW;
  L.layerS = H / CFG.LAYER_REF_H;

  const m = Math.min(W, H);
  L.btn.r = clamp(m * 0.11, 34, 60);
  L.btn.x = W / 2; L.btn.y = H - L.safe.b - L.btn.r - m * 0.04;
  L.mute.s = 44; L.mute.x = W - L.safe.r - 12 - 44; L.mute.y = L.safe.t + 12;
  L.sun.x = W * 0.72; L.sun.y = L.horizonY - H * 0.05; L.sun.r = m * 0.07;

  const f = L.font;
  f.hud = clamp(m * 0.13, 28, 72); f.best = f.hud * 0.38;
  f.title = clamp(m * 0.17, 36, 110); f.tap = clamp(m * 0.07, 18, 44); f.hint = clamp(m * 0.032, 11, 20);
  f.btn = L.btn.r * 0.5; f.pop = clamp(m * 0.08, 20, 44); f.panel = clamp(m * 0.11, 26, 64); f.panelS = f.panel * 0.45;

  L.sky = ctx.createLinearGradient(0, 0, 0, L.horizonY);
  L.sky.addColorStop(0, '#241a4d'); L.sky.addColorStop(0.45, '#6a3a8c');
  L.sky.addColorStop(0.8, '#d9603f'); L.sky.addColorStop(1, '#ffb46a');

  L.band = ctx.createLinearGradient(0, L.horizonY, 0, L.roadTop);   // far plaza: dark at the buildings, lighter near the curb
  L.band.addColorStop(0, '#45405e'); L.band.addColorStop(1, '#6e6886');

  buildSprites();
  for (const o of G.obstacles) if (o.alive) sizeObstacle(o);
}

function buildSprites() {
  const s = L.px;
  for (const n of ['musk_ride', 'musk_air']) { const [w, h] = natSize(n); sprite(n, w * L.muskS, h * L.muskS); }
  for (const n of ['tesla_side', 'tesla_bottom', ...CFG.OBST_KINDS]) { const [w, h] = natSize(n); sprite(n, w * s, h * s); }
  for (const n of ['bg_far', 'bg_mid', 'bg_near']) {
    const [w, h] = natSize(n);
    const k = L.layerS * (n === 'bg_near' ? CFG.NEAR_LAYER_SCALE : 1);
    sprite(n, w * k, h * k);
  }
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
    c.lineWidth = Math.max(2, 4 * L.dpr); c.strokeStyle = '#1b1430'; c.strokeRect(0, 0, pw, ph);
    c.fillStyle = '#1b1430'; c.textAlign = 'center'; c.textBaseline = 'middle';
    c.font = 'bold ' + Math.max(10, Math.min(ph * 0.3, pw * 0.09)) + 'px ' + FONT_FAMILY;
    c.fillText(name, pw / 2, ph / 2);
  }
  return sp;
}

/* ───────────────────────────── 4. State ───────────────────────────── */
const G = {
  state: 'boot',                 // boot → title → play → crash → over → play …
  progress: 0, time: 0, scroll: 0,
  speedMul: 1,                   // ramps with score
  roadK: 1,                      // 0..1, road motion factor (eases to 0 during a crash)
  score: 0, best: 0, scoreStr: '0', bestStr: 'BEST 0', newBest: false,
  flip: { active: false, t: 0, dur: 1, turns: 1, y: 0, vy: 0, g: 0, cy: 0, cvy: 0, cg: 0, carDelay: 0, theta: 0, omega: 0, thetaMax: 0 },
  queued: false,
  squashT: 0, shakeT: 0, btnT: 0,  // ms timers
  dustTimer: 0,
  spawnDist: 0, nextKind: 'obst_sedan', pairPending: false, afterPair: false,
  crash: { t: 0, mx: 0, my: 0, mvx: 0, mvy: 0, ma: 0, mav: 0, cx: 0, cy: 0, cvx: 0, cvy: 0, ca: 0, cav: 0 },
  particles: [], lines: [], pops: [], obstacles: [],
};
for (let i = 0; i < CFG.POOL.particles; i++) G.particles.push({ life: 0, max: 1, x: 0, y: 0, vx: 0, vy: 0, r: 1, smoke: false });
for (let i = 0; i < CFG.POOL.lines; i++) G.lines.push({ x: 0, y: 0, len: 0, spd: 1, a: 0.2 });
for (let i = 0; i < CFG.POOL.pops; i++) G.pops.push({ alive: false, x: 0, y: 0, t: 0, text: '' });
for (let i = 0; i < CFG.POOL.obstacles; i++) G.obstacles.push({ alive: false, kind: 'obst_sedan', x: 0, w: 0, h: 0, hx1: 0, hx2: 0, htop: 0, scored: false, puffT: 0 });

try { G.best = parseInt(localStorage.getItem(CFG.KEY_BEST), 10) || 0; } catch (e) { /* storage blocked */ }
G.bestStr = 'BEST ' + G.best;

function clamp(v, a, b) { return v < a ? a : v > b ? b : v; }
function rand(a, b) { return a + Math.random() * (b - a); }
function roadSpeed() { return CFG.SCROLL_SPEED * L.carW * G.speedMul * G.roadK; }  // px/s
function squashK() { return G.squashT > 0 ? G.squashT / CFG.SQUASH.ms : 0; }
function muskH() { return SPR.musk_ride.h; }

/* ───────────────────────────── 5. Gameplay ───────────────────────────── */
function startFlip(kind) {
  const f = G.flip, cw = L.carW;
  const h = kind.peak * cw, hc = kind.carPeak * cw, cd = CFG.FLIP.carDelay, cdur = kind.dur - cd;
  f.active = true; f.t = 0; f.dur = kind.dur; f.turns = kind.turns;
  // Parabola with explicit velocity/gravity so a mid-air upgrade to a double stays continuous.
  f.y = 0; f.vy = 4 * h / kind.dur; f.g = 8 * h / (kind.dur * kind.dur);
  f.cy = 0; f.cvy = 4 * hc / cdur; f.cg = 8 * hc / (cdur * cdur); f.carDelay = cd;
  f.theta = 0; f.thetaMax = TAU * kind.turns; f.omega = f.thetaMax / (kind.dur * CFG.SPIN_FRAC);
  G.squashT = 0;
  spawnDust(L.playerX - cw * 0.3, L.groundY, 6, 1);
  Snd.play('pop'); Snd.play('flip', 1, 0.05);
}

/** Second tap within DOUBLE_TAP_MS of takeoff: re-solve gravity so the current height/velocity
 *  flow into a longer, higher flight that touches down exactly at DOUBLE.dur. */
function upgradeToDouble() {
  const f = G.flip, K = CFG.DOUBLE, tau = K.dur - f.t;
  f.turns = 2; f.dur = K.dur;
  f.g = 2 * (f.y + f.vy * tau) / (tau * tau);
  if (f.t >= f.carDelay) f.cg = 2 * (f.cy + f.cvy * tau) / (tau * tau);
  else { const hc = K.carPeak * L.carW, cdur = K.dur - f.carDelay; f.cvy = 4 * hc / cdur; f.cg = 8 * hc / (cdur * cdur); }
  f.thetaMax = TAU * 2; f.omega = (f.thetaMax - f.theta) / (tau * CFG.SPIN_FRAC);
  Snd.play('flip', 1.2);
}

function land() {
  const f = G.flip;
  f.active = false; f.y = f.cy = 0; f.theta = 0;
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
  else G.queued = true;   // at most one queued flip, fired after the landing squash
}

/* Obstacles --------------------------------------------------------------- */
function sizeObstacle(o) {
  const sp = SPR[o.kind];
  o.w = sp.w; o.h = sp.h;
}
function obstacleHitbox(o) {
  const S = CFG.OBST_SHRINK;
  o.hx1 = o.x + o.w * S.side; o.hx2 = o.x + o.w * (1 - S.right);
  o.htop = L.groundY - o.h * (1 - S.top);
}
function spawnObstacle(kind, x) {
  for (const o of G.obstacles) {
    if (o.alive) continue;
    o.alive = true; o.kind = kind; sizeObstacle(o);
    o.x = x === undefined ? L.W + L.carW * 0.15 : x;
    o.scored = false; o.puffT = rand(CFG.PUFF_EVERY[0], CFG.PUFF_EVERY[1]);
    obstacleHitbox(o);
    return o;
  }
  return null;
}
function lowKind() { return Math.random() < 0.5 ? 'obst_muscle' : 'obst_sedan'; }

/** Picks the next spawn: pairs (two low cars, gap < 0.6 car) force the double flip. */
function scheduleNextSpawn(lastWidth) {
  const v = CFG.SCROLL_SPEED * L.carW * G.speedMul;
  if (G.pairPending) {           // partner of a pair: tiny gap, low car only
    G.pairPending = false; G.afterPair = true;
    G.nextKind = lowKind();
    G.spawnDist = lastWidth + rand(CFG.PAIR_GAP[0], CFG.PAIR_GAP[1]) * L.carW;
    return;
  }
  const flipDur = G.afterPair ? CFG.DOUBLE.dur : CFG.FLIP.dur;   // recovering from a double takes longer
  G.afterPair = false;
  const minGap = v * (flipDur + CFG.GAP_SLACK);
  G.spawnDist = lastWidth + minGap * (1 + Math.random() * CFG.GAP_RAND);
  const pair = G.score >= CFG.PAIR_MIN_SCORE && Math.random() < CFG.PAIR_CHANCE;
  G.pairPending = pair;
  G.nextKind = pair ? lowKind() : CFG.OBST_KINDS[(Math.random() * CFG.OBST_KINDS.length) | 0];
}

function updateObstacles(dt) {
  const v = roadSpeed();
  if (G.state === 'play') {
    G.spawnDist -= v * dt;
    if (G.spawnDist <= 0) { const o = spawnObstacle(G.nextKind); scheduleNextSpawn(o ? o.w : L.carW); }
  }
  // Player hitbox (Musk + car, shrunk 15 %). Bottom follows the Roadster; mid-flip the car is
  // edge-on, so its real underside sits higher — credit that so visible clears are clears.
  const f = G.flip, cw = L.carW;
  const px1 = L.playerX - cw * 0.5 * (1 - CFG.PLAYER_SHRINK), px2 = L.playerX + cw * 0.5 * (1 - CFG.PLAYER_SHRINK);
  const edgeOn = f.active ? (1 - Math.abs(Math.cos(f.theta))) * L.carH * 0.5 : 0;
  const pBottom = L.groundY - f.cy - edgeOn - cw * 0.08;
  for (const o of G.obstacles) {
    if (!o.alive) continue;
    o.x -= v * dt;
    obstacleHitbox(o);
    if (o.x + o.w < -cw) { o.alive = false; continue; }
    o.puffT -= dt;
    if (o.puffT <= 0) { o.puffT = rand(CFG.PUFF_EVERY[0], CFG.PUFF_EVERY[1]); spawnSmoke(o.x + o.w * 0.93, L.groundY - o.h * 0.12); }
    if (G.state !== 'play') continue;
    if (!o.scored && o.x + o.w < L.playerX) { o.scored = true; addScore(); }
    if (o.hx1 < px2 && o.hx2 > px1 && pBottom > o.htop) startCrash();
  }
}

function addScore() {
  G.score++; G.scoreStr = String(G.score);
  if (G.score > G.best) {
    G.best = G.score; G.bestStr = 'BEST ' + G.best; G.newBest = true;
    try { localStorage.setItem(CFG.KEY_BEST, String(G.best)); } catch (e) { /* ignore */ }
  }
  G.speedMul = Math.min(CFG.SPEED_CAP, 1 + CFG.SPEED_RAMP * Math.floor(G.score / 10));
  spawnPop('+1');
  Snd.play('score');
}

/* Crash -------------------------------------------------------------------- */
function startCrash() {
  const c = G.crash, f = G.flip, cw = L.carW;
  G.state = 'crash'; c.t = 0;
  c.mx = L.muskFootX; c.my = L.groundY - L.carH - f.y - muskH() / 2;   // rider centre
  c.mvx = cw * 1.3; c.mvy = -cw * 1.8; c.ma = 0; c.mav = 7;
  c.cx = L.playerX; c.cy = L.groundY - L.carH / 2 - f.cy;                 // car centre
  c.cvx = -cw * 0.7; c.cvy = -cw * 1.1; c.ca = 0; c.cav = -5;
  f.active = false; f.y = f.cy = 0; G.queued = false;
  G.shakeT = CFG.SHAKE.ms * 2.5;
  spawnDust(L.playerX, L.groundY - L.carH, 16, 2);
  Snd.play('crash');
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
  G.queued = false; G.squashT = 0; G.flip.active = false; G.flip.y = G.flip.cy = 0; G.flip.theta = 0;
  for (const o of G.obstacles) o.alive = false;
  for (const p of G.particles) p.life = 0;
  G.spawnDist = CFG.SCROLL_SPEED * L.carW * CFG.FIRST_SPAWN_S;
  G.pairPending = false; G.afterPair = false; G.nextKind = lowKind();
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
    p.x = L.playerX + L.carW * 0.1; p.y = L.groundY - L.carH - muskH() - G.flip.y - L.carW * 0.1;
    return;
  }
}
function resetLine(ln, offscreen) {
  ln.x = offscreen ? L.W + rand(0, L.W) : rand(0, L.W);
  ln.y = Math.random() < 0.6 ? rand(L.H * 0.04, L.horizonY * 0.9) : rand(L.groundY + 6, L.H - 6);
  ln.len = rand(0.3, 0.9) * L.carW; ln.spd = rand(1.3, 2.0); ln.a = rand(0.08, 0.2);
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
    f.y += f.vy * dt; f.vy -= f.g * dt;
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
  // sky + sun
  ctx.fillStyle = L.sky; ctx.fillRect(0, 0, W, L.horizonY + 2);
  ctx.globalAlpha = 0.25; ctx.fillStyle = '#ffe0a0';
  ctx.beginPath(); ctx.arc(L.sun.x, L.sun.y, L.sun.r * 1.7, 0, TAU); ctx.fill();
  ctx.globalAlpha = 1; ctx.fillStyle = '#ffd27a';
  ctx.beginPath(); ctx.arc(L.sun.x, L.sun.y, L.sun.r, 0, TAU); ctx.fill();

  drawLayer('bg_far', L.horizonY);
  drawLayer('bg_mid', L.horizonY + H * 0.012);
  // sidewalk band + road
  ctx.fillStyle = L.band; ctx.fillRect(0, L.horizonY, W, L.roadTop - L.horizonY);
  drawLayer('bg_near', L.roadTop);
  ctx.fillStyle = '#2f2d3a'; ctx.fillRect(0, L.roadTop, W, H - L.roadTop);
  ctx.fillStyle = '#8f889f'; ctx.fillRect(0, L.roadTop, W, 3);
  drawDashes();
  drawSpeedLines();

  for (const o of G.obstacles) if (o.alive) { const sp = SPR[o.kind]; ctx.drawImage(sp.cv, o.x, L.groundY - o.h, o.w, o.h); }

  if (G.state === 'crash' || G.state === 'over') drawCrashed();
  else { drawShadow(); drawCar(); drawMusk(); }
  drawParticles();
  drawPops();
  if (DEBUG) drawDebug();

  drawHUD();
  if (G.state === 'title') drawTitle();
  if (G.state === 'over') drawGameOver();
}

function drawBoot() {
  const W = L.W, H = L.H;
  ctx.fillStyle = '#241a4d'; ctx.fillRect(0, 0, W, H);
  drawText('TESLA FLIP', W / 2, H * 0.42, L.font.tap, '#fff');
  const bw = Math.min(W * 0.6, 320), bh = 10, bx = (W - bw) / 2, by = H * 0.42 + L.font.tap * 1.8;
  ctx.fillStyle = 'rgba(255,255,255,0.15)'; ctx.fillRect(bx, by, bw, bh);
  ctx.fillStyle = '#e82127'; ctx.fillRect(bx, by, bw * G.progress, bh);
}

function drawLayer(name, bottomY) {
  const sp = SPR[name], f = CFG.PARALLAX[name];
  const y = bottomY - sp.h;
  let x = -((G.scroll * f) % sp.w);
  for (; x < L.W; x += sp.w) ctx.drawImage(sp.cv, Math.round(x), Math.round(y), sp.w + 1, sp.h);  // +1 hides seams
}

function drawDashes() {
  const dash = L.carW * 0.35, gap = L.carW * 0.3, period = dash + gap, h = Math.max(2, L.H * 0.008);
  ctx.fillStyle = 'rgba(231,217,160,0.8)';
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

function idleBob() { return Math.sin(G.time * TAU * CFG.BOB.hz) * CFG.BOB.px; }

function drawCar() {
  const f = G.flip, cw = L.carW, ch = L.carH;
  ctx.save();
  if (f.active) {
    const u = f.t / f.dur, cosT = Math.cos(f.theta);
    ctx.translate(L.playerX, L.groundY - ch / 2 - f.cy);
    ctx.rotate(-CFG.TILT_Z * Math.sin(TAU * u));              // nose up on takeoff, down on landing
    if (Math.abs(cosT) < 0.04) {                               // edge-on: keep a sliver visible
      ctx.fillStyle = '#2a2838'; ctx.fillRect(-cw / 2, -2, cw, 4);
    } else if (cosT < 0) {                                     // belly view, mirrored by the negative scale
      const sp = SPR.tesla_bottom; ctx.scale(1, cosT); ctx.drawImage(sp.cv, -sp.w / 2, -sp.h / 2, sp.w, sp.h);
    } else {
      ctx.scale(1, cosT); ctx.drawImage(SPR.tesla_side.cv, -cw / 2, -ch / 2, cw, ch);
    }
  } else {
    const k = squashK();
    ctx.translate(L.playerX, L.groundY + idleBob() * 0.5);
    ctx.scale(1 + (CFG.SQUASH.x - 1) * k, 1 - (1 - CFG.SQUASH.y) * k);
    ctx.drawImage(SPR.tesla_side.cv, -cw / 2, -ch, cw, ch);
  }
  ctx.restore();
}

function drawMusk() {
  const f = G.flip, sink = CFG.MUSK_SINK * L.carW;
  let frame = SPR.musk_ride, feetY, lean = 0, sy = 1;
  if (f.active) {
    const u = f.t / f.dur;
    feetY = L.groundY - L.carH - f.y;
    lean = CFG.LEAN * Math.sin(Math.PI * u);
    if (u > 0.1 && u < 0.88) frame = SPR.musk_air;
  } else {
    const k = squashK();
    feetY = L.groundY - L.carH * (1 - (1 - CFG.SQUASH.y) * k) + idleBob() * 0.5;
    sy = 1 - 0.06 * k;
  }
  ctx.save();
  ctx.translate(L.muskFootX, feetY + sink);
  ctx.rotate(lean); ctx.scale(1, sy);
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
    ctx.fillStyle = p.smoke ? '#2b2733' : '#cdbfaa';
    ctx.beginPath(); ctx.arc(p.x, p.y, p.r * (p.smoke ? 1 : 1.6 - 0.6 * k), 0, TAU); ctx.fill();
  }
  ctx.globalAlpha = 1;
}

function drawPops() {
  for (const p of G.pops) {
    if (!p.alive) continue;
    ctx.globalAlpha = p.t < 0.5 ? 1 : 1 - (p.t - 0.5) / 0.3;
    drawText(p.text, p.x, p.y, L.font.pop, '#ffe27a');
  }
  ctx.globalAlpha = 1;
}

function drawText(str, x, y, size, fill, align = 'center') {
  ctx.font = '900 ' + size + 'px ' + FONT_FAMILY;
  ctx.textAlign = align; ctx.textBaseline = 'top'; ctx.lineJoin = 'round';
  ctx.lineWidth = Math.max(2, size * 0.14); ctx.strokeStyle = '#1b1430';
  ctx.strokeText(str, x, y); ctx.fillStyle = fill; ctx.fillText(str, x, y);
}

function drawHUD() {
  const s = L.safe, f = L.font;
  if (G.state !== 'title') {
    drawText(G.scoreStr, L.W / 2, s.t + 10, f.hud, '#fff');
    drawText(G.bestStr, L.W / 2, s.t + 10 + f.hud * 1.1, f.best, '#ffe27a');
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
  if (G.state === 'play' || G.state === 'title') {
    const b = L.btn, k = G.btnT > 0 ? G.btnT / 120 : 0, sc = 1 - 0.1 * k;
    const canFlip = !G.flip.active || (G.flip.turns === 1 && G.flip.t * 1000 <= CFG.DOUBLE_TAP_MS);
    ctx.save(); ctx.translate(b.x, b.y); ctx.scale(sc, sc); ctx.globalAlpha = canFlip ? 1 : 0.5;
    ctx.fillStyle = 'rgba(0,0,0,0.3)'; ctx.beginPath(); ctx.arc(0, 5, b.r, 0, TAU); ctx.fill();
    ctx.fillStyle = '#e82127'; ctx.beginPath(); ctx.arc(0, 0, b.r, 0, TAU); ctx.fill();
    ctx.lineWidth = 4; ctx.strokeStyle = '#1b1430'; ctx.stroke();
    ctx.strokeStyle = 'rgba(255,255,255,0.35)'; ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(0, 0, b.r * 0.78, -2.6, -0.6); ctx.stroke();
    drawText('FLIP', 0, -L.font.btn * 0.58, L.font.btn, '#fff');
    ctx.restore();
  }
}

function drawTitle() {
  const f = L.font, W = L.W, H = L.H;
  const tx = L.portrait ? W / 2 : W * 0.66, ty = L.portrait ? H * 0.14 : L.safe.t + H * 0.1;
  drawText('TESLA', tx, ty, f.title, '#fff');
  drawText('FLIP', tx, ty + f.title * 0.95, f.title, '#e82127');
  ctx.globalAlpha = 0.65 + 0.35 * Math.sin(G.time * 5);
  drawText('TAP TO FLIP', tx, ty + f.title * 2.15, f.tap, '#ffe27a');
  ctx.globalAlpha = 1;
  const hy = ty + f.title * 2.15 + f.tap * 1.6;
  drawText('TAP = KICKFLIP · DOUBLE TAP = DOUBLE FLIP', tx, hy, f.hint, '#e8e0ff');
  drawText("DON'T HIT THE V8s", tx, hy + f.hint * 1.5, f.hint, '#e8e0ff');
  if (G.best > 0) drawText(G.bestStr, W / 2, L.safe.t + 12, f.best, '#ffe27a');
}

function drawGameOver() {
  const f = L.font, W = L.W, H = L.H;
  const pw = Math.min(W * 0.84, 420), ph = f.panel * 4.6, px = (W - pw) / 2, py = Math.max(L.safe.t + f.hud * 1.7, H * 0.5 - ph / 2 - H * 0.05);
  ctx.fillStyle = 'rgba(27,20,48,0.86)'; roundRect(px, py, pw, ph, 22); ctx.fill();
  ctx.lineWidth = 3; ctx.strokeStyle = '#e82127'; ctx.stroke();
  const cx = W / 2;
  drawText('GAME OVER', cx, py + f.panel * 0.35, f.panel * 0.8, '#fff');
  drawText('SCORE ' + G.scoreStr, cx, py + f.panel * 1.45, f.panelS, '#ffe27a');
  drawText(G.newBest ? 'NEW BEST!' : G.bestStr, cx, py + f.panel * 2.15, f.panelS, G.newBest ? '#7cff9a' : '#e8e0ff');
  ctx.globalAlpha = 0.65 + 0.35 * Math.sin(G.time * 5);
  drawText('TAP TO RETRY', cx, py + f.panel * 3.2, f.panelS * 1.15, '#fff');
  ctx.globalAlpha = 1;
}

function drawDebug() {
  const cw = L.carW, f = G.flip;
  const px1 = L.playerX - cw * 0.5 * (1 - CFG.PLAYER_SHRINK), px2 = L.playerX + cw * 0.5 * (1 - CFG.PLAYER_SHRINK);
  const edgeOn = f.active ? (1 - Math.abs(Math.cos(f.theta))) * L.carH * 0.5 : 0;
  const pBottom = L.groundY - f.cy - edgeOn - cw * 0.08;
  ctx.lineWidth = 2; ctx.strokeStyle = '#00ff88';
  ctx.strokeRect(px1, pBottom - muskH() - L.carH, px2 - px1, muskH() + L.carH);
  ctx.strokeStyle = '#ff3366';
  for (const o of G.obstacles) if (o.alive) ctx.strokeRect(o.hx1, o.htop, o.hx2 - o.hx1, L.groundY - o.htop);
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
  acc += dt;
  while (acc >= CFG.FIXED_DT) { update(CFG.FIXED_DT); acc -= CFG.FIXED_DT; }
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

// Small hook for QA automation (state inspection / deterministic spawns). Harmless in production.
window.TF = { G, L, CFG, SPR, tap: () => onTap(-1, -1), spawnObstacle, resetRun };
