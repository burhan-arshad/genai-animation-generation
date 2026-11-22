// Flat vector people. One drawing function for the hero and for every character of a story.
// Units: feet at (0,0), the head centre at (0,-135), a cap reaches y = -172. The film draws it at 3 px per unit (about 520 px tall).
// The look fields are the ones of brand/brand.json: body, pattern, patCol, hat, hatCol, neck, neckCol, extra[], hair, hairStyle, satchel, kid
// plus skin, pants, shoes, dress.
import { TAU, clamp, lerp, shade, circ, ell, poly, rr, limb, alpha } from './util.js';

export const MOODS = ['neutral', 'happy', 'smug', 'laugh', 'shock', 'worried', 'angry', 'sad', 'sly', 'proud', 'tired', 'dizzy', 'think'];
export const HATS = ['none', 'cap', 'tophat', 'bowler', 'crown', 'helmet', 'bonnet', 'turban', 'beret', 'sailor'];
export const HAIRS = ['messy', 'side', 'curly', 'short', 'bald', 'long', 'bun'];
export const NECKS = ['none', 'scarf', 'bowtie', 'tie', 'collar'];
export const PATTERNS = ['plain', 'vest', 'stripes', 'check', 'apron', 'overalls'];
export const EXTRAS = ['glasses', 'blush', 'mustache', 'beard', 'freckles', 'monocle'];
export const SKINS = ['#E0A97A', '#F1C9A0', '#C98B5E', '#9C6240', '#6F4430'];

// arm poses: [shoulder angle, elbow bend] in degrees. 0 = hanging down, 90 = out sideways, 180 = straight up.
export const ARMS = {
  down: [8, 6], hip: [40, -70], present: [70, 60], point: [92, 4], point_up: [140, 10], wave: [150, 25], both_up: [165, 10],
  chin: [35, 185], cheeks: [60, 147], shrug: [52, 38], hold: [45, -95], reach: [100, 20], cross: [20, -150], clap: [25, -125], back: [-10, -5],
};
const POSE_SIDE = (name, side) => { const a = ARMS[name] || ARMS.down; return a; };

export function armAngles(spec, t) {
  // spec: pose name or [a, b]; "wave" swings, "talk" gestures slowly
  let [a, b] = Array.isArray(spec) ? spec : (ARMS[spec] || ARMS.down);
  if (spec === 'wave') b += Math.sin(t * 9) * 22;
  return [a, b];
}

