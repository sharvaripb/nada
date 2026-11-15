// Plays a track's stems in sync with its video and changes the mix from the data.

const STEMS = {
  lightning: ['pad', 'keys', '808', 'drums', 'chimes', 'chops'],
  nightlights: ['pad', 'india', '808', 'drums', 'e_med', 'w_europe'],
};
const REGIONS = { india: 'India', e_med: 'Eastern Mediterranean', w_europe: 'Western Europe', ukraine: 'Ukraine' };
const clamp = (x, a, b) => Math.min(b, Math.max(a, x));

const MAPPINGS = {
  lightning(d, i) {
    const act = d.fields.act[i], surge = d.fields.surge[i];
    const cx = d.fields.centre_x[i], cy = d.fields.centre_y[i];
    const pan = clamp(((cx - 0.3) / 0.4) * 2 - 1, -1, 1) * 0.8;
    const rolling = surge > 0.25;
    return {
      params: { cutoff: 300 * 2 ** (act * 5), reverb: 0.12 + 0.45 * act, bloom: rolling ? Math.min(surge, 1) : 0, pan },
      label: d.dates[i],
      readouts: [
        { label: 'Lightning activity', value: act.toFixed(2),
          effect: act > 0.6 ? 'Above 0.6, so the 808 glides into the next chord'
            : act > 0.45 ? 'Above 0.45, so an extra kick lands before beat four'
            : 'The chords play softer while storms are quiet' },
        { label: 'Lightning surge', value: rolling ? '+' + Math.round(Math.min(surge, 9) * 100) + '%' : 'steady',
          effect: rolling ? 'More than 25% above the recent level, so the hi-hats roll' : 'Below the 25% threshold, so the hi-hats keep time' },
        { label: 'Storm position', value: cy < 0.45 ? 'north' : cy > 0.55 ? 'south' : 'near the equator',
          effect: cy < 0.45 ? 'Storms further north lift the voice to higher notes'
            : cy > 0.55 ? 'Storms further south bring the voice down' : 'The voice sits in its middle range' },
        { label: 'East or west', value: pan > 0.15 ? 'east' : pan < -0.15 ? 'west' : 'centre',
          effect: 'The voice follows the storms to the ' + (pan > 0.15 ? 'right' : pan < -0.15 ? 'left' : 'centre') },
      ],
    };
  },

  nightlights(d, i) {
    const f = d.fields, glow = f.glow[i], g = f.growth_vs_loss[i];
    const levels = {};
    for (const k of ['india', 'e_med', 'w_europe']) {
      levels[k] = clamp((0.25 + 0.75 * f[k + '_glow'][i]) * (1 + 0.5 * f[k + '_growth'][i]), 0, 1.3);
    }
    return {
      params: { cutoff: 400 * 2 ** (glow * 4.5), reverb: 0.2 + 0.35 * glow, bloom: 0, levels },
      label: String(d.years[i]),
      regions: Object.keys(REGIONS).map((k) => ({ name: REGIONS[k], glow: f[k + '_glow'][i] })),
      readouts: [
        { label: 'City glow', value: glow.toFixed(2), effect: 'The chords grow fuller as the world gets brighter' },
        { label: 'Light gained against lost', value: g === 0 ? 'shown later' : (g > 0 ? '+' : '') + g.toFixed(2),
          effect: g > 0.15 ? 'Above 0.15, so the chords take the brighter C9'
            : g < -0.3 ? 'Below minus 0.3, so the drums fall silent' : 'The chords stay in plain G minor' },
      ],
    };
  },
};

// a few seconds of decaying noise works as a simple room reverb
function impulse(ctx, seconds = 3.5) {
  const n = ctx.sampleRate * seconds, buf = ctx.createBuffer(2, n, ctx.sampleRate);
  for (let c = 0; c < 2; c++) {
    const ch = buf.getChannelData(c);
    for (let i = 0; i < n; i++) ch[i] = (Math.random() * 2 - 1) * (1 - i / n) ** 2.6;
  }
  return buf;
}

export class NadaEngine {
  constructor({ video, trackId, onTick, onChapter, onState }) {
    Object.assign(this, { video, trackId, onTick, onChapter, onState });
    this.playing = false;
    this.offset = 0;
    this.chapterIdx = -1;
    this.sources = [];
  }

