# Automated Short Generator and Uploader

An agentic Python pipeline that turns **a topic into a finished vertical short** (script, voice-over, word-synced captions,
animated scenes, sound, loudness-normalised MP4) and uploads it to YouTube. You choose the channel's niche, the on-screen host
and the voice in plain config files; automatic quality gates decide whether a video is good enough to publish.

```
topic ─▶ research ─▶ script ─▶ fact-check ─▶ voice ─▶ word timing ─▶ scene design ─▶ render ─▶ loudness ─▶ QA ─▶ upload
         (Wikipedia)  (LLM,     (evidence +   (Kokoro,  (Whisper)     (LLM writes     (headless  (FFmpeg)    (ffprobe)  (YouTube
                      checked    verifiable    local)                  scene code,     Chrome)                          Data API)
                      by code)   quotes)                               checked by code)
```

* **Free to run** on a normal laptop: the LLM calls use a free Gemini key (or any OpenAI-compatible API), the voice (Kokoro) and
  the timing (Whisper) run locally, rendering uses headless Chrome and FFmpeg. No GPU needed.
* **Fully automatic**: no human review step. Videos that fail a gate are *dropped*, never published.
* **Dynamic**: the niche, the host character, the voice, the models and the upload defaults are all configuration.
* **Resilient**: every LLM task has a *chain* of models; overloaded or rate-limited models are skipped automatically.

