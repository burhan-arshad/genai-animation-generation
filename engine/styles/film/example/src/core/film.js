// The film: turns story.json (shots with absolute times, written by shorts_agent/filmboard.py) into pictures.
// draw(g, t) is a pure function of the film time t. Cameras move in every shot, sets have parallax layers, people act on beats.
import { W, H, TAU, clamp, lerp, seg, eo, eio, eob, ease, rnd, circ, ell, rr, shade, alpha } from './util.js';
import { drawPerson, personShadow, armAngles, drawEmote, EMOTES, ARMS } from './people.js';
import { drawProp, propSize } from './props.js';
import { makeSet, WW } from './worlds.js';
import { drawFx, vignette, lightWash, grain, makeGrainTile, grade } from './fx.js';

const U = 3;                                        // pixels per drawing unit of a person
const FRAMING = { panel: [1.45, 0], establishing: [0.75, 700], wide: [0.95, 520], full: [1.15, 430], medium: [1.6, 330], close: [2.4, 390], extreme_close: [3.6, 405] };
export const CAMERAS = ['static', 'push_in', 'pull_out', 'pan_left', 'pan_right', 'drift', 'crane_down', 'crane_up', 'punch_in', 'handheld'];
export const EFFECTS = ['none', 'shake', 'quake', 'flash', 'storm', 'dutch'];
export const TRANSITIONS = ['cut', 'fade', 'dissolve', 'whip', 'wipe', 'flash', 'iris'];
export const ACTS = ['jump', 'shake', 'bow', 'pop', 'nod'];
export const PROP_MOVES = ['pop', 'rise', 'drop', 'slide_l', 'slide_r', 'grow', 'shake', 'spin', 'none'];
const TD = 0.36;                                    // transition length
const wx = (pct) => 600 + pct * 12;                  // stage percent -> world x (the stage is 1200 px wide, centred on x 1200)
const DEPTH = [0.86, 1, 1.15];

