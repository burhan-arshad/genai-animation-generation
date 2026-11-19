// Screen-space atmosphere. Every effect is a pure function of the time t (no state), so any frame can be drawn on its own.
import { W, H, TAU, clamp, rnd, circ, alpha } from './util.js';

export const FX = ['dust', 'rain', 'snow', 'embers', 'confetti', 'leaves', 'fireflies'];

export function drawFx(g, kind, t, k = 1) {
  g.save();
  if (kind === 'dust') for (let i = 0; i < 46; i++) { const x = (rnd(i) * W + t * (10 + rnd(i + 5) * 16)) % W, y = (rnd(i + 9) * H - t * (6 + rnd(i + 2) * 10) + H * 4) % H; circ(g, x, y, 2 + rnd(i + 3) * 3.5, `rgba(255,240,200,${(0.16 + 0.22 * Math.abs(Math.sin(t + i))) * k})`); }
  if (kind === 'rain') { g.strokeStyle = `rgba(200,220,255,${0.5 * k})`; g.lineWidth = 3; g.lineCap = 'round'; for (let i = 0; i < 120; i++) { const x = (rnd(i) * (W + 300) - t * 160 + 4000) % (W + 300), y = (rnd(i + 7) * H + t * 1500) % (H + 200) - 100; g.beginPath(); g.moveTo(x, y); g.lineTo(x - 22, y + 70); g.stroke(); } g.fillStyle = `rgba(30,40,70,${0.18 * k})`; g.fillRect(0, 0, W, H); }
  if (kind === 'snow') for (let i = 0; i < 90; i++) { const x = (rnd(i) * W + Math.sin(t * 0.8 + i) * 50 + W * 2) % W, y = (rnd(i + 9) * H + t * (70 + rnd(i + 3) * 90)) % H; circ(g, x, y, 3 + rnd(i + 4) * 5, `rgba(255,255,255,${0.85 * k})`); }
  if (kind === 'embers') for (let i = 0; i < 40; i++) { const u = (t * (0.2 + rnd(i) * 0.25) + rnd(i + 3)) % 1, x = rnd(i + 8) * W + Math.sin(t * 2 + i) * 40, y = H - u * (H * 0.9); circ(g, x, y, 3 + rnd(i + 5) * 4, `rgba(255,${130 + rnd(i) * 90 | 0},60,${(1 - u) * 0.9 * k})`); }
  if (kind === 'confetti') for (let i = 0; i < 70; i++) { const x = rnd(i) * W + Math.sin(t * 2 + i) * 30, y = (rnd(i + 6) * H + t * (260 + rnd(i) * 220)) % H; g.save(); g.translate(x, y); g.rotate(t * 3 + i); g.fillStyle = ['#F26B5B', '#F4C542', '#3FA7A0', '#8C6FC9', '#FFFFFF'][i % 5]; g.fillRect(-7, -4, 14, 8); g.restore(); }
  if (kind === 'leaves') for (let i = 0; i < 24; i++) { const x = (rnd(i) * W - t * (60 + rnd(i) * 60) + W * 3) % W, y = (rnd(i + 5) * H + t * (50 + rnd(i + 2) * 40)) % H; g.save(); g.translate(x, y); g.rotate(t * 2 + i); g.fillStyle = ['#D9503F', '#C98B2E', '#8C6B3A'][i % 3]; g.beginPath(); g.ellipse(0, 0, 12, 6, 0, 0, TAU); g.fill(); g.restore(); }
  if (kind === 'fireflies') for (let i = 0; i < 24; i++) { const x = rnd(i) * W + Math.sin(t * 0.7 + i) * 70, y = H * 0.35 + rnd(i + 4) * H * 0.55 + Math.cos(t * 0.6 + i * 2) * 50; const a = 0.4 + 0.6 * Math.abs(Math.sin(t * 1.6 + i)); circ(g, x, y, 9, `rgba(255,240,150,${0.18 * a})`); circ(g, x, y, 3.5, `rgba(255,250,200,${a})`); }
  g.restore();
}

export function vignette(g, k = 0.45) {
  const gr = g.createRadialGradient(W / 2, H / 2, H * 0.32, W / 2, H / 2, H * 0.78);
  gr.addColorStop(0, 'rgba(10,10,30,0)'); gr.addColorStop(1, `rgba(10,10,30,${k})`);
  g.fillStyle = gr; g.fillRect(0, 0, W, H);
}
export function lightWash(g, color) { if (color) { g.fillStyle = color; g.fillRect(0, 0, W, H); } }
export function grain(g, tile, t) {
  if (!tile) return;
  g.save(); g.globalAlpha = 0.07; const ox = (Math.floor(t * 24) * 37) % 64, oy = (Math.floor(t * 24) * 91) % 64;
  g.translate(-ox, -oy); g.fillStyle = g.createPattern(tile, 'repeat'); g.fillRect(0, 0, W + 64, H + 64); g.restore();
}
export function makeGrainTile(makeCanvas) {
  if (!makeCanvas) return null;
  const c = makeCanvas(64, 64), x = c.getContext('2d'), d = x.createImageData(64, 64);
  for (let i = 0; i < 64 * 64; i++) { const v = (rnd(i) * 255) | 0; d.data[i * 4] = v; d.data[i * 4 + 1] = v; d.data[i * 4 + 2] = v; d.data[i * 4 + 3] = 255; }
  x.putImageData(d, 0, 0); return c;
}
