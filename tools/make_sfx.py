#!/usr/bin/env python3
"""Tesla Flip - procedural SFX generator (Sound Designer).

Renders five sound effects with numpy/scipy, writes 44.1 kHz 16-bit WAVs to
tools/_raw/sfx/, encodes them with ffmpeg to assets/sfx/<name>.ogg (vorbis q4)
and assets/sfx/<name>.mp3 (128 kbps), then runs a self-check (levels, DC,
clicks, loop seam, decode test) and draws waveform+spectrogram PNGs to
qa/screenshots/sfx_<name>.png.

Fully deterministic (fixed RNG seeds).

Usage (from the project root):
    python tools/make_sfx.py            # render + encode + QA
    python tools/make_sfx.py --no-qa    # render + encode only
Requires: numpy, scipy, Pillow (QA only), ffmpeg/ffprobe on PATH.
"""
import os
import subprocess
import sys
import wave

import numpy as np
from scipy import signal

SR = 44100
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RAW_DIR = os.path.join(ROOT, "tools", "_raw", "sfx")
OUT_DIR = os.path.join(ROOT, "assets", "sfx")
QA_DIR = os.path.join(ROOT, "qa", "screenshots")

ONESHOT_PEAK_DB = -6.0
CRASH_PEAK_DB = -4.0     # the "fail" moment is allowed to stand out
LOOP_PEAK_DB = -14.0


# ----------------------------------------------------------------------------
# DSP helpers
# ----------------------------------------------------------------------------
def tvec(dur):
    return np.arange(int(round(dur * SR))) / SR


def db2lin(db):
    return 10.0 ** (db / 20.0)


def glide_phase(f_start, f_end, t, glide_time):
    """Exponential frequency glide f_start -> f_end over glide_time, then hold."""
    frac = np.clip(t / glide_time, 0.0, 1.0)
    f = f_start * (f_end / f_start) ** frac
    return 2 * np.pi * np.cumsum(f) / SR, f


def svf(x, fc, q=0.707, mode="bp"):
    """TPT state-variable filter with per-sample cutoff (fc: scalar or array).
    'bp' is normalised to unity gain at the centre frequency."""
    n = len(x)
    fc = np.broadcast_to(np.asarray(fc, dtype=float), (n,))
    g = np.tan(np.pi * np.clip(fc, 10, SR * 0.45) / SR)
    k = 1.0 / q
    a1 = 1.0 / (1.0 + g * (g + k))
    a2 = g * a1
    a3 = g * a2
    out = np.empty(n)
    ic1 = ic2 = 0.0
    for i in range(n):
        v3 = x[i] - ic2
        v1 = a1[i] * ic1 + a2[i] * v3
        v2 = ic2 + a2[i] * ic1 + a3[i] * v3
        ic1 = 2 * v1 - ic1
        ic2 = 2 * v2 - ic2
        if mode == "bp":
            out[i] = k * v1
        elif mode == "lp":
            out[i] = v2
        else:  # hp
            out[i] = x[i] - k * v1 - v2
    return out


def bp4(x, fc, q):
    """Two cascaded SVF band-passes: steeper skirts so a sweep reads clearly."""
    return svf(svf(x, fc, q, "bp"), fc, q, "bp")


def saturate(x, drive):
    """tanh waveshaper; adds odd harmonics so sub-bass hits still read on
    phone speakers (which roll off below ~150-200 Hz)."""
    return np.tanh(drive * x) / np.tanh(drive)


def env_exp(t, t0, tau, attack=0.001):
    """Linear attack (`attack` s) then exponential decay, starting at t0."""
    tt = t - t0
    e = np.where(tt < 0, 0.0, np.exp(-np.maximum(tt - attack, 0) / tau))
    if attack > 0:
        e *= np.clip(tt / attack, 0, 1)
    return e


def fades(x, fin, fout):
    """Raised-cosine fade in/out (seconds). Works on (n,) or (n, ch)."""
    x = x.copy()
    n = x.shape[0]
    ni, no = int(fin * SR), int(fout * SR)
    if ni > 0:
        w = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, ni))
        x[:ni] *= w if x.ndim == 1 else w[:, None]
    if no > 0:
        w = 0.5 + 0.5 * np.cos(np.linspace(0, np.pi, no))
        x[n - no:] *= w if x.ndim == 1 else w[:, None]
    x[0] = 0.0   # guarantee exact zero at the edges
    x[-1] = 0.0
    return x


