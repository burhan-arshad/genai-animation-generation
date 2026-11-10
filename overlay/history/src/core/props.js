// Scenery library in the cut-paper look. Origin of every prop = ground contact (x centre, y bottom); s = scale.
// t = film time (sway, smoke, flicker). All functions are pure: same arguments, same picture.
import { ctx, W, H, TAU, rnd } from './lib.js';
import { cut, P, P_rr, P_circ, P_poly, figure } from './kit.js';

export const C = { brick: '#B5654A', brickDark: '#8E4A38', roof: '#A8322D', roofDark: '#7E2420', timber: '#8A6A48', timberDark: '#6B4F34',
  plaster: '#EBDDBF', window: '#F3D98A', windowDark: '#5A4A3A', leaf: '#6E8B4E', leaf2: '#5C7A45', leaf3: '#4F6D4A', trunk: '#6B4A2E',
  snow: '#F4F1EA', smoke: '#CFC7B8', night: '#1F2A44', fire1: '#A8322D', fire2: '#E0772F', fire3: '#F3C34F', grass: '#8FA663',
  grassDark: '#788F52', dirt: '#B99A6B', cobble: '#A99B84', sandy: '#D9C48D', ink: '#2B2118' };

// ───────────── sky, backdrops, ground ─────────────
export function cloud(x, y, s = 1, color = '#F7EFDC') {
  ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
  for (const [dx, dy, r] of [[-70, 10, 50], [-10, -14, 66], [60, 6, 52], [10, 24, 56]]) cut(P_circ(dx, dy, r), color, { shadow: 0.35, edge: 0 });
  ctx.restore();
}
export function sky(kind = 'day', t = 0) {
  const cols = { day: '#E7D7AE', dusk: '#E3B98F', night: C.night, storm: '#B9B5A8', dawn: '#EBD3B0' };
  ctx.fillStyle = cols[kind] || cols.day; ctx.fillRect(-300, -300, W + 600, H + 600);
  if (kind === 'night') {
    for (let i = 0; i < 40; i++) { ctx.globalAlpha = 0.4 + 0.5 * (0.5 + 0.5 * Math.sin(t * 2 + i * 1.7)); ctx.fillStyle = '#F3E9D2'; ctx.beginPath(); ctx.arc(rnd(i) * W, rnd(i + 50) * 700, 2 + rnd(i + 9) * 3, 0, TAU); ctx.fill(); }
    ctx.globalAlpha = 1; cut(P_circ(820, 300, 80), '#F3E9D2', { shadow: 0.3, edge: 0 });
  } else if (kind !== 'storm') {
    const dusk = kind === 'dusk' || kind === 'dawn';
    cut(P_circ(dusk ? 300 : 820, dusk ? 760 : 330, 90), dusk ? '#E0772F' : '#EFC66A', { shadow: 0.4, edge: 5 });
  }
  if (kind !== 'night') for (let i = 0; i < 3; i++) cloud(((i * 420 + t * 18 + 80) % (W + 500)) - 250, 260 + i * 170 + rnd(i) * 40, 0.9 + 0.3 * rnd(i + 3), kind === 'storm' ? '#8F8B80' : '#F7EFDC');
}
export function mountains(y, seed = 1) {
  for (let i = 0; i < 6; i++) {
    const cx = i * 230 - 40 + rnd(seed + i) * 80, hh = 260 + rnd(seed + i + 9) * 220, ww = 200 + rnd(seed + i + 4) * 120;
    cut(P_poly([[cx - ww, y], [cx, y - hh], [cx + ww, y]]), i % 2 ? '#A9A08C' : '#BDB39B', { shadow: 0.6, edge: 5 });
    cut(P_poly([[cx - ww * 0.28, y - hh * 0.72], [cx, y - hh], [cx + ww * 0.28, y - hh * 0.72], [cx + ww * 0.1, y - hh * 0.64], [cx - ww * 0.08, y - hh * 0.7]]), C.snow, { shadow: 0, edge: 0 });
  }
}
export function skyline(y, seed = 1, color = '#BFAF8E', n = 11) {
  for (let i = 0; i < n; i++) {
    const bw = 80 + rnd(seed + i) * 70, bh = 120 + rnd(seed + i + 20) * 260, bx = i * (W / (n - 1)) - 40;
    cut(P_rr(bx - bw / 2, y - bh, bw, bh, 3), color, { shadow: 0.5, edge: 4 });
    if (rnd(seed + i + 40) > 0.5) cut(P_poly([[bx - bw / 2 - 8, y - bh], [bx, y - bh - 60], [bx + bw / 2 + 8, y - bh]]), '#A99B84', { shadow: 0.5, edge: 4 });
  }
}
export function hills(y, seed = 1, color = C.grassDark, amp = 80) {
  cut(() => { ctx.beginPath(); ctx.moveTo(-300, H + 300); for (let x = -300; x <= W + 300; x += 30) ctx.lineTo(x, y + Math.sin(x * 0.006 + seed) * amp + Math.sin(x * 0.013 + seed * 2) * amp * 0.4); ctx.lineTo(W + 300, H + 300); ctx.closePath(); }, color, { shadow: 0.8, edge: 6 });
}
export function ground(y, kind = 'grass') {
  const base = { grass: C.grass, street: C.cobble, dirt: C.dirt, snow: C.snow, sand: C.sandy }[kind] || C.grass;
  cut(() => { ctx.beginPath(); ctx.rect(-300, y, W + 600, H + 600 - y); }, base, { shadow: 0.9, edge: 6 });
  ctx.save(); ctx.strokeStyle = 'rgba(62,44,30,0.16)'; ctx.lineWidth = 3;
  if (kind === 'street') { for (let r = 0; r < 6; r++) for (let x = -40 + (r % 2) * 40; x < W + 80; x += 80) { ctx.beginPath(); ctx.roundRect(x, y + 20 + r * 46, 72, 38, 8); ctx.stroke(); } }
  else for (let i = 0; i < 26; i++) { const x = rnd(i) * W, yy = y + 30 + rnd(i + 20) * 300; ctx.beginPath(); ctx.moveTo(x, yy); ctx.lineTo(x + 18, yy - 12); ctx.moveTo(x + 18, yy); ctx.lineTo(x + 30, yy - 14); ctx.stroke(); }
  ctx.restore();
}
/** one call for the whole backdrop: sky + far layer + ground. o = { sky, ground, groundY, hills, skyline, mountains, seed } */
export function stage(o = {}, t = 0) {
  const gy = o.groundY ?? 1180, seed = o.seed ?? 1;
  sky(o.sky || 'day', t);
  if (o.mountains) mountains(gy - 60, seed);
  if (o.skyline) skyline(gy - 10, seed, o.sky === 'night' ? '#46506B' : '#BFAF8E');
  else if (o.hills !== false) { hills(gy - 150, seed, '#9DB07A', 70); hills(gy - 60, seed + 3, C.grassDark, 55); }
  ground(gy, o.ground || 'grass');
}

