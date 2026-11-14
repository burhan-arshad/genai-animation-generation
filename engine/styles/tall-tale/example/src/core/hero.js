// The channel host, our own character: a Toon (flat cut-out) with two extra drawing hooks.
// Hair (messy / curly / side) and a leather satchel with a rolled map. Colours come from brand/brand.json.
import { INK, shadeOf } from './toon.js';

export const HERO = {
  // drawn on the body, before the arms
  decorBody(g, { bx, top, bot }) {
    const bag = this.satchel || '#8A5A35';
    g.save(); g.lineCap = 'round'; g.lineJoin = 'round';
    g.save(); g.translate(bx - 96, bot - 62); g.rotate(-0.5);                       // rolled map sticking out of the bag
    g.fillStyle = '#F2E6CF'; g.strokeStyle = INK; g.lineWidth = 7; g.beginPath(); g.roundRect(-16, -96, 32, 100, 10); g.fill(); g.stroke();
    g.fillStyle = '#A8322D'; g.fillRect(-16, -62, 32, 12); g.strokeRect(-16, -62, 32, 12);
    g.restore();
    g.strokeStyle = INK; g.lineWidth = 20; g.beginPath(); g.moveTo(bx + 54, top + 14); g.lineTo(bx - 86, bot - 36); g.stroke();   // strap
    g.strokeStyle = bag; g.lineWidth = 11; g.beginPath(); g.moveTo(bx + 54, top + 14); g.lineTo(bx - 86, bot - 36); g.stroke();
    g.fillStyle = bag; g.strokeStyle = INK; g.lineWidth = 8;                                                                        // bag
    g.beginPath(); g.roundRect(bx - 142, bot - 62, 88, 78, 12); g.fill(); g.stroke();
    g.fillStyle = shadeOf(bag, 0.8); g.beginPath(); g.roundRect(bx - 142, bot - 62, 88, 30, [12, 12, 4, 4]); g.fill(); g.stroke();
    g.fillStyle = '#C8952F'; g.beginPath(); g.arc(bx - 98, bot - 30, 7, 0, 7); g.fill();
    g.restore();
  },
  // drawn on the head, after everything else (same squash / lean / flip as the head)
  decorHead(g, { hx, hy, r }) {
    const col = this.hair || '#2B2118', style = this.hairStyle || 'messy';
    const n = style === 'curly' ? 26 : style === 'side' ? 24 : 14, rx = r * 1.04, ry = r;
    const outer = [];
    for (let i = 0; i <= n; i++) {
      const a = Math.PI * (1.03 + 0.94 * i / n);
      const k = style === 'messy' ? (i % 2 ? 1.2 : 1.03) : style === 'curly' ? (i % 2 ? 1.14 : 1.0) : 1.05 + 0.05 * Math.sin(i * 0.5);
      outer.push([hx + Math.cos(a) * rx * k, hy + Math.sin(a) * ry * k]);
    }
    const xl = outer[0][0], xr = outer[n][0], fringe = [];
    for (let i = 0; i <= 20; i++) {
      const u = 1 - i / 20, x = xr + (xl - xr) * (i / 20);
      const y = style === 'side' ? hy - r * 0.8 + u * r * 0.3 + Math.sin(u * 9) * 5 : hy - r * 0.6 + Math.sin(u * (style === 'curly' ? 26 : 18)) * (style === 'curly' ? 10 : 12);
      fringe.push([x, y]);
    }
    g.save(); g.fillStyle = col; g.strokeStyle = INK; g.lineWidth = 9; g.lineJoin = 'round';
    g.beginPath(); outer.forEach(([x, y], i) => (i ? g.lineTo(x, y) : g.moveTo(x, y))); fringe.forEach(([x, y]) => g.lineTo(x, y)); g.closePath(); g.fill(); g.stroke();
    g.strokeStyle = shadeOf(col, 1.7); g.lineWidth = 8; g.lineCap = 'round'; g.beginPath(); g.arc(hx - 24, hy + 6, r * 0.9, Math.PI * 1.2, Math.PI * 1.48); g.stroke();
    g.restore();
  },
};

/** brand look + the hero's drawing hooks */
export function heroLook(look = {}) { return { ...look, ...HERO, extra: [...(look.extra || [])] }; }