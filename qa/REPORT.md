# Tesla Flip — QA report (v0.1, commit 9f55ac3)

Date: 2026-10-16. Tester: QA lead (automated: playwright-core + Edge headless, deterministic rAF stepping via `window.TF`; no real phone / no iOS Safari available — iOS notes are code-review based).
Viewports: 390×844 @2 (primary), 360×780, 430×932, 844×390 landscape, 1280×800 desktop. Evidence: `qa/screenshots/qa_*.png` (67 files; note `qa/screenshots/*.png` is git-ignored, so the evidence lives only locally).

## Score table

| # | Area | Score | Verdict |
|---|------|-------|---------|
| 1 | Visual / art direction | **6/10** | Style is consistent and charming, HUD/title/game-over read well, no seams or halos — but two obstacle sprites carry opaque white ground patches, the far skyline and the sun are completely hidden behind `bg_mid` (parallax collapses to one layer), and the portrait composition is ~55 % empty sky. |
| 2 | Gameplay / feel | **6/10** | Spawn logic is fair and deterministic (no overlaps, no unfair pairs, 2.5 s breathing room after retry). But the single-flip window on the pickup is only 100 ms, the double flip is a strictly dominant strategy (600–700 ms window over everything), and the speed ramp is imperceptible within a 60 s session (1.03× at 36 s). Fun for ~30 s, flat after. |
| 3 | Mobile engineering | **8/10** | Zero console errors/404s, no scroll/zoom, safe-area insets honoured, orientation change mid-game OK, tap→frame 9–21 ms, heap flat over 60 s, 1.77 MB / 24 requests, title in 0.35 s local. Not measured on a real phone. |
| 4 | Audio | **7/10** | All 8 buffers decode, ogg→mp3 fallback works, gains per contract, SFX fire on the right events, loops gapless. Defect: the motor hum (`roll`) keeps running through the crash and the GAME OVER panel. Music quality not auditable here. |
| 5 | Code quality | **8/10** | Clean sections, pooled objects, fixed-dt loop, graceful fallbacks, good iOS hygiene. Minor: magic numbers in layout/render, per-frame font-string allocation, duplicated hitbox math, no way to stop a loop. |
| 6 | Repo / deploy | **8/10** | `.env` untracked, Pages live and byte-identical to local, asset weight within budget. README is thin (no controls / local run / likeness note). |

**Ship / don't ship: DON'T SHIP YET.** Two areas are below 7. All blocking items are small (est. half a day for dev + art); see "Top 5 fixes" at the end.

---

## Measurements (evidence for the scores)

### Layout at 390×844 @2 (`TF.L`)
carW 105.3 px, carH 33.6, groundY 658 (78 %), horizonY 523 (62 %), roadTop 637, playerX 94. Road speed 315.9 px/s (3.0 carW/s). Sky occupies y 0–523, buildings 350–533, flat band 533–581, sidewalk strip 581–637 (56 px, lamps ~40 px tall vs Musk 100 px), asphalt 637–844 (207 px = 24.5 % of the screen; cars occupy only its top 34 px).

### Timing windows (deterministic, dt = 1/60, base speed; "lead" = seconds before the player's hitbox would touch the obstacle's hitbox; sweep step 25 ms, 44 trials per row)
| Situation | Usable tap window | Width |
|---|---|---|
| Warning time: car enters right edge → contact | — | **0.82 s** |
| Single flip over muscle car | tap 0.10–0.35 s before contact | 250 ms |
| Single flip over sedan | 0.125–0.35 s | 225 ms |
| Single flip over **pickup** | 0.175–0.275 s | **100 ms** |
| Double flip over muscle / sedan / pickup | 0.10–0.80 / 0.125–0.825 / 0.15–0.75 s | 600–700 ms |
| Pair gap 0.30 carW, single flip | never clears | 0 |
| Pair gap 0.30 / 0.42 / 0.55 carW, double (2nd tap +50…190 ms) | 0.10–0.375 / 0.10–0.325 / 0.10–0.275 s | 275 / 225 / 150–175 ms |

Second-tap timing for the double is forgiving: +50, +120 and +190 ms all give the same window. Tapping earlier than the window lands you on the car (expected for the genre), so only ~30–40 % of the 0.82 s warning time is usable with a single flip.