function face(g, st, look, skin) {
  const m = st.mood || 'neutral', lk = st.look || [0, 0], hasG = (look.extra || []).includes('glasses');
  const ox = lk[0] * 3, oy = lk[1] * 2, blink = (st.blink || 0) > 0.5;
  const ink = '#1A1420', brow = '#2B1A10', lip = '#7A2E2A';
  const B = { // brow lift (negative = higher) and tilt (positive = inner end down) for [left, right]
    neutral: [[0, 0], [0, 0]], happy: [[-3, 0], [-3, 0]], smug: [[0, 5], [-5, -3]], laugh: [[-5, 0], [-5, 0]], shock: [[-9, 0], [-9, 0]], worried: [[-3, -7], [-3, -7]],
    angry: [[2, 8], [2, 8]], sad: [[-1, -8], [-1, -8]], sly: [[2, 5], [-4, -2]], proud: [[-4, 0], [-4, 0]], tired: [[3, -2], [3, -2]], dizzy: [[-2, 0], [-2, 0]], think: [[0, 3], [-7, -4]],
  }[m] || [[0, 0], [0, 0]];
  const ex = [-12, 12], ey = -132, extras = look.extra || [];
  const cheek = `rgba(242,107,91,${extras.includes('blush') ? 0.5 : 0.28})`;
  circ(g, -21, -120, 5.6, cheek); circ(g, 21, -120, 5.6, cheek);                       // soft cheeks for everybody: it makes a face friendly
  ex.forEach((x, i) => {
    const px = x + ox, py = ey + oy, outer = i === 0 ? -1 : 1;
    if (hasG) { circ(g, x, ey, 10.8, 'rgba(255,255,255,0.95)'); g.beginPath(); g.arc(x, ey, 10.8, 0, TAU); g.strokeStyle = ink; g.lineWidth = 2.6; g.stroke(); }
    else circ(g, x, ey, 8.2, '#FFFFFF');
    if (blink || m === 'laugh' || m === 'proud') { g.beginPath(); g.arc(x, ey + 1.5, 5.6, Math.PI * 1.1, Math.PI * 1.9); g.strokeStyle = ink; g.lineWidth = 2.6; g.lineCap = 'round'; g.stroke(); return; }
    if (m === 'dizzy') { g.beginPath(); for (let a = 0; a < 12; a += 0.3) { const r = a * 0.5; g.lineTo(x + Math.cos(a) * r, ey + Math.sin(a) * r); } g.strokeStyle = ink; g.lineWidth = 1.8; g.stroke(); return; }
    const pr = m === 'shock' ? 3 : 4.7;
    circ(g, px, py, pr, ink);
    circ(g, px - 1.6, py - 1.8, 1.8, '#FFFFFF'); circ(g, px + 1.5, py + 1.6, 0.9, 'rgba(255,255,255,0.85)');       // two highlights: the eyes shine
    if (look.dress) { g.beginPath(); g.moveTo(x + outer * 8, ey - 3); g.lineTo(x + outer * 12.5, ey - 7.5); g.moveTo(x + outer * 9, ey - 0.5); g.lineTo(x + outer * 13.5, ey - 2); g.strokeStyle = ink; g.lineWidth = 2; g.lineCap = 'round'; g.stroke(); }
    if (m === 'tired' || m === 'sly') { const lid = m === 'tired' ? 11 : 8; g.save(); g.beginPath(); g.arc(x, ey, hasG ? 10.2 : 7.8, 0, TAU); g.clip(); g.fillStyle = skin; g.fillRect(x - 12, ey - 12, 24, lid + 1); g.restore(); g.beginPath(); g.moveTo(x - 8, ey - 12 + lid + 1); g.lineTo(x + 8, ey - 12 + lid + 1); g.strokeStyle = ink; g.lineWidth = 2.2; g.stroke(); }
  });
  if (hasG) { g.beginPath(); g.moveTo(-3, ey); g.lineTo(3, ey); g.strokeStyle = ink; g.lineWidth = 2.6; g.stroke(); }
  // brows
  ex.forEach((x, i) => {
    const [lift, tilt] = B[i], o = i === 0 ? -1 : 1, y = -147 + lift;
    g.beginPath(); g.moveTo(x + o * 9, y - tilt * 0.3);
    g.quadraticCurveTo(x, y - 4 - Math.abs(tilt) * 0.15, x - o * 9, y + tilt * 0.55);
    g.strokeStyle = brow; g.lineWidth = 3; g.lineCap = 'round'; g.stroke();
  });
  // nose
  ell(g, ox * 0.6, -123 + oy * 0.5, 3.1, 2.6, shade(skin, 0.86));
  // freckles, moustache, monocle: drawn before the mouth, so they stay while he talks
  const ex2 = look.extra || [];
  if (ex2.includes('freckles')) [[-18, -122], [-13, -119], [-22, -118], [18, -122], [13, -119], [22, -118]].forEach(([x, y]) => circ(g, x, y, 1.3, shade(skin, 0.7)));
  if (ex2.includes('mustache')) { g.beginPath(); g.moveTo(-14, -116); g.quadraticCurveTo(-6, -124, 0, -118); g.quadraticCurveTo(6, -124, 14, -116); g.quadraticCurveTo(6, -111, 0, -114); g.quadraticCurveTo(-6, -111, -14, -116); g.fillStyle = look.hair || '#4A3020'; g.fill(); }
  if (ex2.includes('monocle')) { g.beginPath(); g.arc(12, ey, 11, 0, TAU); g.strokeStyle = '#C98B2E'; g.lineWidth = 2.2; g.stroke(); g.beginPath(); g.moveTo(12, ey + 11); g.quadraticCurveTo(16, -105, 22, -98); g.stroke(); }

  // mouth
  const mx = ox * 0.5, my = -111, talk = st.talk || 0;
  g.lineCap = 'round'; g.lineJoin = 'round';
  const open = (w, h) => { g.beginPath(); g.ellipse(mx, my + 2, w, h, 0, 0, TAU); g.fillStyle = lip; g.fill(); if (h > 5) { g.beginPath(); g.ellipse(mx, my + 2 + h * 0.45, w * 0.6, h * 0.4, 0, 0, TAU); g.fillStyle = '#D9645E'; g.fill(); } };
  if (talk > 0.08 && m !== 'shock') {                              // a D-shaped mouth that opens and closes, with a smile at the corners
    const w = 6 + talk * 3.5, h = 1 + talk * 6.5;
    g.beginPath(); g.moveTo(mx - w, my - 0.5); g.quadraticCurveTo(mx, my - 2.4, mx + w, my - 0.5); g.quadraticCurveTo(mx, my + h * 2.3, mx - w, my - 0.5); g.closePath(); g.fillStyle = lip; g.fill();
    if (h > 3.2) { g.save(); g.clip(); ell(g, mx, my + h * 1.15, w * 0.62, h * 0.55, '#E06B66'); g.restore(); }
    return;
  }
  const line = (pts, col = lip, w = 2.8) => { g.beginPath(); pts.forEach(([x, y], k) => (k ? g.lineTo(x, y) : g.moveTo(x, y))); g.strokeStyle = col; g.lineWidth = w; g.stroke(); };
  const curve = (x0, y0, cx, cy, x1, y1, col = lip, w = 2.8) => { g.beginPath(); g.moveTo(x0, y0); g.quadraticCurveTo(cx, cy, x1, y1); g.strokeStyle = col; g.lineWidth = w; g.stroke(); };
  if (m === 'happy') { g.beginPath(); g.moveTo(mx - 9, my - 1); g.quadraticCurveTo(mx, my + 14, mx + 9, my - 1); g.closePath(); g.fillStyle = lip; g.fill(); g.beginPath(); g.moveTo(mx - 6, my + 1); g.lineTo(mx + 6, my + 1); g.lineTo(mx + 4, my + 4); g.lineTo(mx - 4, my + 4); g.closePath(); g.fillStyle = '#FFFFFF'; g.fill(); }
  else if (m === 'laugh') { g.beginPath(); g.moveTo(mx - 11, my - 3); g.quadraticCurveTo(mx, my + 20, mx + 11, my - 3); g.closePath(); g.fillStyle = lip; g.fill(); g.beginPath(); g.moveTo(mx - 9, my - 2); g.lineTo(mx + 9, my - 2); g.lineTo(mx + 7, my + 2); g.lineTo(mx - 7, my + 2); g.closePath(); g.fillStyle = '#FFFFFF'; g.fill(); }
  else if (m === 'shock') open(5, 7.5);
  else if (m === 'worried') curve(mx - 8, my + 3, mx - 3, my - 3, mx, my + 1) || curve(mx, my + 1, mx + 3, my + 5, mx + 8, my - 1);
  else if (m === 'angry' || m === 'sad') curve(mx - 8, my + 5, mx, my - 3, mx + 8, my + 5);
  else if (m === 'smug' || m === 'sly') curve(mx - 7, my + 2, mx + 3, my + 4, mx + 9, my - 3);
  else if (m === 'proud') curve(mx - 8, my, mx, my + 6, mx + 8, my);
  else if (m === 'tired') line([[mx - 6, my + 2], [mx + 6, my + 2]]);
  else if (m === 'dizzy') curve(mx - 7, my + 2, mx - 2, my - 3, mx + 1, my + 2) || curve(mx + 1, my + 2, mx + 4, my + 6, mx + 8, my + 1);
  else if (m === 'think') curve(mx - 6, my + 3, mx + 2, my + 1, mx + 8, my + 4);
  else curve(mx - 6, my + 1, mx, my + 5, mx + 6, my + 1);          // neutral: a small smile
}