// ───────────── effects ─────────────
export function smoke(x, y, s = 1, t = 0, n = 5, color = C.smoke) {
  for (let i = 0; i < n; i++) {
    const p = (t * 0.35 + i / n) % 1, r = (18 + 40 * p) * s;
    ctx.globalAlpha = 0.9 * (1 - p); cut(P_circ(x + Math.sin(p * 5 + i) * 22 * s + p * 40 * s, y - p * 260 * s, r), color, { shadow: 0.3, edge: 0 });
  }
  ctx.globalAlpha = 1;
}
export function flame(x, y, s = 1, t = 0) {
  ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
  [[C.fire1, 1], [C.fire2, 0.72], [C.fire3, 0.42]].forEach(([c, k], i) => {
    const fl = 1 + 0.12 * Math.sin(t * 11 + i * 2), sw = Math.sin(t * 7 + i) * 10;
    cut(() => { ctx.beginPath(); ctx.moveTo(-46 * k, 0); ctx.bezierCurveTo(-60 * k, -70 * k, -10 + sw, -110 * k * fl, 6 + sw, -190 * k * fl); ctx.bezierCurveTo(30 * k, -110 * k, 66 * k, -60 * k, 46 * k, 0); ctx.closePath(); }, c, { shadow: 0.4, edge: i ? 0 : 4 });
  });
  ctx.restore();
}
export function rain(t, n = 90) {
  ctx.save(); ctx.lineCap = 'round';
  for (let i = 0; i < n; i++) {
    const x = (rnd(i) * (W + 200) + t * 120) % (W + 200) - 100, y = ((rnd(i + 70) * H + t * 900) % (H + 200)) - 100;
    ctx.strokeStyle = 'rgba(62,44,30,0.35)'; ctx.lineWidth = 5; ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x - 14, y + 44); ctx.stroke();
    ctx.strokeStyle = 'rgba(243,233,210,0.75)'; ctx.lineWidth = 2.5; ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x - 14, y + 44); ctx.stroke();
  }
  ctx.restore();
}
export function snow(t, n = 70) {
  ctx.save(); ctx.fillStyle = '#FFFFFF'; ctx.globalAlpha = 0.9;
  for (let i = 0; i < n; i++) { const x = (rnd(i) * W + Math.sin(t * 1.5 + i) * 30 + W) % W, y = ((rnd(i + 70) * H + t * 140) % (H + 100)) - 50; ctx.beginPath(); ctx.arc(x, y, 4 + rnd(i + 9) * 6, 0, TAU); ctx.fill(); }
  ctx.restore();
}
export function nightWash(a = 0.4) { ctx.fillStyle = `rgba(31,42,68,${a})`; ctx.fillRect(-300, -300, W + 600, H + 600); }