  async load(onProgress) {
    this.data = await (await fetch(`data/${this.trackId}.json`)).json();
    this.duration = this.data.duration;

    const ctx = this.ctx = new AudioContext();
    this.master = ctx.createGain();
    this.master.connect(ctx.destination);
    this.verb = ctx.createConvolver();
    this.verb.buffer = impulse(ctx);
    this.verbOut = ctx.createGain();
    this.verb.connect(this.verbOut).connect(this.master);

    let done = 0;
    this.stems = await Promise.all(STEMS[this.trackId].map(async (name) => {
      const res = await fetch(`audio/${this.trackId}_${name}.mp3`);
      const buffer = await ctx.decodeAudioData(await res.arrayBuffer());
      onProgress(++done / STEMS[this.trackId].length);

      const gain = ctx.createGain();
      let out = gain, filter, panner;
      if (name === 'pad') { filter = ctx.createBiquadFilter(); out = out.connect(filter); }
      if (name === 'chops') { panner = ctx.createStereoPanner(); out = out.connect(panner); }
      const send = ctx.createGain();
      send.gain.value = 0.3;
      out.connect(this.master);
      out.connect(send).connect(this.verb);
      return { name, buffer, gain, filter, panner };
    }));

    this.video.muted = true;
    this.apply(0, true);
  }

  get currentTime() {
    return this.playing ? Math.min(this.offset + this.ctx.currentTime - this.startedAt, this.duration) : this.offset;
  }

  async play() {
    if (this.playing) return;
    await this.ctx.resume();
    if (this.offset >= this.duration - 0.05) this.offset = 0;
    const when = this.ctx.currentTime + 0.05;
    this.sources = this.stems.map((s) => {
      const src = this.ctx.createBufferSource();
      src.buffer = s.buffer;
      src.connect(s.gain);
      src.start(when, this.offset);
      return src;
    });
    this.startedAt = when;
    this.playing = true;
    this.video.currentTime = this.offset;
    this.video.play().catch(() => {});
    this.onState('playing');
    this.tick();
  }

  pause() {
    if (!this.playing) return;
    this.offset = this.currentTime;
    this.stop();
    this.video.pause();
    this.onState('paused');
  }

  toggle() { this.playing ? this.pause() : this.play(); }

  seek(t) {
    const was = this.playing;
    if (was) this.stop();
    this.offset = clamp(t, 0, this.duration);
    this.video.currentTime = this.offset;
    this.apply(this.offset, true);
    if (was) this.play();
  }

  stop() {
    this.sources.forEach((s) => s.stop());
    this.sources = [];
    this.playing = false;
  }

  destroy() {
    this.pause();
    this.ctx.close();
  }

  tick() {
    if (!this.playing) return;
    const t = this.currentTime;
    if (t >= this.duration - 0.02) {
      this.pause();
      this.offset = this.duration;
      return;
    }
    // the audio is the clock, the picture follows it
    if (Math.abs(this.video.currentTime - t) > 0.12) this.video.currentTime = t;
    this.apply(t);
    requestAnimationFrame(() => this.tick());
  }

  apply(t, instant = false) {
    const d = this.data;
    const i = clamp(Math.round(t * d.hz), 0, Object.values(d.fields)[0].length - 1);
    const m = MAPPINGS[this.trackId](d, i), p = m.params;
    const now = this.ctx.currentTime, tc = instant ? 0.001 : 0.15;

    for (const s of this.stems) {
      if (s.filter) s.filter.frequency.setTargetAtTime(p.cutoff, now, tc);
      if (s.panner) s.panner.pan.setTargetAtTime(p.pan, now, tc);
      if (p.levels && s.name in p.levels) s.gain.gain.setTargetAtTime(p.levels[s.name], now, tc);
    }
    this.verbOut.gain.setTargetAtTime(p.reverb + 0.35 * p.bloom, now, p.bloom ? 0.03 : 0.4);

    // fade out over the last few seconds
    const fade = clamp((this.duration - t) / (this.trackId === 'lightning' ? 9 : 7), 0, 1);
    this.master.gain.setTargetAtTime(0.9 * fade * fade, now, tc);

    let ci = 0;
    d.chapters.forEach((c, k) => { if (t >= c.t) ci = k; });
    if (ci !== this.chapterIdx) {
      this.chapterIdx = ci;
      this.onChapter(d.chapters[ci]);
    }
    this.onTick({ t, duration: this.duration, label: m.label, readouts: m.readouts, regions: m.regions });
  }
}