// ---- hair: smooth shapes only (no jagged polygons): a rounded cap with a wavy fringe, soft tufts, a gloss band ----
const tuft = (g, x, y, dx, h, w = 7) => { g.beginPath(); g.moveTo(x - w, y); g.quadraticCurveTo(x - w * 0.5, y - h * 0.75, x + dx, y - h); g.quadraticCurveTo(x + w * 0.2, y - h * 0.45, x + w, y); g.closePath(); g.fill(); };
function capPath(g, style) {
  g.beginPath(); g.moveTo(-31, -130);
  g.bezierCurveTo(-38, -158, -16, -177, 0, -177); g.bezierCurveTo(16, -177, 38, -158, 31, -130);
  if (style === 'side') {                                     // a side part: the fringe sweeps from the left over the forehead
    g.bezierCurveTo(29, -140, 25, -148, 16, -152); g.bezierCurveTo(4, -158, -14, -154, -24, -143); g.bezierCurveTo(-27, -138, -29, -134, -31, -130);
  } else if (style === 'short') {
    g.bezierCurveTo(30, -139, 26, -146, 18, -148); g.bezierCurveTo(8, -144, -4, -149, -14, -147); g.bezierCurveTo(-22, -145, -29, -138, -31, -130);
  } else {                                                    // messy, curly, bun, long: a wavy fringe in three soft scallops
    g.bezierCurveTo(29, -139, 27, -146, 21, -149); g.bezierCurveTo(15, -143, 9, -152, 3, -148); g.bezierCurveTo(-3, -143, -10, -154, -17, -148); g.bezierCurveTo(-24, -145, -29, -139, -31, -130);
  }
  g.closePath();
}
function hair(g, look, col, front) {
  const style = look.hairStyle || 'short';
  if (style === 'bald') return;
  if (!front) {                                               // behind the head
    if (style === 'long') { g.beginPath(); g.moveTo(-33, -138); g.bezierCurveTo(-44, -120, -42, -86, -30, -76); g.quadraticCurveTo(0, -70, 30, -76); g.bezierCurveTo(42, -86, 44, -120, 33, -138); g.closePath(); g.fillStyle = shade(col, 0.82); g.fill(); }
    if (style === 'bun') { circ(g, 0, -181, 12, shade(col, 0.95)); g.beginPath(); g.moveTo(-9, -171); g.lineTo(9, -171); g.lineWidth = 4; g.strokeStyle = '#F26B5B'; g.lineCap = 'round'; g.stroke(); }
    return;
  }
  g.fillStyle = col;
  if (style === 'curly') {                                    // a cloud of curls around the top of the head
    for (let i = 0; i <= 10; i++) { const a = Math.PI * (1.04 + 0.92 * i / 10); circ(g, Math.cos(a) * 29, -135 + Math.sin(a) * 28, 9.5 + (i % 2) * 1.5, col); }
  }
  capPath(g, style); g.fillStyle = col; g.fill();
  if (style === 'messy') { g.fillStyle = col; tuft(g, -8, -174, -5, 11, 8); tuft(g, 4, -176, 6, 13, 7.5); circ(g, 14, -171, 6.5, col); }
  if (style === 'long') {                                     // two soft locks in front of the ears
    [-1, 1].forEach((s) => { g.beginPath(); g.moveTo(s * 29, -146); g.bezierCurveTo(s * 40, -134, s * 40, -108, s * 31, -98); g.bezierCurveTo(s * 28, -112, s * 27, -126, s * 24, -136); g.closePath(); g.fillStyle = col; g.fill(); });
  }
  g.beginPath(); g.arc(-2, -134, 25, Math.PI * 1.13, Math.PI * 1.36);   // a soft gloss band inside the cap
  g.strokeStyle = 'rgba(255,255,255,0.11)'; g.lineWidth = 5; g.lineCap = 'round'; g.stroke();
}