// ───────────── buildings and nature ─────────────
/** o = { w, h, kind: 'timber'|'brick'|'cottage', lit, smoke, roof, t } */
export function house(x, y, s = 1, o = {}) {
  const w = o.w || 300, h = o.h || 260, kind = o.kind || 'timber', roof = o.roof || (kind === 'cottage' ? '#C9A45C' : kind === 'brick' ? C.roofDark : C.roof);
  ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
  cut(P_rr(w * 0.2, -h - w * 0.36, 34, 90, 3), C.brickDark);
  cut(P_rr(-w / 2, -h, w, h, 4), kind === 'brick' ? C.brick : kind === 'cottage' ? '#E6D3A8' : C.plaster);
  if (kind === 'brick') { ctx.strokeStyle = 'rgba(62,44,30,0.25)'; ctx.lineWidth = 2; for (let r = 1; r < h / 24; r++) { ctx.beginPath(); ctx.moveTo(-w / 2, -h + r * 24); ctx.lineTo(w / 2, -h + r * 24); ctx.stroke(); } }
  if (kind === 'timber') { ctx.strokeStyle = C.timber; ctx.lineWidth = 8; ctx.beginPath(); ctx.moveTo(-w / 2, -h * 0.5); ctx.lineTo(w / 2, -h * 0.5); ctx.moveTo(-w / 2, -h); ctx.lineTo(w / 2, -h * 0.5); ctx.moveTo(w / 2, -h); ctx.lineTo(-w / 2, -h * 0.5); ctx.stroke(); }
  cut(P_poly([[-w / 2 - 24, -h + 6], [0, -h - w * 0.38], [w / 2 + 24, -h + 6]]), roof);
  for (const wx of [-w * 0.26, w * 0.26]) {
    cut(P_rr(wx - 22, -h * 0.62, 44, 50, 4), o.lit ? C.window : C.windowDark, { shadow: 0.4, edge: 4 });
    ctx.strokeStyle = C.timberDark; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(wx, -h * 0.62); ctx.lineTo(wx, -h * 0.62 + 50); ctx.moveTo(wx - 22, -h * 0.62 + 25); ctx.lineTo(wx + 22, -h * 0.62 + 25); ctx.stroke();
  }
  cut(P_rr(-20, -76, 40, 76, [18, 18, 0, 0]), C.timberDark);
  ctx.restore();
  if (o.smoke) smoke(x + (w * 0.2 + 17) * s, y + (-h - w * 0.36) * s, s * 0.8, o.t || 0, 4);
}
export function tree(x, y, s = 1, kind = 'oak', t = 0, seed = 0) {
  ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
  cut(P_rr(-16, -150, 32, 150, 6), C.trunk);
  ctx.rotate(Math.sin(t * 1.6 + seed) * 0.03);
  if (kind === 'pine') [[-150, 120, 120], [-230, 100, 110], [-310, 78, 100], [-380, 52, 90]].forEach(([by, hw, hh], i) => cut(P_poly([[-hw, by], [hw, by], [0, by - hh]]), i % 2 ? C.leaf3 : C.leaf2));
  else if (kind === 'bare') { ctx.strokeStyle = C.trunk; ctx.lineCap = 'round'; for (const [x1, y1, x2, y2, w] of [[0, -140, -70, -250, 14], [0, -170, 60, -280, 12], [-40, -210, -100, -250, 8], [40, -230, 100, -300, 8], [0, -200, 4, -320, 10]]) { ctx.lineWidth = w; ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke(); } }
  else { cut(P_circ(0, -250, 100), C.leaf2); cut(P_circ(-70, -190, 70), C.leaf); cut(P_circ(72, -196, 74), C.leaf3); cut(P_circ(10, -300, 70), C.leaf); }
  ctx.restore();
}
export function church(x, y, s = 1) {
  ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
  cut(P_rr(-150, -170, 220, 170, 4), P.stone);
  cut(P_poly([[-170, -166], [-40, -270], [90, -166]]), C.roofDark);
  cut(P_rr(40, -400, 90, 400, 4), P.stoneDark);
  cut(P_poly([[28, -396], [85, -540], [142, -396]]), C.roof);
  ctx.strokeStyle = P.gold; ctx.lineWidth = 8; ctx.lineCap = 'round'; ctx.beginPath(); ctx.moveTo(85, -540); ctx.lineTo(85, -596); ctx.moveTo(66, -574); ctx.lineTo(104, -574); ctx.stroke();
  cut(P_rr(70, -340, 30, 60, [15, 15, 0, 0]), C.windowDark);
  cut(P_rr(-112, -112, 44, 112, [22, 22, 0, 0]), C.timberDark);
  for (const wx of [-30, 20]) cut(P_rr(wx - 14, -120, 28, 60, [14, 14, 0, 0]), C.window, { shadow: 0.3, edge: 3 });
  ctx.restore();
}
export function castle(x, y, s = 1) {
  ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
  cut(P_rr(-260, -220, 520, 220, 4), P.stone);
  for (let i = 0; i < 9; i++) cut(P_rr(-260 + i * 60, -254, 34, 38, 2), P.stone);
  for (const tx of [-300, 240]) { cut(P_rr(tx - 20, -360, 80, 360, 4), P.stoneDark); cut(P_poly([[tx - 36, -356], [tx + 20, -450], [tx + 76, -356]]), C.roof); cut(P_rr(tx + 8, -250, 12, 46, 6), C.windowDark, { shadow: 0, edge: 0 }); }
  cut(P_rr(-50, -140, 100, 140, [50, 50, 0, 0]), C.timberDark);
  ctx.restore();
}
export function factory(x, y, s = 1, t = 0) {
  ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
  for (const cx of [-120, 110]) cut(P_rr(cx - 24, -420, 48, 230, 3), C.brickDark);
  cut(P_rr(-200, -200, 400, 200, 4), C.brick);
  for (let i = 0; i < 3; i++) cut(P_poly([[-200 + i * 133, -200], [-200 + i * 133, -260], [-67 + i * 133, -200]]), C.roofDark);
  for (let i = 0; i < 5; i++) cut(P_rr(-170 + i * 72, -150, 44, 56, 4), C.window, { shadow: 0.3, edge: 3 });
  ctx.restore();
  smoke(x - 120 * s, y - 420 * s, s * 1.2, t, 6); smoke(x + 110 * s, y - 420 * s, s * 1.2, t + 0.4, 6);
}

