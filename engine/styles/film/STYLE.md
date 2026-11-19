# Film: history stories as a short film, 9:16

Flat vector people and places, drawn by code (2D canvas, no GPU, no three.js). Every scene is a layered set with parallax, the camera moves in
every shot, people act on beats, objects move, and the host (the History Student) appears only at the start (the hook) and at the end (the punchline).
Example: `example/` = **THE CARDIFF GIANT HOAX** (1869; 52 s, 19 shots).

## 1. Rules
- The host introduces (first 1-3 lines) and closes (last 1-2 lines) in his study, in front of a panel showing the story's key object. His voice then runs over the story.
- In between the story is a film: places, people, objects, cause and effect. A viewer with the sound off must understand it. Reveal each object on its spoken word.
- Camera moves in every shot (push_in, pull_out, pan, drift, crane, punch_in, handheld). At least 4 different moves and 3 framings per film, close-ups for reactions only.
- People act: a mood on a spoken word (`beats`), a gesture (arms), a walk (x0 -> x1). Objects move (rise, drop, slide, grow, shake, spin).
- Captions: one word at a time, white with a dark edge, low on the screen (y 1590). Callouts (years, numbers, names, signs) in `label`, `pop` or `stamp` style.
- Palette: flat saturated colours, navy #17203A for night and title cards, warm gold #F4C542 for emphasis, red #D9503F for danger and stamps.

## 2. Engine map (`example/src/core/`)
| file | gives you |
|---|---|
| `film.js` | `createFilm({ story, hero, makeCanvas })` -> `draw(g, t)`, `shots()`, `cues()`. Cameras, acting, props, callouts, transitions, sound cues |
| `people.js` | `drawPerson(g, look, state)`: moods, arm poses, walk, talk. Look fields = brand/brand.json (`body, pattern, hat, neck, extra, hairStyle, satchel, kid` + `skin, pants, dress`) |
| `props.js` | 52 built-in objects (`P`), `drawBlueprint` for the story's own objects (plain shapes), `PROP_SIZE` |
| `worlds.js` | `makeSet(def)`: kinds field, street, room, study (the host's), city, sea, desert, mountain, map, card; times day, dusk, night, dawn, sepia, storm |
| `fx.js` | dust, rain, snow, embers, confetti, leaves, fireflies, vignette, grain |
| `captions.js`, `timing.js` | one-word captions and the narration clock (same as the other styles) |
| `brand.js` | generated from brand/brand.json (the host's look) |

## 3. story.json (written by shorts_agent/filmboard.py, times are absolute seconds)
`{ title, meta, duration, cast{id: look}, sets{id: {kind, time, sign, deck, dress[]}}, custom{name: blueprint}, shots[] }`
shot = `{ id, at, end, set, framing, camera, focus_x, transition, effect, fx, note, actors[], props[], callouts[], panel? }`
actor = `{ who, x0, x1, d, face, mood, arms{l,r}, legs, talk, held{r}, beats[{t, mood, arms, act, face}] }`
prop = `{ name, x, d, s, t0, move, c, text }`. Stage x runs 0..100, depth d 0 (back) .. 2 (front).

## 4. QA
`node tools/capture.mjs sheet review/all.jpg 1 10` and read the sheet: every shot must show the thing its line talks about; nothing may cover a face
(callouts sit at y 210-700); people stay inside the frame. Rendering is cheap: a full film draws in about a minute.
