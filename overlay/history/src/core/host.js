// Adds the channel host on top of the first (and optionally last) shot. Called automatically by the storyboard agent.
import { clamp, lerp } from './lib.js';
import { hero } from './hero.js';
import { BRAND } from './brand.js';

const eo = (x) => 1 - Math.pow(1 - clamp(x), 3);

function intro(s) {
  const base = s.draw;
  return { ...s, draw(lt, d, t) {
    base(lt, d, t);
    const k = eo(lt / 0.5), talking = lt > 0.35 && lt < d - 0.2;
    hero({ x: lerp(1320, 800, k), y: 1440, s: 1.1, dir: -1, mood: lt > d * 0.62 ? 'smug' : 'happy',
      arm: lt < d * 0.6 ? 'wave' : 'point', talk: talking ? Math.abs(Math.sin(lt * 9)) : 0,
      walk: k < 1 ? t * 10 : undefined, eye: -0.4, t });
  } };
}

function outro(s) {
  const base = s.draw;
  return { ...s, draw(lt, d, t) {
    base(lt, d, t);
    const k = eo(lt / 0.4), hopT = lt - (d - 0.5);
    hero({ x: lerp(1300, 820, k), y: 1440, s: 1.0, dir: -1, mood: 'smug', arm: 'hip',
      hop: hopT > 0 ? Math.abs(Math.sin(hopT * 6)) * 0.5 : 0, eye: 0, t });
  } };
}

/** brand.json character.appear: 'first' | 'first_last' | 'none' */
export function withHost(S, appear = BRAND.character.appear) {
  if (appear === 'none' || !S.length) return S;
  const out = S.slice();
  out[0] = intro(out[0]);
  if (appear === 'first_last' && out.length > 1) out[out.length - 1] = outro(out[out.length - 1]);
  return out;
}