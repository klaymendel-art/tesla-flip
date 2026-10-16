#!/usr/bin/env python
"""Tesla Flip -- procedural synthwave theme ("Occupy Mars" energy, not epic).

Pure numpy/scipy synthesis. Renders a sample-exact seamless loop:
  tools/_raw/music/theme.wav   44.1 kHz 16-bit stereo master
  assets/music/theme.ogg       libvorbis -q:a 4
  assets/music/theme.mp3       libmp3lame (128k, falls back to 112k/96k to stay <= 900 KB)
and (unless --no-check) runs the self-check and writes
  qa/screenshots/music_loop_join.png, qa/screenshots/music_overview.png

Usage:  python tools/make_music.py [--no-check] [--lufs -14]

Song: 124 BPM, A minor / C major, 32 bars = A(8) A'(8) B(8) A''(8).
  A  : Am F C G x2  -- thin: hook, 8th octave bass, closed hats only, pad -3 dB, everything ~3 dB down
  A' : same chords  -- hook + 3rd harmony, 16th bass, filter opens, riser + roll into B
  B  : F G C Am F G Esus4 E -- new long-note motif, 16th arp, offbeat open hats;
       bars 21-22 breakdown (no kick/snare/hats/bass: pad + arp + lead + riser), crash back in at bar 23
  A'': fullest: hook + octave double + soft arp, 16th hats, climax bar 31, bar 32 leads back to bar 1
v2 mix: 10 % swing + +-4 ms / +-3 % humanise on hats & arp (kick/snare rigid), pad HP 220 Hz,
arp HP 300 Hz, bass LP so it owns 50-200 Hz, lead = 2 pulses (-6 ct) + tri, 1.5 ms click attack,
2-voice chorus (12-18 ms), master at -14 LUFS / -1 dBTP with a soft knee (crest ~14 dB).

Loop technique: everything is rendered on a timeline of N samples (exactly 32 bars)
plus a tail; the tail is folded back onto the head and every bus effect (filters,
delay, reverb, limiter) is applied circularly. The file is therefore one period of a
periodic signal: playing it back-to-back is identical to the music continuing.
"""
import argparse, os, re, subprocess, sys
import numpy as np
from scipy import signal
from scipy.io import wavfile
from scipy.ndimage import maximum_filter1d, minimum_filter1d, uniform_filter1d

# ---------------------------------------------------------------- constants
SR = 44100
BPM = 124
BARS = 32
SPB = 60.0 / BPM                 # seconds per beat
S16 = SPB / 4                    # seconds per 16th
N = int(round(BARS * 16 * S16 * SR))   # loop length in samples
TAIL = int(3.0 * SR)
M = N + TAIL
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(ROOT, "tools", "_raw", "music")
OUT_DIR = os.path.join(ROOT, "assets", "music")
QA_DIR = os.path.join(ROOT, "qa", "screenshots")
rng = np.random.default_rng(20261016)


def pos(bar, s16=0.0):
    """sample index of (bar 0-based, 16th position)"""
    return int(round((bar * 16 + s16) * S16 * SR))


SWING = 0.10          # off-16ths of hats/arp are late by 10 % of a 16th (~12 ms)
JITTER = 0.004        # +-4 ms humanise on hats/arp only (kick/snare stay rigid)
BREAKDOWN = (20, 21)  # bars 21-22: kick/snare/hats/bass out; pad + arp + lead + riser


# per-section energy (applied per note/hit BEFORE folding, so tails and the loop join stay exact)
SEC_E = {"kick": {"A": 0.72, "A'": 0.88, "B": 1.0, "A''": 1.0},
         "snare": {"A": 0.75, "A'": 0.9, "B": 1.0, "A''": 1.0},
         "hat": {"A": 0.8, "A'": 0.9, "B": 1.0, "A''": 1.0},
         "bass": {"A": 0.7, "A'": 0.85, "B": 1.0, "A''": 1.0},
         "lead": {"A": 0.75, "A'": 0.9, "B": 1.0, "A''": 1.0}}


def hpos(bar, s16):
    """humanised position for hats/arp: swing on odd 16ths + timing jitter"""
    t = (bar * 16 + s16 + (SWING if s16 % 2 else 0.0)) * S16 + rng.uniform(-JITTER, JITTER)
    return int(round(t * SR))


def mtof(m):
    return 440.0 * 2 ** ((m - 69) / 12.0)


_NN = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def nm(s):
    """'C#5' -> midi"""
    m = re.fullmatch(r"([A-G])(#|b)?(-?\d)", s)
    v = _NN[m.group(1)] + {"#": 1, "b": -1, None: 0}[m.group(2)]
    return v + 12 * (int(m.group(3)) + 1)


