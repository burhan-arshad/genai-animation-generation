import * as HOST from './core/host.js';
import { ctx, W, H, TAU, clamp, lerp, seg, eo, eio, eob, rnd, rr, circle, ell, line } from './core/lib.js';
import { L, Wd, T } from './core/timing.js';
import * as K from './core/kit.js';
import * as SC from './core/props.js';

// Local helper functions for Paper Atlas "The Great Stink" (1858)
function stinkFog(x, y, s, t, seed = 0) {
  ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
  for (let i = 0; i < 5; i++) {
    const p = (t * 0.25 + i * 0.2 + rnd(seed + i)) % 1;
    const dy = -p * 200;
    const dx = Math.sin(t * 1.5 + i + seed) * 40;
    ctx.globalAlpha = 0.4 * (1 - p);
    K.cut(K.P_circ(dx, dy, 45 + p * 50), '#7A8042', { shadow: 0.2, edge: 0 });
  }
  ctx.restore();
}

function sewerPipe(x, y, s, t) {
  ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
  K.cut(K.P_rr(-220, -220, 440, 220, 4), SC.C.brickDark);
  K.cut(() => {
    ctx.beginPath();
    ctx.arc(0, -90, 100, Math.PI, 0);
    ctx.lineTo(100, 0); ctx.lineTo(-100, 0); ctx.closePath();
  }, '#231B15', { shadow: 0, edge: 4 });
  K.cut(() => {
    ctx.beginPath();
    ctx.moveTo(-80, -90);
    ctx.bezierCurveTo(-70, 40, -110, 90, -130, 160);
    ctx.lineTo(130, 160);
    ctx.bezierCurveTo(110, 90, 70, 40, 80, -90);
    ctx.closePath();
  }, '#4A4220', { shadow: 0.4, edge: 0 });
  ctx.restore();
}

function parliament(x, y, s) {
  ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
  K.cut(K.P_rr(-360, -180, 720, 180, 4), K.P.stone);
  for (let i = -3; i <= 3; i++) {
    if (i === 2) continue;
    K.cut(K.P_poly([[i * 90 - 20, -180], [i * 90, -260], [i * 90 + 20, -180]]), K.P.stoneDark);
  }
  const tx = 180;
  K.cut(K.P_rr(tx - 45, -420, 90, 240, 4), K.P.stoneDark);
  K.cut(K.P_poly([[tx - 55, -420], [tx, -520], [tx + 55, -420]]), SC.C.roofDark);
  circle(tx, -360, 22, K.P.gold);
  circle(tx, -360, 18, K.P.parch);
  ctx.restore();
}

function pumpingStation(x, y, s, t) {
  ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
  K.cut(K.P_rr(-220, -260, 440, 260, 6), SC.C.brick);
  K.cut(K.P_rr(-80, -380, 160, 120, 4), SC.C.brickDark);
  K.cut(K.P_poly([[-100, -380], [0, -500], [100, -380]]), SC.C.roofDark);
  for (const wx of [-150, -60, 60, 150]) {
    K.cut(K.P_rr(wx - 20, -180, 40, 90, [20, 20, 0, 0]), SC.C.window, { shadow: 0.3, edge: 3 });
  }
  K.cut(K.P_rr(180, -480, 40, 220, 3), SC.C.brickDark);
  ctx.restore();
  SC.smoke(x + 200 * s, y - 480 * s, s * 1.1, t, 6, '#8E887B');
}