function hat(g, look) {
  const h = look.hat || 'none', c = look.hatCol || '#8C5A3A';
  if (h === 'none') return;
  const dk = shade(c, 0.78);
  if (h === 'cap') { g.beginPath(); g.moveTo(-32, -146); g.quadraticCurveTo(-30, -172, 0, -172); g.quadraticCurveTo(30, -172, 32, -146); g.quadraticCurveTo(16, -150, 0, -150); g.quadraticCurveTo(-16, -150, -32, -146); g.fillStyle = c; g.fill(); g.beginPath(); g.moveTo(-4, -149); g.quadraticCurveTo(18, -147, 36, -140); g.quadraticCurveTo(28, -153, 12, -152); g.fillStyle = dk; g.fill(); circ(g, 0, -172, 3, dk); }
  if (h === 'tophat') { rr(g, -22, -208, 44, 54, 4); g.fillStyle = c; g.fill(); ell(g, 0, -153, 38, 7, dk); rr(g, -22, -170, 44, 9, 0); g.fillStyle = look.neckCol || '#C8283A'; g.fill(); }
  if (h === 'bowler') { g.beginPath(); g.moveTo(-26, -152); g.quadraticCurveTo(-26, -186, 0, -186); g.quadraticCurveTo(26, -186, 26, -152); g.closePath(); g.fillStyle = c; g.fill(); ell(g, 0, -151, 38, 6, dk); }
  if (h === 'crown') { poly(g, [[-26, -152], [-26, -184], [-13, -168], [0, -190], [13, -168], [26, -184], [26, -152]], '#F4C542'); circ(g, 0, -190, 4, '#F26B5B'); circ(g, -26, -184, 3.5, '#F26B5B'); circ(g, 26, -184, 3.5, '#F26B5B'); rr(g, -26, -158, 52, 8, 2); g.fillStyle = '#C98B2E'; g.fill(); }
  if (h === 'helmet') { g.beginPath(); g.moveTo(-33, -134); g.quadraticCurveTo(-34, -178, 0, -178); g.quadraticCurveTo(34, -178, 33, -134); g.lineTo(26, -134); g.lineTo(26, -146); g.lineTo(-26, -146); g.lineTo(-26, -134); g.closePath(); g.fillStyle = c; g.fill(); rr(g, -3, -190, 6, 14, 3); g.fillStyle = '#C8283A'; g.fill(); }
  if (h === 'bonnet') { g.beginPath(); g.moveTo(-33, -124); g.quadraticCurveTo(-40, -178, 0, -178); g.quadraticCurveTo(40, -178, 33, -124); g.quadraticCurveTo(26, -146, 0, -151); g.quadraticCurveTo(-26, -146, -33, -124); g.closePath(); g.fillStyle = c; g.fill(); g.beginPath(); g.moveTo(-28, -150); g.quadraticCurveTo(0, -156, 28, -150); g.strokeStyle = shade(c, 0.8); g.lineWidth = 3; g.stroke(); circ(g, 30, -128, 3, look.neckCol || '#F26B5B'); }
  if (h === 'turban') { ell(g, 0, -158, 36, 24, c); g.beginPath(); g.moveTo(-30, -158); g.quadraticCurveTo(0, -140, 30, -164); g.strokeStyle = dk; g.lineWidth = 4; g.stroke(); g.beginPath(); g.moveTo(-28, -170); g.quadraticCurveTo(0, -150, 28, -176); g.stroke(); circ(g, 0, -150, 4, '#F4C542'); }
  if (h === 'beret') { ell(g, 4, -166, 36, 14, c, -0.12); circ(g, 4, -180, 3, dk); }
  if (h === 'sailor') { rr(g, -28, -170, 56, 18, 8); g.fillStyle = '#F4F1E8'; g.fill(); ell(g, 0, -153, 34, 6, '#F4F1E8'); rr(g, -28, -158, 56, 5, 0); g.fillStyle = '#2F4E8F'; g.fill(); }
}

