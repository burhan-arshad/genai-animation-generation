
// Young History Student / Historical Explorer
// Cut-paper character renderer.
// Origin = ground point under the feet.
// At s = 1, character is approximately 640 px tall.

import { ctx, TAU, clamp } from './lib.js';
import { cut, P, P_rr, P_circ } from './kit.js';
import { BRAND } from './brand.js';

const CH = BRAND.character;

const ellP = (x, y, rx, ry) => () => {
  ctx.beginPath();
  ctx.ellipse(x, y, rx, ry, 0, 0, TAU);
};

// Safe color shading
const shade = (hex, k) => {
  if (typeof hex !== 'string' || !/^#[0-9A-Fa-f]{6}$/.test(hex)) {
    hex = '#4A3425';
  }

  const n = parseInt(hex.slice(1), 16);

  const f = v =>
    Math.max(0, Math.min(255, Math.round(v * (1 + k))));

  return `rgb(${f((n >> 16) & 255)},${f((n >> 8) & 255)},${f(n & 255)})`;
};

const stroke = (pts, color, w) => {
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = w;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';

  ctx.beginPath();

  pts.forEach((p, i) =>
    i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])
  );

  ctx.stroke();
  ctx.restore();
};

const limb = (a, b, color, w) => {
  stroke([a, b], P.edge, w + 8);
  stroke([a, b], color, w);
};

// ─────────────────────────────────────────
// POSES
// ─────────────────────────────────────────

export const POSES = {
  down:  { e: [92, -352], h: [96, -268] },
  wave:  { e: [134, -486], h: [146, -584] },
  point: { e: [140, -424], h: [232, -452] },
  hip:   { e: [132, -382], h: [76, -326] },
  think: { e: [104, -392], h: [38, -474] },
  up:    { e: [118, -524], h: [128, -624] },
};

// ─────────────────────────────────────────
// FACIAL EXPRESSIONS
// ─────────────────────────────────────────

export const MOODS = {
  happy: {
    bl: [0, -4],
    br: [-4, 0],
    eyes: 1,
    mouth: 'smile'
  },

  wow: {
    bl: [-14, -18],
    br: [-18, -14],
    eyes: 1.2,
    mouth: 'open'
  },

  worried: {
    bl: [4, -10],
    br: [-10, 4],
    eyes: 1,
    mouth: 'frown'
  },

  smug: {
    bl: [2, 2],
    br: [-14, -10],
    eyes: 0.8,
    mouth: 'smirk'
  },

  thinking: {
    bl: [0, 0],
    br: [-12, -8],
    eyes: 1,
    mouth: 'flat'
  },
};

// ─────────────────────────────────────────
// BODY SHAPES
// ─────────────────────────────────────────

const torso = () => {
  ctx.beginPath();

  ctx.moveTo(-58, -482);
  ctx.quadraticCurveTo(0, -498, 58, -482);
  ctx.quadraticCurveTo(96, -470, 90, -396);

  ctx.lineTo(76, -232);
  ctx.quadraticCurveTo(0, -216, -76, -232);
  ctx.lineTo(-90, -396);

  ctx.quadraticCurveTo(-96, -470, -58, -482);
  ctx.closePath();
};

const vestShape = () => {
  ctx.beginPath();

  ctx.moveTo(-54, -470);
  ctx.lineTo(-18, -462);
  ctx.lineTo(0, -438);
  ctx.lineTo(18, -462);
  ctx.lineTo(54, -470);

  ctx.lineTo(67, -240);
  ctx.quadraticCurveTo(0, -226, -67, -240);

  ctx.closePath();
};

const scarfWrap = () => {
  ctx.beginPath();

  ctx.moveTo(-58, -486);
  ctx.quadraticCurveTo(-35, -506, 0, -496);
  ctx.quadraticCurveTo(38, -506, 58, -486);

  ctx.lineTo(48, -462);
  ctx.quadraticCurveTo(0, -478, -48, -462);

  ctx.closePath();
};

