// Sets: layered, parallax backdrops drawn in world coordinates (the world is 2400 px wide, 1920 px tall; the camera starts at x 1200, y 960).
// makeSet(def) -> { kind, groundY, layers: [{ p, front, draw(g, t) }], light }. p = parallax: 0 never moves, 1 moves with the actors.
import { TAU, clamp, lerp, shade, mix, alpha, rnd, circ, ell, poly, rr, vgrad } from './util.js';
import { drawProp } from './props.js';

export const WW = 2400, WH = 1920;
export const KINDS = ['field', 'street', 'room', 'study', 'city', 'sea', 'desert', 'mountain', 'map', 'card'];
export const TIMES = ['day', 'dusk', 'night', 'dawn', 'sepia', 'storm'];

const PAL = {
  day:   { top: '#6FB8E8', bot: '#D4EEF9', sun: '#FFF1B8', far: '#A9CFB0', mid: '#7DBB86', near: '#5FA36A', grass: '#6BB36F', dirt: '#C99A63', wall: '#EAD9B8', light: null },
  dawn:  { top: '#7A9AD0', bot: '#FFD9A8', sun: '#FFE9A8', far: '#B5B5C8', mid: '#8FAF9A', near: '#6E9C7C', grass: '#7FAE78', dirt: '#C99A7A', wall: '#EAD0B0', light: 'rgba(255,190,130,0.10)' },
  dusk:  { top: '#4A3A7A', bot: '#F29A6B', sun: '#FFC27A', far: '#7A5A8C', mid: '#5A4A7E', near: '#44406E', grass: '#4E7A5E', dirt: '#8A5E5A', wall: '#C9A890', light: 'rgba(255,140,70,0.16)' },
  night: { top: '#0C1230', bot: '#27386A', sun: '#F4EAD0', far: '#1F2D56', mid: '#18244C', near: '#121C3C', grass: '#1F3A4C', dirt: '#2B3358', wall: '#3A4468', light: 'rgba(20,30,90,0.34)' },
  sepia: { top: '#C9A877', bot: '#EAD7B0', sun: '#F8EBC8', far: '#B89868', mid: '#9A7C4E', near: '#7B6038', grass: '#9A8650', dirt: '#B8956A', wall: '#E2CCA0', light: 'rgba(150,110,60,0.16)' },
  storm: { top: '#363F54', bot: '#7A8AA0', sun: '#B9C2D0', far: '#5C6C7C', mid: '#4A5C64', near: '#3E5058', grass: '#4A6A5A', dirt: '#6A5A52', wall: '#8A8A90', light: 'rgba(30,40,60,0.26)' },
};
export const palette = (time) => PAL[time] || PAL.day;

