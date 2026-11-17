// Tall Tale director: builds the whole film from a checked story (see shorts_agent/director.py).
// Everything here is a pure function of time: sets, people with acting, objects that move, effects, camera, transitions.
import * as THREE from 'three';
import { ctx, W, H, clamp, lerp, seg, eo, eio, eob, rnd } from './lib.js';
import { camera, RES } from './engine.js';
import * as WD from './world.js';
import * as PR from './props.js';
import { Toon, PROPS } from './toon.js';
import { BRAND } from './brand.js';
import { heroLook } from './hero.js';
import { buildProp } from './propkit.js';

const DEG = Math.PI / 180;
const V3 = (x, y, z) => new THREE.Vector3(x, y, z);
const INK = '#1F1C33', CRIMSON = '#C8283A';
const hexOr = (s, d) => (/^#[0-9a-fA-F]{6}$/.test(s || '') ? s : d);
const LITE = +(new URLSearchParams(location.search).get('lite') ?? 1);     // < 1 = fewer grass and flower instances (faster without a GPU)
let CUSTOM = {}, SNAP = null;
const snap = () => (SNAP ||= Object.assign(document.createElement('canvas'), { width: W, height: H }));

const CENTER = { street: [0, 0, -10], interior: [-0.5, 0, -2.6], meadow: [0, 0, -2], open: [0, 0, -2] };
const FOV = { street: 40, interior: 52, meadow: 40, open: 40 };
const LOOK = { street: { bloom: 0.15, aperture: 0.0012, maxblur: 0.008 }, interior: { bloom: 0.3, aperture: 0.001, maxblur: 0.008 }, meadow: { bloom: 0.25, aperture: 0.001, maxblur: 0.007 }, open: { bloom: 0.25, aperture: 0.001, maxblur: 0.007 } };
const FR = { extreme_close: { d: 1.3, y: 1.6, e: 0 }, close: { d: 1.8, y: 1.5, e: 0.05 }, medium: { d: 2.4, y: 1.3, e: 0.1 }, full: { d: 3.4, y: 1.0, e: 0.2 }, wide: { d: 7, y: 1.2, e: 0.7 }, establishing: { d: 14, y: 2.4, e: 4.5 } };
const YAWS = [0, 12, -12, 20, -20, 8, -8];
const MOVES = {
  drift: { d: [1.05, 0.95], yaw: [-3, 3] }, push_in: { d: [1.25, 0.92] }, pull_out: { d: [0.85, 1.2] },
  truck_left: { lat: [1.0, -1.0] }, truck_right: { lat: [-1.0, 1.0] }, orbit_left: { yaw: [-18, 14] }, orbit_right: { yaw: [18, -14] },
  crane_down: { elev: [1.6, 0], d: [1.1, 1] }, crane_up: { elev: [0, 1.4], d: [1, 1.12] }, punch_in: { d: [1.1, 0.86] }, handheld: { d: [1, 0.97] },
};
const TRANS = { fade: 0.35, wipe: 0.35, slide: 0.3, zoom: 0.35 };            // blends with the previous shot
const CLAMP = {
  street: (p) => { p.x = clamp(p.x, -3.3, 3.3); p.y = clamp(p.y, 0.5, 14); },
  interior: (p, S) => { p.x = clamp(p.x, -S.w / 2 + 0.5, S.w / 2 - 2.0); p.z = clamp(p.z, -S.depth + 1.2, 1.8); p.y = clamp(p.y, 0.5, S.h - 0.5); },
  meadow: (p) => { p.y = Math.max(p.y, 0.4); },
  open: (p) => { p.y = Math.max(p.y, 0.4); },
};
const SLOT_X = { far_left: -2.6, left: -1.3, center: 0, right: 1.3, far_right: 2.6 }, SLOT_Z = { front: 1.1, back: -1.4 };

const HELD = {
  parcels: () => PROPS.parcels, ticket: () => PROPS.ticket, purse: () => PROPS.purse, letters: () => PROPS.letters, rubberStamp: () => PROPS.rubberStamp,
  stamp: () => PROPS.stamp, bill: () => PROPS.bill, stack: () => PROPS.stack, mirror: () => PROPS.mirror, cup: () => PROPS.cup, key: () => PROPS.key,
  book: (a) => PROPS.book(a || 'BOOK', 0), paper: (a) => PROPS.paper(a || 'NEWS'), sign: (a) => PROPS.sign(a || 'SALE'),
  cash: (a) => PROPS.cash(Math.max(1, Math.min(6, parseInt(a, 10) || 2))),
};
const MAKE = {
  tree: (it) => WD.tree(1, hexOr(it.color, '#4E9A3C'), /cypress/i.test(it.text) ? 'cypress' : 'round'),
  barrel: () => WD.barrel(), crate: () => WD.crate(0.6), car: (it) => WD.car(hexOr(it.color, '#2C3A4A')), fence: () => WD.fence(6), lamp: () => WD.lamp(),
  pole: () => WD.pole(7), house: (it) => PR.house({ wall: hexOr(it.color, '#F2E6CF') }),
  signpost: (it) => PR.signpost([[String(it.text || 'NEXT TOWN').toUpperCase().slice(0, 20), 'r']]),
  parcel: () => PR.parcel(0.5, 0.35, 0.4), mail_sack: () => PR.mailSack(1), desk: () => PR.desk(2.2), cubbies: () => PR.cubbies(3, 1.8),
  poster: (it) => PR.poster(String(it.text || 'NOTICE').split('|').slice(0, 5)), chick_crate: () => PR.chickCrate(6),
  scale: (it) => { const s = PR.platformScale(); s.set(parseFloat(it.text) || 0); return s; },
  train: () => { const g = new THREE.Group(), tr = PR.train(); g.add(PR.rails(400), tr); g.tr = tr; return g; },
  crowd: () => { const g = new THREE.Group(); g.toons = WD.extras(g, [[-1.3, 0.2, 0, 'happy'], [-0.6, -0.5, 1, 'shock'], [0.1, 0.3, 2, 'laugh'], [0.8, -0.4, 3, 'happy'], [1.4, 0.2, 4, 'shock'], [0.2, -1.1, 5, 'laugh']]); return g; },
  board: (it) => {
    const g = new THREE.Group(), wood = new THREE.MeshStandardMaterial({ color: '#7A5236', roughness: 0.9 });
    [-0.9, 0.9].forEach((x) => { const p = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, 1.9, 8), wood); p.position.set(x, 0.95, 0); p.castShadow = true; g.add(p); });
    const s = WD.signBoard(String(it.text || 'SIGN').toUpperCase().slice(0, 26), { w: 2.4, h: 0.8, bg: '#F2E6CF', fg: '#B5372E' }); s.position.set(0, 1.55, 0.08); g.add(s); return g;
  },
  fire: () => {
    const g = new THREE.Group(), fl = ['#C8283A', '#F28A2E', '#F6D54A'].map((c, i) => { const h = 1.2 - i * 0.3, m = new THREE.Mesh(new THREE.ConeGeometry(0.4 - i * 0.1, h, 8), new THREE.MeshBasicMaterial({ color: c })); m.position.y = h / 2; g.add(m); return m; });
    g.update = (t) => fl.forEach((m, i) => m.scale.set(1 + 0.12 * Math.sin(t * 14 + i), 1 + 0.2 * Math.sin(t * 11 + i * 2), 1 + 0.12 * Math.cos(t * 13 + i)));
    return g;
  },
  smoke: () => {
    const g = new THREE.Group(), ps = [];
    for (let i = 0; i < 6; i++) { const m = new THREE.Mesh(new THREE.SphereGeometry(0.4, 10, 8), new THREE.MeshBasicMaterial({ color: '#C9C5BE', transparent: true, opacity: 0.8 })); g.add(m); ps.push(m); }
    g.update = (t) => ps.forEach((m, i) => { const u = (t * 0.4 + i / 6) % 1; m.position.set(Math.sin(u * 5 + i) * 0.35, 0.3 + u * 3.2, 0); m.scale.setScalar(0.5 + u * 1.6); m.material.opacity = 0.85 * (1 - u); });
    return g;
  },
  water: () => {
    const g = new THREE.Group(), m = new THREE.Mesh(new THREE.PlaneGeometry(40, 40), new THREE.MeshStandardMaterial({ color: '#3F8FD2', transparent: true, opacity: 0.78, roughness: 0.2 }));
    m.rotation.x = -Math.PI / 2; m.position.y = 0.08; g.add(m); g.update = (t) => { m.position.y = 0.08 + Math.sin(t * 2) * 0.03; };
    return g;
  },
  crack: () => {
    const g = new THREE.Group(), mm = new THREE.MeshBasicMaterial({ color: '#2A2118' });
    let x = -1.6, z = 0;
    for (let i = 0; i < 6; i++) { const b = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.02, 0.1 + (i % 2) * 0.05), mm); b.position.set(x + 0.28, 0.02, z); b.rotation.y = i % 2 ? 0.6 : -0.6; g.add(b); x += 0.55; z += i % 2 ? 0.25 : -0.25; }
    return g;
  },
  rubble: () => {
    const g = new THREE.Group();
    for (let i = 0; i < 9; i++) { const s = 0.18 + rnd(i) * 0.3, b = new THREE.Mesh(new THREE.BoxGeometry(s, s * 0.7, s), new THREE.MeshStandardMaterial({ color: ['#8E8A82', '#A8A298', '#6F6A62'][i % 3] })); b.position.set((rnd(i + 3) - 0.5) * 1.6, s * 0.35 + (i > 5 ? 0.25 : 0), (rnd(i + 7) - 0.5) * 1.2); b.rotation.set(rnd(i) * 0.6, rnd(i + 1) * 3, rnd(i + 2) * 0.6); b.castShadow = true; g.add(b); }
    return g;
  },
};
const makeItem = (name, it) => (MAKE[name] ? MAKE[name](it) : CUSTOM[name] ? buildProp(CUSTOM[name]) : null);
const register = (S, o) => { if (o && o.toons) S.facers.push(...o.toons); };

