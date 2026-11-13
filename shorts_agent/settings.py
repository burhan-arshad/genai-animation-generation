"""Dashboard settings: read/write .env safely, field list for the Settings tab, niche creation and saving."""
from __future__ import annotations

import json
import os
import re

from . import niche
from .config import REPO

ENV = REPO / ".env"
CHAINS = ["RESEARCH", "SCRIPT", "FACTCHECK", "TOPICS", "STORYBOARD", "STORYBOARD_HARD", "PROPS", "PROPS_HARD", "VISION"]

# (key, label, kind, hint, group).  kind: text | number | secret | select:a,b,c | hidden
FIELDS = [
    ("NICHE", "Niche", "hidden", "", "hidden"),
    ("GEMINI_API_KEY", "Gemini API key", "secret", "Free key: aistudio.google.com/apikey", "ai"),
    ("GEMINI_MODEL", "AI model", "text", "Example: gemini-3.5-flash-lite", "ai"),
    ("PROJECTS_ROOT", "Folder where videos are saved", "text", "Empty = your home folder / faceless-shorts", "paths"),
    ("SKILL_DIR", "Engine folder (faceless-shorts)", "text", "The folder that contains SKILL.md. Empty = next to this project", "paths"),
    ("SKILL_PY", "Engine Python (python.exe of its venv)", "text", "Empty = ~/.faceless-shorts/venv", "paths"),
    ("UPLOAD_PRIVACY", "Upload as", "select:private,unlisted,public", "Keep private until you trust the videos", "youtube"),
    ("VIDEOS_PER_DAY", "Videos per day (daily routine)", "number", "1 to 10", "youtube"),
    ("PUBLISH_AT_UTC_HOUR", "Publish hour, UTC (public only)", "number", "0 to 23, empty = publish immediately", "youtube"),
    ("CATEGORY_ID", "YouTube category id", "text", "27 = Education, 17 = Sports. Empty = niche default", "youtube"),
    ("SYNTHETIC_DISCLOSURE", "Mark as AI/synthetic content", "select:false,true", "Read YouTube's policy before turning on", "youtube"),
    ("SMTP_USER", "Gmail address (for alerts)", "text", "Optional", "email"),
    ("SMTP_APP_PASSWORD", "Gmail app password", "secret", "Optional", "email"),
    ("ALERT_TO", "Send alerts to", "text", "Empty = same Gmail", "email"),
    ("VISION_QA", "Vision check", "select:off,advisory,gate", "Experimental, keep off", "adv"),
    ("DAILY_LIMITS", "Daily limits", "text", "model:number, comma separated", "adv"),
    ("RPM_LIMITS", "Per-minute limits", "text", "model:number, comma separated", "adv"),
] + [(f"GEMINI_MODEL_{c}", f"Models for {c.lower().replace('_', ' ')}", "text", "Comma separated, tried in order", "adv") for c in CHAINS]

NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{1,30}$")
BASE_BLOCK = "genocide|massacre|terror|suicide|\\brape|torture|murder|\\bsex\\b"
WRITING = ("- Clear, curious documentary narration; full flowing sentences with connecting words.\n"
           "- 95-110 words. Each entry in `lines` is one CUT (2-4 s): split sentences into 1-3 lines at natural pauses.\n"
           "- Structure: the surprising fact first (hook), what and where and when, how it unfolded, the turning point, "
           "why it matters, a punchy last line that echoes the hook.\n"
           "- Explain special terms in a few words. No invented quotes or dialogue. Nothing graphic.\n"
           "- Write years and numbers as spoken words in `text`; `caps` may use digits.")


def read() -> dict:
    out = []
    for key, label, kind, hint, group in FIELDS:
        v = os.environ.get(key, "")
        out.append({"key": key, "label": label, "kind": kind, "hint": hint, "group": group,
                    "value": "" if kind == "secret" else v, "set": bool(v)})
    return {"fields": out, "niche": os.getenv("NICHE") or "history"}


def _check(key: str, kind: str, v: str) -> str | None:
    if "\n" in v or "\r" in v:
        return "line breaks are not allowed"
    if kind == "number":
        if not v.isdigit():
            return "must be a number"
        if key == "PUBLISH_AT_UTC_HOUR" and not 0 <= int(v) <= 23:
            return "must be 0-23"
        if key == "VIDEOS_PER_DAY" and not 1 <= int(v) <= 10:
            return "must be 1-10"
    if kind.startswith("select:") and v not in kind[7:].split(","):
        return "invalid choice"
    if key == "NICHE" and v not in niche.available():
        return "unknown niche"
    return None