function skyLayer(pal, groundY, time, o = {}) {
  return { p: 0, draw(g, t) {
    vgrad(g, -1400, -1400, WW + 2800, groundY + 1500, [[0, pal.top], [1, pal.bot]]);
    if (time === 'night') { for (let i = 0; i < 70; i++) { const x = rnd(i) * WW, y = rnd(i + 99) * (groundY - 300); circ(g, x, y, 1.5 + rnd(i + 7) * 2, `rgba(255,255,255,${0.35 + 0.4 * Math.abs(Math.sin(t * 1.5 + i))})`); } }
    if (o.sun !== false) { const sx = o.sunX ?? 1500, sy = time === 'dusk' || time === 'dawn' ? groundY - 380 : groundY - 900; const gr = g.createRadialGradient(sx, sy, 20, sx, sy, 380); gr.addColorStop(0, alpha(pal.sun, 0.55)); gr.addColorStop(1, alpha(pal.sun, 0)); g.fillStyle = gr; g.fillRect(sx - 400, sy - 400, 800, 800); if (time === 'night') { g.save(); g.beginPath(); g.arc(sx, sy, 64, 0, TAU); g.clip(); g.beginPath(); g.arc(sx, sy, 70, 0, TAU); g.arc(sx + 26, sy - 12, 56, 0, TAU); g.fillStyle = pal.sun; g.fill('evenodd'); g.restore(); } else circ(g, sx, sy, 90, pal.sun); }
  } };
}
function cloudLayer(pal, groundY, time) {
  if (time === 'night') return null;
  return { p: 0.12, draw(g, t) { const col = time === 'storm' ? 'rgba(70,80,96,0.85)' : time === 'dusk' ? 'rgba(255,200,170,0.75)' : 'rgba(255,255,255,0.85)';
    for (let i = 0; i < 7; i++) { const x = ((rnd(i) * 3200 + t * (8 + i * 2)) % 3600) - 600, y = 180 + rnd(i + 4) * (groundY - 900) * 0.7, s = 0.7 + rnd(i + 9) * 0.9; g.fillStyle = col; [[0, 0, 60], [64, 12, 50], [-64, 16, 46], [20, 26, 54]].forEach(([dx, dy, r]) => { g.beginPath(); g.arc(x + dx * s, y + dy * s, r * s, 0, TAU); g.fill(); }); } } };
}
function hillLayer(p, y0, amp, freq, seed, col, trees) {
  return { p, draw(g, t) { const pts = []; for (let x = -900; x <= WW + 900; x += 30) pts.push([x, y0 + Math.sin(x * freq + seed) * amp + Math.sin(x * freq * 2.3 + seed * 2) * amp * 0.4]);
    g.beginPath(); pts.forEach(([x, y], i) => (i ? g.lineTo(x, y) : g.moveTo(x, y))); g.lineTo(WW + 900, 2600); g.lineTo(-900, 2600); g.closePath(); g.fillStyle = col; g.fill();
    if (trees) for (let i = 0; i < 26; i++) { const x = -600 + i * 150 + rnd(i + seed) * 60, y = y0 + Math.sin(x * freq + seed) * amp + Math.sin(x * freq * 2.3 + seed * 2) * amp * 0.4 + 6, s = 26 + rnd(i) * 22; circ(g, x, y - s * 1.4, s, shade(col, 0.82)); rr(g, x - 3, y - s * 0.6, 6, s * 0.7, 2); g.fillStyle = shade(col, 0.6); g.fill(); } } };
}
function groundLayer(pal, groundY, kind = 'grass') {
  return { p: 1, draw(g, t) {
    if (kind === 'grass') { vgrad(g, -900, groundY - 120, WW + 1800, 700, [[0, pal.grass], [1, shade(pal.grass, 0.8)]]); g.fillStyle = shade(pal.grass, 0.8); g.fillRect(-900, groundY + 580, WW + 1800, 2400); for (let i = 0; i < 90; i++) { const x = rnd(i) * (WW + 600) - 300, y = groundY - 110 + rnd(i + 50) * 520; g.strokeStyle = shade(pal.grass, i % 2 ? 1.18 : 0.78); g.lineWidth = 4; g.beginPath(); g.moveTo(x, y); g.lineTo(x - 6, y - 16); g.moveTo(x, y); g.lineTo(x + 7, y - 14); g.stroke(); }
      g.beginPath(); g.moveTo(-900, groundY - 120); for (let x = -900; x <= WW + 900; x += 40) g.lineTo(x, groundY - 120 - Math.sin(x * 0.01) * 6); g.lineTo(WW + 900, groundY - 150); g.lineTo(-900, groundY - 150); g.closePath(); g.fillStyle = shade(pal.grass, 1.12); g.fill(); }
    else if (kind === 'dirt') { g.fillStyle = pal.dirt; g.fillRect(-900, groundY - 140, WW + 1800, 2400); g.fillStyle = shade(pal.dirt, 0.9); g.fillRect(-900, groundY + 100, WW + 1800, 2400); for (let i = 0; i < 60; i++) { const x = rnd(i) * (WW + 600) - 300, y = groundY - 120 + rnd(i + 30) * 500; ell(g, x, y, 30 + rnd(i + 3) * 40, 6, shade(pal.dirt, 0.82)); } }
    else if (kind === 'wood') { g.fillStyle = shade(pal.wall, 0.6); g.fillRect(-900, groundY - 130, WW + 1800, 2400); g.fillStyle = shade(pal.wall, 0.42); g.fillRect(-900, groundY - 140, WW + 1800, 26); for (let y = groundY - 100, k = 0; y < 2100; y += 64 + k * 8, k++) { g.fillStyle = k % 2 ? shade(pal.wall, 0.55) : shade(pal.wall, 0.64); g.fillRect(-900, y, WW + 1800, 60 + k * 8); for (let x = -900 + ((k * 211) % 300); x < WW + 900; x += 360 + k * 30) { g.fillStyle = shade(pal.wall, 0.44); g.fillRect(x, y, 4, 60 + k * 8); } } }
    else if (kind === 'stone') { g.fillStyle = shade(pal.dirt, 0.8); g.fillRect(-900, groundY - 120, WW + 1800, 2400); for (let y = groundY - 120, k = 0; y < 2100; y += 70 + k * 6, k++) for (let x = -900 + (k % 2) * 60; x < WW + 900; x += 130 + k * 8) { rr(g, x + 3, y + 3, 124 + k * 8, 64 + k * 6, 10); g.fillStyle = shade(pal.dirt, 0.7 + ((x * 7 + y * 3) % 5) * 0.04); g.fill(); } }
    else if (kind === 'sand') { g.fillStyle = '#E8C98A'; g.fillRect(-900, groundY - 120, WW + 1800, 2400); g.fillStyle = '#D9B773'; g.fillRect(-900, groundY + 140, WW + 1800, 2400); }
  } };
}
function dressLayer(def, groundY) {
  const items = def.dress || [];
  if (!items.length) return null;
  return { p: 1, draw(g, t) { items.slice().sort((a, b) => (a.d ?? 1) - (b.d ?? 1)).forEach((it) => { const d = it.d ?? 0; g.save(); g.translate(600 + (it.x ?? 50) * 12, groundY + (d - 1) * 70 - 6); const s = (it.s || 1) * (0.78 + d * 0.22); g.scale(s, s); drawProp(g, it.item, { c: it.c, text: it.text, t }); g.restore(); }); } };
}