def soft_clip(x, drive=1.3):
    """Normalise to 1, gentle tanh saturation (acts as a soft limiter)."""
    p = np.max(np.abs(x))
    if p == 0:
        return x
    return np.tanh(drive * x / p) / np.tanh(drive)


def normalise(x, peak_db):
    return x * (db2lin(peak_db) / np.max(np.abs(x)))


def remove_dc(x):
    sos = signal.butter(2, 25, "highpass", fs=SR, output="sos")
    return signal.sosfilt(sos, x, axis=0)


def finish_oneshot(x, fin, fout, drive=1.3, peak_db=ONESHOT_PEAK_DB):
    x = remove_dc(x)
    x = soft_clip(x, drive)
    x = fades(x, fin, fout)
    x = x - x.mean(axis=0)          # kill residual DC
    x = fades(x, 0.0005, 0.0005)    # re-zero the edges after the shift
    return normalise(x, peak_db)


def circular_filter(x, response_fn):
    """Zero-phase filtering in the frequency domain on a *circular* signal:
    the result is exactly periodic over len(x) -> perfect loop."""
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    X *= response_fn(f)
    X[0] = 0.0
    return np.fft.irfft(X, n=len(x))


# ----------------------------------------------------------------------------
# Sounds
# ----------------------------------------------------------------------------
def make_roll():
    """2.0 s seamless loop. Everything is synthesised loop-periodically:
    integer cycles for every oscillator/modulator, circular FFT filtering for
    noise, ticks wrapped around the loop end. No crossfade needed."""
    rng = np.random.default_rng(101)
    dur = 2.0
    n = int(dur * SR)
    t = np.arange(n) / SR

    # electric motor whine: 220 Hz (440 cycles / loop), slight 1.5 Hz FM
    f0 = 220.0
    phase = 2 * np.pi * f0 * t + 0.5 * np.sin(2 * np.pi * 1.5 * t)   # 3 cyc
    motor = (np.sin(phase)
             + 0.30 * np.sin(2 * phase + 0.4)
             + 0.12 * np.sin(3 * phase + 1.1)
             + 0.05 * np.sin(4 * phase))
    # faint high "inverter" whine (6th harmonic) for the electric character
    motor += 0.06 * np.sin(6 * phase) * (1 + 0.5 * np.sin(2 * np.pi * 0.5 * t))
    motor *= 1.0 + 0.22 * np.sin(2 * np.pi * 2.5 * t)                 # 5 cyc

    # wheel rumble on asphalt: circular low-passed noise
    def rumble_resp(f):
        lp = 1 / np.sqrt(1 + (f / 220.0) ** 4)
        hp = 1 / np.sqrt(1 + (35.0 / np.maximum(f, 1e-3)) ** 4)
        return lp * hp
    rumble = circular_filter(rng.standard_normal(n), rumble_resp)
    rumble /= np.std(rumble)
    rumble *= 1.0 + 0.15 * np.sin(2 * np.pi * 2.0 * t + 0.7)          # 4 cyc

    def hiss_resp(f):
        return np.exp(-0.5 * ((f - 3500.0) / 1200.0) ** 2)
    hiss = circular_filter(rng.standard_normal(n), hiss_resp)
    hiss /= np.std(hiss)

    # tiny periodic ticks (wheel seam): 8 per loop, offset by 1/8 s so the
    # loop seam sits between ticks; placement is still wrapped circularly
    ticks = np.zeros(n)
    tick_len = int(0.006 * SR)
    tt = np.arange(tick_len) / SR
    for i in range(8):
        pos = int((0.125 + i * 0.25 + rng.uniform(-0.004, 0.004)) * SR) % n
        amp = rng.uniform(0.7, 1.0)
        burst = (np.sin(2 * np.pi * 2900 * tt) * 0.6
                 + rng.standard_normal(tick_len) * 0.4) * np.exp(-tt / 0.0012)
        idx = (pos + np.arange(tick_len)) % n
        ticks[idx] += amp * burst

    mix = (0.45 * motor / np.max(np.abs(motor)) + 0.30 * rumble / 3.0
           + 0.03 * hiss / 3.0 + 0.12 * ticks)
    mix -= mix.mean()
    mix = soft_clip(mix, 1.2)           # sample-wise -> stays periodic
    mix -= mix.mean()                   # tanh asymmetry can leave tiny DC
    # Rotate the (periodic) loop so the wrap point lands in its quietest
    # 3 ms spot. The master is seamless anyway; this minimises the small edge
    # error lossy codecs (vorbis/mp3) add at the file boundaries.
    w = int(0.003 * SR)
    energy = np.convolve(np.concatenate([mix, mix[:w]]) ** 2, np.ones(w), "valid")[:n]
    mix = np.roll(mix, -(int(np.argmin(energy)) + w // 2))
    return normalise(mix, LOOP_PEAK_DB)


def make_pop():
    rng = np.random.default_rng(202)
    t = tvec(0.30)
    n = len(t)

    # transient click: 5 ms bright noise burst
    click = svf(rng.standard_normal(n), 2500, 0.8, "hp") * env_exp(t, 0.0, 0.0012, 0.0002)
    click *= (t < 0.005)
    # wooden body: two damped resonances
    wood = (0.55 * np.sin(2 * np.pi * 820 * t) * env_exp(t, 0, 0.012, 0.0003)
            + 0.30 * np.sin(2 * np.pi * 1730 * t) * env_exp(t, 0, 0.006, 0.0003))
    # pitched thump 150 -> 60 Hz over 60 ms
    ph, _ = glide_phase(150, 60, t, 0.060)
    thump = saturate(np.sin(ph), 2.0) * env_exp(t, 0.0, 0.035, 0.001)
    # start of a whoosh: band-passed noise, centre freq rising 500 -> 1.4 kHz,
    # level swelling to ~0.18 s and easing off so the file ends quietly
    ramp = np.clip((t - 0.03) / 0.27, 0, 1)
    wenv = np.sin(np.pi * np.clip((t - 0.03) / 0.30, 0, 1)) ** 1.5
    whoosh = bp4(rng.standard_normal(n), 500 + 900 * ramp, 1.0) * wenv

    x = 0.9 * click + 0.7 * wood + 1.0 * thump + 0.55 * whoosh
    return finish_oneshot(x, 0.0005, 0.040)


def make_flip():
    rng = np.random.default_rng(303)
    t = tvec(0.50)
    n = len(t)

    # centre freq 400 -> 2000 (at 0.24 s) -> 900 Hz, log interpolation
    fc = np.exp(np.interp(t, [0.0, 0.24, 0.50], np.log([400.0, 2000.0, 900.0])))
    # amplitude swell peaking ~0.22 s
    swell = np.sin(np.pi * np.clip(t / 0.5, 0, 1)) ** 1.6
    swell *= 1 + 0.25 * np.sin(np.pi * np.clip(t / 0.22, 0, 1))

    common = rng.standard_normal(n)
    nl = 0.85 * common + 0.53 * rng.standard_normal(n)   # partly decorrelated
    nr = 0.85 * common + 0.53 * rng.standard_normal(n)
    wl = bp4(nl, fc, 1.1) * swell
    wr = bp4(nr, fc * 1.04, 1.1) * swell

    # faint rising sine (car spinning) 300 -> 620 Hz with rotation flutter
    ph, _ = glide_phase(300, 620, t, 0.45)
    spin = 0.10 * np.sin(ph) * (0.6 + 0.4 * np.sin(2 * np.pi * 13 * t)) * swell

    # small left -> right movement (equal power pan 0.35 -> 0.65)
    pan = 0.35 + 0.30 * np.clip(t / 0.5, 0, 1)
    gl, gr = np.cos(pan * np.pi / 2), np.sin(pan * np.pi / 2)
    x = np.stack([(wl + spin) * gl, (wr + spin) * gr], axis=1)
    return finish_oneshot(x, 0.010, 0.040, drive=1.1)


def make_land():
    rng = np.random.default_rng(404)
    t = tvec(0.35)
    n = len(t)

    # thud: sine 90 -> 45 Hz, fast decay + short low "thwack" noise
    ph, _ = glide_phase(90, 45, t, 0.080)
    thud = saturate(np.sin(ph), 2.2) * env_exp(t, 0.0, 0.050, 0.0015)
    knock = np.sin(2 * np.pi * 210 * t) * env_exp(t, 0.0, 0.015, 0.0008)
    thwack = svf(rng.standard_normal(n), 700, 0.7, "lp") * env_exp(t, 0, 0.008, 0.0005)

    # wheel chirp: 40 ms noise burst, band-pass 3 kHz -> 1.6 kHz, fairly tight
    t0, cl = 0.008, 0.040
    w = np.clip((t - t0) / cl, 0, 1)
    chirp_env = np.sin(np.pi * w) ** 2 * ((t >= t0) & (t <= t0 + cl))
    chirp = svf(rng.standard_normal(n), 3000 * (1600 / 3000) ** w, 6.0, "bp") * chirp_env

    # subtle metallic clank: inharmonic partials (ratio ~1.575)
    clank = (np.sin(2 * np.pi * 1530 * t) * env_exp(t, 0.003, 0.045, 0.0005)
             + 0.7 * np.sin(2 * np.pi * 2410 * t + 0.5) * env_exp(t, 0.003, 0.030, 0.0005)
             + 0.25 * np.sin(2 * np.pi * 3970 * t + 1.3) * env_exp(t, 0.003, 0.015, 0.0005))

    x = 1.0 * thud + 0.30 * knock + 0.35 * thwack + 0.55 * chirp + 0.10 * clank
    return finish_oneshot(x, 0.0005, 0.030)


def make_combo():
    t = tvec(0.50)
    n = len(t)

    def chime(f, t0, tau):
        ph = 2 * np.pi * f * np.maximum(t - t0, 0)
        tone = np.sin(ph) + 0.12 * np.sin(2 * ph) + 0.05 * np.sin(3 * ph)
        sparkle = 0.18 * np.sin(4.2 * ph) * env_exp(t, t0, 0.025, 0.002)
        return tone * env_exp(t, t0, tau, 0.006) + sparkle

    E5, B5 = 659.26, 987.77
    dry = 0.85 * chime(E5, 0.0, 0.09) + 1.0 * chime(B5, 0.10, 0.17)

    # reverb-ish tail: a few decaying, progressively darker echoes
    wet = np.zeros(n)
    lp = dry.copy()
    b, a = signal.butter(1, 4500, fs=SR)
    for delay, gain in [(0.043, 0.38), (0.081, 0.27), (0.127, 0.18),
                        (0.173, 0.11), (0.229, 0.06)]:
        lp = signal.lfilter(b, a, lp)
        d = int(delay * SR)
        wet[d:] += gain * lp[:n - d]
    return finish_oneshot(dry + wet, 0.002, 0.080)


def make_score():
    """Tiny +1 blip: quick G5 -> C6 glide, near-sine, 2 ms attack, fast decay.
    Deliberately soft-edged (no noise, few harmonics) since it plays often."""
    t = tvec(0.15)
    ph, _ = glide_phase(783.99, 1046.50, t, 0.025)
    tone = np.sin(ph) + 0.08 * np.sin(3 * ph) + 0.04 * np.sin(2 * ph)
    x = tone * env_exp(t, 0.0, 0.028, 0.002)
    return finish_oneshot(x, 0.001, 0.030, drive=0.3)  # ~linear: no added overtones


def saw_bl(phase, f, fmax=9000.0):
    """Band-limited sawtooth by additive synthesis (no aliasing)."""
    out = np.zeros_like(phase)
    for k in range(1, int(fmax / np.max(f)) + 1):
        out += np.sin(k * phase) / k
    return out * (2 / np.pi)


def make_crash():
    rng = np.random.default_rng(505)
    t = tvec(0.80)
    n = len(t)

    # --- metal crunch 0-200 ms: dense low-mid noise, granular crackle ------
    nz = rng.standard_normal(n)
    body = bp4(nz, 700, 0.6)
    grains = np.zeros(n)                               # crunchy crackle
    for g in np.sort(rng.uniform(0.0, 0.20, 60)):
        grains += rng.uniform(0.3, 1.0) * env_exp(t, g, rng.uniform(0.002, 0.008), 0.0005)
    crunch_env = env_exp(t, 0.0, 0.060, 0.002) * (1 - np.clip((t - 0.15) / 0.06, 0, 1))
    crunch = body * (0.55 * crunch_env + 0.45 * np.minimum(grains, 1.5) * crunch_env)
    # low impact weight (saturated so phones hear it)
    ph, _ = glide_phase(110, 50, t, 0.10)
    impact = saturate(np.sin(ph), 2.5) * env_exp(t, 0.0, 0.070, 0.002)
    # inharmonic clangs at a few onsets
    clang = np.zeros(n)
    for t0, base, a in [(0.0, 523.0, 1.0), (0.045, 691.0, 0.7), (0.11, 433.0, 0.6)]:
        for ratio, pa, tau in [(1.0, 1.0, 0.14), (1.593, 0.7, 0.10),
                               (2.405, 0.5, 0.07), (3.62, 0.3, 0.045)]:
            clang += a * pa * np.sin(2 * np.pi * base * ratio * np.maximum(t - t0, 0)
                                     + rng.uniform(0, 2 * np.pi)) * env_exp(t, t0, tau, 0.001)

    # --- glass tinkle: sparse high pings 3-7 kHz, 100-500 ms --------------
    glass = np.zeros(n)
    for t0 in np.sort(rng.uniform(0.10, 0.50, 16)):
        f = rng.uniform(3000, 7000)
        a = rng.uniform(0.4, 1.0) * (1.15 - (t0 - 0.10) / 0.40 * 0.6)   # thinning out
        glass += a * np.sin(2 * np.pi * f * np.maximum(t - t0, 0))             * env_exp(t, t0, rng.uniform(0.012, 0.035), 0.0005)

    # --- old car horn 250-550 ms: two detuned saws ~370/440 Hz, droop -----
    droop = 1.0 - 0.06 * np.clip((t - 0.47) / 0.08, 0, 1) ** 1.5
    f1, f2 = 370.0 * 1.004 * droop, 440.0 * 0.996 * droop
    p1 = 2 * np.pi * np.cumsum(f1) / SR
    p2 = 2 * np.pi * np.cumsum(f2) / SR
    horn = saw_bl(p1, f1, 4500) + saw_bl(p2, f2, 4500)
    horn = bp4(horn, 1000, 0.9) + 0.2 * horn          # nasal horn-bell resonance
    horn = saturate(horn / np.max(np.abs(horn)), 1.5)  # cheap, buzzy speaker
    horn = signal.sosfilt(signal.butter(2, 3500, fs=SR, output="sos"), horn)
    # keep 3-7 kHz free for the glass
    hon = np.clip((t - 0.25) / 0.015, 0, 1)
    hoff = 1 - np.clip((t - 0.53) / 0.045, 0, 1)
    horn *= hon * hoff

    x = (0.9 * crunch + 0.8 * impact + 0.22 * clang + 0.16 * glass + 0.30 * horn)
    x *= 1 - np.clip((t - 0.62) / 0.18, 0, 1) ** 0.7   # everything gone by 0.8 s
    return finish_oneshot(x, 0.0005, 0.030, drive=1.4, peak_db=CRASH_PEAK_DB)


SOUNDS = {
    "roll": make_roll,
    "pop": make_pop,
    "flip": make_flip,
    "land": make_land,
    "combo": make_combo,
    "score": make_score,
    "crash": make_crash,
}


# ----------------------------------------------------------------------------
# IO
# ----------------------------------------------------------------------------
def write_wav(path, x):
    x = np.asarray(x)
    ch = 1 if x.ndim == 1 else x.shape[1]
    pcm = np.clip(np.round(x * 32767), -32768, 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def read_wav(path):
    with wave.open(path, "rb") as w:
        ch = w.getnchannels()
        data = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(float) / 32768
    return data.reshape(-1, ch) if ch > 1 else data


def encode(wav, name):
    ogg = os.path.join(OUT_DIR, name + ".ogg")
    mp3 = os.path.join(OUT_DIR, name + ".mp3")
    common = ["ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-map_metadata", "-1"]
    subprocess.run(common + ["-c:a", "libvorbis", "-q:a", "4", ogg], check=True)
    subprocess.run(common + ["-c:a", "libmp3lame", "-b:a", "128k", mp3], check=True)
    return ogg, mp3


def decode(path, ch):
    out = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-f", "f32le",
                          "-ac", str(ch), "-ar", str(SR), "-"],
                         check=True, capture_output=True).stdout
    x = np.frombuffer(out, "<f4").astype(float)
    return x.reshape(-1, ch) if ch > 1 else x


def ffprobe_info(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "format=duration:stream=codec_name,channels,sample_rate",
                          "-of", "default=nw=1", path],
                         check=True, capture_output=True, text=True).stdout
    return dict(line.split("=", 1) for line in out.split() if "=" in line)