function torso(g, look, body, dress) {
  const pat = look.pattern || 'plain', pc = look.patCol || shade(body, 0.7);
  const path = () => { g.beginPath(); if (dress) { g.moveTo(-27, -100); g.quadraticCurveTo(-30, -70, -34, -12); g.lineTo(34, -12); g.quadraticCurveTo(30, -70, 27, -100); g.quadraticCurveTo(0, -92, -27, -100); } else { g.moveTo(-26, -100); g.quadraticCurveTo(-30, -60, -24, -40); g.lineTo(24, -40); g.quadraticCurveTo(30, -60, 26, -100); g.quadraticCurveTo(0, -92, -26, -100); } g.closePath(); };
  const gr = g.createLinearGradient(-26, -100, 26, -40); gr.addColorStop(0, shade(body, 1.14)); gr.addColorStop(1, shade(body, 0.9));
  path(); g.fillStyle = gr; g.fill();
  g.save(); path(); g.clip();
  if (pat === 'stripes') for (let y = -100; y < -10; y += 14) { g.fillStyle = pc; g.fillRect(-40, y, 80, 6); }
  if (pat === 'check') { g.fillStyle = alpha(pc, 0.55); for (let y = -100; y < -10; y += 16) g.fillRect(-40, y, 80, 7); for (let x = -40; x < 40; x += 16) g.fillRect(x, -104, 7, 100); }
  if (pat === 'vest') { poly(g, [[-26, -100], [-12, -100], [0, -66], [12, -100], [26, -100], [26, -40], [-26, -40]], pc); poly(g, [[-12, -100], [12, -100], [0, -72]], '#F4EAD0'); [-62, -52, -42].forEach((y) => circ(g, 0, y, 2, '#F4C542')); }
  if (pat === 'apron') { rr(g, -18, -88, 36, 52, 6); g.fillStyle = pc; g.fill(); g.fillRect(-4, -100, 8, 16); }
  if (pat === 'overalls') { g.fillStyle = pc; g.fillRect(-18, -100, 8, 30); g.fillRect(10, -100, 8, 30); rr(g, -18, -76, 36, 40, 4); g.fill(); circ(g, -14, -72, 2.2, '#F4C542'); circ(g, 14, -72, 2.2, '#F4C542'); }
  g.restore();
  path(); g.strokeStyle = shade(body, 0.74); g.lineWidth = 1.9; g.lineJoin = 'round'; g.stroke();
  if (pat === 'plain' || pat === 'stripes' || pat === 'check' || pat === 'apron') poly(g, [[-9, -100], [9, -100], [0, -86]], 'rgba(244,234,208,0.9)');
}