function skyline(p, base, col, seed, windows, lit, smoke) {
  return { p, draw(g, t) { let x = -700; let i = 0; while (x < WW + 700) { const w = 110 + rnd(seed + i) * 130, h = 200 + rnd(seed + i + 40) * 420; rr(g, x, base - h, w, h + 400, 3); g.fillStyle = col; g.fill();
    if (rnd(seed + i + 7) > 0.6) poly(g, [[x - 6, base - h], [x + w / 2, base - h - 60], [x + w + 6, base - h]], shade(col, 0.88));
    if (windows) for (let wy = base - h + 30; wy < base - 20; wy += 46) for (let wx = x + 16; wx < x + w - 24; wx += 34) { g.fillStyle = lit && rnd(wx + wy + seed) > 0.45 ? '#FFE9A8' : shade(col, 0.82); g.fillRect(wx, wy, 16, 22); }
    if (smoke && rnd(seed + i + 3) > 0.72) { rr(g, x + w * 0.3, base - h - 90, 28, 90, 3); g.fillStyle = shade(col, 0.8); g.fill(); for (let k = 0; k < 5; k++) { const u = ((t * 0.25 + k / 5) % 1); circ(g, x + w * 0.3 + 14 + u * 40, base - h - 90 - u * 260, 22 + u * 46, `rgba(120,120,140,${(1 - u) * 0.4})`); } }
    x += w + 6 + rnd(seed + i + 90) * 20; i++; } } };
}
function buildings(pal, groundY, def) {
  const cols = ['#C9A878', '#B5776A', '#7FA08C', '#C98E5A', '#8C9AB8', '#D8C090', '#A8856A'];
  return { p: 0.92, draw(g, t) { let x = -300, i = 0; const base = groundY - 120;
    while (x < WW + 300) { const w = 300 + rnd(i) * 130, h = 380 + rnd(i + 11) * 200, c = shade(cols[i % cols.length], pal === PAL.night ? 0.45 : pal === PAL.dusk ? 0.8 : 1); const shop = i === (def.signIndex ?? 2);
      rr(g, x, base - h, w, h, 4); g.fillStyle = c; g.fill(); g.fillStyle = 'rgba(0,0,0,0.12)'; g.fillRect(x + w - 26, base - h, 26, h);
      rr(g, x - 8, base - h - 26, w + 16, 30, 3); g.fillStyle = shade(c, 0.78); g.fill();
      for (let r = 0; r < 2; r++) for (let k = 0; k < 3; k++) { const wx = x + 36 + k * (w - 90) / 2.2, wy = base - h + 50 + r * 130; rr(g, wx, wy, 52, 80, 4); g.fillStyle = pal === PAL.night || pal === PAL.dusk ? '#FFE0A0' : '#9CC8DC'; g.fill(); g.strokeStyle = shade(c, 0.6); g.lineWidth = 5; g.stroke(); }
      rr(g, x + w / 2 - 36, base - 190, 72, 190, 4); g.fillStyle = shade(c, 0.55); g.fill();
      if (shop) { g.save(); g.translate(x + w / 2, base - 214); drawProp(g, 'sign', { text: def.sign || 'SHOP', c: '#F4EAD0' }); g.restore(); }
      for (let k = 0; k < 6; k++) poly(g, [[x + k * (w / 6), base - 190], [x + (k + 1) * (w / 6), base - 190], [x + (k + 1) * (w / 6) - 5, base - 150], [x + k * (w / 6) + 5, base - 150]], k % 2 ? '#F4F1E8' : '#C8283A');
      x += w + 10; i++; } } };
}