> **Status:** a working personal project, not a product. Read [Responsible use and limits](#responsible-use-and-limits) first.

---

## Contents
1. [How it works](#how-it-works)
2. [Requirements](#requirements)
3. [Quick start](#quick-start)
4. [Configuration](#configuration) (`.env`, `brand.json`, niches, LLM chains)
5. [Commands](#commands)
6. [Running it every day](#running-it-every-day)
7. [YouTube setup](#youtube-setup)
8. [Quality and safety gates](#quality-and-safety-gates)
9. [Troubleshooting](#troubleshooting)
10. [Project layout](#project-layout)
11. [Extending](#extending)
12. [Responsible use and limits](#responsible-use-and-limits)

---

## How it works

Every video is a **job** in a small SQLite database (`jobs.db`). A job moves through these stages; each stage is an idempotent step,
and a failed job resumes from the stage where it stopped.

| status after stage | stage | what happens | who decides |
|---|---|---|---|
| `scripted` | research + script | The planner picks search queries, Wikipedia evidence is collected (`E1..E16`), the writer writes the script **only from that evidence** and lists the evidence ids and every number it uses. Code checks that each number really appears in the cited evidence, plus word count and caption format. | LLM writes, code verifies |
| `verified` | fact-check | Claims are extracted, evidence is retrieved (Wikipedia + PubMed), a judge rules `SUPPORTED / PARTIAL / CONTRADICTED / NO_EVIDENCE` and must give a **verbatim quote** that code checks against the evidence. Weak claims are trimmed or removed automatically; a script that cannot be fixed is rewritten from scratch. | LLM judges, code verifies |
| `timed` | voice + timing | Kokoro speaks the script locally; Whisper gives the start time of every word. | local models |
| `storyboarded` | scene design | An LLM writes `shots.js` (one animated scene per line) from a library of props, people and backgrounds. Code validates it (forbidden APIs, era check, name clashes, enough scenery) and the renderer's own `check` command runs it; errors are fed back for retries. The host character is added **by code**, not by the LLM. | LLM writes, code + renderer verify |
| `rendered` | render | Headless Chrome captures every frame, FFmpeg encodes the MP4. | renderer |
| `finalized` | loudness | Audio is normalised (video stream copied, not re-encoded). | FFmpeg |
| `ready` | QA | Duration, resolution, audio, loudness, silence, black and frozen frames are measured. | `ffprobe` / `ffmpeg` |
| `uploaded` | upload | The video is uploaded with a title, a description that lists its sources, tags and category. | YouTube API |

Other statuses: `dropped` (a gate failed for good), `rejected` (you rejected it by hand).

The LLM only ever produces **text and code that is then checked by deterministic code**. That is the central design rule.

---

## Requirements

* Python **3.10 to 3.12** (3.12 recommended)
* **Node.js 22+**, **FFmpeg** (with `ffprobe`) and **Google Chrome**
* About 1 GB of disk for the voice and Whisper models, plus space for renders
* The **rendering engine pack** (see below). It is **not included** in this repository
* A free Gemini API key (https://aistudio.google.com) or any OpenAI-compatible API key
* Optional: a YouTube channel plus a Google Cloud OAuth client (only for uploading), a Gmail app password (only for e-mail alerts)

### The engine pack

The renderer (canvas / three.js scenes captured in headless Chrome), the Kokoro voice script and the Whisper timing script come from
a separate "faceless shorts" template pack. This repo only *drives* it and adds its own host character, scenery library and
all the automation around it. Get the pack from its author, check its license before reusing or redistributing anything from it,
and unzip it next to this repository (default `../faceless-shorts`) or point `SKILL_DIR` at it.

Install its models once (on Windows run this in **Git Bash**, which comes with Git for Windows):

```bash
cd faceless-shorts
bash scripts/setup.sh        # prints "All set"; installs Kokoro + Whisper into ~/.faceless-shorts
```

---

## Quick start

```bash
# 1. get the code and the engine pack side by side
git clone https://github.com/<you>/shorts-agent.git
cd shorts-agent

# 2. virtual environment + dependencies
python -m venv .venv
#   Windows PowerShell:  .\.venv\Scripts\Activate.ps1      (if blocked: Set-ExecutionPolicy -Scope Process Bypass)
#   macOS / Linux:       source .venv/bin/activate
pip install -r requirements.txt

# 3. configuration
cp .env.example .env         # Windows: copy .env.example .env
#    then edit .env: at least GEMINI_API_KEY (and CONTACT)

# 4. check the whole setup; fix every [FAIL] line
python -m shorts_agent.doctor
python -m shorts_agent.doctor --ping      # optional: one tiny request to each model, catches wrong names / keys

# 5. make your first video
python -m shorts_agent.pipeline add "The Great Molasses Flood of 1919"
python -m shorts_agent.pipeline run --job 1
python -m shorts_agent.pipeline list
# the video is in <PROJECTS_ROOT>/001-.../renders/final_norm.mp4

# 6. the dashboard (local only)
python -m shorts_agent.api       # then open http://127.0.0.1:8000
```

*(Using `uv`? `python -m uv venv --python 3.12`, then `python -m uv pip install -r requirements.txt`. Do not run `python -m uv` while a venv is activated.)*


Needs Node 22+, Python 3.10+, FFmpeg, Chrome, and a local copy of a faceless-shorts template/skill pack for rendering, voice and timing. That pack is **not included** in this repo and is not redistributed. Check its license before reuse.

Make one or two videos by hand first. Only then set up YouTube and the daily schedule.

---

## Configuration

### `.env`

`.env.example` documents every variable. The important ones:

| variable | meaning | default |
|---|---|---|
| `NICHE` | which niche pack (`niches/<name>.json`) new jobs use | `history` |
| `GEMINI_API_KEY` | Gemini key | |
| `GEMINI_MODEL_<TASK>` | model chain for a task: `RESEARCH`, `SCRIPT`, `FACTCHECK`, `TOPICS`, `STORYBOARD`, `STORYBOARD_HARD`, `VISION` (falls back to `GEMINI_MODEL`) | |
| `DAILY_LIMITS`, `RPM_LIMITS` | free-tier limits of your key, `model:number,...` | 20 / day, 5 / min |
| `PROVIDER_<NAME>_URL`, `PROVIDER_<NAME>_KEY` | an OpenAI-compatible provider, used as `name:model` in a chain | |
| `SKILL_DIR`, `PROJECTS_ROOT`, `SKILL_PY` | engine pack, output folder, engine Python | sensible defaults |
| `VIDEOS_PER_DAY` | target for `daily` | 1 |
| `UPLOAD_PRIVACY` | `private`, `unlisted` or `public` | `private` |
| `SYNTHETIC_DISCLOSURE` | set YouTube's altered/synthetic-content flag | `false` |
| `PUBLISH_AT_UTC_HOUR` | with `public`: schedule publication at this UTC hour | immediately |
| `SMTP_*`, `ALERT_TO` | e-mail alerts after the daily run | off |
| `VISION_QA` | `off`, `advisory`, `gate` (experimental) | `off` |

### `brand/brand.json`: the channel's identity

Created automatically on the first run; edit it (or use the dashboard's *Brand* tab).

* `channel.name`, `channel.tagline`
* `character.presets`: any number of host looks (skin, hair, hair style, glasses, shirt, vest, scarf, boots, satchel...);
  `character.preset` selects one; `character.appear` is `first`, `first_last` or `none`
* `voice.name`: a Kokoro voice (try several with `python -m shorts_agent.audition`), `voice.speed`, `voice.fx` (an optional FFmpeg audio filter)
* `audience.writing_note`: instructions to the writer about who is watching (language variant, context to explain, tone)

After changing the look of an existing video, reset it to `storyboarded` and run it again: only the render repeats.

### Niches: `niches/<name>.json`

A niche pack is everything that is specific to *what the channel is about*:

| section | controls |
|---|---|
| `writing` | the narration rules, word count, music choices |
| `research` | a hint for the search planner |
| `topics` | the topic agent's prompt, allowed regions and years, a block-list regex, story formats that rotate |
| `storyboard` | extra scene rules, and the **era check** (`era.props`: a prop name and the first year it may appear) |
| `upload` | YouTube category, hashtags, tags, description footer |

Shipped niches: `history` and `inventions`. Switch with `NICHE=inventions` in `.env` (or `pipeline add --niche inventions "..."`).
To create your own: copy `niches/_template.json` to `niches/<name>.json`, edit it, set `NICHE=<name>`, and run `python -m shorts_agent.doctor`.

The *visual* library (houses, trees, crowds, vehicles, fire, weather, people) is shared by all niches. A niche that needs new
props (planets, animals, food...) should add them to `overlay/<niche>/src/core/props.js`; the scene designer can also draw one-off
objects itself, with lower reliability.

### LLM chains, failover and other providers

Each task has a **chain**, for example `GEMINI_MODEL_SCRIPT=gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-3.8-flash`. For every call:

* a model that has used up its daily or per-minute budget is skipped (the counters live in `usage.db`);
* a `429` puts the model on a 60-second cool-down and the next model is used immediately;
* a `5xx` or timeout gets one quick retry, then the next model is used; after two failures in a row the model is skipped for
  `LLM_BREAKER_SECONDS` and then probed once;
* a model that returns unusable JSON is skipped for that call; a bad key or unknown model is skipped for ten minutes;
* if every model is busy the call waits for the soonest one (up to about a minute, a few times) and then gives up. A pipeline run
  stops without counting it as a video failure and continues next time.

To add a non-Gemini provider, set `PROVIDER_<NAME>_URL` and `PROVIDER_<NAME>_KEY` and write `name:model` in a chain.
Any API with an OpenAI-style `/chat/completions` endpoint works (Groq, OpenRouter, Mistral, OpenAI, a local server...). Vision
checks stay on Gemini models. Free tiers and model names change often: check the provider's docs, and use `doctor --ping`.

`python -m shorts_agent.llm usage` shows today's calls per model.

---

## Commands

```bash
python -m shorts_agent.doctor [--ping]              # check the installation
python -m shorts_agent.topics --n 3 --dry           # let the topic agent propose topics (does not queue)
python -m shorts_agent.pipeline add "Topic ..."     # queue a topic   (--niche <name> to override NICHE)
python -m shorts_agent.pipeline run [--job N]       # advance the next job (or job N) until ready / dropped
python -m shorts_agent.pipeline list                # all jobs, status, fact-check, QA
python -m shorts_agent.pipeline events N            # time per stage and errors of job N
python -m shorts_agent.pipeline reset N <status>    # re-run from a stage, e.g. storyboarded (re-render) or timed (new scenes)
python -m shorts_agent.pipeline reject N [N...]     # never upload these
python -m shorts_agent.uploader login               # one-time YouTube login
python -m shorts_agent.uploader run                 # upload the oldest ready video
python -m shorts_agent.daily                        # the whole day: topic -> video -> upload -> e-mail
python -m shorts_agent.api                          # dashboard on http://127.0.0.1:8000 (PORT in .env)
python -m shorts_agent.brandkit                     # channel avatar + banner from brand.json
python -m shorts_agent.audition                     # the same sentence in several voices
python -m shorts_agent.llm usage                    # LLM usage today
python -m pytest -q                                 # unit tests (no network, no quota)
```

The dashboard lets you queue topics, ask the topic agent for ideas, run a job, watch the log live, inspect the script, sources,
fact-check verdicts, QA and stage timings, edit `brand.json` and see LLM usage. It listens on `127.0.0.1` only and has **no login**:
do not expose it to the internet.

---

## Running it every day

`python -m shorts_agent.daily` does one day's work: if a ready video exists it uploads it; otherwise it asks the topic agent for
topics (when the queue is empty), builds videos until one passes every gate (up to four attempts), uploads it, and e-mails a summary.
It keeps a lock file so two runs never overlap and does nothing if today's upload already happened.

Google's free quotas reset at midnight Pacific time; schedule the run some hours after that. The computer must be on at that time.

**Windows (Task Scheduler)**

```powershell
@'
Set-Location C:\path\to\shorts-agent
New-Item -ItemType Directory -Force logs | Out-Null
.\.venv\Scripts\python.exe -m shorts_agent.daily *>> logs\daily.log
'@ | Set-Content run_daily.ps1
schtasks /Create /SC DAILY /ST 14:00 /TN "ShortsAgentDaily" /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\path\to\shorts-agent\run_daily.ps1" /F
```

In Task Scheduler tick *Run task as soon as possible after a scheduled start is missed* and untick *Start only if on AC power*.

**macOS / Linux (cron)**

```cron
0 14 * * * cd /path/to/shorts-agent && .venv/bin/python -m shorts_agent.daily >> logs/daily.log 2>&1
```

---

## YouTube setup

1. Create the channel; add an avatar and banner (`python -m shorts_agent.brandkit` makes both from your `brand.json`).
2. In Google Cloud: create a project, enable **YouTube Data API v3**, configure the OAuth consent screen (type *External*, *Testing*),
   **add your own Google account under Test users**, then create an **OAuth client ID of type Desktop app** and save the JSON as
   `client_secret.json` in the repository root.
3. `python -m shorts_agent.uploader login` (a browser opens; an "unverified app" warning is normal for your own app).
4. Keep `UPLOAD_PRIVACY=private` for the first uploads and look at them in YouTube Studio. When you trust the output, switch to
   `unlisted`, then `public`. The uploader prints the privacy YouTube actually applied; if it differs from what you asked for, your
   API project may still be restricted.

Notes: while the OAuth app is in *Testing* the login can expire after about a week (`daily` then e-mails you to run `login` again).
Upload quotas and the rules for unverified API projects change; check Google's current documentation.

---

## Quality and safety gates

| gate | catches |
|---|---|
| script validator | wrong length, broken captions, numbers that are not in the cited evidence |
| fact-check with verifiable quotes | claims the evidence contradicts or does not support, invented quotes |
| era check | props that did not exist in the story's year (a train in 1666) |
| code validator + renderer `check` | forbidden APIs, name clashes, thin scenes, scene code that crashes |
| QA | wrong duration/resolution, no audio, bad loudness, silence, black or frozen frames |
| topic agent filters | duplicates, risky themes, thin evidence, wrong region or years |
| vision QA (optional, experimental) | an image model looks at 8 frames. In our tests it gave different answers for the same video, so it is **off** by default |

The gates reduce risk, they do not remove it: a retrieval-based checker is only as good as its sources.

---

## Troubleshooting

| symptom | what to do |
|---|---|
| `doctor` prints `[FAIL]` | fix the lines in order: tools, engine pack, `.env`, model chains |
| `No module named uv` | you ran `python -m uv` with a venv activated: `deactivate` first |
| `[llm] ... 503 / ServerError` | normal on busy free tiers; the next model in the chain is used. If it is constant, add more models or another provider to the chain, and check `llm usage` |
| `[llm] ... 429` | a rate limit; the model cools down for 60 s. Check `RPM_LIMITS` / `DAILY_LIMITS` against aistudio.google.com/rate-limit |
| storyboard keeps failing | read `<project>/logs/shots_attemptN.js` and `check_attemptN.txt`; `pipeline reset N timed` tries again with fresh scenes |
| a video was `dropped` | `pipeline list` shows why; `pipeline events N` shows the stage |
| Google `Error 403: access_denied` | add your account under *Test users* of the OAuth consent screen |
| `YouTube Data API v3 has not been used` | enable the API in the Google Cloud project |
| dashboard port busy | set `PORT=8010` in `.env` |
| e-mail `SMTPServerDisconnected` | use port 587 (`SMTP_PORT=587`) and a Gmail *App Password* |

---

## Project layout

```
shorts_agent/
  config.py          paths and settings from .env
  llm.py             model chains, failover, usage log, Gemini + OpenAI-compatible providers
  niche.py styles.py niche packs -> styles
  topics.py          topic agent
  retrieval.py       Wikipedia / PubMed evidence
  script_agent.py    research-first writer
  factcheck_agent.py claim extraction, judge, verifiable quotes, auto-trim
  storyboard_agent.py scene-code writer + validators
  runner.py          drives the engine pack (voice, timing, check, cues, mix, render)
  finalize.py qa.py visionqa.py    loudness, QA, optional vision QA
  pipeline.py        job state machine        store.py  SQLite jobs and events
  uploader.py daily.py notify.py   YouTube upload, daily run, e-mail
  api.py web/        dashboard                brand.py brandkit.py audition.py
  doctor.py          installation check
overlay/<niche>/src/core/   host character (hero.js, host.js), scenery library (props.js), brand.js (generated)
niches/              niche packs
brand/brand.json     channel identity
tests/               unit tests
```

---

## Extending

* **New niche:** see [Niches](#niches-nichesnamejson).
* **New host look:** add a preset to `brand.json`; for new body parts edit `overlay/<niche>/src/core/hero.js`.
* **New props:** add functions to `props.js` and describe them in `SCENERY_API` in `styles.py`.
* **New LLM provider:** nothing to code if it speaks the OpenAI chat API; otherwise add a function next to `_gemini` / `_openai` in `llm.py`.
* **New upload target** (Instagram, TikTok): add a module next to `uploader.py`; the `ready` status is the hand-over point.

---

## Responsible use and limits

* **Platform rules.** YouTube has policies on repetitive or mass-produced content, on AI-generated content and on health, finance
  and political advice. Read them. Use a small daily volume, vary topics and formats, and watch your first videos.
* **Accuracy.** The fact-checker lowers the chance of a wrong claim but cannot remove it. You are responsible for what you publish.
  Every description lists the sources; keep that.
* **Sources.** Evidence comes from Wikipedia (CC BY-SA) and PubMed abstracts. Facts are paraphrased and sources are credited.
* **Reach and income are not guaranteed.** Short-form monetisation is small and the rules change.
* **Secrets.** Never commit `.env`, `client_secret.json`, `token.json` or `*.db` (the `.gitignore` already excludes them).
* **Licenses.** This repository's code is yours to license as you wish; the engine pack, the Kokoro voice model and Whisper have
  their own licenses. This project is not affiliated with Google, YouTube or any model provider.
