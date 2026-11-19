// Boot: fonts -> script + timing -> story -> film. draw(t) renders film time t (a pure function of t).
// window.OP is the API tools/capture.mjs drives (same contract as every style of the engine pack).
import { W, H, clamp } from './core/util.js';
import { T, loadTiming } from './core/timing.js';
import { buildCaptions, drawCaption, captionList } from './core/captions.js';
import { createFilm } from './core/film.js';
import { BRAND } from './core/brand.js';

const cv = document.getElementById('cv'), ctx = cv.getContext('2d');
const OP = (window.OP = { ready: false });

(async () => {
  try {
    await document.fonts.load('900 100px Inter'); await document.fonts.load('800 100px Inter');
    const script = await (await fetch('script.json', { cache: 'no-store' })).json();
    await loadTiming();
    const story = await (await fetch('data/story.json', { cache: 'no-store' })).json();
    buildCaptions(script);
    const film = createFilm({ story, hero: BRAND.character.look, makeCanvas: (w, h) => { const c = document.createElement('canvas'); c.width = w; c.height = h; return c; } });
    const cues = film.cues();
    function draw(t) {
      t = clamp(t, 0, T.dur - 1e-4);
      ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 1; ctx.letterSpacing = '0px';
      ctx.save(); film.draw(ctx, t); ctx.restore();
      ctx.globalAlpha = 1; ctx.letterSpacing = '0px';
      const fade = Math.min(clamp(t / 0.25), clamp((T.dur - t) / 0.4));
      if (fade < 1) { ctx.fillStyle = '#000'; ctx.globalAlpha = 1 - fade; ctx.fillRect(0, 0, W, H); ctx.globalAlpha = 1; }
      drawCaption(ctx, t);
    }
    OP._shots = film.shots(); OP.script = script;
    OP.duration = () => T.dur;
    OP.draw = draw;
    OP.frame = (t, q = 0.92) => { draw(t); return cv.toDataURL('image/jpeg', q); };
    OP.shots = () => film.shots();
    OP.captions = () => captionList().map((c) => ({ s: +c.s.toFixed(3), e: +c.e.toFixed(3), text: c.words.map((w) => w.txt).join(' ') }));
    OP.cues = () => cues.slice();
    OP.ready = true;
    const q = new URLSearchParams(location.search);
    if (!q.has('capture')) {
      if (q.has('t')) draw(+q.get('t'));
      else {
        const audio = new Audio('data/mix.wav'); let t0 = null; const btn = document.getElementById('play'); btn.hidden = false;
        btn.onclick = () => { btn.hidden = true; t0 = performance.now(); audio.currentTime = 0; audio.play().catch(() => {}); };
        const loop = (now) => { const t = t0 == null ? 0 : (now - t0) / 1000; draw(t); if (t0 != null && t > T.dur) { t0 = null; btn.hidden = false; } requestAnimationFrame(loop); };
        requestAnimationFrame(loop);
      }
    }
  } catch (e) { OP.bootError = String(e && e.stack || e); console.error(e); }
})();