// ───────────── vehicles, street furniture ─────────────
export function wheel(x, y, r, a) {
  cut(P_circ(x, y, r), C.timberDark, { shadow: 0.5, edge: 4 });
  ctx.save(); ctx.translate(x, y); ctx.rotate(a); ctx.strokeStyle = P.edge; ctx.lineWidth = 6;
  for (let k = 0; k < 4; k++) { ctx.rotate(Math.PI / 4); ctx.beginPath(); ctx.moveTo(-r * 0.8, 0); ctx.lineTo(r * 0.8, 0); ctx.stroke(); }
  ctx.restore(); cut(P_circ(x, y, 9), P.gold, { shadow: 0, edge: 0 });
}
export function cart(x, y, s = 1, t = 0, spin = 4) {
  ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
  cut(P_poly([[-120, -120], [120, -120], [96, -50], [-96, -50]]), C.timber);
  cut(P_rr(-120, -140, 240, 22, 6), C.timberDark);
  wheel(-64, -40, 44, t * spin); wheel(64, -40, 44, t * spin);
  ctx.restore();
}
export function train(x, y, s = 1, t = 0) {
  ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
  cut(P_rr(-170, -240, 50, 100, 4), C.ink); cut(P_poly([[-196, -236], [-145, -280], [-94, -236]]), C.ink);
  cut(P_rr(-200, -150, 300, 100, 14), C.ink);
  cut(P_rr(100, -240, 120, 190, 6), C.roof); cut(P_rr(130, -214, 60, 56, 4), C.window, { shadow: 0.3, edge: 3 });
  cut(P_rr(-210, -70, 440, 22, 4), C.timberDark);
  for (const wx of [-120, -30, 70, 160]) wheel(wx, -34, 40, t * 6);
  ctx.restore();
  smoke(x - 145 * s, y - 280 * s, s, t, 6);
}
export function lamp(x, y, s = 1, lit = true, t = 0) {
  ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
  cut(P_rr(-8, -300, 16, 300, 4), C.ink); cut(P_rr(-30, -350, 60, 56, 8), lit ? C.window : C.windowDark, { shadow: 0.5, edge: 4 });
  cut(P_poly([[-38, -348], [0, -384], [38, -348]]), C.ink);
  if (lit) { ctx.globalAlpha = 0.18 + 0.05 * Math.sin(t * 8); ctx.fillStyle = '#F3D98A'; ctx.beginPath(); ctx.arc(0, -322, 110, 0, TAU); ctx.fill(); ctx.globalAlpha = 1; }
  ctx.restore();
}
export function fence(x, y, w = 400, s = 1) {
  ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
  cut(P_rr(0, -80, w, 14, 3), C.timber, { shadow: 0.4, edge: 3 }); cut(P_rr(0, -44, w, 14, 3), C.timber, { shadow: 0.4, edge: 3 });
  for (let px = 0; px <= w; px += 50) cut(P_poly([[px - 12, 0], [px - 12, -110], [px, -128], [px + 12, -110], [px + 12, 0]]), C.timberDark, { shadow: 0.4, edge: 3 });
  ctx.restore();
}
export function barrel(x, y, s = 1) {
  ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
  cut(P_rr(-40, -90, 80, 90, 18), C.timber); ctx.strokeStyle = C.ink; ctx.lineWidth = 5;
  for (const hy of [-66, -24]) { ctx.beginPath(); ctx.moveTo(-40, hy); ctx.lineTo(40, hy); ctx.stroke(); }
  ctx.restore();
}
export function crate(x, y, s = 1) {
  ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
  cut(P_rr(-45, -90, 90, 90, 4), C.timber); ctx.strokeStyle = C.timberDark; ctx.lineWidth = 6;
  ctx.beginPath(); ctx.moveTo(-45, -90); ctx.lineTo(45, 0); ctx.moveTo(45, -90); ctx.lineTo(-45, 0); ctx.stroke();
  ctx.restore();
}

// ───────────── people ─────────────
/** a row of period paper people. o = { moving, h } */
export function crowd(x, y, w, n = 6, seed = 0, t = 0, o = {}) {
  const roles = ['merchant', 'worker', 'scholar', 'sailor', 'worker', 'merchant'];
  for (let i = 0; i < n; i++) {
    const px = x + (n === 1 ? 0 : (w * i) / (n - 1)) + (rnd(seed + i) - 0.5) * 30;
    figure({ x: px, y: y + (i % 2) * 14, h: (o.h || 240) * (0.9 + rnd(seed + i + 9) * 0.2), dir: rnd(seed + i + 4) > 0.5 ? 1 : -1,
      role: roles[Math.floor(rnd(seed + i * 3) * roles.length)], walk: o.moving ? t * 3 + i : undefined, arm: 0 });
  }
}