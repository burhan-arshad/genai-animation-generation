// Props: every object is drawn flat, standing on the origin (base centre), y up = negative. Size at scale 1: a person is 520 px tall.
// drawProp(g, name, o) -> true when the prop exists. o = { t: seconds since it appeared, c: main colour, text }.
// A custom prop designed for one story (a blueprint of plain shapes, never code) is drawn by drawBlueprint().
import { TAU, clamp, lerp, shade, mix, alpha, rnd, circ, ell, poly, rr, limb, vgrad } from './util.js';
import { drawPerson } from './people.js';

const WOOD = '#8C5A3A', WOOD_D = '#6B4526', WOOD_L = '#C98B2E', STONE = '#B9BCC4', STONE_D = '#8C8F99', CREAM = '#F4EAD0', GOLD = '#F4C542', RED = '#D9503F', TEAL = '#3FA7A0', NAVY = '#2F4E8F';

function sign(g, w, h, text, bg = CREAM, fg = '#2B1A10') {
  rr(g, -w / 2, -h, w, h, 10); g.fillStyle = bg; g.fill(); rr(g, -w / 2 + 6, -h + 6, w - 12, h - 12, 7); g.strokeStyle = fg; g.lineWidth = 3; g.stroke();
  if (text) { g.fillStyle = fg; g.textAlign = 'center'; g.textBaseline = 'middle'; let fs = h * 0.5; g.font = `900 ${fs}px Inter, sans-serif`; while (g.measureText(text).width > w - 30 && fs > 12) { fs -= 3; g.font = `900 ${fs}px Inter, sans-serif`; } g.fillText(text, 0, -h / 2 + 2); }
}
function windowPane(g, x, y, w, h, lit) { rr(g, x, y, w, h, 4); g.fillStyle = lit ? '#FFE9A8' : '#7FB6D6'; g.fill(); g.strokeStyle = shade(WOOD, 0.7); g.lineWidth = 4; g.stroke(); g.beginPath(); g.moveTo(x + w / 2, y); g.lineTo(x + w / 2, y + h); g.moveTo(x, y + h / 2); g.lineTo(x + w, y + h / 2); g.stroke(); }
function flame(g, x, y, s, t, k = 0) { const w = Math.sin(t * 9 + k) * 0.12; g.save(); g.translate(x, y); g.scale(s * (1 + w), s * (1 + Math.cos(t * 7 + k) * 0.1)); g.beginPath(); g.moveTo(0, 0); g.quadraticCurveTo(-26, -34, -8, -86); g.quadraticCurveTo(0, -56, 18, -64); g.quadraticCurveTo(34, -30, 0, 0); g.fillStyle = '#F26B5B'; g.fill(); g.beginPath(); g.moveTo(0, 0); g.quadraticCurveTo(-13, -18, -3, -44); g.quadraticCurveTo(2, -28, 11, -32); g.quadraticCurveTo(16, -12, 0, 0); g.fillStyle = GOLD; g.fill(); g.restore(); }