function stars() {
  const n = 500, pos = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) { const a = rnd(i) * Math.PI * 2, y = 0.05 + rnd(i + 900) * 0.9, q = Math.sqrt(1 - y * y); pos.set([Math.cos(a) * q * 330, y * 330, Math.sin(a) * q * 330], i * 3); }
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  return new THREE.Points(g, new THREE.PointsMaterial({ color: '#FFFFFF', size: 3, sizeAttenuation: false, fog: false, toneMapped: false, depthWrite: false }));
}

function outsideView(E, S) {
  const c = new THREE.PerspectiveCamera(42, 4 / 3, 0.1, 800);
  if (S.kind === 'street') { c.position.set(2, 1.8, -12); c.lookAt(-3, 2.2, 10); S.extras.faceAll(c); } else { c.position.set(0, 1.8, 4); c.lookAt(0, 2.4, -30); }
  const tx = WD.snapshot(E, S.scene, c); tx.wrapS = THREE.RepeatWrapping; return tx;
}

function addDress(S, items) {
  for (const it of items) {
    const o = makeItem(it.item, it); if (!o) continue;
    let x = S.C.x + it.x, y = 0, z = S.C.z + it.z;
    if (S.kind === 'interior') {
      if (it.item === 'poster') { y = 2.1; z = -S.depth + 0.15; }
      else if (it.item === 'cubbies') { y = 0.95; z = -S.depth + 0.25; }
      else if (it.item === 'scale' || it.item === 'chick_crate') { x = 2.7; y = 1.18; z = clamp(z, -5, -1); }
    }
    o.position.set(x, y, z); o.rotation.y = (it.rot || 0) * DEG; o.scale.multiplyScalar(it.scale || 1);
    S.scene.add(o); register(S, o);
    if (o.update) S.anim.push((t) => o.update(t));
    if (it.item === 'train') S.anim.push((t) => { o.tr.position.x = ((t * 5.5) % 70) - 35; o.tr.update(t); });
  }
}