function roomLayers(pal, groundY, def) {
  const floorY = groundY - 130, wallC = pal.wall;
  const wall = { p: 0.94, draw(g, t) {
    g.fillStyle = wallC; g.fillRect(-900, -900, WW + 1800, floorY + 2600);
    for (let x = -800; x < WW + 800; x += 90) for (let y = -60; y < floorY - 300; y += 110) { circ(g, x + ((y / 110) % 2) * 45, y, 6, shade(wallC, 0.9)); }
    g.fillStyle = shade(wallC, 0.78); g.fillRect(-900, floorY - 300, WW + 1800, 300); g.fillStyle = shade(wallC, 0.6); g.fillRect(-900, floorY - 306, WW + 1800, 10);
    // window with a view
    const wx = 380, wy = 360; rr(g, wx - 14, wy - 14, 388, 548, 8); g.fillStyle = shade(wallC, 0.5); g.fill(); vgrad(g, wx, wy, 360, 520, [[0, pal.top], [1, pal.bot]]); g.fillStyle = pal.far; g.fillRect(wx, wy + 380, 360, 140); g.fillStyle = shade(wallC, 0.5); g.fillRect(wx + 172, wy, 16, 520); g.fillRect(wx, wy + 250, 360, 16);
    // pictures
    [[1250, 420, 220, 280], [1560, 520, 160, 200]].forEach(([x, y, w, h], i) => { rr(g, x - 10, y - 10, w + 20, h + 20, 6); g.fillStyle = WOOD(); g.fill(); g.fillStyle = i ? pal.far : '#C9B58A'; g.fillRect(x, y, w, h); circ(g, x + w * 0.35, y + h * 0.4, w * 0.2, i ? '#F4C542' : '#8C5A3A'); });
    // hanging lamp
    g.strokeStyle = '#3A3F55'; g.lineWidth = 6; g.beginPath(); g.moveTo(1200, -100); g.lineTo(1200, 160); g.stroke(); poly(g, [[1140, 230], [1260, 230], [1230, 160], [1170, 160]], '#3A3F55'); circ(g, 1200, 236, 22, '#FFE9A8');
    const gr = g.createRadialGradient(1200, 240, 10, 1200, 240, 620); gr.addColorStop(0, 'rgba(255,225,150,0.35)'); gr.addColorStop(1, 'rgba(255,225,150,0)'); g.fillStyle = gr; g.fillRect(500, -300, 1400, 1400);
  } };
  const floor = groundLayer(pal, groundY, 'wood');
  return [wall, floor];
}
const WOOD = () => '#6B4526';