const scarfTail = () => {
  ctx.beginPath();

  ctx.moveTo(-40, -478);
  ctx.quadraticCurveTo(-70, -450, -68, -400);
  ctx.lineTo(-92, -322);
  ctx.quadraticCurveTo(-55, -344, -42, -370);
  ctx.lineTo(-20, -450);

  ctx.closePath();
};

// ─────────────────────────────────────────
// MODERN HAIRSTYLES
// ─────────────────────────────────────────

// 1. Textured hairstyle
// Modern layered top with a natural front fringe.

const texturedHair = () => {
  ctx.beginPath();

  ctx.moveTo(-67, -548);

  ctx.bezierCurveTo(-80, -584, -77, -632, -43, -655);
  ctx.bezierCurveTo(-18, -675, 15, -674, 37, -655);
  ctx.bezierCurveTo(65, -645, 79, -610, 68, -565);

  ctx.bezierCurveTo(55, -578, 45, -590, 31, -594);
  ctx.bezierCurveTo(20, -575, 5, -577, -5, -597);
  ctx.bezierCurveTo(-19, -576, -36, -581, -44, -601);
  ctx.bezierCurveTo(-54, -585, -61, -568, -67, -548);

  ctx.closePath();
};

// 2. Side-part hairstyle
// Neat side sweep with a clean silhouette.

const sidePartHair = () => {
  ctx.beginPath();

  ctx.moveTo(-67, -548);

  ctx.bezierCurveTo(-83, -587, -77, -636, -40, -657);
  ctx.bezierCurveTo(-8, -680, 42, -663, 62, -632);
  ctx.bezierCurveTo(77, -609, 78, -578, 65, -550);

  ctx.bezierCurveTo(52, -573, 43, -589, 26, -598);
  ctx.bezierCurveTo(5, -607, -16, -595, -32, -585);
  ctx.bezierCurveTo(-43, -576, -55, -561, -67, -548);

  ctx.closePath();
};

// 3. Messy hairstyle
// Relaxed youthful hairstyle with irregular soft spikes.

const messyHair = () => {
  ctx.beginPath();

  ctx.moveTo(-67, -548);

  ctx.bezierCurveTo(-82, -574, -81, -609, -63, -626);
  ctx.lineTo(-69, -649);
  ctx.quadraticCurveTo(-42, -651, -34, -666);

  ctx.quadraticCurveTo(-10, -682, 2, -660);
  ctx.quadraticCurveTo(20, -688, 39, -659);

  ctx.quadraticCurveTo(67, -650, 75, -620);
  ctx.lineTo(67, -598);

  ctx.bezierCurveTo(62, -576, 58, -562, 65, -548);

  ctx.bezierCurveTo(46, -578, 31, -584, 16, -593);
  ctx.bezierCurveTo(-3, -579, -20, -585, -33, -601);
  ctx.bezierCurveTo(-47, -585, -57, -562, -67, -548);

  ctx.closePath();
};

// ─────────────────────────────────────────
// HISTORICAL BOOTS
// ─────────────────────────────────────────