function buildSet(E, def, STORY, built) {
  const era = STORY.era || {};
  let S;
  if (def.kind === 'street') {
    const st = WD.mainStreet(E, { len: 46, dusk: def.mood === 'dusk', cars: !!era.cars, poles: !!era.poles, wires: !!era.poles, lamps: !!era.lamps });
    S = { kind: 'street', scene: st.scene, sun: st.sun, extras: st };
  } else if (def.kind === 'meadow') {
    const m = WD.meadow(E, { sunset: def.mood === 'dusk', fenceOn: false });
    S = { kind: 'meadow', scene: m.scene, sun: m.sun };
  } else if (def.kind === 'open') {
    const scene = new THREE.Scene(), dark = !!def.stars, hor = hexOr(def.horizon, '#CBEAF8');
    WD.sky(scene, { top: hexOr(def.top, '#3D8EE0'), horizon: hor, ground: hexOr(def.ground, hor) });
    const sun = WD.sunlight(scene, E, dark ? { col: '#CFD8FF', i: 1.7, pos: [8, 12, 6], box: 14, sky: '#8FA0FF', ground: '#3A3F63', hemi: 0.9 } : { pos: [8, 12, 6], box: 14 });
    if (def.ground) { const g = new THREE.Mesh(new THREE.PlaneGeometry(300, 300), WD.mat({ map: WD.T.grass(def.ground, [60, 60]) })); g.rotation.x = -Math.PI / 2; g.position.y = -0.02; g.receiveShadow = true; scene.add(g); }
    else { const p = new THREE.Mesh(new THREE.CylinderGeometry(6, 6, 0.3, 40), WD.mat({ color: '#3A3F63' })); p.position.y = -0.15; p.receiveShadow = true; scene.add(p); }
    if (def.hills) WD.hills(scene, { col: def.hills, z: -70 });
    if (dark) scene.add(stars());
    S = { kind: 'open', scene, sun };
  } else {
    const out = [...built.values()].find((s) => s.kind === 'street') || [...built.values()].find((s) => s.kind === 'meadow');
    const it = WD.interior(E, { wall: def.wall, motif: def.motif, floor: def.floor, ceiling: def.ceiling, signText: def.sign || null, picture: false, litter: false, view: out ? outsideView(E, out) : null });
    S = { kind: 'interior', scene: it.scene, sun: it.sun, w: it.w, depth: it.depth, h: it.h };
  }
  if (LITE < 1) S.scene.traverse((o) => { if (o.isInstancedMesh && o.count > 300) o.count = Math.max(120, Math.floor(o.count * LITE)); });
  S.id = def.id; S.C = V3(...CENTER[def.kind]); S.toons = new Map(); S.anim = []; S.facers = []; S.shotObjs = [];
  if (S.kind !== 'interior') S.sunOff = S.sun.key.position.clone().sub(S.sun.key.target.position);
  addDress(S, def.dress || []);
  return S;
}