def section(bar):
    return ("A", "A'", "B", "A''")[bar // 8]


# ---------------------------------------------------------------- harmony
A_PROG = ["Am", "F", "C", "G"] * 2
B_PROG = ["F", "G", "C", "Am", "F", "G", "Esus4", "E"]
PROG = A_PROG + A_PROG + B_PROG + A_PROG
CHORD = {  # bass root (low octave of the pump), pad voicing (smooth voice leading), chord pcs
    "Am":    dict(root=nm("A2"), pad=["A3", "C4", "E4"]),
    "F":     dict(root=nm("F2"), pad=["A3", "C4", "F4"]),
    "C":     dict(root=nm("C2"), pad=["G3", "C4", "E4"]),
    "G":     dict(root=nm("G2"), pad=["G3", "B3", "D4"]),
    "Esus4": dict(root=nm("E2"), pad=["A3", "B3", "E4"]),
    "E":     dict(root=nm("E2"), pad=["G#3", "B3", "E4"]),
}
for c in CHORD.values():
    c["pad"] = [nm(p) for p in c["pad"]]
    c["pcs"] = {p % 12 for p in c["pad"]} | {c["root"] % 12}
SCALE_AM = {9, 11, 0, 2, 4, 5, 7}            # A natural minor
SCALE_E = SCALE_AM | {8}                       # + G# over the E chord (harmonic minor)

# ---------------------------------------------------------------- melody
# (16th position in bar, note, length in 16ths)
H1 = [(0, "A4", 2), (2, "C5", 2), (4, "E5", 3), (7, "D5", 1), (8, "E5", 4), (14, "G5", 2)]
H2 = [(0, "A5", 3), (3, "G5", 1), (4, "F5", 2), (6, "E5", 2), (8, "C5", 6)]
H3 = [(0, "E5", 2), (2, "G5", 2), (4, "E5", 3), (7, "D5", 1), (8, "E5", 2), (10, "D5", 2), (12, "C5", 4)]
H4 = [(0, "D5", 6), (6, "B4", 2), (8, "G4", 4), (12, "B4", 4)]
H7 = [(0, "E5", 2), (2, "G5", 2), (4, "C6", 3), (7, "B5", 1), (8, "G5", 4), (12, "E5", 4)]
H8 = [(0, "D5", 4), (4, "E5", 2), (6, "D5", 2), (8, "B4", 6)]
RUN = [(0, "D5", 2), (2, "B4", 2), (4, "D5", 2), (6, "G5", 2), (8, "B5", 2), (10, "A5", 2), (12, "G5", 2), (14, "D5", 2)]
UP16 = [(0, "D5", 4), (4, "G5", 2), (6, "A5", 2), (8, "B5", 4), (12, "D6", 4)]
B17 = [(0, "C6", 6), (6, "A5", 2), (8, "F5", 4), (12, "A5", 4)]
B18 = [(0, "B5", 6), (6, "G5", 2), (8, "D5", 4), (12, "G5", 4)]
B19 = [(0, "C6", 4), (4, "G5", 4), (8, "E5", 4), (12, "G5", 4)]
B20 = [(0, "A5", 8), (8, "E5", 4), (12, "G5", 2), (14, "A5", 2)]
B22 = [(0, "B5", 6), (6, "G5", 2), (8, "B5", 4), (12, "D6", 4)]
B23 = [(0, "B5", 8), (8, "A5", 8)]
B24 = [(0, "G#5", 6), (6, "B5", 2), (8, "G#5", 4), (12, "E5", 4)]
C31 = [(0, "E5", 2), (2, "G5", 2), (4, "C6", 3), (7, "B5", 1), (8, "C6", 2), (10, "D6", 2), (12, "E6", 4)]
C32 = [(0, "D6", 4), (4, "B5", 2), (6, "G5", 2), (8, "D5", 4), (12, "B4", 4)]

LEAD_BARS = ([H1, H2, H3, H4, H1, H2, H7, H8] +           # A
             [H1, H2, H3, RUN, H1, H2, H7, UP16] +        # A'
             [B17, B18, B19, B20, B17, B22, B23, B24] +   # B
             [H1, H2, H3, RUN, H1, H2, C31, C32])         # A''


def lead_notes():
    out = []
    for bar, phrase in enumerate(LEAD_BARS):
        for s, n, ln in phrase:
            out.append((bar, s, ln, nm(n)))
    return out


def third_below(m):
    """diatonic third below in A minor"""
    for d in (3, 4):
        if (m - d) % 12 in SCALE_AM:
            return m - d
    return m - 3


# ---------------------------------------------------------------- oscillators
def _blep(ph, dt):
    dt = np.broadcast_to(dt, ph.shape)
    out = np.zeros_like(ph)
    m = ph < dt
    x = ph[m] / dt[m]
    out[m] = x + x - x * x - 1.0
    m = ph > 1.0 - dt
    x = (ph[m] - 1.0) / dt[m]
    out[m] = x * x + x + x + 1.0
    return out


def saw(ph, dt):
    return 2.0 * ph - 1.0 - _blep(ph, dt)


def pulse(ph, dt, w=0.5):
    return saw(ph, dt) - saw((ph + w) % 1.0, dt)


def tri(ph):
    return 4.0 * np.abs(ph - 0.5) - 1.0


def noise(n):
    return rng.uniform(-1, 1, n)


def sos_lp(fc, order=2):
    return signal.butter(order, min(fc, SR * 0.45), "low", fs=SR, output="sos")


def sos_hp(fc, order=2):
    return signal.butter(order, fc, "high", fs=SR, output="sos")


def sos_bp(lo, hi, order=2):
    return signal.butter(order, [lo, hi], "band", fs=SR, output="sos")


def circ_filt(sos, x, pre=None):
    """IIR filter applied as if the signal were periodic (prewarm with the end)."""
    pre = pre or SR
    y = signal.sosfilt(sos, np.concatenate([x[-pre:], x], axis=0), axis=0)
    return y[pre:]


def high_shelf(fc, gain_db, q=0.707):
    A = 10 ** (gain_db / 40)
    w0 = 2 * np.pi * fc / SR
    al = np.sin(w0) / (2 * q)
    c = np.cos(w0)
    b0 = A * ((A + 1) + (A - 1) * c + 2 * np.sqrt(A) * al)
    b1 = -2 * A * ((A - 1) + (A + 1) * c)
    b2 = A * ((A + 1) + (A - 1) * c - 2 * np.sqrt(A) * al)
    a0 = (A + 1) - (A - 1) * c + 2 * np.sqrt(A) * al
    a1 = 2 * ((A - 1) - (A + 1) * c)
    a2 = (A + 1) - (A - 1) * c - 2 * np.sqrt(A) * al
    return signal.tf2sos([b0 / a0, b1 / a0, b2 / a0], [1, a1 / a0, a2 / a0])


# ---------------------------------------------------------------- bus helpers
def new_bus():
    return np.zeros((M, 2))


def pan_gains(p):  # equal power, p in [-1, 1]
    a = (p + 1) * np.pi / 4
    return np.cos(a), np.sin(a)


def place(bus, start, x, gain=1.0, p=0.0):
    x = np.asarray(x)
    if start < 0:          # circular timeline: a hit pushed before 0 belongs at the end
        start += N
    end = min(M, start + len(x))
    seg = x[: end - start] * gain
    if seg.ndim == 1:
        gl, gr = pan_gains(p)
        bus[start:end, 0] += seg * gl
        bus[start:end, 1] += seg * gr
    else:
        bus[start:end] += seg


def fold(x):
    """wrap everything rendered after the loop end back onto the start"""
    y = x[:N].copy()
    y[:TAIL] += x[N:]
    return y


def fade_tail(x, ms=4):
    k = int(SR * ms / 1000)
    x[-k:] *= np.linspace(1, 0, k)
    return x


# ---------------------------------------------------------------- drum voices
def v_kick():
    n = int(0.42 * SR)
    t = np.arange(n) / SR
    f = 46 + 120 * np.exp(-t / 0.032)
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.tanh(1.8 * np.sin(ph) * np.exp(-t / 0.20)) / np.tanh(1.8)
    click = signal.sosfilt(sos_hp(2500), noise(n)) * np.exp(-t / 0.0035) * 0.5
    return fade_tail(body + click, 8)


def v_snare():
    n = int(0.32 * SR)
    t = np.arange(n) / SR
    body = np.sin(2 * np.pi * np.cumsum(175 + 40 * np.exp(-t / 0.02)) / SR) * np.exp(-t / 0.055) * 0.55
    nz = signal.sosfilt(sos_bp(1200, 9000), noise(n)) * np.exp(-t / 0.11) * 0.9
    clap = np.zeros(n)
    cb = signal.sosfilt(sos_bp(900, 3200), noise(n))
    for i, d in enumerate((0.0, 0.009, 0.019)):
        k = int(d * SR)
        tt = t[: n - k]
        clap[k:] += cb[: n - k] * np.exp(-tt / (0.007 if i < 2 else 0.09)) * (0.7 if i < 2 else 0.8)
    return fade_tail(body + nz + clap, 8)


_METAL = np.array([205.3, 304.4, 369.6, 522.7, 540.0, 800.0]) * 1.6


def _metal(n):
    t = np.arange(n) / SR
    return sum(np.sign(np.sin(2 * np.pi * f * t + rng.uniform(0, 6.28))) for f in _METAL) / 6


def v_hat(open_=False):
    n = int((0.42 if open_ else 0.09) * SR)
    t = np.arange(n) / SR
    src = 0.6 * noise(n) + 0.5 * _metal(n)
    x = signal.sosfilt(sos_hp(7500, 4), src)
    env = np.exp(-t / (0.16 if open_ else 0.022))
    return fade_tail(x * env, 6)


def v_crash(n_sec=2.6):
    n = int(n_sec * SR)
    t = np.arange(n) / SR
    out = np.zeros((n, 2))
    for ch in range(2):
        src = 0.7 * noise(n) + 0.4 * _metal(n)
        x = signal.sosfilt(sos_hp(4500, 2), src)
        x = signal.sosfilt(sos_lp(13000), x)
        out[:, ch] = x * np.exp(-t / 0.75) * (0.5 + 0.5 * np.exp(-t / 0.05))
    out[-int(0.01 * SR):] *= np.linspace(1, 0, int(0.01 * SR))[:, None]
    return out


def v_tom(f0):
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    f = f0 * (0.72 + 0.28 * np.exp(-t / 0.06))
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.16)
    x += signal.sosfilt(sos_bp(500, 4000), noise(n)) * np.exp(-t / 0.02) * 0.25
    return fade_tail(x, 8)


