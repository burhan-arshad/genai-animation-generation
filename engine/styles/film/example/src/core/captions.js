// Captions: ONE word at a time (short words ride along with the next: "a single", "the whole"), white heavy sans with a dark outline
// and a soft shadow, low on the screen so faces and hands stay free. A script line may set "caps": "He bet | his life | savings".
import { clamp, lerp, seg, eob } from './util.js';
import { T, lineWords } from './timing.js';

export const CAP = { y: 1590, size: 86, maxW: 940 };
let caps = [];
const SHORT = /^(a|an|the|to|of|in|on|at|by|and|but|or|so|is|it|he|she|we|i|his|her|my|no|up|for|was)$/i;

function autoChunks(ws) {
  const out = [];
  for (let i = 0; i < ws.length; i++) {
    const w = ws[i], n = ws[i + 1], bare = w.replace(/[^A-Za-z']/g, '');
    if (n && SHORT.test(bare) && !/[,.!?;:]$/.test(w) && (w + n).length <= 11) { out.push([i, i + 1]); i++; } else out.push([i, i]);
  }
  return out;
}

export function buildCaptions(script) {
  caps = [];
  script.lines.forEach((ln, i) => {
    const ws = lineWords(i); if (!ws.length) return;
    const textWords = ln.text.split(/\s+/).filter(Boolean);
    const spoken = ws.length === textWords.length ? textWords : ws.map((w) => w.w);
    if (ln.caps) {
      const nm = (w) => String(w).toLowerCase().replace(/[^a-z0-9']+/g, '');
      let from = 0;
      ln.caps.split('|').map((c) => c.trim()).filter(Boolean).forEach((c, j) => {
        const first = nm(c.split(/\s+/)[0]);
        let idx = j === 0 ? 0 : ws.findIndex((w, k) => k > from && nm(w.w) === first);
        if (idx < 0) idx = Math.min(ws.length - 1, from + 1);
        from = idx; caps.push({ line: i, s: ws[idx].s - 0.03, text: c.replace(/\*/g, '') });
      });
    } else autoChunks(spoken).forEach(([a, b]) => caps.push({ line: i, s: ws[a].s - 0.03, text: spoken.slice(a, b + 1).join(' ') }));
  });
  caps.forEach((c, k) => { const next = caps[k + 1], lineEnd = T.lines[c.line].end; c.e = next ? (next.s - lineEnd > 0.6 && next.line !== c.line ? lineEnd + 0.25 : next.s) : T.dur; });
  return caps;
}
export const captionList = () => caps.map((c) => ({ ...c, words: [{ txt: c.text }] }));

export function captionText(g, text, x = 540, y = CAP.y, sc = 1) {
  const size = CAP.size;
  g.save(); g.font = `900 ${size}px Inter, sans-serif`; g.letterSpacing = '0px';
  const fit = Math.min(1, CAP.maxW / g.measureText(text).width);
  g.translate(x, y); g.scale(sc * fit, sc * fit); g.textAlign = 'center'; g.textBaseline = 'middle'; g.lineJoin = 'round';
  g.fillStyle = 'rgba(0,0,0,0.45)'; g.fillText(text, 3, 9);
  g.lineWidth = 15; g.strokeStyle = '#0B0B10'; g.strokeText(text, 0, 0);
  g.fillStyle = '#FFFFFF'; g.fillText(text, 0, 0);
  g.restore();
}
export function drawCaption(g, t) {
  const c = caps.find((c) => t >= c.s && t < c.e); if (!c) return;
  const lt = t - c.s; captionText(g, c.text, 540, CAP.y, lt < 0.1 ? lerp(0.86, 1, eob(seg(lt, 0, 0.1))) : 1);
}