export const P = {
  // ---- buildings ----
  house(g, o) { const c = o.c || '#E9D3A3', w = 460, h = 330; rr(g, -w / 2, -h, w, h, 6); g.fillStyle = c; g.fill(); poly(g, [[-w / 2 - 26, -h + 4], [0, -h - 170], [w / 2 + 26, -h + 4]], '#B5553C'); poly(g, [[-w / 2 - 26, -h + 4], [0, -h - 170], [0, -h - 150], [-w / 2 - 6, -h + 4]], shade('#B5553C', 0.85)); rr(g, -34, -190, 68, 190, 5); g.fillStyle = WOOD_D; g.fill(); circ(g, 18, -96, 5, GOLD); windowPane(g, -170, -250, 90, 100, true); windowPane(g, 80, -250, 90, 100, true); rr(g, 120, -h - 140, 40, 90, 3); g.fillStyle = STONE_D; g.fill(); },
  shop(g, o) { const c = o.c || '#7FB6A0', w = 520, h = 380; rr(g, -w / 2, -h, w, h, 4); g.fillStyle = c; g.fill(); rr(g, -w / 2, -h - 30, w, 34, 3); g.fillStyle = shade(c, 0.75); g.fill(); g.save(); g.translate(0, -h + 8); sign(g, 340, 70, o.text || 'SHOP', CREAM); g.restore(); windowPane(g, -220, -250, 150, 170, true); windowPane(g, 70, -250, 150, 170, true); rr(g, -34, -190, 68, 190, 4); g.fillStyle = WOOD_D; g.fill(); for (let i = 0; i < 7; i++) poly(g, [[-w / 2 + i * 74, -h + 94], [-w / 2 + (i + 1) * 74, -h + 94], [-w / 2 + (i + 1) * 74 - 6, -h + 140], [-w / 2 + i * 74 + 6, -h + 140]], i % 2 ? '#F4F1E8' : RED); },
  barn(g, o) { const c = o.c || '#B5453A'; poly(g, [[-260, 0], [-260, -250], [-150, -380], [150, -380], [260, -250], [260, 0]], c); rr(g, -90, -240, 180, 240, 3); g.fillStyle = shade(c, 0.7); g.fill(); g.strokeStyle = CREAM; g.lineWidth = 8; g.strokeRect(-90, -240, 180, 240); g.beginPath(); g.moveTo(-90, -240); g.lineTo(90, 0); g.moveTo(90, -240); g.lineTo(-90, 0); g.stroke(); },
  tent(g, o) { const c = o.c || '#D9503F'; poly(g, [[-220, 0], [0, -300], [220, 0]], c); for (let i = -2; i < 3; i++) poly(g, [[i * 44 - 22, 0], [0, -300], [i * 44 + 22, 0]], i % 2 ? CREAM : c); poly(g, [[-40, 0], [0, -140], [40, 0]], '#3A2415'); poly(g, [[0, -300], [0, -360], [50, -340], [0, -320]], GOLD); },
  // ---- nature and street ----
  tree(g, o) { const c = o.c || '#4F9A5E'; rr(g, -18, -240, 36, 240, 8); g.fillStyle = WOOD_D; g.fill(); g.save(); g.translate(0, -230); g.rotate(Math.sin((o.t || 0) * 1.1) * 0.022); g.translate(0, 230); circ(g, 0, -330, 130, shade(c, 0.85)); circ(g, -80, -270, 90, c); circ(g, 84, -280, 96, c); circ(g, 8, -388, 92, shade(c, 1.12)); g.restore(); },
  pine(g, o) { const c = o.c || '#2F7A5A'; rr(g, -14, -80, 28, 80, 4); g.fillStyle = WOOD_D; g.fill(); g.save(); g.translate(0, -80); g.rotate(Math.sin((o.t || 0) * 1.3) * 0.016); g.translate(0, 80); [[0, -80, 150, 150], [0, -170, 120, 130], [0, -250, 90, 120]].forEach(([x, y, w, h], i) => poly(g, [[-w, y], [0, y - h], [w, y]], shade(c, 0.85 + i * 0.1))); g.restore(); },
  bush(g, o) { const c = o.c || '#5FB38A'; circ(g, -50, -40, 50, shade(c, 0.9)); circ(g, 40, -44, 56, c); circ(g, 0, -62, 56, shade(c, 1.1)); },
  fence(g, o) { for (let i = -3; i <= 3; i++) { rr(g, i * 70 - 14, -130, 28, 130, 6); g.fillStyle = o.c || CREAM; g.fill(); } rr(g, -250, -105, 500, 18, 4); g.fillStyle = shade(o.c || CREAM, 0.85); g.fill(); rr(g, -250, -55, 500, 18, 4); g.fill(); },
  lamp(g, o) { rr(g, -8, -480, 16, 480, 4); g.fillStyle = '#3A3F55'; g.fill(); rr(g, -26, -520, 52, 44, 6); g.fillStyle = '#FFE9A8'; g.fill(); g.strokeStyle = '#3A3F55'; g.lineWidth = 7; g.strokeRect(-26, -520, 52, 44); poly(g, [[-36, -520], [0, -560], [36, -520]], '#3A3F55'); },
  signpost(g, o) { rr(g, -8, -300, 16, 300, 3); g.fillStyle = WOOD_D; g.fill(); g.save(); g.translate(0, -230); g.rotate(-0.05); sign(g, 230, 80, o.text || 'TOWN', CREAM); g.restore(); },
  sign(g, o) { rr(g, -7, -200, 14, 200, 3); g.fillStyle = WOOD_D; g.fill(); g.save(); g.translate(0, -140); sign(g, 300, 120, o.text || 'SIGN', o.c || CREAM); g.restore(); },
  poster(g, o) { g.save(); g.translate(0, 0); sign(g, 230, 300, o.text || 'WANTED', o.c || CREAM); g.restore(); },
  // ---- furniture and small things ----
  crate(g, o) { const c = o.c || WOOD_L; rr(g, -70, -140, 140, 140, 4); g.fillStyle = c; g.fill(); g.strokeStyle = shade(c, 0.6); g.lineWidth = 7; g.strokeRect(-70, -140, 140, 140); g.beginPath(); g.moveTo(-70, -140); g.lineTo(70, 0); g.moveTo(70, -140); g.lineTo(-70, 0); g.stroke(); },
  barrel(g, o) { const c = o.c || WOOD; g.beginPath(); g.moveTo(-58, 0); g.quadraticCurveTo(-78, -90, -58, -180); g.lineTo(58, -180); g.quadraticCurveTo(78, -90, 58, 0); g.closePath(); g.fillStyle = c; g.fill(); [-140, -40].forEach((y) => { rr(g, -70, y - 8, 140, 14, 3); g.fillStyle = '#4A5568'; g.fill(); }); },
  table(g, o) { const c = o.c || WOOD; rr(g, -190, -210, 380, 26, 6); g.fillStyle = c; g.fill(); [-160, 140].forEach((x) => { rr(g, x, -190, 24, 190, 4); g.fillStyle = shade(c, 0.8); g.fill(); }); },
  desk(g, o) { const c = o.c || WOOD; rr(g, -200, -230, 400, 26, 5); g.fillStyle = c; g.fill(); rr(g, -190, -206, 120, 206, 4); g.fillStyle = shade(c, 0.85); g.fill(); rr(g, -180, -190, 100, 40, 3); g.fillStyle = shade(c, 0.7); g.fill(); circ(g, -130, -170, 5, GOLD); rr(g, 150, -206, 24, 206, 3); g.fillStyle = shade(c, 0.8); g.fill(); },
  chair(g, o) { const c = o.c || WOOD; rr(g, -60, -140, 120, 20, 5); g.fillStyle = c; g.fill(); rr(g, -60, -300, 20, 170, 5); g.fill(); [-50, 36].forEach((x) => { rr(g, x, -120, 14, 120, 3); g.fillStyle = shade(c, 0.8); g.fill(); }); },
  bookshelf(g, o) { const c = o.c || WOOD_D; rr(g, -160, -520, 320, 520, 6); g.fillStyle = c; g.fill(); const cols = ['#C8283A', '#2F4E8F', '#F4C542', '#3FA7A0', '#8C5A3A', '#9A6BC9']; [0, 1, 2, 3].forEach((r) => { const y = -490 + r * 124; rr(g, -146, y + 100, 292, 12, 2); g.fillStyle = shade(c, 0.75); g.fill(); let x = -140; for (let i = 0; i < 9 && x < 130; i++) { const w = 20 + rnd(r * 9 + i) * 16, h = 60 + rnd(r * 13 + i) * 36; rr(g, x, y + 100 - h, w, h, 2); g.fillStyle = cols[(r * 3 + i) % cols.length]; g.fill(); x += w + 3; } }); },
  book(g, o) { const c = o.c || '#C8283A'; rr(g, -60, -22, 120, 22, 3); g.fillStyle = c; g.fill(); rr(g, -56, -18, 112, 14, 2); g.fillStyle = CREAM; g.fill(); rr(g, -60, -48, 116, 24, 3); g.fillStyle = shade(c, 0.8); g.fill(); },
  openbook(g, o) { poly(g, [[-110, -10], [0, 0], [0, -120], [-110, -130]], CREAM); poly(g, [[110, -10], [0, 0], [0, -120], [110, -130]], shade(CREAM, 0.94)); g.strokeStyle = '#C9B58A'; g.lineWidth = 3; for (let i = 0; i < 4; i++) { g.beginPath(); g.moveTo(-96, -30 - i * 24); g.lineTo(-14, -22 - i * 24); g.moveTo(14, -22 - i * 24); g.lineTo(96, -30 - i * 24); g.stroke(); } },
  scroll(g, o) { rr(g, -80, -110, 160, 110, 10); g.fillStyle = CREAM; g.fill(); ell(g, -80, -55, 14, 55, shade(CREAM, 0.85)); ell(g, 80, -55, 14, 55, shade(CREAM, 0.85)); g.strokeStyle = '#8C5A3A'; g.lineWidth = 3; for (let i = 0; i < 4; i++) { g.beginPath(); g.moveTo(-56, -85 + i * 22); g.lineTo(56, -85 + i * 22); g.stroke(); } },
  letter(g, o) { rr(g, -80, -110, 160, 110, 6); g.fillStyle = CREAM; g.fill(); poly(g, [[-80, -110], [0, -50], [80, -110]], shade(CREAM, 0.88)); circ(g, 0, -56, 12, '#C8283A'); },
  coin(g, o) { circ(g, 0, -50, 50, GOLD); g.beginPath(); g.arc(0, -50, 38, 0, TAU); g.strokeStyle = WOOD_L; g.lineWidth = 4; g.stroke(); g.fillStyle = WOOD; g.textAlign = 'center'; g.textBaseline = 'middle'; g.font = '900 36px Inter, sans-serif'; g.fillText(o.text || '$', 0, -48); },
  coins(g, o) { for (let i = 0; i < 5; i++) { ell(g, (i % 2) * 6, -10 - i * 14, 46, 14, WOOD_L); ell(g, (i % 2) * 6, -16 - i * 14, 46, 14, GOLD); } },
  key(g, o) { circ(g, 0, -86, 30, GOLD); circ(g, 0, -86, 14, 'rgba(0,0,0,0.0)'); g.fillStyle = GOLD; g.fillRect(-7, -60, 14, 60); g.fillRect(0, -26, 24, 10); g.fillRect(0, -44, 18, 10); g.globalCompositeOperation = 'destination-out'; circ(g, 0, -86, 12, '#000'); g.globalCompositeOperation = 'source-over'; },
  bell(g, o) { g.beginPath(); g.moveTo(-60, -10); g.quadraticCurveTo(-60, -110, 0, -120); g.quadraticCurveTo(60, -110, 60, -10); g.closePath(); g.fillStyle = GOLD; g.fill(); circ(g, 0, -4, 12, WOOD_L); },
  bucket(g, o) { poly(g, [[-50, -90], [50, -90], [40, 0], [-40, 0]], o.c || '#8FA3B8'); ell(g, 0, -90, 50, 10, shade(o.c || '#8FA3B8', 0.75)); },
  shovel(g, o) { limb(g, [[0, 0], [0, -280]], WOOD_L, 12); rr(g, -14, -316, 28, 40, 4); g.fillStyle = WOOD_D; g.fill(); poly(g, [[-34, 0], [34, 0], [26, 80], [0, 100], [-26, 80]], '#8FA3B8'); },
  hammer(g, o) { limb(g, [[0, 0], [0, -150]], WOOD_L, 14); rr(g, -50, -190, 100, 46, 6); g.fillStyle = '#6B7280'; g.fill(); },
  chisel(g, o) { rr(g, -8, -150, 16, 110, 3); g.fillStyle = WOOD_L; g.fill(); poly(g, [[-8, -40], [8, -40], [3, 0], [-3, 0]], '#B9BCC4'); },
  ladder(g, o) { [-30, 30].forEach((x) => { rr(g, x - 6, -360, 12, 360, 3); g.fillStyle = WOOD_L; g.fill(); }); for (let y = -320; y < 0; y += 60) { rr(g, -30, y, 60, 10, 2); g.fillStyle = WOOD; g.fill(); } },
  lightbulb(g, o) { circ(g, 0, -100, 56, '#FFE9A8'); rr(g, -24, -48, 48, 48, 6); g.fillStyle = '#8C8F99'; g.fill(); [-34, -22, -10].forEach((y) => { g.fillStyle = '#6B7280'; g.fillRect(-24, y, 48, 4); }); },
  globe(g, o) { rr(g, -40, -14, 80, 14, 4); g.fillStyle = WOOD_D; g.fill(); rr(g, -6, -70, 12, 60, 3); g.fill(); circ(g, 0, -130, 70, '#3F7FC4'); [[-20, -150, 30, 22], [24, -118, 24, 30], [-30, -108, 14, 10]].forEach(([x, y, rx, ry]) => ell(g, x, y, rx, ry, '#5FB38A')); },
  clock(g, o) { circ(g, 0, -110, 90, WOOD_D); circ(g, 0, -110, 78, CREAM); const t = o.t || 0; limb(g, [[0, -110], [0, -170]], '#2B1A10', 7); limb(g, [[0, -110], [Math.sin(t) * 44, -110 - Math.cos(t) * 44]], '#2B1A10', 7); circ(g, 0, -110, 7, RED); },
  telescope(g, o) { limb(g, [[-30, -6], [0, -90], [30, -6]], WOOD_D, 9); g.save(); g.translate(0, -96); g.rotate(-0.55); rr(g, -150, -18, 300, 36, 8); g.fillStyle = WOOD_L; g.fill(); rr(g, 100, -24, 60, 48, 6); g.fillStyle = '#6B7280'; g.fill(); g.restore(); },
  podium(g, o) { poly(g, [[-90, 0], [90, 0], [78, -180], [-78, -180]], o.c || WOOD); rr(g, -104, -196, 208, 22, 5); g.fillStyle = shade(o.c || WOOD, 1.2); g.fill(); },
  flag(g, o) { const c = o.c || RED, t = o.t || 0; limb(g, [[0, 0], [0, -420]], '#8C8F99', 8); g.beginPath(); g.moveTo(4, -410); for (let i = 0; i <= 20; i++) g.lineTo(4 + i * 10, -410 + Math.sin(i * 0.5 + t * 4) * 6 * (i / 20)); for (let i = 20; i >= 0; i--) g.lineTo(4 + i * 10, -310 + Math.sin(i * 0.5 + t * 4) * 6 * (i / 20)); g.closePath(); g.fillStyle = c; g.fill(); },
  ticket(g, o) { rr(g, -90, -90, 180, 90, 8); g.fillStyle = GOLD; g.fill(); circ(g, -90, -45, 12, 'rgba(0,0,0,0)'); g.fillStyle = WOOD; g.textAlign = 'center'; g.textBaseline = 'middle'; g.font = '900 34px Inter, sans-serif'; g.fillText(o.text || 'ADMIT', 0, -44); },
  // ---- stone and the ground ----
  stone_block(g, o) { poly(g, [[-150, 0], [150, 0], [130, -140], [-110, -150]], STONE); poly(g, [[-110, -150], [130, -140], [90, -190], [-70, -196]], shade(STONE, 1.15)); poly(g, [[130, -140], [150, 0], [180, -40], [160, -150]], STONE_D); },
  stone_giant(g, o) { // a huge stone man lying on his back
    const c = o.c || STONE; ell(g, 0, -34, 230, 58, c); ell(g, -190, -52, 64, 54, shade(c, 1.1)); poly(g, [[-196, -70], [-176, -70], [-186, -52]], shade(c, 0.8)); circ(g, -208, -62, 5, STONE_D); circ(g, -172, -62, 5, STONE_D); ell(g, -190, -36, 16, 6, STONE_D);
    ell(g, 40, -70, 70, 30, shade(c, 0.95), -0.1); ell(g, 180, -44, 70, 26, shade(c, 0.9)); ell(g, 232, -30, 24, 14, shade(c, 0.85)); ell(g, -60, -22, 46, 12, shade(c, 0.85)); },
  pit(g, o) { const w = o.w || 360; ell(g, 0, 0, w / 2 + 20, 34, '#5A3A22'); ell(g, 0, 6, w / 2, 26, '#2B1A10'); },
  mound(g, o) { g.beginPath(); g.moveTo(-170, 0); g.quadraticCurveTo(0, -120, 170, 0); g.closePath(); g.fillStyle = '#8C5A3A'; g.fill(); g.beginPath(); g.moveTo(-120, 0); g.quadraticCurveTo(-20, -70, 60, -50); g.quadraticCurveTo(10, -30, 20, 0); g.fillStyle = '#A8734A'; g.fill(); },
  // ---- transport ----
  wagon(g, o) { rr(g, -170, -150, 340, 90, 8); g.fillStyle = o.c || WOOD; g.fill(); [-110, 110].forEach((x) => { circ(g, x, -48, 52, WOOD_D); circ(g, x, -48, 40, CREAM); circ(g, x, -48, 8, WOOD_D); for (let i = 0; i < 6; i++) { const a = (i * TAU) / 6 + (o.t || 0) * 2; limb(g, [[x, -48], [x + Math.cos(a) * 40, -48 + Math.sin(a) * 40]], WOOD_D, 5); } }); },
  ship(g, o) { const t = o.t || 0; g.save(); g.rotate(Math.sin(t * 1.4) * 0.03); poly(g, [[-260, -60], [260, -60], [210, 20], [-210, 20]], WOOD_D); rr(g, -258, -76, 516, 22, 4); g.fillStyle = WOOD; g.fill(); limb(g, [[0, -76], [0, -420]], WOOD_L, 12); poly(g, [[8, -400], [200, -250], [8, -110]], CREAM); poly(g, [[-8, -360], [-170, -230], [-8, -120]], shade(CREAM, 0.9)); poly(g, [[0, -420], [60, -440], [0, -460]], RED); g.restore(); },
  train(g, o) { const t = o.t || 0; rr(g, -240, -190, 330, 150, 10); g.fillStyle = o.c || '#2B3A55'; g.fill(); rr(g, 90, -250, 130, 210, 8); g.fillStyle = shade(o.c || '#2B3A55', 1.25); g.fill(); rr(g, 110, -230, 90, 70, 6); g.fillStyle = '#FFE9A8'; g.fill(); rr(g, -240, -250, 60, 70, 6); g.fillStyle = '#2B1A10'; g.fill(); [-170, -60, 50, 160].forEach((x, i) => { circ(g, x, -34, 38, '#2B1A10'); circ(g, x, -34, 8, GOLD); limb(g, [[x, -34], [x + Math.cos(t * 6 + i) * 20, -34 + Math.sin(t * 6 + i) * 20]], GOLD, 4); }); poly(g, [[220, -40], [260, -10], [220, -10]], GOLD); },
  rails(g, o) { g.fillStyle = WOOD_D; for (let x = -360; x <= 360; x += 60) g.fillRect(x - 9, -16, 18, 32); g.fillStyle = '#8C8F99'; g.fillRect(-380, -10, 760, 8); },
  // ---- events ----
  fire(g, o) { const t = o.t || 0, s = o.s || 1; [-60, 0, 62].forEach((x, i) => flame(g, x, 0, 1.0 + (i === 1 ? 0.5 : 0) * s, t, i * 2)); },
  smoke(g, o) { const t = o.t || 0; for (let i = 0; i < 8; i++) { const u = ((t * 0.4 + i / 8) % 1), a = (1 - u) * 0.5; circ(g, Math.sin(i * 3 + t) * 30 * u, -u * 420, 34 + u * 70, `rgba(90,90,110,${a})`); } },
  water(g, o) { const t = o.t || 0, h = 80 + clamp(t / 2) * 120; g.beginPath(); g.moveTo(-600, 0); for (let x = -600; x <= 600; x += 20) g.lineTo(x, -h + Math.sin(x * 0.02 + t * 3) * 10); g.lineTo(600, 0); g.closePath(); g.fillStyle = 'rgba(63,127,196,0.78)'; g.fill(); },
  crowd(g, o) { // a crowd of little cut-out people, cheering
    const t = o.t || 0, LOOKS = [{ body: '#F26B5B', hat: 'cap', hatCol: '#8C5A3A', hairStyle: 'short' }, { body: '#3FA7A0', hairStyle: 'messy', hair: '#4A3020' }, { body: '#F4C542', hat: 'bowler', hatCol: '#2B2638', extra: ['mustache'] },
      { body: '#8C6FC9', dress: true, hairStyle: 'long', hair: '#7A4A2A', hat: 'bonnet', hatCol: '#F4EAD0', skin: '#C98B5E' }, { body: '#5B79B8', hairStyle: 'curly', hair: '#1B1410', skin: '#9C6240' }, { body: '#C8283A', hat: 'tophat', hatCol: '#2B2638', hairStyle: 'side' }, { body: '#7FB6A0', hairStyle: 'bun', hair: '#2B1A10', dress: true }];
    for (let i = 0; i < 9; i++) { const row = i % 2, x = -330 + i * 82 + rnd(i) * 16, up = Math.abs(Math.sin(t * 5 + i * 1.7)), look = { ...LOOKS[i % LOOKS.length], skin: LOOKS[i % LOOKS.length].skin || ['#E0A97A', '#F1C9A0', '#C98B5E'][i % 3] };
      g.save(); g.translate(x, -row * 26); g.scale(0.5 - row * 0.04, 0.5 - row * 0.04); g.translate(0, -up * 26); g.scale(3, 3); drawPerson(g, look, { mood: i % 3 === 0 ? 'laugh' : 'happy', armL: up > 0.5 ? 'both_up' : 'down', armR: up > 0.5 ? 'both_up' : 'point_up', t: t + i, legs: 'stand' }); g.restore(); } },
  rubble(g, o) { for (let i = 0; i < 9; i++) { const x = -150 + rnd(i) * 300, s = 18 + rnd(i + 3) * 36; poly(g, [[x - s, 0], [x + s, 0], [x + s * 0.5, -s * 1.3], [x - s * 0.7, -s]], i % 2 ? STONE : STONE_D); } },
  sparkle(g, o) { const t = o.t || 0; for (let i = 0; i < 6; i++) { const a = i * 1.05 + t, r = 80 + Math.sin(t * 3 + i) * 12; const x = Math.cos(a) * r, y = -90 + Math.sin(a) * r * 0.7, s = 10 + Math.abs(Math.sin(t * 4 + i * 2)) * 10; poly(g, [[x, y - s], [x + s * 0.3, y - s * 0.3], [x + s, y], [x + s * 0.3, y + s * 0.3], [x, y + s], [x - s * 0.3, y + s * 0.3], [x - s, y], [x - s * 0.3, y - s * 0.3]], GOLD); } },
};