function studyLayers(pal, groundY, def) {
  const floorY = groundY - 130, wall = pal.wall;
  const back = { p: 0.94, draw(g, t) {
    g.fillStyle = shade('#3A2A55', 1); vgrad(g, -900, -900, WW + 1800, floorY + 900, [[0, '#2A2748'], [1, '#3B3466']]); g.fillStyle = '#3B3466'; g.fillRect(-900, floorY, WW + 1800, 2600);
    for (let x = -800; x < WW + 800; x += 120) for (let y = -60; y < floorY; y += 120) { g.fillStyle = 'rgba(255,255,255,0.035)'; g.beginPath(); g.arc(x + ((y / 120) % 2) * 60, y, 8, 0, TAU); g.fill(); }
    g.fillStyle = '#241F3E'; g.fillRect(-900, floorY - 120, WW + 1800, 2600);
    [260, 2140].forEach((x) => { g.save(); g.translate(x, floorY); g.scale(1.25, 1.25); drawProp(g, 'bookshelf', {}); g.restore(); });
    // the story panel (the film draws the story's key picture here)
    rr(g, 1200 - 330, 440, 660, 520, 16); g.fillStyle = '#F4EAD0'; g.fill(); g.strokeStyle = '#C98B2E'; g.lineWidth = 14; g.stroke();
    const gr = g.createRadialGradient(1200, 640, 10, 1200, 640, 900); gr.addColorStop(0, 'rgba(255,225,150,0.28)'); gr.addColorStop(1, 'rgba(255,225,150,0)'); g.fillStyle = gr; g.fillRect(0, -200, WW, 1500);
  } };
  const floor = { p: 1, draw(g, t) { g.fillStyle = '#4A3322'; g.fillRect(-900, groundY - 120, WW + 1800, 2400); for (let y = groundY - 120, k = 0; y < 2100; y += 64 + k * 8, k++) { g.fillStyle = k % 2 ? '#3E2A1C' : '#553A28'; g.fillRect(-900, y, WW + 1800, 60 + k * 8); } rr(g, 600, groundY - 40, 1200, 220, 20); g.fillStyle = '#8C2F3A'; g.fill(); rr(g, 640, groundY - 20, 1120, 180, 14); g.strokeStyle = '#F4C542'; g.lineWidth = 5; g.stroke(); } };
  return [back, floor];
}

function seaLayers(pal, groundY, def) {
  const yH = groundY - 420;
  const water = { p: 0.3, draw(g, t) { vgrad(g, -900, yH, WW + 1800, 2200, [[0, shade('#3F7FC4', pal === PAL.night ? 0.35 : pal === PAL.dusk ? 0.7 : 1)], [1, shade('#1F4E8C', pal === PAL.night ? 0.35 : 0.9)]]);
    for (let i = 0; i < 22; i++) { const y = yH + 20 + i * i * 2.4, a = 0.1 + i * 0.01; g.beginPath(); for (let x = -900; x <= WW + 900; x += 30) g.lineTo(x, y + Math.sin(x * 0.012 + t * (0.8 + i * 0.05) + i) * (4 + i * 0.6)); g.strokeStyle = `rgba(255,255,255,${a})`; g.lineWidth = 2 + i * 0.1; g.stroke(); } } };
  const front = { p: 1.15, front: true, draw(g, t) { g.beginPath(); g.moveTo(-900, 2300); for (let x = -900; x <= WW + 900; x += 30) g.lineTo(x, groundY + 330 + Math.sin(x * 0.006 + t * 1.6) * 26); g.lineTo(WW + 900, 2300); g.closePath(); g.fillStyle = 'rgba(31,78,140,0.88)'; g.fill(); } };
  const deck = def.deck ? { p: 1, draw(g, t) { g.fillStyle = '#8C5A3A'; g.fillRect(-900, groundY - 120, WW + 1800, 2400); for (let y = groundY - 120, k = 0; y < 2100; y += 70, k++) { g.fillStyle = k % 2 ? '#7A4C30' : '#9A6642'; g.fillRect(-900, y, WW + 1800, 66); } g.fillStyle = '#6B4526'; g.fillRect(-900, groundY - 330, WW + 1800, 22); for (let x = -900; x < WW + 900; x += 160) g.fillRect(x, groundY - 330, 16, 220); } } : null;
  return { water, front, deck };
}