### Natural spawning, 150 s autopilot (using the windows above): 62 obstacles, 0 crashes, score 62
- First obstacle spawns 1.62 s after retry (+0.87 s travel = 2.5 s of calm). Good.
- Non-pair gaps 1.75–4.33 s (contract minimum 1.35 s). Pair partner spawns 0.43–0.52 s later (0.3–0.55 carW gap). First pair at score 7 (`PAIR_MIN_SCORE` 4 respected). No overlapping spawns.
- Speed multiplier: 1.03 at score 10, 1.09 at 30, 1.18 at 60. In the 36 s scroll run the player reached 14 points → 1.03×.

### Engineering
- Console: 0 errors / 0 warnings in all viewports (local and Pages). No failed requests.
- Load: 24 requests, 1.77 MB transferred (music 930 KB ogg = 53 %). Title screen at 348 ms local, 843 ms on GitHub Pages, 5.5 s on a 1.6 Mbps/150 ms throttle with cache disabled (all audio decoded at 9.3 s; audio is not awaited, so play starts earlier).
- FPS (headless Edge, desktop CPU, 10 s of autopilot play): avg 100, min 96, p1 98, max frame 10.4 ms, 0 frames > 25 ms. Phone not measured.
- Heap over 60 s of play (CDP `Performance.getMetrics`): 2.0–2.8 MB, oscillating with GC, no growth; DOM nodes 62 and listeners 45 constant. Buffer-source nodes created = SFX plays (109 ≈ 107), no leak.
- Tap latency (pointerdown handler → next rendered frame, 6 real touch taps during play): 9.1 / 9.1 / 21.1 / 18.3 / 9.8 / 9.5 ms. (A 184 ms outlier on the very first tap is the audio unlock + loop start.)
- No horizontal scroll (`scrollWidth` 390 = `innerWidth`), `touch-action: none`, `body` fixed, viewport meta has `viewport-fit=cover, user-scalable=no`.
- Safe area: injected `--sat: 59px; --sab: 34px` → mute button moved to y 71, FLIP button raised by 34 px, HUD under the notch (`qa_eng_safearea_59_34.png`, `qa_eng_safearea_gameover.png`).
- Resize/orientation mid-game: 390×844 → 844×390 → back: layout, sprite rasters and canvas pixel size rebuilt correctly (`qa_eng_resize_landscape_midgame.png`).
- Visibility: `document.hidden` → `AudioContext` suspended; shown → running.
- Mute: tap on the icon toggles, persists (`teslaflip.muted` = 1/0), master gain ramps to 0, SFX `play()` is a no-op while muted, loops keep running in sync. The mute tap does not trigger a flip.
- Best score persisted (`teslaflip.best`), shown on title and in the panel; "NEW BEST!" path present. Taps during the 0.8 s crash are ignored (panel cannot be skipped).
- `file://` (real browser flags): images load, game is fully playable, audio silently absent — but the console shows 8 CORS errors + 8 `net::ERR_FAILED` + 8 `[TeslaFlip] audio missing` warnings (`qa_eng_file_url.png`).
- ogg blocked (routed to 404): all 8 files fall back to mp3, both loops start; 8 expected 404 console errors.

### Audio state (`Snd`) after first gesture
unlocked true, ctx running, buffers 8/8 (durations: score 0.147, pop 0.297, land 0.347, flip 0.497, combo 0.497, crash 0.8, roll 2.0, theme 61.94 s), loops `roll` + `theme` running, master 1.0, musicBus 0.6, sfxBus 0.9 (roll 0.8 × 0.9 = 0.72 effective). SFX sequence observed: `pop`+`flip` at takeoff, `flip`@1.2× on the double upgrade, `land` on landing, `score` when the car passes, `crash` on crash (`combo` on double landing verified in the code path). After crash → over: `roll` still playing, `theme` still playing.

### Assets
Images 721 KB (11 PNGs, all 8-bit palette; no visible banding), SFX 66 KB ogg / 81 KB mp3, music 930 KB ogg / 868 KB mp3. Total first-load (ogg path) 1.76 MB — within the 3 MB budget; images < 1.5 MB; audio 0.99 MB < 1.2 MB. Background tiles: left/right edge columns identical (diff 0.0) → tileable; 36 s scroll and forced tile-boundary shots show no seams (`qa_scroll_*.png`, `qa_seam_mid_0.png`, `qa_seam_near.png`). The mirror-tiling symmetry (two water towers facing each other, mirrored billboard graffiti) is visible if you look for it. No white halos around sprites on the dark road.