// ---- custom props: a blueprint of plain shapes. Coordinates: x -50..50 (left to right), y 0..100 (up from the ground), sizes in the same units ----
export const SHAPES = ['rect', 'circle', 'ellipse', 'poly', 'line', 'text'];
export function drawBlueprint(g, bp, o = {}) {
  const k = (bp.span || 300) / 100;
  g.save(); g.scale(k, -k);                                     // y up
  g.save(); g.scale(1, -1);
  g.restore();
  for (const p of bp.parts || []) {
    g.save(); g.translate(p.x || 0, p.y || 0); g.rotate(-(p.rot || 0) * Math.PI / 180);
    const col = p.color || '#8C5A3A';
    if (p.shape === 'rect') { g.beginPath(); g.roundRect(-p.w / 2, -p.h / 2, p.w, p.h, Math.min(p.w, p.h) * 0.12); g.fillStyle = col; g.fill(); }
    else if (p.shape === 'circle') { g.beginPath(); g.arc(0, 0, p.w / 2, 0, TAU); g.fillStyle = col; g.fill(); }
    else if (p.shape === 'ellipse') { g.beginPath(); g.ellipse(0, 0, p.w / 2, p.h / 2, 0, 0, TAU); g.fillStyle = col; g.fill(); }
    else if (p.shape === 'poly' && (p.pts || []).length >= 3) { g.beginPath(); p.pts.forEach(([x, y], i) => (i ? g.lineTo(x, y) : g.moveTo(x, y))); g.closePath(); g.fillStyle = col; g.fill(); }
    else if (p.shape === 'line' && (p.pts || []).length >= 2) { g.beginPath(); p.pts.forEach(([x, y], i) => (i ? g.lineTo(x, y) : g.moveTo(x, y))); g.strokeStyle = col; g.lineWidth = p.w || 2; g.lineCap = 'round'; g.lineJoin = 'round'; g.stroke(); }
    else if (p.shape === 'text') { g.scale(1, -1); g.fillStyle = col; g.textAlign = 'center'; g.textBaseline = 'middle'; g.font = `900 ${p.h || 12}px Inter, sans-serif`; g.fillText(String(p.text || '').slice(0, 24), 0, 0); }
    g.restore();
  }
  g.restore();
}