function mapLayer(def) {
  return { p: 0, draw(g, t) {
    vgrad(g, -100, -100, WW, WH + 200, [[0, '#E9D6A8'], [1, '#D2B987']]);
    for (let i = 0; i < 30; i++) ell(g, rnd(i) * 1080, rnd(i + 20) * 1920, 40 + rnd(i + 9) * 90, 30 + rnd(i + 3) * 60, 'rgba(150,110,60,0.07)');
    // seas and land
    g.fillStyle = 'rgba(111,160,196,0.45)'; g.fillRect(-100, -100, 1300, 2200);
    const land = [[620, 560, 330], [380, 1140, 250], [760, 1380, 300]];
    land.forEach(([x, y, r], i) => { g.beginPath(); for (let a = 0; a <= TAU + 0.1; a += 0.2) g.lineTo(x + Math.cos(a) * (r + Math.sin(a * 3 + i) * 50), y + Math.sin(a) * (r * 0.7 + Math.cos(a * 4 + i) * 36)); g.closePath(); g.fillStyle = '#C8B07A'; g.fill(); g.strokeStyle = '#8C6B3A'; g.lineWidth = 6; g.stroke(); });
    for (let y = 80; y < 1900; y += 60) { g.strokeStyle = 'rgba(63,127,196,0.35)'; g.lineWidth = 2; g.beginPath(); g.moveTo(40, y); g.quadraticCurveTo(80, y - 10, 120, y); g.stroke(); }
    // compass
    g.save(); g.translate(880, 1620); circ(g, 0, 0, 90, 'rgba(255,255,255,0.35)'); poly(g, [[0, -86], [16, 0], [0, 86], [-16, 0]], '#8C2F3A'); poly(g, [[-86, 0], [0, -16], [86, 0], [0, 16]], '#2F4E8F'); g.fillStyle = '#2B1A10'; g.font = '900 30px Inter, sans-serif'; g.textAlign = 'center'; g.fillText('N', 0, -100); g.restore();
    // route
    const route = def.route || [], dur = def.routeDur || 5;
    if (route.length > 1) { const prog = clamp((t % (dur + 1.5)) / dur); const pts = route.map(([x, y]) => [x / 100 * 1080, y / 100 * 1920]); let total = 0; const L = []; for (let i = 1; i < pts.length; i++) { const d = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); L.push(d); total += d; }
      let left = prog * total; g.beginPath(); g.moveTo(...pts[0]); let end = pts[0]; for (let i = 1; i < pts.length && left > 0; i++) { const f = Math.min(1, left / L[i - 1]); end = [lerp(pts[i - 1][0], pts[i][0], f), lerp(pts[i - 1][1], pts[i][1], f)]; g.lineTo(...end); left -= L[i - 1]; }
      g.setLineDash([26, 18]); g.strokeStyle = '#C8283A'; g.lineWidth = 12; g.lineCap = 'round'; g.stroke(); g.setLineDash([]); circ(g, end[0], end[1], 20, '#C8283A'); circ(g, end[0], end[1], 8, '#F4EAD0'); }
    (def.pins || []).forEach((p) => { const x = p.x / 100 * 1080, y = p.y / 100 * 1920; circ(g, x, y, 16, '#2F4E8F'); circ(g, x, y, 6, '#F4EAD0'); g.fillStyle = '#2B1A10'; g.font = '900 40px Inter, sans-serif'; g.textAlign = 'left'; g.fillText(p.label || '', x + 28, y + 12); });
    const gr = g.createRadialGradient(540, 960, 500, 540, 960, 1250); gr.addColorStop(0, 'rgba(90,50,10,0)'); gr.addColorStop(1, 'rgba(90,50,10,0.45)'); g.fillStyle = gr; g.fillRect(-100, -100, 1300, 2200);
  } };
}
function cardLayer(pal) {
  return { p: 0, draw(g, t) { vgrad(g, -100, -100, WW, WH + 200, [[0, '#17203A'], [1, '#243A6B']]); for (let i = -6; i < 16; i++) { g.fillStyle = 'rgba(255,255,255,0.03)'; g.beginPath(); g.moveTo(i * 120 + t * 12, 0); g.lineTo(i * 120 + 60 + t * 12, 0); g.lineTo(i * 120 - 400 + 60 + t * 12, 1920); g.lineTo(i * 120 - 400 + t * 12, 1920); g.closePath(); g.fill(); } } };
}