function neckItem(g, look) {
  const n = look.neck || 'none', c = look.neckCol || '#F26B5B';
  if (n === 'scarf') { g.beginPath(); g.moveTo(-22, -108); g.quadraticCurveTo(0, -100, 22, -108); g.lineTo(24, -96); g.quadraticCurveTo(0, -88, -24, -96); g.closePath(); g.fillStyle = c; g.fill(); poly(g, [[10, -98], [26, -66], [14, -62], [4, -90]], shade(c, 0.82)); }
  if (n === 'bowtie') { poly(g, [[-11, -99], [0, -94], [-11, -89]], c); poly(g, [[11, -99], [0, -94], [11, -89]], c); circ(g, 0, -94, 2.6, shade(c, 0.8)); }
  if (n === 'tie') { poly(g, [[-3, -98], [3, -98], [6, -64], [0, -58], [-6, -64]], c); }
  if (n === 'collar') { poly(g, [[-14, -102], [0, -92], [-6, -100]], '#F4F1E8'); poly(g, [[14, -102], [0, -92], [6, -100]], '#F4F1E8'); }
}

function satchel(g, look) {
  const c = look.satchel; if (!c) return;
  g.save();
  g.translate(34, -62); g.rotate(14 * Math.PI / 180); rr(g, -4, -16, 8, 32, 4); g.fillStyle = '#F4EAD0'; g.fill(); g.fillStyle = '#F26B5B'; g.fillRect(-4, -4, 8, 6);
  g.restore();
  limb(g, [[-24, -98], [20, -42]], shade(c, 0.78), 7);
  rr(g, 12, -54, 26, 22, 4); g.fillStyle = c; g.fill(); rr(g, 12, -54, 26, 9, 3); g.fillStyle = shade(c, 0.8); g.fill(); circ(g, 25, -42, 2.3, '#F4C542');
}