function slotPos(S, slot) {
  const C = S.C;
  if (slot === 'counter_clerk') return V3(3.55, 0, -2.5);
  if (slot === 'counter_top') return V3(2.7, 1.26, -2.0);
  if (slot === 'boardwalk_left') return V3(-5.0, 0.18, C.z);
  if (slot === 'boardwalk_right') return V3(5.0, 0.18, C.z);
  const m = /^(?:(front|back)_)?(far_left|left|center|right|far_right)$/.exec(slot) || [];
  return V3(C.x + SLOT_X[m[2] || 'center'], 0, C.z + (SLOT_Z[m[1]] || 0));
}

function stand(S, a, lt, d, t) {
  const p = slotPos(S, a.slot), run = a.action.startsWith('run_');
  const reach = S.kind === 'interior' ? 2.4 : 7, side = S.kind === 'interior' ? 2 : 3.2;
  const k = eio(clamp(lt / Math.max(0.6, d * 0.85)));
  const T = S.toons.get(a.who), hk = T ? (T.H * 0.96) / 1.75 : 1;                  // 1 = grown-up, 0.8 = child
  let moving = false;
  if (a.action === 'walk_in' || a.action === 'run_in') { p.z -= reach * (1 - k); moving = k < 1; }
  else if (a.action === 'walk_out' || a.action === 'run_out') { p.z -= reach * k; moving = k < 1; }
  else if (a.action === 'cross_left' || a.action === 'run_left') { p.x += side * (0.5 - k); moving = k < 1; }
  else if (a.action === 'cross_right' || a.action === 'run_right') { p.x -= side * (0.5 - k); moving = k < 1; }
  if (S.kind === 'interior' && !a.slot.startsWith('counter')) p.x = Math.min(p.x, 2.0);
  let legs = moving ? (run ? 'run' : 'walk') : a.action === 'sit' ? 'sit' : 'stand';
  if (a.action === 'jump') { const j = Math.sin(t * 8); legs = j > 0.2 ? 'jump' : 'stand'; p.y += Math.max(0, j) * 0.22; }
  return { a, p, legs, moving, run, hk };
}

function arms(g, t, lt, hasProp, lx) {
  const side = lx < 0 ? 'armL' : 'armR';
  switch (g) {
    case 'wave': return { armR: [150 + Math.sin(t * 9) * 18, 10] };
    case 'point': return { [side]: [95, -15] };
    case 'cheer': return { armL: [150 + Math.sin(t * 10) * 10, 15], armR: [150 + Math.sin(t * 10 + 1) * 10, 15] };
    case 'arms_up': return { armL: [150, 20], armR: [150, 20] };
    case 'shrug': { const k = eob(clamp((lt - 0.1) / 0.4)); const s = [lerp(40, 75, k), lerp(-80, -60, k)]; return { armL: s, armR: s }; }
    case 'hip': return { armL: [40, -80], armR: [40, -80] };
    case 'present': return { [side]: [60, -60] };
    case 'think': return { armR: [30, -110] };
    case 'hold': return { armR: [30, -100] };
    default: return hasProp ? { armR: [30, -100] } : {};
  }
}

// the body language of a mood: lean (degrees), bob (px), hop (metres). Rounded so the cut-out is not redrawn every frame.
function moodMotion(mood, t, since, n) {
  const q = (v) => Math.round(v * 2) / 2;
  switch (mood) {
    case 'shock': return { lean: since < 0.5 ? q(-8 * Math.exp(-since * 5)) : 0, hop: since < 0.35 ? Math.sin((since / 0.35) * Math.PI) * 0.22 : 0 };
    case 'laugh': return { bob: Math.round(Math.sin(t * 16 + n) * 6), lean: q(Math.sin(t * 8) * 3) };
    case 'worried': return { lean: q(Math.sin(t * 22 + n) * 1.5) };
    case 'angry': return { bob: -Math.round(Math.abs(Math.sin(t * 9)) * 6), lean: 3 };
    case 'sad': case 'tired': return { lean: 6, bob: 0 };
    case 'smug': return { lean: -3 };
    case 'proud': return { lean: -2, bob: Math.round(Math.sin(t * 3) * 2) };
    case 'happy': return { bob: Math.round(Math.sin(t * 4 + n) * 4) };
    case 'dizzy': return { lean: q(Math.sin(t * 5) * 9) };
    default: return {};
  }
}

function evalBeats(a, t) {
  let mood = a.mood, gesture = a.gesture, prop = a.prop, bt = -1;
  for (const b of a.beats) {
    if (b.t > t) break;
    if (b.mood) mood = b.mood;
    if (b.gesture) gesture = b.gesture;
    if (b.prop !== null && b.prop !== undefined) prop = b.prop || null;
    bt = b.t;
  }
  return { mood, gesture, prop, bt };
}

