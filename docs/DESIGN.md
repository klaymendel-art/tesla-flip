# Tesla Flip — design & asset contract

**One-liner:** Elon Musk rides a tiny Tesla Roadster like a skateboard through a parallax city. Gas-guzzling V8 cars sit on the road — tap to kickflip over them. +1 per car cleared, crash = game over.

## Hard constraints
- Mobile-first, portrait 9:16 primary (also works landscape + desktop). Single tap anywhere = kickflip. Space/ArrowUp on desktop.
- Zero build step: `index.html` + `src/*.js` + `src/style.css` + `assets/**`. Vanilla Canvas 2D. No frameworks, no npm.
- Deployed via GitHub Pages from `main` root. Everything must work from a static file server and from `file://` where possible (assets by relative path).
- Total asset weight target < 3 MB (images ≤ 1.5 MB, audio ≤ 1.2 MB).
- 60 fps on a mid-range phone: no per-frame allocations in the loop, pre-scaled images, `devicePixelRatio` capped at 2.
- Audio only after first user gesture (iOS). Music loops seamlessly; SFX are short.
- `.env` is NEVER committed (already in .gitignore).

## Visual style (lock this — all art must match)
Flat vector cartoon, clean bold dark outlines, soft cel shading, saturated but not neon palette. Reference: `tools/_raw/probe_musk.png` (keep that look). Sky is drawn in code as a gradient (dusk: warm orange → violet), so city layers must have **transparent** sky.

## Scene layout (portrait 1080×1920 logical; game scales to fit)
- Sky gradient (code).
- `bg_far.png`  — distant skyline silhouette, low contrast, bluish/violet, scroll factor 0.15.
- `bg_mid.png`  — mid-ground buildings with windows, scroll factor 0.4.
- `bg_near.png` — foreground sidewalk strip + lampposts / small details, scroll factor 0.8 (optional; can be skipped if it clutters).
- Ground: asphalt road strip drawn in code (dark grey with dashed center line scrolling at factor 1.0). Horizon ≈ 62% of height; ground line ≈ 78% of height in portrait.
- Player at x ≈ 30% of width, standing on the car at ground line.

## Sprites (PNG, transparent, trimmed, power-of-two not required)
| file | content | size (px, approx) | notes |
|---|---|---|---|
| `assets/img/musk_ride.png` | Musk alone, skate stance, facing RIGHT, knees slightly bent, arms relaxed, **no car/board** | ~520×900 | feet on a flat invisible line at the bottom edge |
| `assets/img/musk_air.png` | Musk alone, mid-air pose: knees tucked up, arms out for balance, facing RIGHT | ~520×900 | same scale/proportions as ride pose |
| `assets/img/tesla_side.png` | **new Tesla Roadster (2026 reveal)** — see `tools/_raw/ref_roadster.png`: low angular wedge, flat faceted panels, pearl-white body, dark lower sill, thin full-width light bar at the front, dark glass canopy, large multi-spoke wheels. Side view, facing RIGHT, skateboard-like, wheels at bottom edge | ~900×330 | this is the "deck" |
| `assets/img/tesla_bottom.png` | Same car seen from UNDERNEATH as a side silhouette (undercarriage, battery pan, 4 wheels) — shown at the mid-point of the flip | ~900×330 | same width as tesla_side; if unobtainable, dev darkens tesla_side instead |
| `assets/img/bg_far.png` | far skyline, transparent sky | 2048×600, **horizontally tileable** | make tileable by mirroring: generate 1024 wide, append mirrored copy |
| `assets/img/bg_mid.png` | mid buildings, transparent sky | 2048×700, tileable | same trick |
| `assets/img/bg_near.png` | foreground strip (optional) | 2048×300, tileable | |
| `assets/img/obst_muscle.png` | old V8 muscle car (e.g. 70s Dodge Charger/Mustang vibe, no logos), side view facing LEFT, chunky, loud colour (orange/yellow) | ~900×330 | same scale as tesla_side (so the Roadster looks slightly lower/sleeker) |
| `assets/img/obst_pickup.png` | big V8 pickup truck, facing LEFT, dusty green/brown | ~1000×420 | taller than muscle car |
| `assets/img/obst_sedan.png` | boxy old sedan, facing LEFT, beige/maroon | ~900×340 | |
| `assets/img/icon.png` | app icon / favicon: Musk head on white Roadster | 512×512 | |

Transparency: generate on pure white, then remove white via flood fill from the borders (PIL) with tolerance + 1px edge feathering. Bold outlines protect interiors. Verify no white halo on a dark background.