/** build a set from its definition { id, kind, time, sign, dress, deck, route, pins } */
function raysLayer(pal, groundY, time) {
  return { p: 0.08, draw(g, t) { const sx = 1500, sy = time === 'dusk' || time === 'dawn' ? groundY - 380 : groundY - 900; g.save(); g.globalCompositeOperation = 'lighter';
    for (let i = 0; i < 9; i++) { const a = -0.5 + i * 0.34 + Math.sin(t * 0.18 + i) * 0.05, w = 0.07 + 0.03 * Math.sin(t * 0.4 + i * 2); g.beginPath(); g.moveTo(sx, sy); g.lineTo(sx + Math.cos(a + w) * 3400, sy + Math.sin(a + w) * 3400); g.lineTo(sx + Math.cos(a - w) * 3400, sy + Math.sin(a - w) * 3400); g.closePath(); g.fillStyle = alpha(pal.sun, 0.05); g.fill(); }
    g.restore(); } };
}
function birdsLayer(groundY) {
  return { p: 0.14, draw(g, t) { g.strokeStyle = 'rgba(40,50,70,0.75)'; g.lineWidth = 5; g.lineCap = 'round';
    for (let i = 0; i < 5; i++) { const x = ((rnd(i) * 3000 + t * (46 + i * 8)) % 3800) - 700, y = 260 + rnd(i + 5) * (groundY - 1200) * 0.6 + Math.sin(t * 0.8 + i) * 18, f = Math.sin(t * 9 + i * 2) * 14, s = 1 + rnd(i + 9) * 0.6;
      g.beginPath(); g.moveTo(x - 26 * s, y - f * s); g.quadraticCurveTo(x - 10 * s, y - 6 * s, x, y); g.quadraticCurveTo(x + 10 * s, y - 6 * s, x + 26 * s, y - f * s); g.stroke(); } } };
}
function foregroundGrass(pal, groundY) {
  return { p: 1.22, front: true, draw(g, t) { for (let i = 0; i < 70; i++) { const x = -500 + i * 52 + rnd(i) * 30, h = 70 + rnd(i + 3) * 120, sway = Math.sin(t * 1.6 + i) * 9, base = groundY + 470 + rnd(i + 8) * 40; g.beginPath(); g.moveTo(x - 14, base); g.quadraticCurveTo(x - 4 + sway * 0.5, base - h * 0.6, x + sway, base - h); g.quadraticCurveTo(x + 6 + sway * 0.5, base - h * 0.6, x + 14, base); g.closePath(); g.fillStyle = shade(pal.near, i % 3 ? 0.62 : 0.5); g.fill(); } } };
}
function windowBeams(time) {
  return { p: 1, front: true, draw(g, t) { if (time === 'night') return; const a = 0.06 + 0.02 * Math.sin(t * 0.5); g.save(); g.globalCompositeOperation = 'lighter'; [[380, 740, 760, 1260], [520, 740, 1020, 1500]].forEach(([x0, x1, y1, xx], i) => { g.beginPath(); g.moveTo(x0, 360); g.lineTo(x1, 360); g.lineTo(x1 + 520 + i * 160, 1560); g.lineTo(x0 + 420 + i * 160, 1560); g.closePath(); g.fillStyle = `rgba(255,238,190,${a * (i ? 0.6 : 1)})`; g.fill(); }); g.restore(); } };
}

