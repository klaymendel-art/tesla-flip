/* Tesla Flip — audio manager (WebAudio).
 *
 * - Loads every sound in SOUND_FILES, trying .ogg first where supported, else .mp3,
 *   and falling back to the other extension on a 404. Missing files fail soft:
 *   the game runs silently and a single console.warn names the file.
 * - Unlocks the AudioContext on the first user gesture (iOS requirement).
 * - Music and the motor hum loop via AudioBufferSourceNode.loop (gapless; HTMLAudio
 *   loops have audible gaps).
 * - One-shot SFX play through a small round-robin pool of pre-created gain "voices"
 *   (buffer source nodes are single-use by spec, so the pool holds the gain stages).
 * - Mute is a master gain of 0 (loops stay in sync) and is persisted in localStorage.
 *
 * Exposes a single global: `Snd`.
 */
'use strict';

const SOUND_FILES = {
  roll:  'assets/sfx/roll',     // seamless loop while riding
  pop:   'assets/sfx/pop',
  flip:  'assets/sfx/flip',
  land:  'assets/sfx/land',
  combo: 'assets/sfx/combo',
  score: 'assets/sfx/score',
  crash: 'assets/sfx/crash',
  theme: 'assets/music/theme',  // seamless music loop
};

const Snd = {
  KEY_MUTE: 'teslaflip.muted',
  VOL: { music: 0.6, sfx: 0.9, roll: 0.8 },  // roll is mastered quiet (-14 dBFS)
  VOICES: 8,

  ctx: null, master: null, musicBus: null, sfxBus: null,
  voices: [], voiceIdx: 0,
  buffers: {},       // name → AudioBuffer (absent/undefined when missing)
  loops: {},         // name → running AudioBufferSourceNode
  exts: ['.mp3', '.ogg'],
  unlocked: false,
  muted: false,

  init() {
    try { this.muted = localStorage.getItem(this.KEY_MUTE) === '1'; } catch (e) { /* storage blocked */ }
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    try { this.ctx = new AC(); } catch (e) { this.ctx = null; return; }

    const probe = document.createElement('audio');
    if (probe.canPlayType && probe.canPlayType('audio/ogg; codecs="vorbis"')) this.exts = ['.ogg', '.mp3'];

    this.master = this.ctx.createGain();
    this.master.gain.value = this.muted ? 0 : 1;
    this.master.connect(this.ctx.destination);
    this.musicBus = this._gain(this.VOL.music, this.master);
    this.sfxBus = this._gain(this.VOL.sfx, this.master);
    for (let i = 0; i < this.VOICES; i++) this.voices.push(this._gain(1, this.sfxBus));

    for (const name of Object.keys(SOUND_FILES)) this._load(name);
  },

  _gain(value, dest) {
    const g = this.ctx.createGain();
    g.gain.value = value;
    g.connect(dest);
    return g;
  },

  async _load(name) {
    let data = null;
    for (const ext of this.exts) {
      try {
        const res = await fetch(SOUND_FILES[name] + ext);
        if (!res.ok) continue;
        data = await res.arrayBuffer();
        break;
      } catch (e) { /* offline, file:// or CORS — try the next extension */ }
    }
    if (!data) { console.warn('[TeslaFlip] audio missing (running silently): ' + SOUND_FILES[name]); return; }
    try {
      // Callback form works on both old Safari (no promise) and modern browsers.
      this.buffers[name] = await new Promise((res, rej) => this.ctx.decodeAudioData(data, res, rej));
    } catch (e) {
      console.warn('[TeslaFlip] audio decode failed: ' + SOUND_FILES[name]);
      return;
    }
    // Loop files that finished decoding after the first gesture start right away.
    if (this.unlocked && (name === 'theme' || name === 'roll')) this._startLoop(name);
  },

  /** Call synchronously inside the first pointer/key handler. */
  unlock() {
    if (!this.ctx || this.unlocked) return;
    this.unlocked = true;
    if (this.ctx.state !== 'running') this.ctx.resume().catch(() => {});
    this._startLoop('theme');
    this._startLoop('roll');
  },

  _startLoop(name) {
    if (!this.buffers[name] || this.loops[name]) return;
    const src = this.ctx.createBufferSource();
    src.buffer = this.buffers[name];
    src.loop = true;
    const g = this._gain(name === 'roll' ? this.VOL.roll : 1, name === 'theme' ? this.musicBus : this.sfxBus);
    src.connect(g);
    src.start();
    this.loops[name] = src;
  },

  /** One-shot SFX. rate = playbackRate, delay in seconds. No-op if the file is missing. */
  play(name, rate = 1, delay = 0) {
    const buf = this.buffers[name];
    if (!buf || !this.unlocked || this.muted) return;
    const src = this.ctx.createBufferSource();
    src.buffer = buf;
    src.playbackRate.value = rate;
    src.connect(this.voices[this.voiceIdx]);
    this.voiceIdx = (this.voiceIdx + 1) % this.VOICES;
    src.start(this.ctx.currentTime + delay);
  },

  toggleMute() {
    this.muted = !this.muted;
    try { localStorage.setItem(this.KEY_MUTE, this.muted ? '1' : '0'); } catch (e) { /* ignore */ }
    if (this.master) this.master.gain.setTargetAtTime(this.muted ? 0 : 1, this.ctx.currentTime, 0.02);
  },

  /** Tab hidden / shown. */
  setSuspended(hidden) {
    if (!this.ctx || !this.unlocked) return;
    if (hidden) this.ctx.suspend().catch(() => {});
    else this.ctx.resume().catch(() => {});
  },
};