## Obstacles & scoring (added 16.10 by producer)
- Obstacles: old V8 gasoline cars (muscle car, pickup truck, sedan — 3 variants) sitting on the road, scrolling left at road speed (factor 1.0) like parked cars, occasionally puffing dark exhaust (code-drawn particles). Facing LEFT (nose toward the player) reads best as "oncoming/blocking".
- Spawn: random gap between obstacles, min gap = distance travelled during (flip duration + 0.35 s) so a single flip can always recover; sometimes a pair of cars close together (gap < 0.6 car length) that needs the longer **double flip** to clear. Speed ramps slowly (+~3 % per 10 points, cap at 1.8×).
- Scoring: +1 the moment an obstacle's right edge passes behind the player's x while the player is not crashed (any flip, single or double). No points for flipping in empty air. Best score in localStorage.
- Collision: AABB of player (Musk + car, shrunk 15 %) vs obstacle (shrunk 10 %). Player is "over" the obstacle when its bottom is above the obstacle top — a single flip's apex must clear a car with margin; tune jump height so a single flip clears one car comfortably and a double flip (higher, longer) clears a pair.
- Crash: tumble (Musk and Tesla separate, spin, fall), `crash` sfx, 0.8 s, then GAME OVER panel: score, best, "TAP TO RETRY". Retry restarts instantly.
- Title screen hint: "TAP = KICKFLIP · DOUBLE TAP = DOUBLE FLIP · DON'T HIT THE V8s".

## Kickflip animation (dev owns, art provides 2 car frames)
Duration ~0.65 s. Character: parabolic jump (peak ~ 0.33× car width above ground), switch `musk_ride`→`musk_air` while airborne, small forward lean. Car: same parabola with slight lag, rotation about its long axis simulated as `scaleY = cos(θ)`, θ: 0→2π, plus a small Z-rotation (±12°). While `cos(θ) < 0` draw `tesla_bottom` (mirrored vertically). Landing: squash 1.12×/0.9× for 80 ms, dust puff particles, screen micro-shake 2px. Tap while airborne is ignored (or queued at most once). Score +1 per landed flip; double-tap (2 taps within 200 ms before takeoff) = double flip (θ 0→4π, 0.9 s, +3). Counter top-centre, best score in `localStorage`.

## Audio contract
| file | content | len |
|---|---|---|
| `assets/sfx/roll.ogg` + `.mp3` | electric motor hum + wheel rumble, seamless loop | 2 s |
| `assets/sfx/pop.ogg/.mp3` | kick/pop at takeoff (wooden click + whoosh start) | 0.3 s |
| `assets/sfx/flip.ogg/.mp3` | airy whoosh with slight pitch-up during rotation | 0.5 s |
| `assets/sfx/land.ogg/.mp3` | thud + wheel chirp | 0.35 s |
| `assets/sfx/combo.ogg/.mp3` | short 2-note bright chime for double flip | 0.5 s |
| `assets/sfx/score.ogg/.mp3` | tiny bright blip (+1 point) | 0.15 s |
| `assets/sfx/crash.ogg/.mp3` | metal crunch + glass tinkle + short car-horn honk | 0.8 s |
| `assets/music/theme.ogg` + `.mp3` | synthwave/chiptune loop, 110–125 BPM, 16 or 32 bars, seamless loop point, ≤ 900 KB mp3 | ~30–60 s |
Peak −1 dBFS, SFX normalised to ≈ −6 dBFS RMS below music by ~3 dB. Provide ogg (vorbis q4) and mp3 (128 kbps) for every file (ffmpeg available).

## Code structure
- `index.html` — viewport meta (`viewport-fit=cover, user-scalable=no`), canvas, overlay for "TAP TO START".
- `src/game.js` — loader (manifest, progress), state machine (boot → title → play), loop with fixed dt, input (pointerdown + keydown), renderer, audio manager (HTMLAudio or WebAudio, unlock on gesture).
- `src/style.css` — full-screen canvas, `touch-action: none`, safe-area insets, no scroll bounce.
- Graceful fallback: if an image fails to load, draw a placeholder shape so the game still runs.

## Roles
- **Producer (main session)** — this doc, repo, integration, final deploy.
- **Dev** — everything under `index.html`, `src/`.
- **Art** — `assets/img/*`, `tools/_raw/*`, `tools/gen_image.py` tweaks. Budget: ≤ $2.50 on OpenRouter.
- **SFX** — `assets/sfx/*`, `tools/make_sfx.py`.
- **Music** — `assets/music/*`, `tools/make_music.py`.
- **QA lead** — `qa/REPORT.md`, screenshots in `qa/screenshots/`; scores each area 1–10, lists must-fix items; nothing ships below 7.
