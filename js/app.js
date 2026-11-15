import { NadaEngine } from './engine.js';

// hero: the earth turns as you scroll
const FRAMES = 90;
const globe = document.getElementById('globe');
const hero = document.querySelector('.hero');
const frame = (i) => `globe/g${String(i).padStart(3, '0')}.jpg`;
for (let i = 1; i <= FRAMES; i++) new Image().src = frame(i);

window.addEventListener('scroll', () => {
  const span = hero.offsetHeight - window.innerHeight;
  const p = clamp(-hero.getBoundingClientRect().top / span, 0, 1);
  globe.src = frame(1 + Math.round(p * (FRAMES - 1)));
}, { passive: true });

// player
const TRACKS = {
  lightning: { title: 'lightning', video: 'video/lightning.mp4' },
  nightlights: { title: 'night lights', video: 'video/nightlights.mp4' },
};
const $ = (id) => document.getElementById(id);
const dialog = $('player'), video = $('pvideo'), seek = $('p-seek'), caption = $('p-caption');
const PLAY = '<path d="M8 5v14l11-7z" fill="currentColor"/>';
const PAUSE = '<rect x="6" y="5" width="4" height="14" rx="1" fill="currentColor"/><rect x="14" y="5" width="4" height="14" rx="1" fill="currentColor"/>';
let engine = null, dragging = false, describe = true, opener = null;

function clamp(x, a, b) { return Math.min(b, Math.max(a, x)); }
const mmss = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`;

function dateLabel(s) {
  if (s === 'intro') return 'orbit';
  if (s.startsWith('2017-03-01 ')) return '1 March 2017';
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) {
    return new Date(s).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
  }
  return s;
}

function show(info) {
  if (!dragging) seek.value = Math.round((info.t / info.duration) * 1000);
  $('p-time').textContent = `${mmss(info.t)} of ${mmss(info.duration)}`;
  $('p-label').textContent = dateLabel(info.label);
  $('p-list').innerHTML = info.readouts.map((r) =>
    `<dt>${r.label}</dt><dd>${r.value}</dd><dd class="eff">${r.effect}</dd>`).join('');
  $('p-regions').hidden = !info.regions;
  if (info.regions) {
    $('p-regions').innerHTML = info.regions.map((g) =>
      `<div class="p-region"><span>${g.name}</span><span class="p-bar"><i style="width:${Math.round(g.glow * 100)}%"></i></span></div>`).join('');
  }
}

function chapterText(c) { return describe && c ? `${c.name}. ${c.describe}` : ''; }

async function open(id) {
  opener = document.activeElement;
  $('player-title').textContent = TRACKS[id].title;
  $('p-list').innerHTML = '';
  caption.textContent = '';
  $('p-loading').hidden = false;
  video.src = TRACKS[id].video;
  dialog.showModal();
  $('p-close').focus();

  engine = new NadaEngine({
    video, trackId: id,
    onTick: show,
    onChapter: (c) => { caption.textContent = chapterText(c); },
    onState: (s) => {
      $('p-icon').innerHTML = s === 'playing' ? PAUSE : PLAY;
      $('p-play').setAttribute('aria-label', s === 'playing' ? 'Pause' : 'Play');
    },
  });
  await engine.load((p) => { $('p-pct').textContent = Math.round(p * 100) + '%'; });
  $('p-loading').hidden = true;
  $('p-chapters').innerHTML = engine.data.chapters.map((c) =>
    `<span style="left:${(c.t / engine.duration) * 100}%">${c.name}</span>`).join('');
  engine.play();
}

function close() {
  engine?.destroy();
  engine = null;
  video.pause();
  video.removeAttribute('src');
  dialog.close();
  opener?.focus();
}

document.querySelectorAll('.track-open').forEach((b) => b.addEventListener('click', () => open(b.dataset.track)));
$('p-close').addEventListener('click', close);
dialog.addEventListener('cancel', (e) => { e.preventDefault(); close(); });
$('p-play').addEventListener('click', () => engine?.toggle());
$('p-describe').addEventListener('click', () => {
  describe = !describe;
  $('p-describe').setAttribute('aria-pressed', describe);
  caption.textContent = engine ? chapterText(engine.data.chapters[engine.chapterIdx]) : '';
});
seek.addEventListener('input', () => { dragging = true; });
seek.addEventListener('change', () => {
  engine?.seek((seek.value / 1000) * engine.duration);
  dragging = false;
});
dialog.addEventListener('keydown', (e) => {
  if (!engine || e.target === seek) return;
  if (e.code === 'Space' && e.target.tagName !== 'BUTTON') { e.preventDefault(); engine.toggle(); }
  if (e.key === 'ArrowRight') engine.seek(engine.currentTime + 5);
  if (e.key === 'ArrowLeft') engine.seek(engine.currentTime - 5);
});