# ----------------------------------------------------------------------------
# QA
# ----------------------------------------------------------------------------
def dbfs(v):
    return 20 * np.log10(max(v, 1e-12))


def mono(x):
    return x if x.ndim == 1 else x.mean(axis=1)


def spec_sim(a, b):
    w = np.hanning(len(a))
    A, B = np.abs(np.fft.rfft(a * w)), np.abs(np.fft.rfft(b * w))
    return float(np.dot(A, B) / (np.linalg.norm(A) * np.linalg.norm(B)))


def seam_metrics(m):
    """Loop-seam click test. A click shows up as a spike in the 2nd difference
    (linear-prediction error) at the wrap point. We compute that error
    circularly for every sample and report where the seam ranks."""
    e = np.abs(m - 2 * np.roll(m, 1) + np.roll(m, 2))
    seam_err = max(e[0], e[1])
    k = int(0.1 * SR)
    c = len(m) // 2
    return {
        "step": abs(m[0] - m[-1]),
        "nb_step": float(np.mean(np.abs(np.diff(np.concatenate([m[-4:], m[:4]]))))),
        "err": float(seam_err),
        "err_med": float(np.median(e)),
        "err_rank": float(np.mean(e < seam_err) * 100),
        "sim_seam": spec_sim(m[-k:], m[:k]),            # tail vs head
        "sim_ref": spec_sim(m[c - k:c], m[c:c + k]),    # two adjacent mid windows
    }