---

## Defects, prioritised

### D1 — White ground patches baked into two obstacle sprites · **blocker (visual)**
- Repro: start a run, wait for the pickup or the muscle car. Under the chassis, between the wheels, there is a solid white rectangle; the muscle car's rear quarter window is also solid white.
- Evidence: `qa_zoom_white_patch_and_band.png` (3× crops), `qa_debug_00_ground.png`, `qa_d1280_04_gameover.png`. Pixel count: `obst_pickup.png` has 37 182 opaque near-white pixels in its lower-middle (rows 352–464 of 470); `obst_muscle.png` 18 652 in its bottom 20 %. `obst_sedan.png` and `tesla_side.png` have 0.
- Fix (art): `tools/cutout.py` — the border flood fill cannot reach regions enclosed by the outline. Add a second pass: remove connected near-white components (tolerance ~12) that lie below the chassis line / between the wheels, or paint them transparent manually. Re-export, re-run the contact sheet, check on the dark road.

### D2 — Far skyline layer and the sun are never visible · **must-fix (visual)**
- Repro: play; there is only one building layer. `bg_far.png` (domes, TV tower) is drawn with its bottom at `horizonY` (y 356–523) and `bg_mid` is drawn at y 350–533 on top of it — the far layer is 100 % covered. The sun (`L.sun`, y = horizonY − 42) is likewise behind the mid buildings.
- Evidence: `qa_layers_far_only.png` (bg_mid cleared → the whole far skyline appears). Every normal screenshot shows no skyline and no sun.
- Fix (dev, `game.js` `render()` / `layout()`): draw `bg_far` with its bottom at `L.horizonY - H*0.07` (or scale the far layer ~1.5×) so its roofline rises above `bg_mid`; move `L.sun.y` to `L.horizonY - H*0.16` and keep it behind both layers. Consider drawing `bg_mid` with its bottom exactly at `L.horizonY` (currently +1.2 % H) so the band under it shrinks.

### D3 — Pickup single-flip window is 100 ms · **must-fix (gameplay)**
- Repro: let a pickup come; tap once. Only taps 0.175–0.275 s before contact clear it (vs 225–250 ms windows for the two low cars). With 60–100 ms of real touch latency on a phone this is near frame-perfect for a casual player and reads as "the tall one is unfair".
- Evidence: timing table above.
- Fix (dev): the pickup's hitbox top is `groundY − 0.94·h` across its full width, but only the cab (front ~40 %) is that tall. Give `OBST_SHRINK` a per-kind `top` (e.g. `obst_pickup: 0.22`) or split the hitbox into cab + bed in `obstacleHitbox()`; alternatively raise `CFG.FLIP.carPeak` 0.85 → 0.95 and `peak` 0.95 → 1.05. Target: ≥ 200 ms for every single car (re-run the sweep).

### D4 — No difficulty curve: double flip dominates and speed barely ramps · **must-fix (gameplay)**
- Repro: double-tap on every car. The double clears any single car with a 600–700 ms window and every pair; the single flip is strictly worse. Meanwhile `SPEED_RAMP` gives 1.03× at score 10 and 1.18× at 60 — after the first 30 s nothing changes.
- Evidence: timing table; `speedAt` {10: 1.03, 30: 1.09, 60: 1.18}; 150 s autopilot with 0 crashes.
- Fix (dev, `CFG`): ramp per 5 points (`SPEED_RAMP 0.04`, step 5, cap 1.6) and shrink `GAP_RAND` with score; make the double cost something — e.g. `DOUBLE.dur` 1.45 → 1.3 s with the same height, or schedule the next car relative to the player's landing when a double was used. Re-measure windows after D3 so the single stays ≥ 200 ms at the cap.

### D5 — FLIP button sits inside the obstacle lane in landscape and desktop · **must-fix (visual/UX)**
- Repro: 844×390 or 1280×800, play. The button (centre-bottom, r 43–60) is drawn over the road at the cars' height; incoming cars pass behind a semi-transparent red disc.
- Evidence: `qa_l844_03_flip_apex.png` (pickup half-covered), `qa_d1280_03_flip_apex.png`, `qa_d1280_04_gameover.png`.
- Fix (dev, `layout()`): in landscape put the button bottom-right (`x = W − safe.r − r − m·0.06`), or drop the button entirely in landscape/desktop (the whole screen is the tap target; the hint already says so). Also add a translucent panel behind the title hints in landscape (`qa_l844_01_title.png`: hints overlap windows).