function rig(S, sh, live, lt, d, t) {
  let fr = FR[sh.framing] || FR.medium;
  if (S.kind === 'interior' && (sh.framing === 'wide' || sh.framing === 'establishing')) fr = FR.full;
  const fov = FOV[S.kind];
  const pool = sh.focus.length ? live.filter((l) => sh.focus.includes(l.a.who)) : live;
  const tight = sh.framing === 'close' || sh.framing === 'extreme_close';
  const pts = pool.map((l) => ({ x: l.p.x, z: l.p.z, r: tight ? 0.12 : 0.45 }));      // everything that must be in the picture
  if (!sh.intro) sh.objs.forEach(({ it, rad }) => { if (rad < 3.5) pts.push({ x: S.C.x + it.x, z: S.C.z + it.z, r: Math.max(0.35, rad * 0.9) }); });
  const F = V3(0, 0, 0);
  if (pts.length) { pts.forEach((p) => F.add(V3(p.x, 0, p.z))); F.multiplyScalar(1 / pts.length); } else F.copy(S.C);
  const baseY = pool.length ? Math.max(...pool.map((l) => l.p.y)) : 0;
  const hk = pool.length ? pool.reduce((s, l) => s + l.hk, 0) / pool.length : 1;
  const yaw0 = YAWS[sh.index % YAWS.length] * (S.kind === 'interior' ? 0.6 : 1);
  const mv = MOVES[sh.camera] || MOVES.drift;
  let k = eio(clamp(lt / d));
  if (sh.camera === 'punch_in') { const tp = (sh.punch ?? sh.at + d * 0.55) - sh.at; k = eo(seg(lt, tp - 0.05, tp + 0.28)); }
  const m = (pair, def) => (pair ? lerp(pair[0], pair[1], k) : def);
  const r0 = yaw0 * DEG, rx = Math.cos(r0), rz = -Math.sin(r0);
  let lo = 0, hi = 0;
  if (pts.length) { const pr = pts.map((p) => p.x * rx + p.z * rz); lo = Math.min(...pts.map((p, i) => pr[i] - p.r)); hi = Math.max(...pts.map((p, i) => pr[i] + p.r)); }
  const span = hi - lo;
  const fit = Math.min(14, ((span + 0.1) * 0.55) / (Math.tan(fov * DEG / 2) * 0.5625));   // portrait frames are narrow
  const base = Math.max(fr.d * hk * (Math.tan(20 * DEG) / Math.tan(fov * DEG / 2)), fit);
  const dist = Math.min(24, base * m(mv.d, 1));
  const yaw = (yaw0 + m(mv.yaw, 0)) * DEG, elev = fr.e + m(mv.elev, 0) * (tight ? 0.3 : 1), lat = m(mv.lat, 0);
  const ly = baseY + fr.y * hk;
  const right = V3(Math.cos(yaw), 0, -Math.sin(yaw));
  const target = V3(F.x, ly, F.z).addScaledVector(right, lat);
  const pos = V3(F.x + Math.sin(yaw) * dist, ly + elev, F.z + Math.cos(yaw) * dist).addScaledVector(right, lat);
  let amp = sh.camera === 'handheld' ? 0.012 : 0;
  if (sh.effect === 'quake') amp += 0.05 * (0.7 + 0.3 * Math.sin(t * 3));
  if (sh.effect === 'storm') amp += 0.015;
  for (const f of sh.fx) if (f.type === 'shake' && t >= f.t && t < f.t + 0.5) amp += 0.07 * Math.exp(-(t - f.t) * 9);
  if (amp) { pos.x += Math.sin(t * 31) * amp; pos.y += Math.cos(t * 27) * amp; target.x += Math.sin(t * 23 + 1) * amp * 0.6; }
  CLAMP[S.kind](pos, S);
  const dd = Math.max(0.5, pos.distanceTo(target)), need = ((span + 0.1) * 0.55) / (0.5625 * dd);   // a wall stopped the camera: widen the lens
  const fovOut = clamp(Math.max(fov, (2 * Math.atan(need)) / DEG), fov, 78);
  return { pos, target, fov: fovOut, right, F };
}

