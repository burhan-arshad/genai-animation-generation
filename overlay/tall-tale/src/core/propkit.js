// Builds a 3D prop from a blueprint: plain data written by the prop designer (shorts_agent/propgen.py). Never runs code from the LLM.
import * as THREE from 'three';
import { canvasTex } from './world.js';

const DEG = Math.PI / 180;
const mat = (c) => new THREE.MeshStandardMaterial({ color: c, roughness: 0.85, metalness: 0, side: THREE.DoubleSide });

function part(p) {
  const [a, b, c] = p.size;
  let mesh;
  if (p.shape === 'label') {
    const w = Math.max(64, Math.round(a * 220)), h = Math.max(32, Math.round(b * 220));
    const tex = canvasTex('lbl|' + p.text + p.color + p.fg + w + h, w, h, (g, cw, ch) => {
      g.fillStyle = p.color; g.fillRect(0, 0, cw, ch); g.strokeStyle = p.fg; g.lineWidth = Math.max(3, ch * 0.05); g.strokeRect(ch * 0.06, ch * 0.06, cw - ch * 0.12, ch * 0.88);
      g.fillStyle = p.fg; g.textAlign = 'center'; g.textBaseline = 'middle'; let fs = ch * 0.55; g.font = `900 ${fs}px Inter`;
      while (g.measureText(p.text).width > cw * 0.86 && fs > 8) { fs -= 2; g.font = `900 ${fs}px Inter`; }
      g.fillText(p.text, cw / 2, ch / 2 + 2);
    });
    mesh = new THREE.Mesh(new THREE.PlaneGeometry(a, b), new THREE.MeshStandardMaterial({ map: tex, roughness: 0.8, side: THREE.DoubleSide }));
  } else {
    let geo;
    if (p.shape === 'box') geo = new THREE.BoxGeometry(a, b, c);
    else if (p.shape === 'sphere') { geo = new THREE.SphereGeometry(1, 20, 14); geo.scale(a, b, c); }
    else if (p.shape === 'cylinder') geo = new THREE.CylinderGeometry(a, b, c, 22);
    else if (p.shape === 'cone') geo = new THREE.ConeGeometry(a, b, 22);
    else if (p.shape === 'torus') geo = new THREE.TorusGeometry(a, b, 10, 28);
    else if (p.shape === 'slab') {
      const sh = new THREE.Shape(); p.pts.forEach(([x, y], i) => (i ? sh.lineTo(x, y) : sh.moveTo(x, y)));
      geo = new THREE.ExtrudeGeometry(sh, { depth: a, bevelEnabled: false }); geo.translate(0, 0, -a / 2);
    } else if (p.shape === 'lathe') geo = new THREE.LatheGeometry(p.profile.map(([r, y]) => new THREE.Vector2(Math.max(0.001, r), y)), 28);
    else return null;
    mesh = new THREE.Mesh(geo, mat(p.color));
  }
  mesh.position.set(p.pos[0], p.pos[1], p.pos[2]); mesh.rotation.set(p.rot[0] * DEG, p.rot[1] * DEG, p.rot[2] * DEG);
  mesh.castShadow = mesh.receiveShadow = true;
  return mesh;
}

/** the finished object stands on the ground (y = 0), is centred, and its longest side is `def.span` metres */
export function buildProp(def) {
  try {
    const inner = new THREE.Group();
    for (const p of def.parts) { try { const m = part(p); if (m) inner.add(m); } catch (e) { /* a bad part is skipped */ } }
    if (!inner.children.length) return null;
    const box = new THREE.Box3().setFromObject(inner), size = box.getSize(new THREE.Vector3()), ctr = box.getCenter(new THREE.Vector3());
    const k = def.span / Math.max(size.x, size.y, size.z, 1e-3);
    inner.scale.setScalar(k);
    inner.position.set(-ctr.x * k, -box.min.y * k, -ctr.z * k);
    const g = new THREE.Group(); g.add(inner); return g;
  } catch (e) { return null; }
}