### D6 — Portrait composition: dead sky, toy-scale sidewalk, flat band, deep asphalt · **should-fix (visual)**
- Repro: any portrait screenshot in play. Sky 0–62 % of height with only faint speed lines; buildings end at 63 %; a 48 px flat slate band; a 56 px sidewalk strip whose lamp posts are shorter than Musk and whose benches are the size of the Tesla's wheel, sitting directly on the cars' roofline; then 207 px of asphalt under the cars.
- Evidence: `qa_p390_02_play_obstacles.png`, `qa_p430_02_play_obstacles.png`, `qa_zoom_white_patch_and_band.png` (bottom strip).
- Fix (dev): `NEAR_LAYER_SCALE` 0.6 → 1.0 and draw `bg_near` with its base a few px above `roadTop` (it then reads as the near kerb, lamps taller than the rider); lower the horizon to ~0.66 H and the ground to ~0.80 H in portrait; close the band (see D2). The sky gets the sun back from D2; a couple of static cloud/star shapes drawn in code would finish it.

### D7 — Motor hum keeps running after the crash and on the GAME OVER panel · **should-fix (audio)**
- Repro: crash. Musk lies on the asphalt and the panel is up, but the `roll` loop continues at full level indefinitely.
- Evidence: `afterCrash.rollPlaying: true` with state `over`; `audio.js` has no stop path for loops.
- Fix (audio.js): add `Snd.stopLoop(name, fadeS)` (gain `setTargetAtTime(0, now, fade/4)` then `src.stop(now+fade)`, delete from `loops`); call `Snd.stopLoop('roll', 0.25)` in `startCrash()` and `Snd._startLoop('roll')` in `resetRun()`. Optionally duck `musicBus` to 0.35 during `over`.

### D8 — `file://` opening floods the console (24 errors/warnings) · **nice**
- Repro: double-click `index.html`. Game runs silently (good), but every audio fetch logs a CORS error, a `net::ERR_FAILED` and a warning.
- Evidence: `qa_eng_file_url.png`, s4 console capture.
- Fix (audio.js `_load`): if `location.protocol === 'file:'`, skip `fetch` and warn once ("audio needs http(s)"), or fall back to `HTMLAudioElement` for file://.

### D9 — Rider pose is a stand, not a skate stance · **nice (art)**
- `musk_ride.png` shows Musk walking-profile with feet in line and arms down, as if standing on a Segway; the contract asked for a skate stance with bent knees. Reads fine at phone size, but the kickflip would sell better with a crouched, sideways stance. Likeness itself is good (hair, face, "OCCUPY MARS" tee).
- Fix (art): regenerate `musk_ride` with knees bent, body turned 3/4 to camera, feet apart.

### D10 — Kickflip is rendered as a card flip · **nice (dev/art)**
- Sequence is side → sliver → belly (plan view, scaled by cos θ) → sliver → side. It reads as a flip (`qa_flip_single_00…10.png`, `qa_flip_double_*.png`), the belly frame at mid-rotation is fine, but a car is a box: at 90° the viewer should see the full underside, not a 4 px line, and at 180° the opposite side upside-down. The rider floats up to ~13 px above the board at 300 ms (acceptable).
- Fix: optional; drawing `tesla_bottom` scaled by |sin θ| and the side view scaled by |cos θ| (two draws) gives a solid-body flip for free.

