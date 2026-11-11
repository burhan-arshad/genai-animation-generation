"""Quota-free test: intro backdrop + automatic host injection, rendered from a copy of the engine example."""
from __future__ import annotations

import os
import shutil

from . import brand, styles
from .config import PROJECTS_ROOT, REPO, SKILL_DIR
from .smoke import node
from .storyboard_agent import inject_host

SHOTS = """import { L } from './core/timing.js';
import * as K from './core/kit.js';
import * as S from './core/props.js';

export function buildShots() {
  const S_ = [], CUES = [];
  const cut = (i) => (i === 0 ? 0 : L(i) - 0.08);
  S_.push({ id: 'S01', at: cut(0), cam: [540, 900], note: 'intro backdrop (host is added by the engine)',
    draw(lt, d, t) {
      S.stage({ sky: 'day', ground: 'street', groundY: 900, skyline: true }, t);
      S.house(150, 1180, 1.3, { kind: 'timber', smoke: true, t });
      S.house(430, 1170, 1.15, { kind: 'brick', lit: true, smoke: true, t });
      S.tree(40, 1280, 1.6, 'oak', t, 1);
      S.barrel(560, 1340, 1.3); S.crate(640, 1350, 1.2);
    } });
  S_.push({ id: 'S02', at: cut(2), cam: [540, 900], note: 'story scene, no host',
    draw(lt, d, t) {
      S.stage({ sky: 'dusk', ground: 'street', groundY: 900, skyline: true }, t);
      S.house(200, 1200, 1.4, { kind: 'timber', smoke: true, t });
      S.house(700, 1190, 1.3, { kind: 'brick', lit: true, smoke: true, t });
      S.crowd(100, 1450, 800, 5, 4, t, { moving: true });
      S.flame(980, 1220, 1.0, t);
    } });
  for (const s of S_) CUES.push({ t: +s.at.toFixed(3), type: 'whoosh' });
  return { shots: S_, cues: CUES };
}
"""

if __name__ == "__main__":
    styles.set_active("history")
    project = PROJECTS_ROOT / "test-host"
    if project.exists():
        shutil.rmtree(project)
    shutil.copytree(SKILL_DIR / "styles" / "paper-atlas" / "example", project)
    shutil.copytree(REPO / "overlay" / "history", project, dirs_exist_ok=True)
    brand.write_js(project)
    (project / "src" / "shots.js").write_text(inject_host(SHOTS), encoding="utf-8")
    node(project, "check")
    node(project, "sheet", "review/all.jpg", "0.5", "10")
    if hasattr(os, "startfile"):
        os.startfile(project / "review" / "all.jpg")