function drawBoot(x, y, Lk) {

  const bootColor = Lk.boots || Lk.shoes || '#4A3425';
  const bootSole = Lk.bootSole || shade(bootColor, -0.35);

  // Outer leather silhouette
  cut(() => {
    ctx.beginPath();

    ctx.moveTo(x - 22, y - 76);
    ctx.lineTo(x + 22, y - 76);
    ctx.lineTo(x + 22, y - 24);

    ctx.quadraticCurveTo(x + 22, y - 13, x + 38, y - 8);

    ctx.lineTo(x + 40, y + 1);
    ctx.lineTo(x - 29, y + 1);

    ctx.quadraticCurveTo(x - 36, y - 4, x - 29, y - 18);
    ctx.lineTo(x - 22, y - 76);

    ctx.closePath();

  }, bootColor, {
    shadow: 0.5,
    edge: 4
  });

  // Boot cuff
  cut(
    P_rr(x - 25, y - 78, 50, 17, 5),
    shade(bootColor, 0.18),
    {
      shadow: 0.2,
      edge: 3
    }
  );

  // Sole
  stroke(
    [[x - 29, y - 2], [x + 40, y - 2]],
    bootSole,
    8
  );

  // Boot details
  stroke(
    [[x - 9, y - 47], [x + 10, y - 47]],
    shade(bootColor, 0.3),
    3
  );

  stroke(
    [[x - 9, y - 35], [x + 10, y - 35]],
    shade(bootColor, 0.3),
    3
  );
}

// ─────────────────────────────────────────
// CHARACTER
// ─────────────────────────────────────────

/**
 * o = {
 *   x, y, s, dir,
 *   mood, talk 0..1,
 *   eye -1..1, blink 0..1,
 *   arm, armL,
 *   walk (phase),
 *   hop 0..1,
 *   t,
 *   look (preset override)
 * }
 */