### D11 — Small code items · **nice**
- Magic numbers outside `CFG`: horizon/ground fractions (0.62/0.78, 0.60/0.82), `roadTop` 0.025, `dashY` 0.38, sun 0.72/0.05/0.07, puff 0.93/0.12, band colours.
- `drawText()` builds a font string per call (~10/frame) — cache per size.
- `edgeOn`/`pBottom` math duplicated in `updateObstacles()` and `drawDebug()`.
- `tryFlip()` queues a flip for any mid-air tap, even 1 s before landing → unintended auto-jump after landing. Consider only queuing taps in the last ~150 ms of flight.
- Speed lines in the sky move at 1.3–2× road speed — inverted parallax for the farthest plane; keep them on the road only or slow them to ≤ 0.3×.
- `G.scroll` wrap at 1e7 shifts every layer's phase once (9 h in; harmless).
- `Snd.loops` is write-only; see D7.
- iOS review: `AudioContext` created at boot and resumed synchronously inside `pointerdown` OK; callback-form `decodeAudioData` OK; no `100vh`; `visualViewport` resize handled; `touch-action:none` + `touchend` preventDefault kills double-tap zoom; `localStorage` guarded. Untested: the hardware mute switch silences WebAudio on iOS (known platform behaviour, nothing to fix).

### D12 — README / repo · **nice**
- README lacks controls (tap / Space / M), how to run locally (`python -m http.server`), the `?debug=1` flag, and a note on the Musk likeness (parody). `qa/screenshots/*.png` is git-ignored, so QA evidence does not ship with the repo — fine if intended.
- `theme.ogg` (930 KB) is heavier than the mp3; re-encode at vorbis q3 (~700 KB) to cut the cold start.

---

## Top 5 fixes to lift Visual and Gameplay above 7
1. **D1** Remove the white ground patches from `obst_pickup.png` and `obst_muscle.png` (art, 30 min).
2. **D2** Make `bg_far` and the sun visible above `bg_mid` (dev, 20 min) — restores the 3-layer parallax the art team already delivered.
3. **D3** Give the pickup a per-kind / cab-only hitbox so the single-flip window is >= 200 ms (dev, 30 min + re-run the sweep).
4. **D4** Real difficulty curve: faster speed ramp and a cost for the double flip (dev, 1 h incl. re-tuning windows).
5. **D5 + D6** Move the FLIP button out of the lane in landscape/desktop, scale the sidewalk strip to 1.0 and tighten the portrait vertical layout (dev, 1 h).

After those, re-run the timing sweeps (per car at 1.0× and at the speed cap) and re-shoot the five viewports before publishing.
---

# Round 2 (v0.2, commit ae07258) — re-verification

Same harness and viewports as round 1 (playwright-core + Edge headless, deterministic rAF stepping, 390×844@2 / 360×780 / 430×932 / 844×390 / 1280×800). Evidence: `qa/screenshots/qa2_*.png` (60 shots + `qa2_zoom_*.png`). Pages (`https://klaymendel-art.github.io/tesla-flip/`) serves the v0.2 `game.js` byte-for-byte (md5 match), title in 0.85 s, 24 requests / 1.79 MB, 0 console messages. `.env` still untracked. Every dev/art claim below was re-measured, not taken from the report.

## Round-2 score table

| # | Area | R1 | R2 | Verdict |
|---|------|----|----|---------|
| 1 | Visual / art direction | 6 | **7** | Far skyline + sun now visible (diff test: 16.6k device px of `bg_far` show above `bg_mid`), stars/clouds fill the sky, kerb strip at full scale (lamps taller than the rider), white patches gone. Held back by the new solid-body flip, which draws the car as two stacked cars at takeoff/landing (N1), and an unchanged standing rider pose. |
| 2 | Gameplay / feel | 6 | **7** | Single-flip windows now 225–325 ms for every car at 1.0×, pairs need the double at 1.0× (single: NEVER), speed ramp is felt (1.08× at 10, 1.32× at 40, cap 1.6× at 80), gaps tighten to 1.57 s, pairs spawn together and read as pairs. Held back by: the double is still strictly dominant (575–675 ms vs 225–325 ms) and difficulty *inverts* as speed rises (N2). |
| 3 | Mobile engineering | 8 | **8** | Unchanged and still clean: 0 console errors, FPS avg 100 / min 92 / 0 frames > 25 ms (isolated 15 s run), heap 2.0–2.8 MB flat over 60 s, safe-area and orientation handling intact, mute persists. |
| 4 | Audio | 7 | **8** | `roll` now stops on crash (`loops` = [theme] in `over`), music ducked to 0.35 on the panel, `file://` logs exactly one warning. mp3 fallback still works (8/8). |
| 5 | Code quality | 8 | **8** | `CFG.LAYOUT`/`COLORS`, font cache, shared `playerBottom()`, 150 ms queue window, sky speed lines slowed to 0.25× — all verified in source. New: `drawCarFaces()` allocates 5 arrays per frame while airborne (N3). |
| 6 | Repo / deploy | 8 | **9** | README now has controls, local run, `?debug=1`, parody note; Pages = local. `theme.ogg` still 930 KB (not re-encoded). |