function weather(kind, t) {
  ctx.save();
  if (kind === 'rain' || kind === 'storm') {
    ctx.fillStyle = kind === 'storm' ? 'rgba(25,35,60,0.32)' : 'rgba(30,45,70,0.16)'; ctx.fillRect(0, 0, W, H);
    ctx.strokeStyle = 'rgba(235,242,255,0.75)'; ctx.lineWidth = 4; ctx.lineCap = 'round'; ctx.beginPath();
    for (let i = 0; i < 120; i++) { const x = ((rnd(i) * (W + 300) + t * 160) % (W + 300)) - 150, y = ((rnd(i + 90) * H + t * 1700) % (H + 200)) - 100; ctx.moveTo(x, y); ctx.lineTo(x - 24, y + 76); }
    ctx.stroke();
  } else if (kind === 'snow') {
    ctx.fillStyle = 'rgba(210,225,245,0.14)'; ctx.fillRect(0, 0, W, H); ctx.fillStyle = '#FFFFFF';
    for (let i = 0; i < 90; i++) { const x = (rnd(i) * W + Math.sin(t * 1.4 + i) * 40 + W) % W, y = ((rnd(i + 70) * H + t * 190) % (H + 80)) - 40; ctx.beginPath(); ctx.arc(x, y, 4 + rnd(i + 9) * 7, 0, 6.3); ctx.fill(); }
  } else if (kind === 'dust' || kind === 'quake') {
    ctx.fillStyle = kind === 'dust' ? 'rgba(160,120,70,0.2)' : 'rgba(120,100,80,0.1)'; ctx.fillRect(0, 0, W, H); ctx.fillStyle = 'rgba(190,160,120,0.5)';
    for (let i = 0; i < 40; i++) { const x = ((rnd(i) * W + t * 60 * (1 + rnd(i + 5))) % (W + 60)) - 30, y = (rnd(i + 30) * H + Math.sin(t * 3 + i) * 30 + H) % H; ctx.beginPath(); ctx.arc(x, y, 3 + rnd(i + 8) * 8, 0, 6.3); ctx.fill(); }
  }
  ctx.restore();
}

function drawCallout(c, t, endT) {
  const a = t - c.t; if (a < 0 || t > endT) return;
  const pop = eob(clamp(a / 0.22)), fade = Math.min(1, a / 0.06) * (1 - clamp((t - (endT - 0.25)) / 0.25));
  const words = c.text.split(' ');
  let lines = [c.text];
  if (c.text.length > 13 && words.length > 1) { const h = Math.ceil(words.length / 2); lines = [words.slice(0, h).join(' '), words.slice(h).join(' ')]; }
  const size = c.style === 'label' ? 56 : c.style === 'stamp' ? 96 : 124;
  ctx.save(); ctx.globalAlpha = fade; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.lineJoin = 'round'; ctx.font = `900 ${size}px Inter`;
  const maxW = Math.max(...lines.map((s) => ctx.measureText(s).width)), fit = Math.min(1, (c.style === 'label' ? 780 : 860) / maxW), lh = size * 1.05;
  if (c.style === 'label') {
    const w = maxW * fit + 80, h = lh * fit * lines.length + 40, x = 540 + lerp(-700, 0, eo(clamp(a / 0.3))), y = 250;
    ctx.fillStyle = 'rgba(0,0,0,0.3)'; ctx.beginPath(); ctx.roundRect(x - w / 2 + 6, y - h / 2 + 10, w, h, 22); ctx.fill();
    ctx.fillStyle = '#F4EBD6'; ctx.strokeStyle = INK; ctx.lineWidth = 7; ctx.beginPath(); ctx.roundRect(x - w / 2, y - h / 2, w, h, 22); ctx.fill(); ctx.stroke();
    ctx.translate(x, y); ctx.scale(fit, fit); ctx.fillStyle = INK; lines.forEach((s, i) => ctx.fillText(s, 0, (i - (lines.length - 1) / 2) * lh));
  } else if (c.style === 'stamp') {
    ctx.translate(540, 470); ctx.rotate(-0.16); const s = fit * lerp(2.6, 1, eo(clamp(a / 0.18))); ctx.scale(s, s);
    const w = maxW + 90, h = lh * lines.length + 50;
    ctx.strokeStyle = CRIMSON; ctx.lineWidth = 14; ctx.beginPath(); ctx.roundRect(-w / 2, -h / 2, w, h, 22); ctx.stroke();
    ctx.fillStyle = CRIMSON; lines.forEach((s2, i) => ctx.fillText(s2, 0, (i - (lines.length - 1) / 2) * lh));
  } else {
    ctx.translate(540, 470); ctx.rotate(-0.05); const s = fit * lerp(1.7, 1, pop); ctx.scale(s, s);
    lines.forEach((s2, i) => { const y = (i - (lines.length - 1) / 2) * lh; ctx.fillStyle = 'rgba(0,0,0,0.4)'; ctx.fillText(s2, 4, y + 10); ctx.lineWidth = 24; ctx.strokeStyle = '#0B0B10'; ctx.strokeText(s2, 0, y); ctx.fillStyle = '#FFFFFF'; ctx.fillText(s2, 0, y); });
  }
  ctx.restore();
}