export function hero(o = {}) {

  // Resolve selected appearance
  const Lk =
    o.look ||
    CH.look ||
    CH.presets?.[CH.preset] ||
    CH.presets?.a ||
    CH;

  const s = (o.s ?? 1) * (CH.scale ?? 1);
  const dir = o.dir ?? 1;
  const t = o.t || 0;

  const mood = MOODS[o.mood] ? o.mood : 'happy';
  const M = MOODS[mood];

  const talk = clamp(o.talk || 0);
  const eye = o.eye || 0;
  const bt = t % 3.4;
  const autoBlink = bt > 3.25 ? Math.sin(((bt - 3.25) / 0.15) * Math.PI) : 0;
  const blink = clamp(o.blink ?? autoBlink);
  const hop = clamp(o.hop || 0);

  // Character colors
  const skin = Lk.skin || '#D9A273';
  const skinSh = shade(skin, -0.2);

  const hair = Lk.hair || '#2B1D14';
  const shirt = Lk.shirt || Lk.top || '#EBDDBF';

  const vest = Lk.vest || '#6B422B';
  const vestDark = Lk.vestDark || '#4B2D20';

  const scarf = Lk.scarf || '#A8322D';
  const pants = Lk.pants || '#3E352D';

  const yy = o.y - hop * 70 + Math.sin(t * 3) * 3;

  // Ground shadow
  ctx.fillStyle = 'rgba(62,44,30,0.28)';
  ctx.beginPath();

  ctx.ellipse(
    o.x,
    o.y + 10 * s,
    120 * s * (1 - hop * 0.25),
    15 * s,
    0,
    0,
    TAU
  );

  ctx.fill();

  ctx.save();
  ctx.translate(o.x, yy);
  ctx.scale(s * dir, s);

  // ───────────────────────────────────────
  // LEGS
  // ───────────────────────────────────────

  const sw = o.walk != null ? Math.sin(o.walk) * 28 : 0;

  for (const k of [-1, 1]) {

    const ax = k * 34 - k * sw;
    const ay = -40 - Math.max(0, k * sw) * 0.5;

    limb(
      [k * 32, -246],
      [ax, ay],
      pants,
      54
    );

    cut(
      P_rr(ax - 24, ay - 40, 48, 17, 4),
      shade(pants, -0.12),
      { shadow: 0.2, edge: 3 }
    );

    drawBoot(ax, ay + 30, Lk);
  }

  // ───────────────────────────────────────
  // SCARF TAIL
  // ───────────────────────────────────────

  cut(scarfTail, scarf, {
    shadow: 0.5,
    edge: 4
  });

  stroke(
    [[-67, -396], [-79, -348]],
    shade(scarf, -0.2),
    4
  );

  // ───────────────────────────────────────
  // SHIRT
  // ───────────────────────────────────────

  cut(torso, shirt, {
    shadow: 0.5,
    edge: 4
  });

  // Shirt collar
  cut(() => {
    ctx.beginPath();

    ctx.moveTo(-29, -486);
    ctx.lineTo(-5, -451);
    ctx.lineTo(0, -470);
    ctx.lineTo(5, -451);
    ctx.lineTo(29, -486);

    ctx.lineTo(15, -495);
    ctx.lineTo(0, -480);
    ctx.lineTo(-15, -495);

    ctx.closePath();
  }, shade(shirt, -0.1), {
    shadow: 0.2,
    edge: 2
  });

  // ───────────────────────────────────────
  // LEATHER VEST
  // ───────────────────────────────────────

  cut(vestShape, vest, {
    shadow: 0.5,
    edge: 4
  });

  stroke(
    [[-18, -462], [-25, -240]],
    vestDark,
    5
  );

  stroke(
    [[18, -462], [25, -240]],
    vestDark,
    5
  );

  stroke(
    [[-60, -242], [0, -230], [60, -242]],
    shade(vest, 0.25),
    5
  );

  // Golden vest buttons
  for (const by of [-430, -390, -350, -310]) {
    cut(
      P_circ(0, by, 5),
      Lk.buttons || '#C8952F',
      { shadow: 0.3, edge: 2 }
    );
  }

  // Vest pockets
  cut(
    P_rr(-48, -328, 28, 34, 4),
    vestDark,
    { shadow: 0.2, edge: 2 }
  );

  cut(
    P_rr(20, -328, 28, 34, 4),
    vestDark,
    { shadow: 0.2, edge: 2 }
  );

  // ───────────────────────────────────────
  // LEATHER BELT
  // ───────────────────────────────────────

  cut(
    P_rr(-70, -260, 140, 17, 3),
    Lk.belt || vestDark,
    { shadow: 0.3, edge: 3 }
  );

  cut(
    P_rr(-12, -266, 24, 28, 4),
    Lk.buckle || '#C8952F',
    { shadow: 0.3, edge: 2 }
  );

  cut(
    P_rr(-6, -260, 12, 16, 2),
    vestDark,
    { shadow: 0, edge: 0 }
  );

  // ───────────────────────────────────────
  // STUDENT SATCHEL
  // ───────────────────────────────────────

  const satchel = Lk.satchel || '#8A5A35';

  limb(
    [48, -463],
    [-58, -294],
    satchel,
    13
  );

  stroke(
    [[45, -460], [-56, -294]],
    shade(satchel, 0.25),
    3
  );

  cut(
    P_rr(-87, -315, 42, 65, 7),
    satchel,
    { shadow: 0.5, edge: 4 }
  );

  cut(
    P_rr(-87, -315, 42, 15, 4),
    vestDark,
    { shadow: 0.2, edge: 2 }
  );

  cut(
    P_circ(-66, -308, 4),
    Lk.buttons || '#C8952F',
    { shadow: 0, edge: 0 }
  );

  // ───────────────────────────────────────
  // ARMS
  // ───────────────────────────────────────

  const arm = (side, name) => {

    const pose = POSES[name] || POSES.down;
    const sh = [side * 62, -440];

    const e = [
      side * pose.e[0],
      pose.e[1]
    ];

    let h = [
      side * pose.h[0],
      pose.h[1]
    ];

    if (name === 'wave') {
      h = [
        h[0] + side * Math.sin(t * 10) * 22,
        h[1] - Math.abs(Math.sin(t * 10)) * 10
      ];
    }

    limb(sh, e, shirt, 36);
    limb(e, h, shirt, 32);

    // Sleeve cuff
    cut(
      P_circ(e[0], e[1], 17),
      shade(shirt, -0.12),
      { shadow: 0.2, edge: 2 }
    );

    // Hands
    cut(
      P_circ(h[0], h[1], 21),
      skin,
      { shadow: 0.4, edge: 4 }
    );
  };

  arm(-1, o.armL || 'down');
  arm(1, o.arm || 'down');

  // ───────────────────────────────────────
  // NECK
  // ───────────────────────────────────────

  cut(
    P_rr(-20, -512, 40, 46, 10),
    skin,
    { shadow: 0.2, edge: 3 }
  );

  // ───────────────────────────────────────
  // SCARF WRAP
  // ───────────────────────────────────────

  cut(scarfWrap, scarf, {
    shadow: 0.5,
    edge: 4
  });

  stroke(
    [[-42, -482], [0, -488], [42, -482]],
    shade(scarf, 0.2),
    4
  );

  // ───────────────────────────────────────
  // HEAD
  // ───────────────────────────────────────

  for (const k of [-1, 1]) {
    cut(
      P_circ(k * 66, -545, 16),
      skin,
      { shadow: 0.3, edge: 3 }
    );
  }

  cut(
    ellP(0, -550, 66, 74),
    skin
  );

  // ───────────────────────────────────────
  // MODERN HAIRSTYLE RENDERING
  // ───────────────────────────────────────

  const hs = Lk.hairStyle || 'textured';

  if (hs === 'textured' || hs === 'quiff') {

    cut(texturedHair, hair, {
      shadow: 0.4,
      edge: 4
    });

    // Natural hair highlights
    stroke(
      [[-42, -632], [-25, -652], [-5, -657]],
      shade(hair, 0.3),
      4
    );

    stroke(
      [[10, -650], [28, -646], [42, -632]],
      shade(hair, 0.2),
      3
    );

  } else if (hs === 'sidePart' || hs === 'short') {

    cut(sidePartHair, hair, {
      shadow: 0.4,
      edge: 4
    });

    // Side-part highlight
    stroke(
      [[-24, -648], [2, -658], [30, -645]],
      shade(hair, 0.3),
      4
    );

    stroke(
      [[24, -620], [42, -610]],
      shade(hair, 0.2),
      3
    );

  } else if (hs === 'messy') {

    cut(messyHair, hair, {
      shadow: 0.4,
      edge: 4
    });

    // Messy hair highlights
    stroke(
      [[-42, -638], [-27, -653], [-10, -653]],
      shade(hair, 0.3),
      4
    );

    stroke(
      [[12, -650], [30, -648]],
      shade(hair, 0.2),
      3
    );

  } else if (hs === 'curly') {

    for (let i = 0; i < 9; i++) {
      const a = Math.PI * (1.12 + i * 0.095);

      cut(
        P_circ(
          Math.cos(a) * 72,
          -552 + Math.sin(a) * 76,
          27
        ),
        hair,
        { shadow: 0.4, edge: 4 }
      );
    }

    cut(
      P_circ(0, -640, 30),
      hair,
      { shadow: 0.2, edge: 0 }
    );
  }

  // Optional full beard
  if (Lk.beard) {

    cut(
      () => {
        ctx.beginPath();

        ctx.moveTo(-64, -536);
        ctx.bezierCurveTo(-66, -462, -34, -446, 0, -446);
        ctx.bezierCurveTo(34, -446, 66, -462, 64, -536);

        ctx.bezierCurveTo(48, -516, 26, -526, 0, -526);
        ctx.bezierCurveTo(-26, -526, -48, -516, -64, -536);

        ctx.closePath();
      },
      hair,
      { shadow: 0.3, edge: 3 }
    );
  }

  // ───────────────────────────────────────
  // CHEEKS
  // ───────────────────────────────────────

  ctx.save();
  ctx.globalAlpha = 0.35;

  for (const k of [-1, 1]) {
    ctx.fillStyle = '#D9705A';

    ctx.beginPath();
    ctx.ellipse(k * 42, -516, 12, 7, 0, 0, TAU);
    ctx.fill();
  }

  ctx.restore();

  // ───────────────────────────────────────
  // EYEBROWS
  // ───────────────────────────────────────

  stroke(
    [[-46, -592 + M.bl[0]], [-14, -592 + M.bl[1]]],
    hair,
    8
  );

  stroke(
    [[14, -592 + M.br[0]], [46, -592 + M.br[1]]],
    hair,
    8
  );

  // ───────────────────────────────────────
  // EYES
  // ───────────────────────────────────────

  const open = M.eyes * (1 - blink);

  for (const k of [-1, 1]) {

    if (open < 0.12) {

      ctx.save();

      ctx.strokeStyle = '#2B2118';
      ctx.lineWidth = 5;
      ctx.lineCap = 'round';

      ctx.beginPath();
      ctx.arc(
        k * 27,
        -560,
        11,
        0.15 * Math.PI,
        0.85 * Math.PI
      );

      ctx.stroke();
      ctx.restore();

      continue;
    }

    cut(
      ellP(k * 27, -556, 14, 16 * open),
      '#FFFFFF',
      { shadow: 0, edge: 0 }
    );

    ctx.fillStyle = '#2B2118';

    ctx.beginPath();
    ctx.arc(
      k * 27 + eye * 5,
      -556,
      mood === 'wow' ? 5.5 : 7.5,
      0,
      TAU
    );

    ctx.fill();

    ctx.fillStyle = '#FFFFFF';

    ctx.beginPath();
    ctx.arc(
      k * 27 + eye * 5 + 2.5,
      -559,
      2.4,
      0,
      TAU
    );

    ctx.fill();
  }

  // ───────────────────────────────────────
  // ROUND VINTAGE GLASSES
  // ───────────────────────────────────────

  if (Lk.glasses) {

    ctx.save();

    ctx.strokeStyle = '#2B2118';
    ctx.lineWidth = 5;

    ctx.beginPath();

    ctx.arc(-27, -556, 24, 0, TAU);

    ctx.moveTo(51, -556);
    ctx.arc(27, -556, 24, 0, TAU);

    ctx.moveTo(-3, -558);
    ctx.lineTo(3, -558);

    ctx.moveTo(-51, -558);
    ctx.lineTo(-66, -550);

    ctx.moveTo(51, -558);
    ctx.lineTo(66, -550);

    ctx.stroke();
    ctx.restore();
  }

  // ───────────────────────────────────────
  // NOSE
  // ───────────────────────────────────────

  stroke(
    [[0, -546], [6, -526], [-4, -524]],
    skinSh,
    5
  );

  // ───────────────────────────────────────
  // MOUTH / TALKING ANIMATION
  // ───────────────────────────────────────

  const mc = '#5A2A22';

  const op = Math.max(
    talk,
    M.mouth === 'open' ? 0.8 : 0
  );

  if (op > 0.08) {

    cut(
      ellP(0, -506, 15 + 5 * op, 5 + 16 * op),
      '#5A2A22',
      { shadow: 0, edge: 0 }
    );

    ctx.fillStyle = '#D9705A';

    ctx.beginPath();
    ctx.ellipse(
      0,
      -498 + 6 * op,
      9,
      4 + 4 * op,
      0,
      0,
      TAU
    );

    ctx.fill();

  } else if (M.mouth === 'smile') {

    stroke(
      [[-20, -512], [0, -498], [20, -512]],
      mc,
      6
    );

  } else if (M.mouth === 'smirk') {

    stroke(
      [[-18, -508], [6, -500], [24, -516]],
      mc,
      6
    );

  } else if (M.mouth === 'frown') {

    stroke(
      [[-18, -500], [0, -512], [18, -500]],
      mc,
      6
    );

  } else {

    stroke(
      [[-16, -506], [16, -506]],
      mc,
      6
    );
  }

  ctx.restore();
}