**Ship / don't ship: SHIP v0.2.** Nothing is below 7. N1 and N2 are the recommended v0.3 items; neither blocks showing it around.

## Status of round-1 defects

| ID | Status | Evidence |
|----|--------|----------|
| D1 white patches in pickup / muscle | **fixed** | 0 opaque near-white px in the lower-middle of both sprites (was 37 182 / 18 652); muscle quarter window now glass-grey. `qa2_zoom_pickup_road.png`, `qa2_debug_00_ground.png`. |
| D2 far layer + sun hidden | **fixed** | `bg_far` top at y 331 vs `bg_mid` top 374 (390×844); TV tower, domes and the sun disc visible in every shot. Diff of `qa2_layers_normal.png` vs `qa2_layers_no_far.png`: 16 632 px differ in the y 662–908 band. |
| D3 pickup single window 100 ms | **fixed** | 1.0×: pickup 225 ms (0.10–0.325 s), muscle 275 ms, sedan 325 ms. Dev claimed 250 ms; measured 225 — still above the 200 ms target. Three-box hitboxes (hood/cab/bed) confirmed in `qa2_debug_00_ground.png`. |
| D4 no difficulty curve | **partially** | Ramp: 1.08× @10, 1.16× @20, 1.32× @40, 1.6× @80 (was 1.03× @10). Min non-pair gap 1.57 s (was 1.75–4.33 → now 1.57–3.65). Pair chance ramps (34 pairs in 143 spawns). But the double still wins everywhere (see N2) and `DOUBLE.dur` 1.35 did not change the dominance at 1.0×. |
| D5 FLIP button in the lane (landscape/desktop) | **fixed (accepted)** | `L.showBtn = false` in landscape; hint panel behind the two hint lines. `qa2_l844_02_play_obstacles.png`, `qa2_d1280_03_flip_apex.png`. Hiding rather than relocating is acceptable: the whole screen is the target, desktop has Space/Enter, and the title says "TAP TO FLIP". A 36 px corner affordance would be nicer (nice-to-have). |
| D6 portrait composition | **partially → acceptable** | Horizon 0.66 H / ground 0.80 H, kerb strip 95 px tall at full scale, flat band gone, stars + 3 clouds. Sky above the skyline is still ~55 % of the screen during play and the asphalt is 20 % — but it now reads as deliberate air for the jump rather than dead space. `qa2_p390_02_play_obstacles.png`. |
| D7 roll loop never stops | **fixed** | After crash: `loops` = ["theme"], `musicBus` 0.35; `startLoop('roll')` + `duckMusic(false)` on `resetRun()` present in code (runtime re-check of the restart not repeated). |
| D8 file:// console flood | **fixed** | Real file:// open (no Chromium flags): 1 warning, 0 errors, game playable silently. `qa2_eng_file_url.png`. |
| D9 standing rider pose | **not fixed** (acknowledged) | `musk_ride.png` unchanged. Cosmetic. |
| D10 card flip | **changed — mixed** | Mid-flight frames (200–500 ms) now show a real belly-up car with wheels up: better than v0.1. Takeoff/landing frames are worse — see N1. |
| D11 code items | **mostly fixed** | Magic numbers → `CFG.LAYOUT`/`COLORS`; `drawText` uses pre-built font strings; `playerBottom()` shared; queue only in last 150 ms; sky lines 0.25×. Left: `G.scroll` wrap (harmless), N3. |
| D12 README / ogg size | **fixed / partially** | README rewritten and accurate. `theme.ogg` still 930 KB (mp3 868 KB). |

## Timing sweeps v0.2 (25 ms steps, "lead" = s before hitbox contact)