def analyse(name, x):
    m = mono(x)
    r = {
        "dur": x.shape[0] / SR,
        "ch": 1 if x.ndim == 1 else x.shape[1],
        "peak": dbfs(np.max(np.abs(x))),
        "rms": dbfs(np.sqrt(np.mean(x ** 2))),
        "dc": float(np.mean(m)),
        "first": float(np.max(np.abs(np.atleast_1d(x[0])))),
        "last": float(np.max(np.abs(np.atleast_1d(x[-1])))),
    }
    if name == "roll":
        r["seam"] = seam_metrics(m)
    return r


def colormap(v):
    """v in [0,1] -> RGB (dark purple -> magenta -> orange -> pale yellow)."""
    stops = np.array([[0.0, 6, 4, 20], [0.3, 70, 16, 110], [0.55, 190, 50, 90],
                      [0.8, 250, 140, 40], [1.0, 252, 250, 190]])
    rgb = np.stack([np.interp(v, stops[:, 0], stops[:, i]) for i in (1, 2, 3)], -1)
    return rgb.astype(np.uint8)


def draw_png(name, x, stats, path):
    from PIL import Image, ImageDraw
    W, M = 1000, 50
    WH, SH = 220, 280
    H = M + WH + 30 + SH + 50
    img = Image.new("RGB", (W, H), (18, 18, 24))
    dr = ImageDraw.Draw(img)
    pw = W - 2 * M
    m = mono(x)
    n = len(m)

    # waveform (min/max per pixel column)
    y0 = M
    dr.rectangle([M, y0, M + pw, y0 + WH], outline=(70, 70, 90))
    mid = y0 + WH / 2
    for db in (-6, -14):
        a = db2lin(db) * WH / 2
        for yy in (mid - a, mid + a):
            dr.line([M, yy, M + pw, yy], fill=(60, 60, 75))
    dr.line([M, mid, M + pw, mid], fill=(80, 80, 100))
    edges = np.linspace(0, n, pw + 1).astype(int)
    for i in range(pw):
        seg = m[edges[i]:max(edges[i + 1], edges[i] + 1)]
        lo, hi = seg.min(), seg.max()
        dr.line([M + i, mid - hi * WH / 2, M + i, mid - lo * WH / 2], fill=(90, 200, 255))
    dr.text((M, 15), f"{name}  |  {stats['dur']:.3f} s  ch={stats['ch']}  "
                     f"peak {stats['peak']:.1f} dBFS  RMS {stats['rms']:.1f} dBFS  "
                     f"(grid: -6 / -14 dBFS, full scale = box)", fill=(230, 230, 230))

    # spectrogram 0..10 kHz
    f, _, S = signal.spectrogram(m, SR, nperseg=512, noverlap=480, window="hann")
    keep = f <= 10000
    S = 10 * np.log10(S[keep] + 1e-14)
    v = np.clip((S - (S.max() - 80)) / 80, 0, 1)[::-1]
    spec = Image.fromarray(colormap(v)).resize((pw, SH), Image.BILINEAR)
    sy = y0 + WH + 30
    img.paste(spec, (M, sy))
    dr.rectangle([M, sy, M + pw, sy + SH], outline=(70, 70, 90))
    for khz in (0, 2, 4, 6, 8, 10):
        yy = sy + SH - khz / 10 * SH
        dr.text((8, yy - 6), f"{khz}k", fill=(200, 200, 200))
    dur = n / SR
    step = 0.05 if dur <= 0.6 else 0.25
    for s in np.arange(0, dur + 1e-9, step):
        xx = M + s / dur * pw
        dr.line([xx, sy + SH, xx, sy + SH + 5], fill=(200, 200, 200))
        dr.text((xx - 10, sy + SH + 8), f"{s:.2f}", fill=(200, 200, 200))
    dr.text((M, H - 20), "spectrogram 0-10 kHz, 80 dB range; x axis = seconds",
            fill=(160, 160, 170))
    img.save(path)