export function armPoints(side, a, b, len = 24) {
  const s = side === 'l' ? -1 : 1, sx = s * 26, sy = -92;
  const r = (d) => (d * Math.PI) / 180;
  const e = [sx + s * Math.sin(r(a)) * len, sy + Math.cos(r(a)) * len];
  const h = [e[0] + s * Math.sin(r(a + b)) * (len - 2), e[1] + Math.cos(r(a + b)) * (len - 2)];
  return [[sx, sy], e, h];
}

/** draw one person. st: { mood, armL, armR (pose name or [a,b]), legs: stand|walk|run|sit, phase, look:[dx,dy], blink, talk, lean, t, onHand(side,x,y,angle) } */
export function drawPerson(g, look, st = {}) {
  const skin = look.skin || SKINS[0], body = look.body || '#3FA7A0', pants = look.pants || '#3A4F8F', shoes = look.shoes || '#6B4526', hairCol = look.hair || '#2B2118';
  const t = st.t || 0, dress = !!look.dress, legs = st.legs || 'stand', ph = st.phase || 0;
  g.save();
  if (st.lean) { g.rotate(st.lean * Math.PI / 180); }
  g.scale(1, 1 + 0.011 * Math.sin(t * 2.3));                       // breathing
  let down = 0;
  if (legs === 'sit') down = 24;
  g.translate(0, down);
  // legs
  const swing = legs === 'walk' ? 18 : legs === 'run' ? 32 : 0;
  [-1, 1].forEach((s) => {
    const a = Math.sin(ph) * swing * s, lift = legs === 'walk' || legs === 'run' ? Math.max(0, Math.sin(ph + (s > 0 ? Math.PI : 0))) * (legs === 'run' ? 8 : 4) : 0;
    g.save(); g.translate(s * 10, -40); g.rotate(a * Math.PI / 180 * -1 * (s)); g.translate(0, -lift * 0);
    if (!dress) { rr(g, -6.5, 0, 13, legs === 'sit' ? 22 : 36, 5); g.fillStyle = pants; g.fill(); g.strokeStyle = shade(pants, 0.72); g.lineWidth = 1.6; g.stroke(); }
    const fy = legs === 'sit' ? 22 : 38; ell(g, s * 2, fy + 0.8, 12.5, 5.6, shade(shoes, 0.62)); ell(g, s * 2, fy, 11.5, 5, shoes); ell(g, s * 2 - 3, fy - 1.6, 4, 1.6, 'rgba(255,255,255,0.28)');
    g.restore();
  });
  if (legs === 'sit') { /* feet forward */ }
  // arms behind torso are not used: the arms are drawn in front, like a cut-out
  // hair behind the head
  hair(g, look, hairCol, false);
  torso(g, look, body, dress);
  satchel(g, look);
  neckItem(g, look);
  // arms
  const sleeve = shade(body, 0.92), handCol = skin;
  [['l', st.armL], ['r', st.armR]].forEach(([side, spec]) => {
    const [a, b] = armAngles(spec || 'down', t);
    const [s0, e, h] = armPoints(side, a, b);
    limb(g, [s0, e, h], shade(sleeve, 0.78), 12.4);
    limb(g, [s0, e, h], sleeve, 10);
    circ(g, h[0], h[1], 6.6, shade(handCol, 0.7)); circ(g, h[0], h[1], 5.6, handCol);
    if (st.onHand) st.onHand(side, h[0], h[1], a + b);
  });
  // head (tilts and bobs around the neck)
  g.save();
  g.translate(0, -105 + (st.headDy || 0)); g.rotate((st.headTilt || 0) * Math.PI / 180); g.translate(0, 105);
  { const hs = look.kid ? 1.24 : 1.1; g.translate(0, -105); g.scale(hs, hs); g.translate(0, 105); }                  // a big round head is cute
  circ(g, -30, -132, 6.6, shade(skin, 0.7)); circ(g, 30, -132, 6.6, shade(skin, 0.7)); circ(g, -30, -132, 5.6, shade(skin, 0.94)); circ(g, 30, -132, 5.6, shade(skin, 0.94));
  circ(g, 0, -135, 31, shade(skin, 0.72)); circ(g, 0, -135, 29.8, skin);
  const ex = look.extra || [];
  if (ex.includes('beard')) { g.beginPath(); g.moveTo(-29, -128); g.quadraticCurveTo(-30, -104, 0, -100); g.quadraticCurveTo(30, -104, 29, -128); g.quadraticCurveTo(20, -113, 0, -111); g.quadraticCurveTo(-20, -113, -29, -128); g.fillStyle = hairCol; g.fill(); }
  hair(g, look, hairCol, true);
  face(g, st, look, skin);
  hat(g, look);
  g.restore();
  g.restore();
}