export function buildFromStory(E, STORY, DEFS) {
  CUSTOM = DEFS || {};
  const cam = camera(40);
  const built = new Map();
  [...STORY.sets].sort((a, b) => (a.kind === 'interior') - (b.kind === 'interior')).forEach((def) => built.set(def.id, buildSet(E, def, STORY, built)));
  const need = new Map();
  STORY.shots.forEach((s) => { if (!need.has(s.set)) need.set(s.set, new Set()); s.actors.forEach((a) => need.get(s.set).add(a.who)); });
  const looks = Object.fromEntries(STORY.cast.map((c) => [c.id, c.look]));
  const hostLook = heroLook((BRAND.character && BRAND.character.look) || {});
  const tres = Math.max(0.75, Math.min(2, RES * 2));                               // cut-out quality follows the render quality
  for (const [sid, ids] of need) {
    const S = built.get(sid); if (!S) continue;
    ids.forEach((who) => {
      const host = who === 'host', look = host ? hostLook : looks[who]; if (!look) return;
      const T = new Toon({ ...look, extra: [...(look.extra || [])] }, { height: host ? 1.75 * ((BRAND.character && BRAND.character.scale) || 1) : look.kid ? 1.4 : 1.75, res: tres });
      S.scene.add(T.group); S.toons.set(who, T);
    });
  }
  // the objects each shot shows: they appear on their spoken word, and the camera frames them from the first frame
  STORY.shots.forEach((sh) => {
    sh.objs = []; const S = built.get(sh.set); if (!S) return;
    for (const it of sh.props || []) {
      const o = makeItem(it.name, it); if (!o) continue;
      o.position.set(S.C.x + it.x, it.y || 0, S.C.z + it.z); o.rotation.y = (it.rot || 0) * DEG;
      o.userData.base = it.scale || 1; o.scale.setScalar(o.userData.base); o.visible = false;
      S.scene.add(o); register(S, o); S.shotObjs.push(o);
      const sz = new THREE.Box3().setFromObject(o).getSize(new THREE.Vector3());
      sh.objs.push({ o, it, rad: Math.max(sz.x, sz.z) / 2 });
    }
  });

  const drawShot = (sh, lt, d, t, blit) => {
    const S = built.get(sh.set);
    S.anim.forEach((f) => f(t));
    S.toons.forEach((T) => { T.group.visible = false; });
    S.shotObjs.forEach((o) => { o.visible = false; });
    const shaky = sh.effect === 'quake';
    sh.objs.forEach(({ o, it }) => {
      if (it.t != null && t < it.t) return;
      const a = t - (it.t == null ? sh.at : it.t), k = it.t == null ? 1 : eob(clamp(a / 0.28));
      o.visible = true; o.scale.setScalar(Math.max(0.001, o.userData.base * k));
      if (o.update) o.update(t);
      const x0 = S.C.x + it.x, z0 = S.C.z + it.z, y0 = it.y || 0, r0 = (it.rot || 0) * DEG;
      let x = x0, y = y0, z = z0, ry = r0, rz = 0;
      if (it.move === 'fly') { const u = clamp(a / 1.1); x = x0 + it.dx * u; z = z0 + it.dz * u; y = y0 + Math.sin(u * Math.PI) * 1.1; ry = r0 + u * 12; }
      else if (it.move === 'spin') ry = r0 + a * 4;
      else if (it.move === 'bounce') y = y0 + Math.abs(Math.sin(a * 6)) * 0.4 * Math.exp(-a * 0.6);
      else if (it.move === 'swing') rz = -Math.sin(clamp(a / 0.35) * Math.PI) * 1.3;
      else if (it.move === 'shake') { x += Math.sin(a * 60) * 0.04; z += Math.cos(a * 53) * 0.03; }
      else if (it.move === 'rise') y = y0 + 1.2 * eio(clamp(a / 3));
      if (shaky) { x += Math.sin(t * 47 + it.x) * 0.03; z += Math.cos(t * 41) * 0.02; }
      o.position.set(x, y, z); o.rotation.set(0, ry, rz);
    });
    const live = sh.actors.map((a) => stand(S, a, lt, d, t));
    const R = rig(S, sh, live, lt, d, t);
    if (cam.fov !== R.fov) { cam.fov = R.fov; cam.updateProjectionMatrix(); }
    cam.position.copy(R.pos); cam.lookAt(R.target);
    S.facers.forEach((T) => T.face(cam));
    const shown = sh.objs.filter(({ it }) => it.t == null || t >= it.t).sort((a, b) => (b.it.t ?? -1) - (a.it.t ?? -1));
    live.forEach((l, n) => {
      const T = S.toons.get(l.a.who); if (!T) return;
      const a = l.a, ev = evalBeats(a, t), since = ev.bt >= 0 ? t - ev.bt : 9;
      const speaking = a.speech.some(([s, e]) => t >= s && t <= e + 0.05);
      let tgt = null;                                                   // who or what this person looks at
      if (a.looks_at) { const o = live.find((x) => x.a.who === a.looks_at); if (o) tgt = o.p; }
      if (!tgt && shown.length) tgt = V3(S.C.x + shown[0].it.x, 0, S.C.z + shown[0].it.z);
      if (!tgt) { let best = 1e9; live.forEach((o) => { if (o !== l) { const dd = Math.abs(o.p.x - l.p.x); if (dd < best) { best = dd; tgt = o.p; } } }); }
      const lx = tgt ? clamp(tgt.clone().sub(l.p).dot(R.right) * 0.6, -1, 1) : 0;
      let g = ev.gesture;
      if ((!g || g === 'none') && speaking && !ev.prop && Math.sin(t * 2.1 + n * 1.7) > 0.35) g = 'present';   // talking hands
      const mm = moodMotion(ev.mood, t, since, n);
      const st = {
        mood: ev.mood, look: [Math.round((lx + Math.sin(t * 1.3 + n) * 0.12) * 20) / 20, 0], blink: ((t + n * 1.3) % 3.3) < 0.12 ? 1 : 0, legs: l.legs,
        phase: l.moving ? t * (l.run ? 11 : 7) + n : 0, bob: l.moving ? 0 : (mm.bob ?? Math.round(Math.sin(t * 2.2 + n) * 3)), lean: mm.lean || 0,
        squash: since < 0.32 ? 0.13 * Math.sin(since * 22) * Math.exp(-since * 9) : 0, ...arms(g, t, lt, !!ev.prop, lx),
      };
      if (speaking) st.talk = 0.25 + 0.75 * Math.abs(Math.sin(t * 13)) * (0.6 + 0.4 * Math.sin(t * 5.3));
      if (ev.prop && HELD[ev.prop.name]) { st.holdR = HELD[ev.prop.name](ev.prop.arg); st.v = ev.prop.name + ':' + ev.prop.arg; }
      T.set(st); T.at(l.p.x, l.p.y + (mm.hop || 0), l.p.z); T.group.visible = true; T.face(cam);
    });
    if (S.sunOff) { const k = S.sun.key; k.target.position.set(R.F.x, 0, R.F.z); k.position.copy(k.target.position).add(S.sunOff); }
    if (S.extras) S.extras.faceAll(cam);
    E.render(S.scene, cam, { ...LOOK[S.kind], focus: cam.position.distanceTo(R.target) });
    if (sh.transition === 'punch' && lt < 0.22) {
      const s = 1 + 0.1 * (1 - eo(lt / 0.22));
      ctx.save(); ctx.translate(W / 2, H / 2); ctx.scale(s, s); ctx.translate(-W / 2, -H / 2); blit(); ctx.restore();
    } else blit();
    if (sh.effect) weather(sh.effect, t);
    const fa = sh.transition === 'flash' ? 1 - clamp(lt / 0.16) : sh.transition === 'dip' ? 1 - clamp(lt / 0.14) : 0;
    if (fa > 0) { ctx.globalAlpha = fa; ctx.fillStyle = sh.transition === 'dip' ? '#000000' : '#FFFFFF'; ctx.fillRect(0, 0, W, H); ctx.globalAlpha = 1; }
    for (const f of sh.fx) if (f.type === 'flash' && t >= f.t && t < f.t + 0.14) { ctx.globalAlpha = 0.55 * (1 - (t - f.t) / 0.14); ctx.fillStyle = '#FFFFFF'; ctx.fillRect(0, 0, W, H); ctx.globalAlpha = 1; }
    sh.callouts.forEach((c) => drawCallout(c, t, Math.min(c.t + c.dur, sh.at + d)));
  };

  const shots = STORY.shots.map((sh, i) => {
    sh.index = i;
    return {
      id: sh.id, at: sh.at, note: sh.note || '',
      draw(lt, d, t, blit) {
        const TD = TRANS[sh.transition];
        if (i > 0 && TD && lt < TD) {                                   // blend with the previous shot, drawn for real, not frozen
          const pv = STORY.shots[i - 1];
          drawShot(pv, t - pv.at, pv.end - pv.at, t, blit);
          ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 1;
          const sc = snap().getContext('2d'); sc.clearRect(0, 0, W, H); sc.drawImage(ctx.canvas, 0, 0);
          drawShot(sh, lt, d, t, blit);
          ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 1;
          const k = eio(clamp(lt / TD)); ctx.save();
          if (sh.transition === 'fade') { ctx.globalAlpha = 1 - k; ctx.drawImage(snap(), 0, 0); }
          else if (sh.transition === 'wipe') { ctx.beginPath(); ctx.rect(W * k, 0, W * (1 - k), H); ctx.clip(); ctx.drawImage(snap(), 0, 0); }
          else if (sh.transition === 'slide') ctx.drawImage(snap(), -W * k, 0);
          else { const s = 1 + k * 0.6; ctx.globalAlpha = 1 - k; ctx.translate(W / 2, H / 2); ctx.scale(s, s); ctx.translate(-W / 2, -H / 2); ctx.drawImage(snap(), 0, 0); }
          ctx.restore();
        } else drawShot(sh, lt, d, t, blit);
      },
    };
  });
  return { shots, cues: STORY.cues };
}