export function makeSet(def) {
  const kind = KINDS.includes(def.kind) ? def.kind : 'field', time = TIMES.includes(def.time) ? def.time : 'day', pal = PAL[time], groundY = def.groundY || 1400;
  const L = [];
  const add = (l) => { if (l) L.push(l); };
  if (kind === 'map') { add(mapLayer(def)); return { kind, time, groundY, layers: L, light: null, bare: true }; }
  if (kind === 'card') { add(cardLayer(pal)); return { kind, time, groundY, layers: L, light: null, bare: true }; }
  if (kind === 'room') { roomLayers(pal, groundY, def).forEach(add); add(dressLayer(def, groundY)); add(windowBeams(time)); return { kind, time, groundY, layers: L, light: pal.light, indoor: true }; }
  if (kind === 'study') { studyLayers(pal, groundY, def).forEach(add); add(dressLayer(def, groundY)); return { kind, time, groundY, layers: L, light: null, indoor: true, panel: { x: 1200, y: 700, w: 600, h: 460 } }; }
  add(skyLayer(pal, groundY, time, { sun: kind !== 'sea' || true }));
  add(cloudLayer(pal, groundY, time));
  if (['day', 'dawn', 'dusk'].includes(time) && kind !== 'sea') add(raysLayer(pal, groundY, time));
  if (time === 'day' || time === 'dawn') add(birdsLayer(groundY));
  if (kind === 'field') { add(hillLayer(0.25, groundY - 460, 70, 0.0032, 1, pal.far)); add(hillLayer(0.45, groundY - 300, 60, 0.0045, 3, pal.mid, true)); add(hillLayer(0.7, groundY - 190, 40, 0.006, 6, pal.near, true)); add(groundLayer(pal, groundY, 'grass')); }
  if (kind === 'street') { add(skyline(0.3, groundY - 280, shade(pal.far, 0.95), 5, false, false, false)); add(buildings(pal, groundY, def)); add(groundLayer(pal, groundY, 'dirt'));
    add({ p: 1, draw(g, t) { g.fillStyle = shade(pal.dirt, 1.18); g.fillRect(-900, groundY - 140, WW + 1800, 70); for (let x = -900; x < WW + 900; x += 120) { g.fillStyle = shade(pal.dirt, 0.95); g.fillRect(x, groundY - 140, 4, 70); } [300, 1100, 1900].forEach((x) => { g.save(); g.translate(x, groundY - 110); drawProp(g, 'lamp', {}); g.restore(); }); } }); }
  if (kind === 'city') { add(skyline(0.25, groundY - 380, shade(pal.far, 1.0), 12, false, false, false)); add(skyline(0.5, groundY - 200, shade(pal.mid, 0.9), 33, true, time !== 'day', true)); add(skyline(0.8, groundY - 120, shade(pal.near, 0.85), 61, true, time !== 'day', true)); add(groundLayer(pal, groundY, 'stone')); }
  if (kind === 'desert') { add(hillLayer(0.3, groundY - 340, 80, 0.0028, 2, '#E8B77A')); add(hillLayer(0.55, groundY - 220, 70, 0.004, 5, '#D9A15F')); add(groundLayer(pal, groundY, 'sand')); }
  if (kind === 'mountain') { add({ p: 0.3, draw(g, t) { for (let i = 0; i < 6; i++) { const x = -300 + i * 520, h = 520 + rnd(i) * 300; poly(g, [[x - 360, groundY - 160], [x, groundY - 160 - h], [x + 360, groundY - 160]], pal.far); poly(g, [[x - 90, groundY - 160 - h + 230], [x, groundY - 160 - h], [x + 90, groundY - 160 - h + 230], [x + 36, groundY - 160 - h + 190], [x, groundY - 160 - h + 250], [x - 40, groundY - 160 - h + 196]], '#F4F1E8'); } } }); add(hillLayer(0.55, groundY - 250, 60, 0.004, 4, pal.mid, true)); add(groundLayer(pal, groundY, 'grass')); }
  if (kind === 'sea') { const s = seaLayers(pal, groundY, def); add(s.water); if (s.deck) add(s.deck); add(dressLayer(def, groundY)); add(s.front); return { kind, time, groundY, layers: L, light: pal.light }; }
  add(dressLayer(def, groundY));
  if (kind === 'field' || kind === 'mountain') add(foregroundGrass(pal, groundY));
  return { kind, time, groundY, layers: L, light: pal.light };
}