/** a soft ground shadow for a person standing at the origin */
export function personShadow(g, w = 40) { ell(g, 4, 0, w, w * 0.2, 'rgba(10,15,40,0.28)'); }

export const EMOTES = { shock: '!', think: '?', worried: 'sweat', angry: 'steam', laugh: 'ha', proud: 'star', tired: 'zzz', sly: 'idea' };
/** a small symbol that pops above the head when the mood changes (age in seconds since the change) */
export function drawEmote(g, kind, age) {
  if (age < 0 || age > 1.5) return;
  const k = eobPop(age / 0.28), out = 1 - Math.max(0, (age - 1.1) / 0.4), y = -196 - Math.min(age, 0.6) * 14;
  g.save(); g.globalAlpha = out; g.translate(34, y); g.scale(k, k);
  g.textAlign = 'center'; g.textBaseline = 'middle'; g.lineJoin = 'round';
  const word = (t, col, size = 46) => { g.font = `900 ${size}px Inter, sans-serif`; g.lineWidth = 9; g.strokeStyle = '#17203A'; g.strokeText(t, 0, 0); g.fillStyle = col; g.fillText(t, 0, 0); };
  if (kind === '!') word('!', '#F26B5B', 56);
  else if (kind === '?') word('?', '#F4C542', 56);
  else if (kind === 'ha') word('HA', '#F4C542', 40);
  else if (kind === 'zzz') word('z z', '#8FD6C8', 34);
  else if (kind === 'star') { g.rotate(age * 1.5); g.beginPath(); for (let i = 0; i < 10; i++) { const r = i % 2 ? 7 : 17, a = -Math.PI / 2 + i * Math.PI / 5; g.lineTo(Math.cos(a) * r, Math.sin(a) * r); } g.closePath(); g.fillStyle = '#F4C542'; g.fill(); g.lineWidth = 4; g.strokeStyle = '#17203A'; g.stroke(); }
  else if (kind === 'sweat') { g.translate(-22, 22 + age * 12); g.beginPath(); g.moveTo(0, -18); g.quadraticCurveTo(14, 4, 0, 14); g.quadraticCurveTo(-14, 4, 0, -18); g.fillStyle = '#8FD6C8'; g.fill(); g.lineWidth = 4; g.strokeStyle = '#17203A'; g.stroke(); }
  else if (kind === 'steam') { for (let i = -1; i <= 1; i += 2) { g.beginPath(); g.arc(i * 14, 0, 11 + Math.sin(age * 14) * 2, 0, TAU); g.fillStyle = '#F26B5B'; g.fill(); } }
  else if (kind === 'idea') { circ(g, 0, 0, 17, '#FFE9A8'); g.fillStyle = '#8C8F99'; g.fillRect(-8, 15, 16, 10); }
  g.restore();
}
const eobPop = (t) => { t = Math.max(0, Math.min(1, t)); const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2); };