function londonSewerMap(p, t) {
  K.parchment(3);
  K.cut(() => {
    ctx.beginPath();
    ctx.moveTo(-300, 950);
    ctx.bezierCurveTo(200, 850, 450, 1050, 750, 920);
    ctx.bezierCurveTo(900, 860, 1050, 920, 1400, 880);
    ctx.lineTo(1400, 1150);
    ctx.bezierCurveTo(1050, 1180, 900, 1120, 750, 1180);
    ctx.bezierCurveTo(450, 1310, 200, 1110, -300, 1210);
    ctx.closePath();
  }, '#8A7D58', { shadow: 0.5, edge: 5 });
  K.label('RIVER THAMES', 540, 1030, 38, '#3E2C1E');

  const northSewer = [[100, 720], [350, 700], [650, 730], [950, 710]];
  const southSewer = [[150, 1280], [400, 1220], [700, 1250], [980, 1200]];

  K.dashedRoute(northSewer, p);
  K.dashedRoute(southSewer, p);

  K.slip('NORTHERN INTERCEPTOR', 480, 640, clamp(p * 2), 0.01, 30);
  K.slip('SOUTHERN INTERCEPTOR', 520, 1340, clamp(p * 2), -0.01, 30);
  K.slip('EASTWARD OUTFALL', 960, 950, clamp((p - 0.4) * 2), 0.02, 28);
}

