"""Quota-free smoke test: host presets and poses, plus a scenery scene, rendered from a copy of the engine example."""
from __future__ import annotations

import os
import shutil
import subprocess

from . import brand, styles
from .config import PROJECTS_ROOT, REPO, SKILL_DIR

SHOTS = """import { clamp } from './core/lib.js';
import { L } from './core/timing.js';
import * as K from './core/kit.js';
import * as H from './core/hero.js';
import * as S from './core/props.js';
import { BRAND } from './core/brand.js';

export function buildShots() {
  const SH = [], CUES = [];
  const cut = (i) => (i === 0 ? 0 : L(i) - 0.08);
  const add = (o) => SH.push(o);
  const pre = BRAND.character.presets, keys = Object.keys(pre);

  add({ id: 'A', at: cut(0), cam: [540, 900], note: 'host presets',
    draw(lt, d, t) {
      K.parchment(2);
      keys.forEach((k, i) => H.hero({ x: 200 + i * 340, y: 1300, s: 0.85, look: pre[k], mood: ['happy', 'smug', 'wow'][i % 3],
        arm: i === 0 ? 'wave' : 'hip', talk: i === 1 ? Math.abs(Math.sin(lt * 9)) : 0, t }));
    } });

  add({ id: 'B', at: cut(2), cam: [540, 900], note: 'poses',
    draw(lt, d, t) {
      K.parchment(4);
      ['wave', 'point', 'hip', 'think', 'up', 'down'].forEach((p, i) => H.hero({ x: 200 + (i % 3) * 340, y: i < 3 ? 800 : 1380, s: 0.5,
        arm: p, mood: ['happy', 'worried', 'thinking'][i % 3], walk: i === 5 ? t * 6 : undefined, hop: i === 4 ? Math.abs(Math.sin(t * 4)) : 0, t }));
    } });

  add({ id: 'C', at: cut(4), cam: [540, 900], note: 'day street scene',
    draw(lt, d, t) {
      S.stage({ sky: 'day', ground: 'street', groundY: 1080, skyline: true }, t);
      S.church(900, 1100, 1.0);
      S.house(170, 1230, 0.9, { kind: 'timber', lit: false, smoke: true, t });
      S.house(520, 1220, 0.85, { kind: 'brick', lit: true, smoke: true, t });
      S.tree(700, 1190, 0.8, 'oak', t, 1);
      S.lamp(620, 1300, 0.9, true, t);
      S.crowd(200, 1400, 600, 5, 3, t, { moving: true });
      S.cart(((lt * 260) % 1500) - 250, 1360, 0.9, t);
      S.flame(980, 1180, 0.8, t);
    } });

  add({ id: 'D', at: cut(6), cam: [540, 900], note: 'night, rain, castle, train',
    draw(lt, d, t) {
      S.stage({ sky: 'night', ground: 'grass', groundY: 1100, mountains: true }, t);
      S.castle(520, 1130, 1.0);
      S.tree(120, 1180, 0.9, 'pine', t, 2); S.tree(940, 1200, 0.8, 'bare', t, 3);
      S.factory(820, 1180, 0.6, t);
      S.train(((lt * 400) % 1700) - 350, 1360, 0.8, t);
      S.nightWash(0.25); S.rain(t);
    } });

  for (const s of SH) CUES.push({ t: +s.at.toFixed(3), type: 'whoosh' });
  return { shots: SH, cues: CUES };
}
"""


def node(project, *args):
    p = subprocess.run(["node", "tools/capture.mjs", *args], cwd=project,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    print((p.stdout + p.stderr)[-900:])
    if p.returncode != 0:
        raise SystemExit(f"capture.mjs {args[0]} failed")


if __name__ == "__main__":
    styles.set_active("history")
    project = PROJECTS_ROOT / "smoke-host"
    if project.exists():
        shutil.rmtree(project)
    shutil.copytree(SKILL_DIR / "styles" / "paper-atlas" / "example", project)
    shutil.copytree(REPO / "overlay" / "history", project, dirs_exist_ok=True)
    brand.write_js(project)
    (project / "src" / "shots.js").write_text(SHOTS, encoding="utf-8")
    node(project, "check")
    node(project, "sheet", "review/all.jpg", "0.5", "10")
    if hasattr(os, "startfile"):
        os.startfile(project / "review" / "all.jpg")