# ---------------------------------------------------------------- render: drums
def render_drums():
    drums, verb_send = new_bus(), new_bus()
    kick, snare = v_kick(), v_snare()
    hats_c = [v_hat(False) for _ in range(4)]
    hat_o = v_hat(True)
    crash = v_crash()
    kicks = []
    for bar in range(BARS):
        sec = section(bar)
        for beat in range(4):
            if beat == 3 and bar in (15, 31):     # gap before B and before the loop restart
                continue
            if bar in BREAKDOWN:
                continue
            p = pos(bar, beat * 4)
            place(drums, p, kick, SEC_E["kick"][sec])
            kicks.append(p)
        if bar in BREAKDOWN:
            continue
        for s in (4, 12):
            place(drums, pos(bar, s), snare, 0.70 * SEC_E["snare"][sec])
            place(verb_send, pos(bar, s), snare, 0.55)
        # hats
        for s in range(16):
            onb = s % 4 == 0
            if sec == "B":
                if s % 4 == 2:
                    place(drums, hpos(bar, s), hat_o, 0.22 * rng.uniform(0.97, 1.03), 0.15)
                    continue
                if s % 2 == 1:
                    continue
                v = 0.10
            elif sec == "A''":
                v = (0.13 if onb else 0.20) if s % 2 == 0 else 0.08
            else:
                if s % 2 == 1:
                    continue
                v = 0.12 if onb else 0.20
            v *= rng.uniform(0.97, 1.03) * SEC_E["hat"][sec]
            place(drums, hpos(bar, s), hats_c[rng.integers(4)], v, 0.15)
        # occasional open hat on the "and" of 4
        if (sec == "A'" and bar % 2 == 1) or sec == "A''":      # A = closed hats only
            if bar not in (15, 31):
                place(drums, hpos(bar, 14), hat_o, 0.18 * rng.uniform(0.97, 1.03), 0.15)
    for bar in (0, 8, 16, 22, 24):
        place(drums, pos(bar), crash, 0.26)
        place(verb_send, pos(bar), crash, 0.10)

    # fills / transitions
    for s, v in ((13, 0.30), (14, 0.40), (15, 0.55)):                   # bar 8
        place(drums, pos(7, s), snare, v)
    for i, s in enumerate(range(8, 16)):                                 # bar 16 roll
        if s != 12:
            place(drums, pos(15, s), snare, 0.18 + 0.05 * i)
        place(verb_send, pos(15, s), snare, 0.2 + 0.04 * i)
    for s, f in zip((12, 13, 14, 15), (210, 175, 140, 112)):            # bar 24 toms
        place(drums, pos(23, s), v_tom(f), 0.55, (0.35, 0.15, -0.15, -0.35)[s - 12])
        place(verb_send, pos(23, s), v_tom(f), 0.3)
    for s, v in ((13, 0.30), (14, 0.40), (15, 0.50)):                   # bar 32 -> bar 1
        place(drums, pos(31, s), snare, v)
    place(drums, pos(31, 14), v_tom(150), 0.40, -0.2)
    place(drums, pos(31, 15), v_tom(115), 0.45, -0.3)

    for i, s in enumerate(range(8, 16)):                                 # bar 22 rebuild roll
        place(drums, pos(21, s), snare, 0.10 + 0.05 * i)
        place(verb_send, pos(21, s), snare, 0.15 + 0.04 * i)

    # risers (filtered noise sweeps): bars 15-16 into B, bars 21-22 (breakdown) into bar 23
    for b0, b1, g in ((14, 16, 0.22), (20, 22, 0.26)):
        n = pos(b1) - pos(b0)
        p = np.linspace(0, 1, n)
        for ch in range(2):
            nz = noise(n)
            lo = signal.sosfilt(sos_bp(300, 1200), nz)
            mid = signal.sosfilt(sos_bp(1200, 4000), nz)
            hi = signal.sosfilt(sos_hp(4000), nz)
            sweep = ((1 - p) ** 2 * lo + 2 * p * (1 - p) * mid + p ** 2 * hi) * p ** 2 * g
            sweep[-int(0.01 * SR):] *= np.linspace(1, 0, int(0.01 * SR))
            drums[pos(b0):pos(b1), ch] += sweep
    # reverse cymbal over the end of bar 24
    rc = v_crash(2 * SPB + 0.05)[::-1]
    rc = rc * np.linspace(0, 1, len(rc))[:, None] ** 2
    rc[-int(0.008 * SR):] *= np.linspace(1, 0, int(0.008 * SR))[:, None]
    place(drums, pos(24) - len(rc), rc, 0.35)
    return drums, verb_send, kicks