def _fmt(v: str) -> str:
    return "'" + v.replace("'", "\\'") + "'" if re.search(r"""[\s#'"]""", v) else v


def write_env(changes: dict) -> None:
    """Replace/append KEY=value lines, delete the line when the value is empty, keep comments and other keys."""
    lines = ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else []
    done, out = set(), []
    for line in lines:
        m = re.match(r"\s*([A-Z0-9_]+)\s*=", line)
        k = m.group(1) if m else None
        if k in changes:
            if k in done or not changes[k]:
                continue
            out.append(f"{k}={_fmt(changes[k])}")
            done.add(k)
        else:
            out.append(line)
    for k, v in changes.items():
        if v and k not in done:
            out.append(f"{k}={_fmt(v)}")
    ENV.write_text("\n".join(out) + "\n", encoding="utf-8")


def update(values: dict) -> list[str]:
    kinds = {k: kind for k, _, kind, _, _ in FIELDS}
    clean, errs = {}, []
    for k, v in values.items():
        if k not in kinds:
            continue
        v = (v or "").strip().strip('"')
        if kinds[k] == "secret" and not v:
            continue                                  # empty secret = keep the saved one
        if v:
            e = _check(k, kinds[k], v)
            if e:
                errs.append(f"{k}: {e}")
                continue
        clean[k] = v
    if errs:
        return errs
    write_env(clean)
    for k, v in clean.items():
        if v:
            os.environ[k] = v
        else:
            os.environ.pop(k, None)
    from . import llm
    llm._client = None                                # a new Gemini key must be picked up
    niche.load.cache_clear()
    return []


# ───────────── niches ─────────────
def build_niche(name: str, label: str, theme: str, topics: str, objects: str, avoid: str) -> dict:
    req: list[str] = []
    for o in re.split(r"[,\n]", objects or ""):
        words = re.findall(r"[A-Za-z0-9]+", o)
        if words:
            ident = words[0].lower() + "".join(w.capitalize() for w in words[1:])
            if re.fullmatch(r"[a-z][A-Za-z0-9]*", ident) and ident != "backdrop" and ident not in req:
                req.append(ident)
    extra = "|".join(re.escape(w.strip()) for w in re.split(r"[,\n]", avoid or "") if w.strip())
    tag = re.sub(r"[^a-z0-9]", "", name)
    return {
        "label": label, "engine": "paper-atlas",
        "props": {"mode": "generate", "theme": theme, "required": req[:8],
                  "style_note": "Muted paper tones with one accent colour. No real logos, brands, flags or likenesses of real people."},
        "writing": {"music_options": ["bed"], "min_words": 85, "max_words": 115, "rules": WRITING},
        "research": {"plan_hint": "Prefer the Wikipedia page about the specific event, person, place or object over generic pages."},
        "topics": {
            "system": ("You propose topics for 40-second educational Shorts about: " + topics + "\n"
                       "Each topic is ONE specific, well-documented subject with its own Wikipedia article, told as a surprising true story. Rules:\n"
                       "- `year` is the year of the event or discovery (use 0 if it does not apply); `region` is the country or place.\n"
                       "- Nothing graphic, political, religious or contested.\n- `topic` is a plain noun phrase.\n"
                       "- Be varied. Never repeat a used topic."),
            "regions": [], "year_min": None, "year_max": None, "min_evidence": 4,
            "block_regex": BASE_BLOCK + ("|" + extra if extra else ""),
            "formats": ["a surprising fact with a simple explanation", "a famous moment or discovery",
                        "a record or milestone", "the origin of something familiar"]},
        "storyboard": {"rules": "\n- Show the story with the NP props generated for this niche.", "era": {"props": {}}},
        "upload": {"category_id": "27", "hashtags": f"#shorts #{tag}", "tags": [name],
                   "footer": "Narrated and animated with AI tools. The script is written from the sources above."},
    }


def save_niche(name: str, data) -> list[str]:
    if not NAME_RE.match(name):
        return ["Name: use 2-31 lowercase letters, numbers, - or _ (start with a letter)."]
    if not isinstance(data, dict):
        return ["The niche must be a JSON object."]
    errs = niche.validate(name, data)
    try:
        re.compile(((data.get("topics") or {}).get("block_regex")) or "x")
    except re.error as e:
        errs.append(f"topics.block_regex is not a valid pattern: {e}")
    if errs:
        return errs
    (niche.DIR / f"{name}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    niche.load.cache_clear()
    return []