export function buildShots() {
  const S = [], CUES = [];
  const add = (o) => (S.push(o), o);
  const cue = (t, type, o = {}) => CUES.push({ t: +t.toFixed(3), type, ...o });
  const cut = (i) => (i === 0 ? 0 : L(i) - 0.08);

  // Shot 1a: 1858 London Intro (Host intro shot, left 60% packed)
  // Line 0 part 1: "In eighteen fifty-eight, a suffocating smell..."
  {
    const st = 0, yr = Wd('eighteen', 0) - st;
    add({
      id: 'S01a', at: st, cam: [540, 960], zoom: 0.08, note: '1858 intro backdrop, gold ribbon',
      draw(lt, d, t) {
        SC.stage({ sky: 'dusk', ground: 'street', groundY: 1100 }, t);
        // Props packed into left 60% (x < 650) for Host
        SC.house(120, 1100, 1.2, { kind: 'brick', lit: true, smoke: true, t });
        SC.factory(360, 1100, 0.8, t);
        SC.lamp(520, 1100, 1.0, true, t);
        SC.barrel(580, 1100, 1.0);
        stinkFog(240, 850, 1.2, t, 1);

        K.ribbon('1858', 340, 360, lt > yr ? eob(seg(lt, yr, yr + 0.35)) : 0);
        K.slip('GREAT STINK OF LONDON', 340, 500, lt > yr + 0.2 ? eob(seg(lt, yr + 0.2, yr + 0.5)) : 0, -0.02, 38);
      }
    });
    cue(st, 'whoosh');
    cue(st + yr, 'pop', { gain: 0.6 });
  }

  // Shot 1b: Smell rises over central London
  // Line 0 part 2: "...rose across central London."
  {
    const st = Wd('rose', 0) - 0.08, rs = Wd('rose', 0) - st;
    add({
      id: 'S01b', at: st, cam: [540, 960], zoom: 0.08, note: 'fog rising over London skyline',
      draw(lt, d, t) {
        SC.stage({ sky: 'dusk', ground: 'street', groundY: 1100, skyline: true }, t);
        SC.house(200, 1100, 1.3, { kind: 'brick', lit: true, smoke: true, t });
        SC.house(880, 1100, 1.3, { kind: 'timber', lit: true, t });
        SC.lamp(540, 1100, 1.1, true, t);

        stinkFog(320, 900, 1.6, t, 2);
        stinkFog(720, 920, 1.5, t, 3);

        K.slip('SUFFOCATING STINK', 540, 340, lt > rs ? eob(seg(lt, rs, rs + 0.3)) : 0, 0.02, 44);
      }
    });
    cue(st, 'whoosh');
    cue(st + rs, 'slide', { dur: 1.4, gain: 0.6 });
  }

  // Shot 2a: Hot summer weather
  // Line 1 part 1: "Hot summer weather exacerbated the stench..."
  {
    const st = cut(1), sm = Wd('summer', 1) - st;
    add({
      id: 'S02a', at: st, cam: [540, 1000], zoom: 0.08, note: 'hot blazing sun over Thames quay',
      draw(lt, d, t) {
        SC.stage({ sky: 'dusk', ground: 'dirt', groundY: 1080, seed: 2 }, t);
        K.cut(() => { ctx.beginPath(); ctx.rect(-300, 1080, W + 600, 220); }, '#6E6842', { shadow: 0.5, edge: 0 });

        SC.house(180, 1080, 1.2, { kind: 'cottage', lit: false, t });
        SC.cart(480, 1080, 1.1, t, 3);
        stinkFog(480, 1050, 1.3, t, 4);

        K.slip('HOT SUMMER 1858', 540, 320, lt > sm ? eob(seg(lt, sm, sm + 0.3)) : 0, -0.02);
      }
    });
    cue(st, 'whoosh');
    cue(st + sm, 'pop');
  }

  // Shot 2b: Untreated human waste along River Thames
  // Line 1 part 2: "...of untreated human waste along the River Thames."
  {
    const st = Wd('waste', 1) - 0.08, stch = Wd('thames', 1) - st;
    add({
      id: 'S02b', at: st, cam: [540, 1000], zoom: 0.08, note: 'dirty Thames river bank and crowds',
      draw(lt, d, t) {
        SC.stage({ sky: 'dusk', ground: 'dirt', groundY: 1050, seed: 3 }, t);
        K.cut(() => { ctx.beginPath(); ctx.rect(-300, 1050, W + 600, 280); }, '#5E5832', { shadow: 0.5, edge: 0 });

        stinkFog(300, 1100, 1.5, t, 5);
        stinkFog(750, 1120, 1.4, t, 6);

        SC.crowd(120, 1020, 840, 6, 2, t, { moving: true, h: 240 });
        K.slip('THE RIVER THAMES', 540, 380, lt > stch ? eob(seg(lt, stch, stch + 0.3)) : 0, 0.02);
      }
    });
    cue(st, 'whoosh');
    cue(st + stch, 'pop');
  }

  // Shot 3a: Inadequate sewer system
  // Line 2 part 1: "For years, an inadequate sewer system..."
  {
    const st = cut(2), sw = Wd('sewer', 2) - st;
    add({
      id: 'S03a', at: st, cam: [540, 1000], zoom: 0.09, note: 'sewer pipe dumping into river',
      draw(lt, d, t) {
        SC.stage({ sky: 'day', ground: 'dirt', groundY: 1100, seed: 4 }, t);
        K.cut(() => { ctx.beginPath(); ctx.rect(-300, 1100, W + 600, 400); }, '#5E5832', { shadow: 0, edge: 0 });

        sewerPipe(350, 1100, 1.15, t);
        stinkFog(350, 1100, 1.5, t, 7);

        K.slip('OLD SEWER SYSTEM', 540, 360, lt > sw ? eob(seg(lt, sw, sw + 0.3)) : 0, 0.02);
      }
    });
    cue(st, 'whoosh');
    cue(st + sw, 'sizzle', { dur: 1.8, gain: 0.7 });
  }

  // Shot 3b: Emptied directly into the waterway
  // Line 2 part 2: "...had emptied directly into the waterway."
  {
    const st = Wd('directly', 2) - 0.08, dr = Wd('waterway', 2) - st;
    add({
      id: 'S03b', at: st, cam: [540, 1000], zoom: 0.09, note: 'sludge pouring directly into Thames waterway',
      draw(lt, d, t) {
        SC.stage({ sky: 'day', ground: 'dirt', groundY: 1100, seed: 5 }, t);
        K.cut(() => { ctx.beginPath(); ctx.rect(-300, 1100, W + 600, 400); }, '#5E5832', { shadow: 0, edge: 0 });

        sewerPipe(350, 1100, 1.15, t);
        K.ship(780, 1180, 0.8, Math.sin(t * 2) * 0.03);

        K.slip('DIRECT TO WATERWAY', 540, 420, lt > dr ? eob(seg(lt, dr, dr + 0.3)) : 0, -0.02, 42);
      }
    });
    cue(st, 'whoosh');
    cue(st + dr, 'pop');
  }

  // Shot 4a: Miasma belief
  // Line 3 part 1: "People believed that miasma from the effluent..."
  {
    const st = cut(3), ms = Wd('miasma', 3) - st;
    add({
      id: 'S04a', at: st, cam: [540, 1000], zoom: 0.08, note: 'miasma fog spreading across town',
      draw(lt, d, t) {
        SC.stage({ sky: 'storm', ground: 'street', groundY: 1120, seed: 6 }, t);
        SC.house(200, 1120, 1.3, { kind: 'timber', lit: true, t });
        SC.house(880, 1120, 1.2, { kind: 'brick', lit: true, t });
        SC.lamp(540, 1120, 1.1, true, t);

        stinkFog(540, 1050, 2.2, t, 8);

        K.slip('MIASMA THEORY', 540, 340, lt > ms ? eob(seg(lt, ms, ms + 0.3)) : 0, 0.02);
      }
    });
    cue(st, 'whoosh');
    cue(st + ms, 'pop');
  }

  // Shot 4b: Contagious diseases
  // Line 3 part 2: "...transmitted contagious diseases."
  {
    const st = Wd('transmitted', 3) - 0.08, ds = Wd('diseases', 3) - st;
    add({
      id: 'S04b', at: st, cam: [540, 1000], zoom: 0.08, note: 'fearful Londoners walking through bad air',
      draw(lt, d, t) {
        SC.stage({ sky: 'storm', ground: 'street', groundY: 1120, seed: 7 }, t);
        SC.house(200, 1120, 1.3, { kind: 'timber', lit: true, t });
        SC.house(880, 1120, 1.2, { kind: 'brick', lit: true, t });

        K.figure({ x: 380, y: 1120, h: 480, role: 'merchant', walk: t * 2 });
        K.figure({ x: 700, y: 1120, h: 460, role: 'worker', dir: -1, walk: -t * 2 });
        stinkFog(540, 1050, 2.0, t, 9);

        K.slip('FEAR OF DISEASE', 540, 380, lt > ds ? eob(seg(lt, ds, ds + 0.3)) : 0, -0.02, 44);
      }
    });
    cue(st, 'whoosh');
    cue(st + ds, 'thud');
  }

  // Shot 5a: Three Cholera Outbreaks timeline
  // Line 4 part 1: "Three outbreaks of cholera had already..."
  {
    const st = cut(4), tr = Wd('three', 4) - st;
    add({
      id: 'S05a', at: st, cam: [540, 950], zoom: 0.07, note: 'timeline of cholera outbreaks',
      draw(lt, d, t) {
        SC.stage({ sky: 'storm', ground: 'dirt', groundY: 1150, seed: 8 }, t);
        SC.church(540, 1150, 1.1);
        SC.tree(200, 1150, 1.2, 'bare', t, 1);
        SC.tree(880, 1150, 1.2, 'bare', t, 2);

        const p = seg(lt, 0.1, d * 0.85);
        K.timeline(['1831', '1848', '1854', '1858'], 180, 680, 720, p, Math.min(2, Math.floor(p * 3.99)));

        K.slip('3 CHOLERA OUTBREAKS', 540, 320, lt > tr ? eob(seg(lt, tr, tr + 0.3)) : 0, 0, 50);
      }
    });
    cue(st, 'whoosh');
    cue(st + tr, 'pop');
  }

  // Shot 5b: Blamed on ongoing river problems
  // Line 4 part 2: "...been blamed on the ongoing river problems."
  {
    const st = Wd('blamed', 4) - 0.08, ch = Wd('river', 4) - st;
    add({
      id: 'S05b', at: st, cam: [540, 950], zoom: 0.07, note: 'focus on death toll and river crisis',
      draw(lt, d, t) {
        SC.stage({ sky: 'storm', ground: 'dirt', groundY: 1150, seed: 9 }, t);
        SC.church(540, 1150, 1.1);
        stinkFog(540, 1100, 1.8, t, 10);

        K.slip('25,000+ DEAD', 540, 380, lt > ch ? eob(seg(lt, ch, ch + 0.3)) : 0, -0.03, 46);
      }
    });
    cue(st, 'whoosh');
    cue(st + ch, 'slam');
  }

  // Shot 6a: Parliament forced to act
  // Line 5 part 1: "The crisis finally forced parliament to accept..."
  {
    const st = cut(5), pr = Wd('parliament', 5) - st;
    add({
      id: 'S06a', at: st, cam: [540, 980], zoom: 0.08, note: 'Palace of Westminster silhouette',
      draw(lt, d, t) {
        SC.stage({ sky: 'dusk', ground: 'street', groundY: 1100, seed: 10 }, t);
        parliament(540, 1100, 1.1);

        K.slip('PALACE OF WESTMINSTER', 540, 320, lt > pr ? eob(seg(lt, pr, pr + 0.3)) : 0, -0.02);
      }
    });
    cue(st, 'whoosh');
    cue(st + pr, 'pop');
  }

  // Shot 6b: Joseph Bazalgette's proposal
  // Line 5 part 2: "...a proposal from civil engineer Joseph Bazalgette."
  {
    const st = Wd('proposal', 5) - 0.08, bz = Wd('bazalgette', 5) - st;
    add({
      id: 'S06b', at: st, cam: [540, 980], zoom: 0.08, note: 'engineer Bazalgette and wax seal approval',
      draw(lt, d, t) {
        SC.stage({ sky: 'dusk', ground: 'street', groundY: 1100, seed: 11 }, t);
        parliament(540, 1100, 1.1);

        K.figure({ x: 280, y: 1100, h: 520, role: 'scholar', arm: 40 });

        K.slip('JOSEPH BAZALGETTE', 540, 360, lt > bz ? eob(seg(lt, bz, bz + 0.3)) : 0, 0.02, 46);
        K.seal(820, 520, lt > bz + 0.15 ? eob(seg(lt, bz + 0.15, bz + 0.45)) : 0, 'B');
      }
    });
    cue(st, 'whoosh');
    cue(st + bz, 'slam');
  }

  // Shot 7a: Vast network of intercepting sewers
  // Line 6 part 1: "He designed a vast network of intercepting sewers..."
  {
    const st = cut(6), sw = Wd('sewers', 6) - st;
    add({
      id: 'S07a', at: st, cam: [540, 900], zoom: 0.06, note: 'sewer network diagram map',
      draw(lt, d, t) {
        const p = seg(lt, 0.1, d * 0.85);
        londonSewerMap(p, t);
        K.compass(900, 340, 0.5);

        K.slip('82 MILES OF MAIN SEWERS', 540, 320, lt > sw ? eob(seg(lt, sw, sw + 0.3)) : 0, -0.02, 42);
      }
    });
    cue(st, 'whoosh');
    cue(st + sw, 'slide', { dur: 1.6, gain: 0.6 });
  }

  // Shot 7b: Move effluent eastward
  // Line 6 part 2: "...to move effluent eastward."
  {
    const st = Wd('move', 6) - 0.08, ea = Wd('eastward', 6) - st;
    add({
      id: 'S07b', at: st, cam: [540, 900], zoom: 0.06, note: 'outfall routes extending eastward',
      draw(lt, d, t) {
        const p = seg(lt + 0.4, 0.1, d * 0.85 + 0.4);
        londonSewerMap(clamp(p), t);

        K.slip('MOVING EFFLUENT EASTWARD', 540, 380, lt > ea ? eob(seg(lt, ea, ea + 0.3)) : 0, 0.02, 40);
      }
    });
    cue(st, 'whoosh');
    cue(st + ea, 'pop');
  }

  // Shot 8a: Massive pumping stations
  // Line 7 part 1: "Massive pumping stations were built..."
  {
    const st = cut(7), pm = Wd('pumping', 7) - st;
    add({
      id: 'S08a', at: st, cam: [540, 980], zoom: 0.08, note: 'Abbey Mills pumping station exterior',
      draw(lt, d, t) {
        SC.stage({ sky: 'day', ground: 'street', groundY: 1120, seed: 12 }, t);
        pumpingStation(540, 1120, 1.1, t);

        K.slip('ABBEY MILLS PUMPING STATION', 540, 330, lt > pm ? eob(seg(lt, pm, pm + 0.3)) : 0, 0.02, 40);
      }
    });
    cue(st, 'whoosh');
    cue(st + pm, 'thud');
  }

  // Shot 8b: Lift sewage into new outfall pipes
  // Line 7 part 2: "...to lift the sewage into new outfall pipes."
  {
    const st = Wd('sewage', 7) - 0.08, lf = Wd('pipes', 7) - st;
    add({
      id: 'S08b', at: st, cam: [540, 980], zoom: 0.08, note: 'steam flywheels turning inside pumping station',
      draw(lt, d, t) {
        SC.stage({ sky: 'day', ground: 'street', groundY: 1120, seed: 13 }, t);
        pumpingStation(540, 1120, 1.1, t);
        SC.wheel(240, 1020, 55, t * 4);
        SC.wheel(840, 1020, 55, t * 4);

        K.slip('STEAM-POWERED PUMPS', 540, 380, lt > lf ? eob(seg(lt, lf, lf + 0.3)) : 0, -0.02, 44);
      }
    });
    cue(st, 'whoosh');
    cue(st + lf, 'sparkle', { dur: 1 });
  }

  // Shot 9a: Monumental achievement
  // Line 8 part 1: "This monumental engineering achievement..."
  {
    const st = cut(8), mn = Wd('monumental', 8) - st;
    add({
      id: 'S09a', at: st, cam: [540, 960], zoom: 0.08, note: 'cleansed river Thames scenery',
      draw(lt, d, t) {
        SC.stage({ sky: 'day', ground: 'grass', groundY: 1080, seed: 14 }, t);
        K.cut(() => { ctx.beginPath(); ctx.rect(-300, 1080, W + 600, 400); }, K.P.sea, { shadow: 0.5, edge: 0 });

        K.ship(360, 1160, 0.85, Math.sin(t * 2) * 0.03);
        SC.tree(150, 1080, 1.3, 'oak', t, 1);
        SC.tree(910, 1080, 1.3, 'oak', t, 2);

        K.slip('ENGINEERING TRIUMPH', 540, 340, lt > mn ? eob(seg(lt, mn, mn + 0.35)) : 0, -0.02, 42);
      }
    });
    cue(st, 'whoosh');
    cue(st + mn, 'pop');
  }

  // Shot 9b: Cleansed the river
  // Line 8 part 2: "...ultimately cleansed the river."
  {
    const st = Wd('cleansed', 8) - 0.08, cl = Wd('cleansed', 8) - st;
    add({
      id: 'S09b', at: st, cam: [540, 960], zoom: 0.08, note: 'gold ribbon & seal of achievement',
      draw(lt, d, t) {
        SC.stage({ sky: 'day', ground: 'grass', groundY: 1080, seed: 15 }, t);
        K.cut(() => { ctx.beginPath(); ctx.rect(-300, 1080, W + 600, 400); }, K.P.sea, { shadow: 0.5, edge: 0 });

        K.ship(360, 1160, 0.85, Math.sin(t * 2) * 0.03);
        K.ship(720, 1220, 0.65, Math.sin(t * 1.8) * 0.03);
        SC.tree(150, 1080, 1.3, 'oak', t, 1);
        SC.tree(910, 1080, 1.3, 'oak', t, 2);

        K.ribbon('CLEANSED', 540, 360, lt > cl ? eob(seg(lt, cl, cl + 0.35)) : 0, 95);
        K.seal(540, 560, lt > cl + 0.25 ? eob(seg(lt, cl + 0.25, cl + 0.55)) * 1.15 : 0, 'V');
      }
    });
    cue(st, 'whoosh');
    cue(st + cl, 'sparkle', { dur: 1.2 });
  }

  return { shots: HOST.withHost(S), cues: CUES };
}