# ---------------------------------------------------------------- render: bass
def render_bass():
    raw = np.zeros(M)
    env = np.zeros(M)
    for bar in range(BARS):
        sec = section(bar)
        r = CHORD[PROG[bar]]["root"]
        if bar in BREAKDOWN:
            continue
        if sec == "A":
            steps = [(s, 2, (r if (s // 2) % 2 == 0 else r + 12)) for s in range(0, 16, 2)]
        elif sec == "B":
            steps = [(s, 1, (r, r, r + 12, r)[s % 4]) for s in range(16)]
        else:
            steps = [(s, 1, (r, r + 12)[s % 2]) for s in range(16)]
        for s, ln, m in steps:
            st = pos(bar, s)
            dur = ln * S16 * 0.72
            n = int((dur + 0.02) * SR)
            t = np.arange(n) / SR
            f = mtof(m)
            ph = (t * f + rng.uniform()) % 1.0
            x = 0.6 * saw(ph, f / SR) + 0.4 * pulse(ph, f / SR, 0.5)
            if m == r:  # sine reinforcement of the low notes' fundamental (55-110 Hz, phone-friendly)
                x += 0.45 * np.sin(2 * np.pi * f * t)
            a = np.minimum(1, t / 0.002) * np.where(t < dur, 1.0, np.exp(-(t - dur) / 0.006))
            vel = (1.0 if s % 4 == 0 else (0.9 if s % 2 == 0 else 0.8)) * SEC_E["bass"][sec]
            raw[st:st + n] += x * a * vel
            e = np.exp(-t / 0.065)
            env[st:st + n] = np.maximum(env[st:st + n], e[: len(env[st:st + n])])
    raw, env = fold(raw), np.minimum(fold(env), 1.0)
    dark = circ_filt(sos_lp(240, 2), raw)
    bright = circ_filt(sos_lp(1600, 2), raw)
    base = np.zeros(N)
    for bar in range(BARS):
        sec = section(bar)
        a, b = pos(bar), pos(bar + 1)
        if sec == "A":
            base[a:b] = 0.12
        elif sec == "A'":   # filter slowly opens across A' -> transition into B
            base[a:b] = np.linspace(0.15 + 0.04 * (bar - 8), 0.15 + 0.04 * (bar - 7), b - a)
        elif sec == "B":
            base[a:b] = 0.45
        else:
            base[a:b] = 0.45
    mix = np.clip(base + 0.45 * env, 0, 1)
    return circ_filt(sos_lp(1100, 2), dark + (bright - dark) * mix)   # bass owns 50-200 Hz


# ---------------------------------------------------------------- render: pad
def render_pad():
    bus = new_bus()
    bar_len = 16 * S16
    for bar in range(BARS):
        sec = section(bar)
        cut = {"A": 1400, "A'": 1400 + 150 * (bar - 8), "B": 2800, "A''": 2300}[sec]
        gain = {"A": 0.60, "A'": 0.95, "B": 1.1, "A''": 1.15}[sec]     # A = -3 dB
        dur = bar_len
        n = int((dur + 0.7) * SR)
        t = np.arange(n) / SR
        a = np.minimum(1, t / 0.32) ** 1.5 * np.where(t < dur, 1.0, np.exp(-(t - dur) / 0.18))
        for m in CHORD[PROG[bar]]["pad"]:
            for cents, p in ((-7, -0.5), (0, 0.0), (7, 0.5)):
                f = mtof(m) * 2 ** (cents / 1200)
                ph = (t * f + rng.uniform()) % 1.0
                x = signal.sosfilt(sos_lp(cut, 2), saw(ph, f / SR))
                place(bus, pos(bar), x * a, 0.33 * gain, p)
    return circ_filt(sos_hp(220, 2), fold(bus))


# ---------------------------------------------------------------- render: lead (mono synth)
def render_lead(notes, wave="lead", glide_tau=0.010, vib_cents=16):
    """notes: list of (bar, s16, len16, midi). Returns mono array length M."""
    freq = np.full(M, np.nan)
    amp = np.zeros(M)
    vib = np.zeros(M)
    notes = sorted(notes, key=lambda x: (x[0], x[1]))
    prev_end, prev_f = None, None
    rel = 0.07
    for bar, s, ln, m in notes:
        st, en = pos(bar, s), pos(bar, s + ln)
        f = mtof(m)
        k = en - st
        seg = np.full(k, f)
        if prev_end == st and prev_f is not None:          # legato -> short portamento
            t = np.arange(k) / SR
            seg = np.exp(np.log(f) + (np.log(prev_f) - np.log(f)) * np.exp(-t / glide_tau))
        freq[st:en] = seg
        dur = k / SR - 0.012
        n = k + int(rel * 5 * SR)
        t = np.arange(n) / SR
        e = np.minimum(1, t / 0.0015) * (0.78 + 0.22 * np.exp(-t / 0.08) + 0.35 * np.exp(-t / 0.0015))
        e = np.where(t < dur, e, e * np.exp(-(t - dur) / rel))
        end = min(M, st + n)
        amp[st:end] = np.maximum(amp[st:end], e[: end - st] * SEC_E["lead"][section(bar)])
        if ln >= 4:
            v = np.clip((t - 0.16) / 0.3, 0, 1)
            vib[st:end] = np.maximum(vib[st:end], v[: end - st])
        prev_end, prev_f = en, f
    # forward fill frequency (release keeps last pitch), backfill head
    idx = np.where(~np.isnan(freq), np.arange(M), 0)
    np.maximum.accumulate(idx, out=idx)
    freq = freq[idx]
    freq[np.isnan(freq)] = mtof(notes[0][3])
    t = np.arange(M) / SR
    inst = freq * 2 ** (vib * vib_cents * np.sin(2 * np.pi * 5.6 * t) / 1200)
    dt = inst / SR
    ph = np.cumsum(dt) % 1.0
    if wave == "lead":
        dt2 = dt * 2 ** (-6 / 1200)                       # second oscillator, -6 cents
        ph2 = (np.cumsum(dt2) + 0.37) % 1.0
        x = 0.40 * pulse(ph, dt, 0.5) + 0.32 * pulse(ph2, dt2, 0.5) + 0.33 * tri(ph)
        x = signal.sosfilt(sos_lp(5200, 2), x)
    else:
        x = tri(ph)
    return x * amp


def render_arp():
    bus = new_bus()
    for bar in range(16, 32):
        g = 1.0 if bar < 24 else 0.45            # A'' gets a soft arp -> fullest section
        pad = CHORD[PROG[bar]]["pad"]
        tones = [p + 12 for p in pad] + [pad[0] + 24]
        pat = [0, 1, 2, 3] * 4 if bar < 20 else [0, 1, 2, 3, 2, 1, 0, 1, 2, 3, 2, 1, 0, 1, 2, 3]
        for s in range(16):
            m = tones[pat[s]]
            n = int(S16 * SR * 1.6)
            t = np.arange(n) / SR
            f = mtof(m)
            ph = (t * f) % 1.0
            x = pulse(ph, f / SR, 0.25)
            e = np.minimum(1, t / 0.002) * np.exp(-t / 0.075)
            v = 1.0 if s % 4 == 0 else 0.8
            v *= rng.uniform(0.97, 1.03)
            place(bus, hpos(bar, s), signal.sosfilt(sos_lp(3200, 2), x * e), 0.5 * v * g, 0.3 if s % 2 else -0.3)
    return circ_filt(sos_hp(300, 2), fold(bus))


# ---------------------------------------------------------------- effects (circular)
def sidechain(kicks, depth, tau=0.10):
    k = np.array(kicks)
    idx = np.searchsorted(k, np.arange(N), side="right") - 1
    last = np.where(idx >= 0, k[idx], k[-1] - N)          # before first kick: wrap to the last one
    dt = (np.arange(N) - last) / SR
    att = np.clip(dt / 0.004, 0, 1)
    return 1 - depth * att * np.exp(-dt / tau)


def pingpong(x, delay_s, fb=0.38, taps=4):
    """x: mono (N,), returns stereo (N,2) wet only, circular"""
    d = int(round(delay_s * SR))
    out = np.zeros((N, 2))
    src = circ_filt(sos_lp(3000), circ_filt(sos_hp(300), x))
    for i in range(1, taps + 1):
        out[:, (i + 1) % 2] += np.roll(src, i * d) * fb ** (i - 1)
    return out


def chorus(x, base=0.015, depth=0.003):
    """two modulated delays (12-18 ms); LFO rates are whole cycles per loop so it stays periodic"""
    T = N / SR
    n = np.arange(N)
    out = np.zeros((N, 2))
    for ch, (k, ph0) in enumerate(((19, 0.0), (23, np.pi / 2))):
        d = (base + depth * np.sin(2 * np.pi * k / T * n / SR + ph0)) * SR
        idx = n - d
        i0 = np.floor(idx).astype(np.int64)
        fr = idx - i0
        out[:, ch] = x[i0 % N] * (1 - fr) + x[(i0 + 1) % N] * fr
    return out


def reverb(x, rt60=1.3):
    """x: stereo (N,2) send, circular convolution with decorrelated noise IR"""
    n = int(1.8 * SR)
    t = np.arange(n) / SR
    pre = int(0.018 * SR)
    out = np.zeros_like(x)
    send = circ_filt(sos_hp(250), x)
    for ch in range(2):
        ir = noise(n) * np.exp(-6.9 * t / rt60)
        ir = signal.sosfilt(sos_lp(6500), ir)
        ir = np.concatenate([np.zeros(pre), ir])
        ir /= np.sqrt(np.sum(ir ** 2))
        H = np.fft.rfft(np.pad(ir, (0, N - len(ir))))
        out[:, ch] = np.fft.irfft(np.fft.rfft(send[:, ch]) * H, n=N)
    return out


# ---------------------------------------------------------------- loudness / peak
def _kweight(x):
    def biquad(f0, Q, G=None):
        K = np.tan(np.pi * f0 / SR)
        if G is None:   # high-pass
            a0 = 1 + K / Q + K * K
            return [1, -2, 1], [1, 2 * (K * K - 1) / a0, (1 - K / Q + K * K) / a0]
        Vh = 10 ** (G / 20)
        Vb = Vh ** 0.4996667741545416
        a0 = 1 + K / Q + K * K
        b = [(Vh + Vb * K / Q + K * K) / a0, 2 * (K * K - Vh) / a0, (Vh - Vb * K / Q + K * K) / a0]
        a = [1, 2 * (K * K - 1) / a0, (1 - K / Q + K * K) / a0]
        return b, a
    b1, a1 = biquad(1681.974450955533, 0.7071752369554196, 3.999843853973347)
    b2, a2 = biquad(38.13547087602444, 0.5003270373238773)
    y = signal.lfilter(b1, a1, x, axis=0)
    return signal.lfilter(b2, a2, y, axis=0)


def lufs(x):
    y = _kweight(x)
    blk, hop = int(0.4 * SR), int(0.1 * SR)
    p = np.cumsum(np.concatenate([np.zeros((1, 2)), y ** 2]), axis=0)
    starts = np.arange(0, len(y) - blk, hop)
    z = (p[starts + blk] - p[starts]) / blk
    zs = z.sum(axis=1)
    l = -0.691 + 10 * np.log10(zs + 1e-20)
    g = zs[l > -70]
    rel = -0.691 + 10 * np.log10(g.mean()) - 10
    g2 = zs[(l > -70) & (l > rel)]
    return -0.691 + 10 * np.log10(g2.mean())


def true_peak(x):
    pad = 512
    xx = np.concatenate([x[-pad:], x, x[:pad]], axis=0)
    up = signal.resample_poly(xx, 4, 1, axis=0)
    return np.max(np.abs(up[4 * pad:-4 * pad]))


def limiter(x, ceiling, look=0.012, hold=0.05):
    a = np.max(np.abs(x), axis=1)
    L = int(look * SR)
    R = int(hold * SR)
    g = np.minimum(1.0, ceiling / np.maximum(a, 1e-9))
    W = R + L + 1
    gm = np.roll(minimum_filter1d(g, size=W, mode="wrap"), R - W // 2)   # min over [i-R, i+L]
    gm = uniform_filter1d(gm, size=2 * L + 1, mode="wrap")
    return x * gm[:, None], gm


def softclip(x, knee=0.6):
    ax = np.abs(x)
    over = ax > knee
    y = x.copy()
    y[over] = np.sign(x[over]) * (knee + (1 - knee) * np.tanh((ax[over] - knee) / (1 - knee)))
    return y


def master(mix, drive):
    x = mix / np.max(np.abs(mix)) * drive
    x, gr = limiter(x, 0.97)
    x = softclip(x, knee=0.85)
    x = x * (10 ** (-1.0 / 20) / true_peak(x))        # -1.0 dBTP
    return x, gr


# ---------------------------------------------------------------- main render
def render(target_lufs):
    print(f"[music] {BPM} BPM, {BARS} bars, N={N} samples ({N / SR:.3f} s)")
    drums, d_send, kicks = render_drums()
    drums, d_send = fold(drums), fold(d_send)
    print("[music] drums done")
    bass = render_bass()
    print("[music] bass done")
    pad = render_pad()
    print("[music] pad done")
    ln = lead_notes()
    lead = fold(render_lead(ln))
    harm = fold(render_lead([(b, s, l, third_below(m)) for b, s, l, m in ln if 8 <= b < 16], vib_cents=10))
    octv = fold(render_lead([(b, s, l, m + 12) for b, s, l, m in ln if b >= 24], wave="tri", vib_cents=10))
    arp = render_arp()
    print("[music] lead/arp done")

    lead_m = lead + 0.38 * harm + 0.30 * octv      # section levels are applied per note

    sc_pad = sidechain(kicks, 0.72)
    sc_bass = sidechain(kicks, 0.55, tau=0.08)
    sc_arp = sidechain(kicks, 0.35)
    sc_lead = sidechain(kicks, 0.12)

    buses = {}
    buses["drums"] = drums * 1.0
    buses["bass"] = np.repeat((bass * sc_bass * 0.42)[:, None], 2, axis=1)            # mono
    buses["pad"] = pad * sc_pad[:, None] * 0.44
    gl, gr = pan_gains(0.0)
    lead_dry = lead_m * sc_lead * 0.40
    cho = chorus(lead_dry)          # two voices, one per side, equal level -> lead stays centred
    lead_st = np.stack([lead_dry * gl, lead_dry * gr], axis=1) + 0.30 * cho
    buses["lead"] = lead_st
    buses["arp"] = arp * sc_arp[:, None] * 1.0
    wet_delay = pingpong(lead_m * sc_lead * 0.40 + 0.5 * arp.mean(axis=1), 3 * S16) * 0.22
    verb_in = d_send * 0.6 + buses["pad"] * 0.5 + lead_st * 0.6 + buses["arp"] * 0.4
    wet_verb = reverb(verb_in) * 0.28
    buses["fx"] = wet_delay + wet_verb * sc_pad[:, None] ** 0.5
    mix = sum(buses.values())
    mix = circ_filt(high_shelf(9000, -3.0), mix)            # gentle top roll-off
    mix -= mix.mean(axis=0)                                  # kill any DC

    lo, hi = 1.0, 6.0
    out = None
    for it in range(14):
        d = 0.5 * (lo + hi)
        out, gr = master(mix, d)
        L = lufs(out)
        if L < target_lufs:
            lo = d
        else:
            hi = d
        if abs(L - target_lufs) < 0.1:
            break
    if L > target_lufs + 0.1:      # louder than target even unlimited -> turn down (peak < -1 dBTP)
        out = out * 10 ** ((target_lufs - L) / 20)
        L = lufs(out)
    print(f"[music] master: drive={d:.2f} LUFS(int, own meter)={L:.2f}  max GR={-20 * np.log10(gr.min()):.1f} dB")
    return out, buses, mix


def write_and_encode(out):
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    wav = os.path.join(RAW_DIR, "theme.wav")
    pcm = np.clip(np.round(out * 32767), -32768, 32767).astype(np.int16)
    wavfile.write(wav, SR, pcm)
    ogg = os.path.join(OUT_DIR, "theme.ogg")
    mp3 = os.path.join(OUT_DIR, "theme.mp3")
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", wav,
                    "-c:a", "libvorbis", "-q:a", "4", ogg], check=True)
    for br in ("128k", "112k", "96k"):
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", wav,
                        "-c:a", "libmp3lame", "-b:a", br, mp3], check=True)
        if os.path.getsize(mp3) <= 900 * 1024:
            break
    print(f"[music] wrote {wav}\n        {ogg} ({os.path.getsize(ogg) / 1024:.0f} KB)"
          f"\n        {mp3} ({os.path.getsize(mp3) / 1024:.0f} KB @ {br})")
    return wav, ogg, mp3, pcm, br


# ---------------------------------------------------------------- checks
def ebur128(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=peak=true",
                        "-f", "null", "-"], capture_output=True, text=True)
    s = r.stderr[r.stderr.rfind("Summary:"):]
    I = float(re.search(r"I:\s+(-?[\d.]+) LUFS", s).group(1))
    LRA = float(re.search(r"LRA:\s+(-?[\d.]+) LU", s).group(1))
    TP = float(re.search(r"Peak:\s+(-?[\d.]+) dBFS", s).group(1))
    return I, LRA, TP


