# Automated Short Generator and Uploader

Python agentic pipeline that turns a topic into a finished vertical short (script → voice → word timing → storyboard → render), with a resumable SQLite job queue.

## Pipeline

```
topic ─▶ Script agent ─▶ Kokoro TTS ─▶ Whisper word timings ─▶ Storyboard agent ─▶ render ─▶ mp4
        (LLM, validated)   (local)       (local)               (LLM + `check` loop)  (FFmpeg)
```

- **Script agent:** LLM writes the script as structured JSON; a deterministic validator (word count, caption rules) feeds problems back until it passes.
- **Storyboard agent:** LLM writes the per-video shot list; the render engine's `check` command is the judge, and its errors are fed back for retries.
- **Job queue:** SQLite state machine (`queued → scripted → timed → storyboarded → rendered`); a failed job resumes from its last good stage.

## Status

Work in progress. Planned: vision QA agent, fact-check agent, YouTube Data API upload, analytics feedback loop.

## Setup

```powershell
python -m uv venv --python 3.12
.\.venv\Scripts\Activate.ps1
python -m uv pip install -r requirements.txt
copy .env.example .env   # then add your own key
```

## Usage

```powershell
python -m shorts_agent.pipeline add "What happens if you hold your breath?"
python -m shorts_agent.pipeline run --limit 1
python -m shorts_agent.pipeline list
```

## Requirements and credits

Needs Node 22+, Python 3.10+, FFmpeg, Chrome, and a local copy of a faceless-shorts template/skill pack for rendering, voice and timing. That pack is **not included** in this repo and is not redistributed. Check its license before reuse.