| Speed (score) | Warning edge→contact | Single: muscle / pickup / sedan | Double over single car | Pair @0.30 / 0.375 / 0.45 carW — single | — double (+80 ms) |
|---|---|---|---|---|---|
| 1.0× (0) | 0.82 s | 275 / 225 / 325 ms | 575–675 ms | NEVER / NEVER / NEVER | 200–225 / 175–200 / 150–175 ms |
| 1.28× (38) | 0.64 s | 400 / 350 / 450 ms | 900–925 ms | 75–100 / 50–75 / 25–50 ms | 425–450 / 400–450 / 375–400 ms |
| 1.6× (75) | 0.51 s | 925 / 900 / 925 ms (any tap while visible) | 900–925 ms | 250 / 225 / 225 ms | 925 ms (any timing) |

Natural spawning, 240 s autopilot: 143 spawns, 34 pairs (gap 0.31–0.44 carW, both cars in the same frame), first pair at score 5, 0 pairs before score 4, 0 overlaps, first obstacle 1.62 s after retry, 0 crashes.

## Flip burst and the two deliberate non-fixes

- **Solid-body flip** (`qa2_flip_single_00…10.png`, `qa2_flip_double_*.png`, `qa2_zoom_flip_frames.png`): frames 02–05 (200–500 ms) are a clear improvement — a white Roadster upside-down with four wheels up, unmistakably a car flipping. Frames 00–01 and 08–09 are a regression: the "roof" face (top 45 % of the side sprite stretched to the box depth) and the far side face render as a second full car stacked on the first, so at takeoff and touchdown the player sees a double-decker. Net: better than the card flip at the apex, worse at the ends. See N1.
- **Rider–roof gap**: traced at 50 ms steps — the feet sit 2–8 CSS px *inside* the car silhouette while it is belly-up (they overlap the upturned wheels) and float at most 5.7 px above it at 0.45 s. At phone scale this reads as "board under the feet". **Acceptable.**
- **FLIP button hidden in landscape/desktop** rather than relocated: **acceptable** (reasons under D5).

## New defects introduced in v0.2

### N1 — Solid-body flip draws two stacked cars at takeoff and landing · **should-fix (visual)**
- Repro: tap once; look at 0–150 ms and 800–1000 ms of the flight (also 400–500 ms on the double). Evidence: `qa2_flip_single_01.png`, `qa2_flip_single_08.png`, `qa2_flip_single_09.png`, `qa2_flip_double_08.png`.
- Cause (`drawCarFaces()`): box depth `Dh = belly.h/2` = 0.76 carH, so the box is 1.5× deeper than it is tall; the roof face is the side sprite's top 45 % *stretched* to that depth (a full-height white car silhouette), and the far side face is drawn at full brightness.
- Fix: `Dh = L.carH * 0.55`; draw the roof as a flat light band (`#eceae6` with ink outline) or crop the side sprite to y 0.12–0.42 and never scale it beyond its own cropped height; multiply far/roof faces by a 0.65 darkening; skip any face whose projected half-height < 3 px. Keep the belly-up frames as they are.

### N2 — Difficulty inverts with speed · **should-fix (gameplay)**
- Flight time is constant (1.0 s / 1.35 s) while the horizontal distance covered scales with speed, so faster = longer jumps over cars of fixed width. Measured: single windows grow 275 → 400 → 925 ms from 1.0× to 1.6×; pairs designed for the double become single-clearable at 1.28× (25–100 ms) and comfortably so at 1.6× (225–250 ms); at 1.6× any tap while the car is on screen clears it and the double clears pairs with any timing. The only thing that gets harder is reaction time (0.82 → 0.51 s).
- Fix (`startFlip()`/`CFG`): scale flight duration by `1 / G.speedMul` (keeps jump length constant in carW: `dur = kind.dur / G.speedMul`, gravity recomputed from the same peak), keep `GAP_SLACK` in distance units so gaps stay fair; re-run the sweep so single windows stay 225–325 ms at every speed. This also fixes the double's dominance at speed. Alternatively cap the ramp at 1.35× and widen pair spacing with score.

### N3 — Per-frame allocations in `drawCarFaces()` · **nice**
- Five arrays (`near`, `bottom`, `far`, `top`, `faces`) are created on every frame while airborne, against the "no per-frame allocations" contract. Hoist them to module scope and fill in place.

### N4 — `theme.ogg` 930 KB · **nice**
- Still the heaviest asset (52 % of first load); vorbis q3 would bring it to ≈ 700 KB.

## Verdict
**SHIP v0.2.** For v0.3: N1 (stacked-car frames), N2 (speed-scaled flight), then D9 (skate stance) and N3/N4.