def decode(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", path, "-f", "s16le",
                        "-ac", "2", "-ar", str(SR), "-"], capture_output=True, check=True)
    return np.frombuffer(r.stdout, dtype=np.int16).reshape(-1, 2).astype(np.float64) / 32768


def join_stats(x):
    d = np.abs(np.diff(x, axis=0)).max(axis=1)
    jump = np.abs(x[0] - x[-1]).max()
    return jump, np.percentile(d, 99.9), d.max()


def check_notes():
    issues = []
    for bar, s, ln, m in lead_notes():
        ch = PROG[bar]
        sc = SCALE_E if ch.startswith("E") else SCALE_AM
        if m % 12 not in sc:
            issues.append(f"bar {bar + 1} pos {s}: {m} out of scale over {ch}")
        if s in (0, 8) and m % 12 not in CHORD[ch]["pcs"]:
            issues.append(f"bar {bar + 1} pos {s}: strong-beat non-chord tone {m % 12} over {ch}")
    return issues


def band_rms(x, lo, hi):
    X = np.fft.rfft(x.mean(axis=1) if x.ndim == 2 else x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    X[(f < lo) | (f >= hi)] = 0
    return np.sqrt(np.mean(np.fft.irfft(X, n=len(x)) ** 2))


def _lerp_cmap(v):
    stops = np.array([[8, 6, 30], [60, 15, 110], [170, 40, 120], [240, 120, 60], [255, 230, 140]], float)
    v = np.clip(v, 0, 1) * (len(stops) - 1)
    i = np.minimum(v.astype(int), len(stops) - 2)
    fr = (v - i)[..., None]
    return (stops[i] * (1 - fr) + stops[i + 1] * fr).astype(np.uint8)


def draw_wave(draw, x, box, color, center_line=True):
    x0, y0, x1, y1 = box
    w = x1 - x0
    h = y1 - y0
    mono = x.mean(axis=1) if x.ndim == 2 else x
    edges = np.linspace(0, len(mono), w + 1).astype(int)
    cy = y0 + h / 2
    if center_line:
        draw.line([(x0, cy), (x1, cy)], fill=(70, 70, 90))
    for i in range(w):
        seg = mono[edges[i]:max(edges[i + 1], edges[i] + 1)]
        draw.line([(x0 + i, cy - seg.max() * h / 2), (x0 + i, cy - seg.min() * h / 2)], fill=color)


def make_pngs(x, dec_ogg):
    from PIL import Image, ImageDraw
    os.makedirs(QA_DIR, exist_ok=True)
    # ---- loop join
    W, H = 1400, 900
    im = Image.new("RGB", (W, H), (16, 14, 28))
    dr = ImageDraw.Draw(im)
    lp = np.concatenate([x, x], axis=0)
    rows = [("+-2 s around loop join (wav, end -> start)", int(2 * SR)),
            ("+-30 ms around loop join (wav)", int(0.03 * SR)),
            ("+-3 ms around loop join (wav, per-sample, L=cyan R=magenta)", int(0.003 * SR))]
    for r, (title, half) in enumerate(rows):
        y0 = 30 + r * 220
        seg = lp[N - half:N + half]
        dr.text((20, y0 - 18), title, fill=(220, 220, 240))
        if half > 1000:
            draw_wave(dr, seg, (20, y0, W - 20, y0 + 190), (120, 200, 255))
        else:
            for ch, col in ((0, (90, 220, 255)), (1, (255, 90, 200))):
                ys = y0 + 95 - seg[:, ch] * 95
                xs = np.linspace(20, W - 20, len(seg))
                dr.line(list(zip(xs, ys)), fill=col, width=2)
                if half < 200:
                    for px, py in zip(xs, ys):
                        dr.ellipse([px - 2, py - 2, px + 2, py + 2], fill=col)
        dr.line([(W / 2, y0), (W / 2, y0 + 190)], fill=(255, 200, 60))
    # ogg decoded join
    y0 = 30 + 3 * 220
    half = int(0.03 * SR)
    lpo = np.concatenate([dec_ogg, dec_ogg], axis=0)
    no = len(dec_ogg)
    dr.text((20, y0 - 18), f"+-30 ms around loop join (theme.ogg decoded, {no} samples)", fill=(220, 220, 240))
    draw_wave(dr, lpo[no - half:no + half], (20, y0, W - 20, y0 + 190), (160, 255, 160))
    dr.line([(W / 2, y0), (W / 2, y0 + 190)], fill=(255, 200, 60))
    p1 = os.path.join(QA_DIR, "music_loop_join.png")
    im.save(p1)

    # ---- overview: waveform + spectrogram + bar markers
    W, H = 1600, 760
    im = Image.new("RGB", (W, H), (16, 14, 28))
    dr = ImageDraw.Draw(im)
    L0, R0 = 50, W - 20
    dr.text((L0, 8), f"Tesla Flip theme - {BPM} BPM, A minor, 32 bars A A' B A'' - waveform (top), "
                     f"spectrogram 0-16 kHz log (bottom)", fill=(230, 230, 240))
    draw_wave(dr, x, (L0, 30, R0, 250), (130, 200, 255))
    mono = x.mean(axis=1)
    f, t, S = signal.spectrogram(mono, fs=SR, nperseg=2048, noverlap=1024)
    S = 10 * np.log10(S + 1e-12)
    S = (S - (S.max() - 90)) / 90
    fy = np.geomspace(30, 16000, 440)
    rowsS = np.array([np.argmin(np.abs(f - q)) for q in fy])
    img = S[rowsS][::-1]
    cols = np.linspace(0, img.shape[1] - 1, R0 - L0).astype(int)
    rgb = _lerp_cmap(img[:, cols])
    im.paste(Image.fromarray(rgb), (L0, 280))
    for q in (50, 100, 250, 500, 1000, 2500, 5000, 10000):
        yy = 280 + 440 - np.argmin(np.abs(fy - q))
        dr.text((2, yy - 6), f"{q if q < 1000 else str(q // 1000) + 'k'}", fill=(180, 180, 200))
    for bar in range(BARS + 1):
        xx = L0 + (R0 - L0) * pos(bar) / N
        col = (255, 200, 60) if bar % 8 == 0 else (60, 60, 80)
        dr.line([(xx, 30), (xx, 250)], fill=col)
        if bar % 8 == 0:
            dr.line([(xx, 280), (xx, 720)], fill=col)
        if bar < BARS and bar % 8 == 0:
            dr.text((xx + 4, 255), f"{section(bar)} (bar {bar + 1})", fill=(255, 220, 120))
    dr.text((L0, 730), "yellow lines = section boundaries (bars 1/9/17/25); grey = bar lines", fill=(160, 160, 180))
    p2 = os.path.join(QA_DIR, "music_overview.png")
    im.save(p2)
    return p1, p2


def run_checks(wav, ogg, mp3, pcm, buses):
    print("\n========== SELF-CHECK ==========")
    x = pcm.astype(np.float64) / 32768
    for p in (wav, ogg, mp3):
        I, LRA, TP = ebur128(p)
        print(f"ebur128 {os.path.basename(p):10s}  I={I:6.1f} LUFS  LRA={LRA:4.1f} LU  TruePeak={TP:5.1f} dBFS"
              f"  size={os.path.getsize(p) / 1024:7.0f} KB")
    print(f"duration: {len(x) / SR:.3f} s ({len(x)} samples, expected {N})")
    print(f"sample peak: {20 * np.log10(np.abs(x).max()):.2f} dBFS; clipped samples (|s|>=32767): "
          f"{int(np.sum(np.abs(pcm.astype(int)) >= 32767))}")
    print(f"crest factor (sample peak / RMS): {20 * np.log10(np.abs(x).max() / np.sqrt(np.mean(x ** 2))):.1f} dB")
    print(f"DC offset: L={x[:, 0].mean():+.2e} R={x[:, 1].mean():+.2e}")
    jump, p999, mx = join_stats(x)
    print(f"loop join (wav): |x[0]-x[-1]|={jump:.4f}  vs in-file diffs: 99.9th pct={p999:.4f} max={mx:.4f}")
    for p in (ogg, mp3):
        d = decode(p)
        j, q, m = join_stats(d)
        print(f"loop join ({os.path.basename(p)} decoded, {len(d)} samples, delta {len(d) - N:+d}): "
              f"jump={j:.4f} (99.9th pct {q:.4f})")
    dec_ogg = decode(ogg)
    # energy per bar -> transitions
    rms = [np.sqrt(np.mean(x[pos(b):pos(b + 1)] ** 2)) for b in range(BARS)]
    print("RMS per bar (dBFS): " + " ".join(f"{20 * np.log10(r):.1f}" + ("|" if (i + 1) % 8 == 0 else "")
                                           for i, r in enumerate(rms)))
    print("bus RMS (pre-master, dB rel. mix):")
    mixall = sum(buses.values())
    ref = np.sqrt(np.mean(mixall ** 2))
    for k, v in buses.items():
        print(f"   {k:6s} {20 * np.log10(np.sqrt(np.mean(v ** 2)) / ref + 1e-12):6.1f} dB")
    print("band energy (dB rel. full mix in band):")
    for lo, hi, name in ((40, 120, "kick/sub 40-120"), (150, 600, "low-mid 150-600"),
                         (1500, 5000, "snare/clap/lead 1.5-5k"), (6000, 16000, "hats 6-16k")):
        tot = band_rms(mixall, lo, hi)
        parts = {k: 20 * np.log10(band_rms(v, lo, hi) / tot + 1e-12) for k, v in buses.items()}
        print(f"   {name:24s} " + "  ".join(f"{k}={v:5.1f}" for k, v in parts.items()))
    # snare audibility: 1.5-5 kHz energy in the first 60 ms after each backbeat, drums vs everything else
    sos = sos_bp(1500, 5000, 4)
    dband = circ_filt(sos, buses["drums"].mean(axis=1))
    oband = circ_filt(sos, (mixall - buses["drums"]).mean(axis=1))
    w = int(0.06 * SR)
    hits = [pos(b, s) for b in range(BARS) if b not in BREAKDOWN for s in (4, 12)]
    de = np.mean([np.mean(dband[h:h + w] ** 2) for h in hits])
    oe = np.mean([np.mean(oband[h:h + w] ** 2) for h in hits])
    print(f"snare window (1.5-5 kHz, 60 ms after beats 2/4): drums {10 * np.log10(de / oe):+.1f} dB vs rest of mix")
    kb = circ_filt(sos_bp(40, 120, 2), buses["drums"].mean(axis=1))
    bb = circ_filt(sos_bp(40, 120, 2), (mixall - buses["drums"]).mean(axis=1))
    w = int(0.05 * SR)
    kh = [pos(b, s) for b in range(BARS) if b not in BREAKDOWN for s in (0, 4, 8, 12)
          if not (s == 12 and b in (15, 31))]
    ke = np.mean([np.mean(kb[h:h + w] ** 2) for h in kh])
    be = np.mean([np.mean(bb[h:h + w] ** 2) for h in kh])
    print(f"kick window (40-120 Hz, 50 ms after each beat): kick {10 * np.log10(ke / be):+.1f} dB vs bass/rest")
    issues = check_notes()
    print("melody note check:", "OK - all notes in scale, strong beats (pos 0/8) are chord tones"
          if not issues else "\n   " + "\n   ".join(issues))
    p1, p2 = make_pngs(x, dec_ogg)
    print(f"PNGs: {p1}\n      {p2}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-check", action="store_true")
    ap.add_argument("--lufs", type=float, default=-14.0)
    a = ap.parse_args()
    out, buses, _ = render(a.lufs)
    wav, ogg, mp3, pcm, br = write_and_encode(out)
    if not a.no_check:
        run_checks(wav, ogg, mp3, pcm, buses)


if __name__ == "__main__":
    main()