// rough size [width, height] in px at scale 1: used to frame the camera and to centre a prop on the host's story panel
export const PROP_SIZE = { house: [520, 500], shop: [560, 430], barn: [540, 380], tent: [440, 360], tree: [300, 520], pine: [300, 330], bush: [200, 110], fence: [500, 130], lamp: [80, 560], signpost: [230, 330], sign: [300, 260], poster: [230, 300], crate: [140, 140], barrel: [140, 180], table: [380, 230], desk: [400, 230], chair: [120, 300], bookshelf: [320, 520], book: [120, 50], openbook: [220, 140], scroll: [180, 120], letter: [160, 110], coin: [100, 100], coins: [100, 90], key: [60, 100], bell: [120, 120], bucket: [100, 90], shovel: [70, 420], hammer: [100, 190], chisel: [16, 150], ladder: [70, 360], lightbulb: [112, 160], globe: [140, 200], clock: [180, 200], telescope: [300, 200], podium: [210, 200], flag: [220, 420], ticket: [180, 90], stone_block: [330, 200], stone_giant: [520, 130], pit: [380, 60], mound: [340, 100], wagon: [340, 200], ship: [520, 480], train: [500, 260], rails: [760, 32], fire: [200, 100], smoke: [100, 420], water: [900, 200], crowd: [740, 260], rubble: [300, 80], sparkle: [200, 200] };
export const propSize = (name, custom = {}) => (custom[name] ? [custom[name].span || 300, (custom[name].span || 300) * 0.8] : PROP_SIZE[name] || [300, 300]);
export const PROP_NAMES = Object.keys(P);
export function drawProp(g, name, o = {}, custom = {}) {
  if (custom[name]) { drawBlueprint(g, custom[name], o); return true; }
  if (P[name]) { g.save(); P[name](g, o); g.restore(); return true; }
  return false;
}