export function createFilm({ story, hero, makeCanvas }) {
  const shots = (story.shots || []).slice().sort((a, b) => a.at - b.at);
  const sets = {};
  Object.entries(story.sets || {}).forEach(([id, d]) => { sets[id] = makeSet(d); });
  const firstSet = Object.values(sets)[0] || makeSet({ kind: 'field' });
  const custom = story.custom || {};
  const grainTile = makeGrainTile(makeCanvas);
  const softCache = {};
  /** draws one layer at a lower resolution and scales it up: far scenery and the foreground get a soft, out-of-focus look, and it is cheap (no blur filter) */
  function drawSoft(g, cam, l, t, sf) {
    const oc = softCache[sf] || (softCache[sf] = makeCanvas(Math.round(W * sf), Math.round(H * sf))), x = oc.getContext('2d');
    x.setTransform(1, 0, 0, 1, 0, 0); x.clearRect(0, 0, oc.width, oc.height); x.setTransform(sf, 0, 0, sf, 0, 0);
    x.save(); place(x, cam, l.p); l.draw(x, t); x.restore();
    g.save(); g.imageSmoothingEnabled = true; g.imageSmoothingQuality = 'high'; g.drawImage(oc, 0, 0, W, H); g.restore();
  }
  const lookOf = (who) => (who === 'hero' ? hero : (story.cast || {})[who]);
  const duration = story.duration || (shots.length ? shots[shots.length - 1].end : 1);

  // ---- camera ----
  function frameTarget(sh, z0) {
    const xs = [], close = sh.framing === 'close' || sh.framing === 'extreme_close';
    (sh.actors || []).forEach((a) => { const lo = Math.min(a.x0, a.x1 ?? a.x0), hi = Math.max(a.x0, a.x1 ?? a.x0); xs.push([wx(lo) - 150, wx(hi) + 150]); });
    if (close) return xs.length ? { cx: (xs[0][0] + xs[0][1]) / 2, z: z0 } : null;
    (sh.props || []).forEach((p) => { const w = propSize(p.name, custom)[0] * (p.s || 1) * DEPTH[clamp(Math.round(p.d ?? 1), 0, 2)]; xs.push([wx(p.x ?? 50) - w / 2, wx(p.x ?? 50) + w / 2]); });
    if (!xs.length || sh.panel) return null;
    const lo = Math.min(...xs.map((a) => a[0])), hi = Math.max(...xs.map((a) => a[1]));
    return { cx: (lo + hi) / 2, z: Math.max(0.72, Math.min(z0, 1000 / Math.max(300, hi - lo))) };
  }
  function camera(sh, set, t) {
    const z00 = (FRAMING[sh.framing] || FRAMING.medium)[0], close = sh.framing === 'close' || sh.framing === 'extreme_close';
    const fit = frameTarget(sh, z00), z0 = fit ? fit.z : z00, hf = close ? FRAMING[sh.framing][1] : 460 / z0;
    const dur = Math.max(0.1, sh.end - sh.at), u = clamp((t - sh.at) / dur), e = eio(u);
    let x = fit ? fit.cx : wx(sh.focus_x ?? 50), y = set.groundY - hf, z = z0;
    if (sh.framing === 'panel' && set.panel) { x = set.panel.x; y = set.panel.y + 130; }
    switch (sh.camera) {
      case 'push_in': z = z0 * lerp(0.92, 1.1, e); break;
      case 'pull_out': z = z0 * lerp(1.12, 0.93, e); break;
      case 'pan_left': x += lerp(150, -150, e); break;
      case 'pan_right': x += lerp(-150, 150, e); break;
      case 'drift': x += lerp(-50, 50, u); y += Math.sin(u * Math.PI) * -26; z = z0 * (1 + 0.03 * Math.sin(u * Math.PI)); break;
      case 'crane_down': y -= lerp(300, 0, e); z = z0 * lerp(0.95, 1.03, e); break;
      case 'crane_up': y -= lerp(0, 300, e); z = z0 * lerp(1.05, 0.95, e); break;
      case 'punch_in': z = z0 * lerp(0.94, 1.22, eo(clamp(u * 2.4))); break;
      case 'handheld': x += Math.sin(t * 2.1) * 14 + Math.sin(t * 5.3) * 5; y += Math.cos(t * 1.7) * 10; z = z0 * (1 + 0.012 * Math.sin(t * 1.3)); break;
      default: break;
    }
    x += Math.sin(t * 0.7 + sh.at) * 7; y += Math.cos(t * 0.9 + sh.at) * 5;                       // a camera is never perfectly still
    z *= 1 + 0.035 * (1 - eo(clamp((t - sh.at) / 0.55)));                                            // each cut settles in
    const shake = sh.effect === 'quake' ? 1 : sh.effect === 'shake' ? Math.max(0, 1 - (t - sh.at) / 0.7) : 0;
    const half = 540 / z; x = clamp(x, half - 260, WW - half + 260);
    return { x, y, z, shake };
  }
  const place = (g, cam, p) => { const z = 1 + (cam.z - 1) * p, cx = 1200 + (cam.x - 1200) * p, cy = 960 + (cam.y - 960) * p; g.translate(540, 960); g.scale(z, z); g.translate(-cx, -cy); };

  // ---- acting ----
  const poseAt = (keys, t) => { // keys: [{t, pose}] -> angles
    let i = 0; while (i + 1 < keys.length && keys[i + 1].t <= t) i++;
    const cur = armAngles(keys[i].pose, t), prev = armAngles(keys[Math.max(0, i - 1)].pose, t);
    const u = i === 0 ? 1 : eob(clamp((t - keys[i].t) / 0.36));
    return [lerp(prev[0], cur[0], u), lerp(prev[1], cur[1], u)];
  };
  function armKeys(a, side, sh) {
    const base = a.arms && typeof a.arms === 'object' && !Array.isArray(a.arms) ? a.arms[side] : a.arms, keys = [{ t: -1e9, pose: base || 'down' }];
    (a.beats || []).forEach((b) => { const v = b.arms && typeof b.arms === 'object' && !Array.isArray(b.arms) ? b.arms[side] : b.arms; if (v) keys.push({ t: b.t, pose: v }); });
    return keys.sort((p, q) => p.t - q.t);
  }

  function actorFrame(a, sh, t) {
    const t0 = a.t0 ?? sh.at, t1 = a.t1 ?? sh.end, moving = a.x1 != null && a.x1 !== a.x0 && t > t0 && t < t1;
    const x = lerp(a.x0, a.x1 ?? a.x0, eio(clamp((t - t0) / Math.max(0.1, t1 - t0))));
    let face = a.face || (a.x1 != null && a.x1 !== a.x0 ? (a.x1 > a.x0 ? 'r' : 'l') : x < 50 ? 'r' : 'l');
    let mood = a.mood || 'neutral', dy = 0, dx = 0, lean = 0, pop = 1, emote = null;
    (a.beats || []).forEach((b) => {
      if (b.t > t) return;
      if (b.mood) { mood = b.mood; emote = EMOTES[b.mood] ? { kind: EMOTES[b.mood], age: t - b.t } : null; }
      if (b.face) face = b.face;
      const age = t - b.t;
      if (b.act === 'jump' && age < 0.55) dy -= Math.sin(Math.PI * age / 0.55) * 90;
      if (b.act === 'shake' && age < 0.6) dx += Math.sin(age * 44) * 12 * (1 - age / 0.6);
      if (b.act === 'bow' && age < 0.8) lean += Math.sin(Math.PI * age / 0.8) * 16;
      if (b.act === 'nod' && age < 0.5) lean += Math.sin(Math.PI * age / 0.5 * 2) * 4;
      if (b.act === 'pop' && age < 0.4) pop += Math.sin(Math.PI * age / 0.4) * 0.14;
    });
    const talking = a.talk === true || (Array.isArray(a.talk) && t >= a.talk[0] && t <= a.talk[1]);
    return { x, face, mood, dy, dx, lean, pop, moving, talking, emote };
  }

  function drawActor(g, a, sh, set, t, cam) {
    const f = actorFrame(a, sh, t), look = lookOf(a.who); if (!look) return;
    const d = a.d ?? 1, sc = (a.s || 1) * DEPTH[clamp(Math.round(d), 0, 2)] * (look.kid ? 0.7 : 1);
    const wxp = wx(f.x) + f.dx, wy = set.groundY + (d - 1) * 70;
    g.save(); g.translate(wxp, wy);
    g.save(); g.scale(sc * 1.1, sc * 1.1); personShadow(g, 40); g.restore();
    g.translate(0, f.dy - (f.moving ? Math.abs(Math.sin(t * 9)) * 9 : 0)); g.scale(sc * U * f.pop * (f.face === 'l' ? -1 : 1), sc * U * f.pop);
    const keysL = armKeys(a, 'l', sh), keysR = armKeys(a, 'r', sh);
    let armL = poseAt(keysL, t), armR = poseAt(keysR, t);
    if (f.talking && !(a.arms && a.arms !== 'down')) armR = [lerp(8, 70, 0.5 + 0.5 * Math.sin(t * 1.9)), lerp(6, 55, 0.5 + 0.5 * Math.sin(t * 1.9))];
    if (f.moving) { const sw = Math.sin(t * 9) * 26; if (a.arms == null || (armL[0] < 20)) armL = [armL[0] + sw, armL[1]]; if (armR[0] < 20) armR = [armR[0] - sw, armR[1]]; }
    const held = a.held || {};
    const idle = (a.who.length * 1.7) % 6, sway = Math.sin(t * 1.25 + idle) * 1.6, talkBob = f.talking ? Math.abs(Math.sin(t * 8 + idle)) * 2.2 : 0;
    const st = { mood: f.mood, armL, armR, legs: f.moving ? 'walk' : (a.legs || 'stand'), phase: t * 9, lean: f.lean, headTilt: sway + (f.talking ? Math.sin(t * 3.1) * 2 : 0), headDy: -talkBob, t, blink: ((t + (a.who.length * 0.37)) % 3.3) < 0.13 ? 1 : 0,
      talk: f.talking ? 0.35 + 0.65 * Math.abs(Math.sin(t * 16 + a.who.length)) : 0, look: [a.look_x ?? 0.3, 0],
      onHand: (side, hx, hy) => { const nm = held[side]; if (!nm) return; g.save(); g.translate(hx, hy); if (f.face === 'l') g.scale(-1, 1); g.scale((a.held_s || 0.55) / U * (f.face === 'l' ? 1 : 1), (a.held_s || 0.55) / U); drawProp(g, nm, { t, text: a.held_text }, custom); g.restore(); } };
    st.armL = typeof st.armL === 'object' ? st.armL : ARMS.down; st.armR = typeof st.armR === 'object' ? st.armR : ARMS.down;
    drawPerson(g, look, st);
    if (f.emote) { g.save(); if (f.face === 'l') g.scale(-1, 1); drawEmote(g, f.emote.kind, f.emote.age); g.restore(); }
    g.restore();
  }

  function drawPropPlace(g, p, sh, set, t) {
    const age = t - (p.t0 ?? sh.at); if (age < 0) return;
    const d = p.d ?? 1, sc = (p.s || 1) * DEPTH[clamp(Math.round(d), 0, 2)], mv = p.move || 'pop';
    let ox = 0, oy = 0, k = 1, rot = p.rot || 0;
    if (mv === 'pop') k = age < 0.4 ? eob(age / 0.4) : 1;
    else if (mv === 'grow') k = eo(clamp(age / 1.2));
    else if (mv === 'rise') { oy = (1 - eo(clamp(age / 0.7))) * 260; k = clamp(age / 0.2); }
    else if (mv === 'drop') { const fall = 0.42; if (age < fall) { const u = age / fall; oy = -820 * (1 - u * u); } else { const b = age - fall; oy = -Math.abs(Math.sin(b * 13)) * 70 * Math.exp(-b * 5.5); } k = 1; }
    else if (mv === 'slide_l') ox = (1 - eo(clamp(age / 0.8))) * 700;
    else if (mv === 'slide_r') ox = -(1 - eo(clamp(age / 0.8))) * 700;
    else if (mv === 'shake') ox = Math.sin(age * 40) * 8;
    else if (mv === 'spin') rot += age * 120;
    if (p.t1 != null && t > p.t1) { const u = clamp((t - p.t1) / 0.25); k *= 1 - u; if (u >= 1) return; }
    const wxp = wx(p.x ?? 50) + ox, wyp = set.groundY + (d - 1) * 70 + oy + (p.dy || 0);
    if (!['sparkle', 'smoke', 'fire', 'water', 'crowd', 'pit', 'mound', 'rails', 'rubble', 'bell'].includes(p.name) && k > 0.05) { const w = propSize(p.name, custom)[0] * sc * k; g.save(); g.translate(wxp, wyp); ell(g, 0, 5, w * 0.46, Math.max(8, w * 0.06), 'rgba(10,15,40,0.26)'); g.restore(); }
    g.save(); g.translate(wxp, wyp); g.scale(sc * k * (p.flip ? -1 : 1), sc * k); if (rot) g.rotate(rot * Math.PI / 180);
    const ok = drawProp(g, p.name, { t: age, c: p.c, text: p.text }, custom);
    g.restore();
    return ok;
  }

  // ---- text on top of the picture ----
  function callout(g, c, t) {
    const age = t - c.t, dur = c.dur || 2.4; if (age < 0 || age > dur) return;
    const fadeOut = clamp((dur - age) / 0.25), inn = eob(clamp(age / 0.35));
    let typed = null;
    let lines = String(c.text || '').split('|').map((s) => s.trim()).filter(Boolean); if (!lines.length) return;
    const nm = lines[0].match(/^(\D*?)(\d[\d,]*)(\D*)$/);
    if (nm && !/^(1[0-9]{3}|20[0-9]{2})$/.test(nm[2]) && parseInt(nm[2].replace(/,/g, ''), 10) >= 10 && (c.style === 'pop' || c.style === 'label')) { const v = parseInt(nm[2].replace(/,/g, ''), 10), shown = Math.round(v * eo(clamp(age / 0.8))); lines = [nm[1] + shown.toLocaleString('en-US') + nm[3]]; }
    else if (c.style === 'label' || !c.style) typed = lines[0].slice(0, Math.max(1, Math.ceil(age * 34)));
    g.save(); g.globalAlpha = fadeOut; g.textAlign = 'center'; g.textBaseline = 'middle';
    const fit = (s, size, maxW) => { let fs = size; g.font = `900 ${fs}px Inter, sans-serif`; while (g.measureText(s).width > maxW && fs > 20) { fs -= 3; g.font = `900 ${fs}px Inter, sans-serif`; } return fs; };
    if (c.style === 'stamp') {
      g.translate(c.x ?? 540, c.y ?? 700); g.rotate(-0.12); const s = lerp(2.2, 1, eo(clamp(age / 0.18))); g.scale(s, s);
      const fs = fit(lines[0], 150, 820), w = g.measureText(lines[0]).width + 70; rr(g, -w / 2, -fs * 0.75, w, fs * 1.5, 16); g.strokeStyle = '#D9503F'; g.lineWidth = 16; g.stroke(); g.fillStyle = 'rgba(244,234,208,0.55)'; g.fill(); g.fillStyle = '#D9503F'; g.fillText(lines[0], 0, 6);
    } else if (c.style === 'pop') {
      g.translate(540, c.y ?? 420); g.scale(inn, inn); const fs = fit(lines[0], 150, 940); g.lineJoin = 'round'; g.lineWidth = fs * 0.22; g.strokeStyle = '#17203A'; g.strokeText(lines[0], 0, 0); g.fillStyle = '#F4C542'; g.fillText(lines[0], 0, 0);
    } else if (c.style === 'title') {
      g.translate(540, c.y ?? 250); const s = lerp(0.9, 1, eo(clamp(age / 0.5))); g.scale(s, s); lines.forEach((l, i) => { const fs = fit(l, i ? 78 : 108, 940); g.lineJoin = 'round'; g.lineWidth = fs * 0.2; g.strokeStyle = '#17203A'; g.strokeText(l, 0, i * 120); g.fillStyle = i ? '#FFFFFF' : '#F4C542'; g.fillText(l, 0, i * 120); });
    } else { // label
      g.translate(540, (c.y ?? 250) - (1 - eo(clamp(age / 0.4))) * 140); const fs = fit(lines[0], 62, 880); const w = g.measureText(lines[0]).width + 80; rr(g, -w / 2 + 6, -fs * 0.8 + 8, w, fs * 1.6, 22); g.fillStyle = 'rgba(15,23,48,0.35)'; g.fill(); rr(g, -w / 2, -fs * 0.8, w, fs * 1.6, 22); g.fillStyle = '#F4EAD0'; g.fill(); g.strokeStyle = '#2B1A10'; g.lineWidth = 6; g.stroke(); g.fillStyle = '#2B1A10'; g.fillText(typed ?? lines[0], 0, 4);
    }
    g.restore();
  }

  // ---- one shot ----
  function renderShot(g, sh, tt, over = {}) {
    const t = clamp(tt, sh.at, sh.end), set = sets[sh.set] || firstSet, cam = camera(sh, set, t);
    g.fillStyle = '#111'; g.fillRect(0, 0, W, H);
    g.save();
    if (cam.shake) g.translate(Math.sin(t * 83) * 9 * cam.shake, Math.cos(t * 71) * 9 * cam.shake);
    if (sh.effect === 'dutch') { const k = eo(clamp((t - sh.at) / 0.6)); g.translate(540, 960); g.rotate(0.058 * k); g.scale(1 + 0.1 * k, 1 + 0.1 * k); g.translate(-540, -960); }
    const front = [];
    set.layers.forEach((l) => {
      if (l.front) { front.push(l); return; }
      if (!set.bare && makeCanvas && l.p >= 0.2 && l.p < 0.6) { drawSoft(g, cam, l, t, 0.45); return; }          // far scenery: slightly out of focus
      g.save(); if (set.bare) { g.translate(540, 960); g.scale(cam.z, cam.z); g.translate(-540, -960); } else place(g, cam, l.p); l.draw(g, t); g.restore();
    });
    if (sh.panel && set.panel) { g.save(); place(g, cam, 0.94); const pn = set.panel, [pw, ph] = propSize(sh.panel.prop, custom), sc = Math.min(pn.w * 0.86 / pw, pn.h * 0.8 / ph, 3) * (sh.panel.s || 1); g.translate(pn.x, pn.y + ph * sc / 2 + 10); g.scale(sc, sc); drawProp(g, sh.panel.prop, { t: t - sh.at, text: sh.panel.text, c: sh.panel.c }, custom); g.restore(); }
    // actors and props, far to near
    const items = [];
    (sh.props || []).forEach((p) => items.push({ y: set.groundY + ((p.d ?? 1) - 1) * 70 + (p.back ? -5 : 0), draw: () => drawPropPlace(g, p, sh, set, t) }));
    (sh.actors || []).forEach((a) => items.push({ y: set.groundY + ((a.d ?? 1) - 1) * 70 + 0.5, draw: () => drawActor(g, a, sh, set, t, cam) }));
    if (!set.bare) { g.save(); place(g, cam, 1); items.sort((p, q) => p.y - q.y).forEach((it) => it.draw()); g.restore(); }
    front.forEach((l) => { if (makeCanvas) drawSoft(g, cam, l, t, 0.5); else { g.save(); place(g, cam, l.p); l.draw(g, t); g.restore(); } });
    g.restore();
    if (sh.fx && sh.fx !== 'none') drawFx(g, sh.fx, t, 1);
    if (sh.effect === 'storm') { drawFx(g, 'rain', t, 1); const f = Math.sin(t * 7) * Math.sin(t * 3.1); if (f > 0.93) { g.fillStyle = 'rgba(255,255,255,0.45)'; g.fillRect(0, 0, W, H); } }
    if (sh.effect === 'flash' && t - sh.at < 0.25) { g.fillStyle = `rgba(255,255,255,${1 - (t - sh.at) / 0.25})`; g.fillRect(0, 0, W, H); }
    if (!set.bare) grade(g, set.time);
    if (set.light && !over.nolight) lightWash(g, set.light);
    vignette(g, set.indoor ? 0.5 : 0.38);
    grain(g, grainTile, t);
    (sh.callouts || []).forEach((c) => callout(g, c, t));
  }

  const shotAt = (t) => { let i = shots.length - 1; while (i > 0 && shots[i].at > t) i--; return i; };

  function draw(g, t0) {
    const t = clamp(t0, 0, duration - 1e-4), i = shotAt(t), sh = shots[i];
    if (!sh) { g.fillStyle = '#17203A'; g.fillRect(0, 0, W, H); return; }
    const k = clamp((t - sh.at) / TD), prev = shots[i - 1], tr = sh.transition || 'cut';
    if (!prev || tr === 'cut' || k >= 1) { renderShot(g, sh, t); return; }
    const pe = prev.end - 1e-3;
    if (tr === 'fade') { if (k < 0.5) { renderShot(g, prev, pe); g.fillStyle = `rgba(0,0,0,${k * 2})`; } else { renderShot(g, sh, t); g.fillStyle = `rgba(0,0,0,${2 - k * 2})`; } g.fillRect(0, 0, W, H); return; }
    if (tr === 'whip') {
      const half = k < 0.5, e = eio(half ? k * 2 : (k - 0.5) * 2); g.save(); g.translate(half ? -e * 760 : (1 - e) * 760, 0); renderShot(g, half ? prev : sh, half ? pe : t); g.restore();
      g.fillStyle = `rgba(255,255,255,${0.16 * Math.sin(k * Math.PI)})`; for (let y = 0; y < H; y += 60) g.fillRect(0, y + (rnd(y) * 30), W, 6 + rnd(y + 4) * 8); return;
    }
    if (tr === 'wipe') { renderShot(g, prev, pe); g.save(); g.beginPath(); g.rect(0, 0, W * eio(k), H); g.clip(); renderShot(g, sh, t); g.restore(); return; }
    if (tr === 'iris') { renderShot(g, prev, pe); g.save(); g.beginPath(); g.arc(W / 2, H / 2, eio(k) * 1250, 0, TAU); g.clip(); renderShot(g, sh, t); g.restore(); return; }
    if (tr === 'flash') { renderShot(g, sh, t); g.fillStyle = `rgba(255,255,255,${1 - k})`; g.fillRect(0, 0, W, H); return; }
    if (tr === 'dissolve' && makeCanvas) {
      const a = makeCanvas(W, H), b = makeCanvas(W, H); renderShot(b.getContext('2d'), prev, pe); renderShot(a.getContext('2d'), sh, t); g.drawImage(b, 0, 0); g.save(); g.globalAlpha = eio(k); g.drawImage(a, 0, 0); g.restore(); return;
    }
    renderShot(g, sh, t);
  }

  // ---- sound cues, made from the story ----
  const HEAVY = ['stone_giant', 'stone_block', 'crate', 'barrel', 'podium', 'rubble'];
  function cues() {
    const out = [];
    const BED = { field: 'wind', mountain: 'wind', desert: 'wind', sea: 'wind', street: 'crowd', city: 'crowd' };
    shots.forEach((sh, i) => {
      if (i) out.push({ t: +(sh.at - 0.02).toFixed(3), type: 'whoosh', gain: 0.5 });
      const kind = (sets[sh.set] || {}).kind;
      if (BED[kind] && (!i || shots[i - 1].set !== sh.set)) { let j = i; while (j + 1 < shots.length && shots[j + 1].set === sh.set) j++; out.push({ t: sh.at, type: BED[kind], dur: +Math.min(8, shots[j].end - sh.at).toFixed(2), gain: BED[kind] === 'crowd' ? 0.45 : 0.6 }); }
      (sh.props || []).forEach((p) => { const t = p.t0 ?? sh.at; if (t < sh.at) return;
        const nm = p.name; const type = nm === 'fire' ? 'crackle' : nm === 'water' ? 'bubbles' : nm === 'crowd' ? 'crowd' : nm === 'train' || nm === 'wagon' ? 'chug' : nm === 'bell' || nm === 'lightbulb' ? 'ding' : nm === 'sparkle' ? 'sparkle' : HEAVY.includes(nm) ? 'thud' : (p.move === 'slide_l' || p.move === 'slide_r') ? 'slide' : 'pop';
        out.push({ t: +(t + 0.04).toFixed(3), type, gain: type === 'pop' ? 0.7 : 0.8, ...(['crackle', 'bubbles', 'crowd', 'chug'].includes(type) ? { dur: +Math.min(3, sh.end - t).toFixed(2) } : {}) }); });
      (sh.callouts || []).forEach((c) => out.push({ t: +c.t.toFixed(3), type: c.style === 'stamp' ? 'stamp' : c.style === 'pop' ? 'pop' : 'ding', gain: c.style === 'stamp' ? 0.9 : 0.5 }));
      (sh.actors || []).forEach((a) => (a.beats || []).forEach((b) => { if (b.act === 'jump') out.push({ t: +b.t.toFixed(3), type: 'boing', gain: 0.5 }); }));
      if (sh.fx === 'rain' || sh.effect === 'storm') out.push({ t: sh.at, type: 'rain', dur: +(sh.end - sh.at).toFixed(2) });
      if (sh.fx === 'snow') out.push({ t: sh.at, type: 'wind', dur: +(sh.end - sh.at).toFixed(2) });
      if (sh.effect === 'quake') out.push({ t: sh.at, type: 'rumble', dur: +(sh.end - sh.at).toFixed(2) });
      if (sh.effect === 'flash') out.push({ t: sh.at, type: 'slam', gain: 0.6 });
    });
    return out.sort((a, b) => a.t - b.t);
  }

  return { draw, duration, shots: () => shots.map((s, i) => ({ id: s.id || 'S' + String(i + 1).padStart(2, '0'), at: +s.at.toFixed(3), end: +s.end.toFixed(3), note: s.note || '' })), cues, shotAt };
}