def run_qa(names):
    rows = []
    for name in names:
        xw = read_wav(os.path.join(RAW_DIR, name + ".wav"))  # what was written
        s = analyse(name, xw)
        enc = {}
        for ext in ("ogg", "mp3"):
            p = os.path.join(OUT_DIR, f"{name}.{ext}")
            y = decode(p, s["ch"])
            enc[ext] = {"size": os.path.getsize(p), "probe": ffprobe_info(p),
                        "dec_len": y.shape[0], "dec_peak": dbfs(np.max(np.abs(y)))}
            if name == "roll":
                enc[ext]["seam"] = seam_metrics(mono(y))
        draw_png(name, xw, s, os.path.join(QA_DIR, f"sfx_{name}.png"))
        rows.append((name, s, enc))

    print("\n=== QA (WAV master | decoded ogg | decoded mp3) ===")
    print(f"{'name':6} {'dur':>6} {'ch':>2} {'peak':>7} {'rms':>7} {'DC':>9} "
          f"{'first':>8} {'last':>8} | {'oggKB':>5} {'ogg len':>7} {'ogg pk':>6} | "
          f"{'mp3KB':>5} {'mp3 len':>7} {'mp3 pk':>6}")
    for name, s, e in rows:
        print(f"{name:6} {s['dur']:6.3f} {s['ch']:2d} {s['peak']:7.2f} {s['rms']:7.2f} "
              f"{s['dc']:9.1e} {s['first']:8.5f} {s['last']:8.5f} | "
              f"{e['ogg']['size']/1024:5.1f} {e['ogg']['dec_len']:7d} {e['ogg']['dec_peak']:6.2f} | "
              f"{e['mp3']['size']/1024:5.1f} {e['mp3']['dec_len']:7d} {e['mp3']['dec_peak']:6.2f}")
    for name, s, e in rows:
        print(f"  ffprobe {name}: ogg={e['ogg']['probe']}  mp3={e['mp3']['probe']}")
        if name == "roll":
            for label, sm in (("wav", s["seam"]), ("ogg", e["ogg"]["seam"]),
                              ("mp3", e["mp3"]["seam"])):
                print(f"  roll seam [{label}]: |x[0]-x[-1]| {sm['step']:.5f} vs neighbour steps "
                      f"{sm['nb_step']:.5f}; 2nd-diff error {sm['err']:.5f} (median {sm['err_med']:.5f}, "
                      f"seam ranks at {sm['err_rank']:.1f} pct); spectral sim tail->head "
                      f"{sm['sim_seam']:.3f} vs mid->mid {sm['sim_ref']:.3f}")
    return rows


def main():
    for d in (RAW_DIR, OUT_DIR, QA_DIR):
        os.makedirs(d, exist_ok=True)
    for name, fn in SOUNDS.items():
        x = fn()
        wav = os.path.join(RAW_DIR, name + ".wav")
        write_wav(wav, x)
        encode(wav, name)
        print(f"rendered {name}: {x.shape[0] / SR:.3f} s")
    if "--no-qa" not in sys.argv:
        run_qa(list(SOUNDS))


if __name__ == "__main__":
    main()
