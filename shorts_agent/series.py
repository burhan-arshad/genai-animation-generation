"""Mystery series: ONE real case told as a mini-series of long episodes (about 7 minutes each, the same cast and objects in every episode,
every episode ends on a real open question and the next one starts with 'previously').
  plan    : research -> the series plan (cast, places, episodes with their reveals and cliffhanger) -> one job per episode (kind 'episode')
  episode : chapter plan -> every chapter written from ITS evidence (small AI calls) -> the usual line-by-line fact-check -> voice
  film    : one scene card per chapter (AI) -> code turns the cards into shots, with the series cast and objects -> the film engine
  python -m shorts_agent.series plan --topic "The Mary Celeste Abandonment (1872)" [--eps 3]     |     list"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from pydantic import BaseModel

from . import brand, filmboard as F, hooks, store, styles
from .config import SKILL_DIR
from .director import Timing
from .gemini_voice import load_plan
from .linecheck import ungrounded_names
from .llm import BudgetExceeded, generate_structured
from .retrieval import wikipedia_facts
from .schemas import Line, ScriptDraft, speak_numbers, to_script_json
from .topicgate import evidence_ok


def cfg() -> dict:
    def num(k, d, lo, hi):
        try:
            return max(lo, min(hi, int(os.getenv(k) or d)))
        except ValueError:
            return d
    return {"eps": num("SERIES_EPS", 3, 2, 6), "minutes": num("SERIES_MINUTES", 7, 3, 12), "wide": os.getenv("SERIES_WIDE", "0") == "1"}


@contextmanager
def episode_env():
    """The settings that make the usual stages work for a long episode (no speed-up of the voice, more shots, other duration limits)."""
    c = cfg()
    want = {"VOICE_MAX_SECONDS": "0", "VOICE_SEGMENTS": "8", "FILM_MAX_SHOTS": "220", "QA_MIN_DUR": "190", "QA_MAX_DUR": str(c["minutes"] * 120),
            "LONGFORM_WIDE": "1" if c["wide"] else "0"}
    old = {k: os.environ.get(k) for k in want}
    os.environ.update(want)
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def get_series(sid) -> dict | None:
    r = store.db().execute("SELECT * FROM series WHERE id=?", (sid,)).fetchone()
    return dict(r) if r else None


def bible_of(job: dict) -> dict:
    return json.loads(get_series(job["series_id"])["bible"])


def _toks(s: str) -> set[str]:
    return set(re.findall(r"[a-z]{4,}|\d{3,}", s.lower()))


def known_objects() -> set[str]:
    return set(F.PROPS) | set(F.EXTRA_PROPS)


# ───────────── 1. the series plan ─────────────
class Member(BaseModel):
    role: str
    look: F.Look


class EpPlan(BaseModel):
    title: str
    summary: str
    reveals: list[str]
    cliffhanger: str
    evidence: list[str]


class SeriesPlan(BaseModel):
    title: str
    logline: str
    place: str
    date: str
    key_object: str
    sets: list[F.SetDef]
    cast: list[Member]
    episodes: list[EpPlan]


PLAN_SYSTEM = """You plan a mini-series about ONE real mystery for a YouTube channel. Each episode is a 7-minute animated film told by a calm investigator host.
Use ONLY the evidence you are given (ids E1, E2...). Invent no event, person, date or number.
Return: title (3-6 words, no colon), logline (one sentence), place (short, e.g. 'North Atlantic'), date (e.g. '1872'), key_object (ONE object at the heart of the case, from the object list),
sets (2-4 recurring places: id lowercase letters, kind @KINDS@, time @TIMES@, sign a short name, deck true for a ship deck, dress = scenery from the object list),
cast (3-5 recurring people WITH a look: only people the evidence names, or plain roles such as 'the captain' or 'an inspector'; id lowercase letters; `role` = who they are in the story),
episodes (exactly @N@): title (2-5 words), summary (2 sentences), reveals (2-4 things the viewer learns, each stated in the evidence), cliffhanger (the REAL open question the episode ends on; the last episode ends on the best question that is still open), evidence (6-12 ids the episode may use).
Order the episodes so that each one answers a question and raises the next. Nothing graphic. No supernatural events: a legend may appear only as 'people said'.
look: body, hatCol, neckCol, hair as #RRGGBB; pattern @PAT@; hat @HATS@; neck @NECKS@; extra any of @EXTRAS@; hairStyle @HAIRS@; skin one of @SKINS@; dress true for a woman's dress; kid true for a child. Clothes fit the era, clearly different colours per person.
Objects: @OBJS@."""


def plan_system(eps: int) -> str:
    rep = {"@N@": str(eps), "@PAT@": ", ".join(F.PATTERNS), "@HATS@": ", ".join(F.HATS), "@NECKS@": ", ".join(F.NECKS), "@EXTRAS@": ", ".join(F.EXTRAS),
           "@HAIRS@": ", ".join(F.HAIRS), "@SKINS@": ", ".join(F.SKINS), "@KINDS@": ", ".join(F.SET_KINDS), "@TIMES@": ", ".join(F.TIMES),
           "@OBJS@": ", ".join(F.PROPS + sorted(F.EXTRA_PROPS))}
    s = PLAN_SYSTEM
    for k, v in rep.items():
        s = s.replace(k, v)
    return s


def gather(topic: str) -> list[dict]:
    """About 36 evidence paragraphs from several Wikipedia pages, interleaved so that every page is represented."""
    from .script_agent import Plan, interleave, plan_system as research_system
    plan = generate_structured(f"Topic: {topic}", Plan, task="research", temperature=0.2,
                               system=research_system() + "\nReturn 5 queries: the case itself, the discovery, the investigation, the theories, the aftermath or solution.")
    seen, items = set(), []
    for q in ([topic] + plan.queries)[:7]:
        for ev in wikipedia_facts(q, pages=3, max_chars=900):
            k = (ev["url"], ev["text"][:60])
            if k not in seen:
                seen.add(k)
                items.append(ev)
    items = interleave(items)[:int(os.getenv("SERIES_EVIDENCE", "36") or 36)]
    for i, ev in enumerate(items, 1):
        ev["id"] = f"E{i}"
    ok, score = evidence_ok(topic, items)
    if not ok or len(items) < 12:
        raise RuntimeError(f"Not enough research for a series about '{topic}' ({len(items)} paragraphs, match {score:.0%}): choose a case with more documents.")
    return items


def supplement(ep: EpPlan, items: list[dict], k: int = 10) -> None:
    have = list(ep.evidence)
    q = _toks(ep.title + " " + ep.summary + " " + " ".join(ep.reveals))
    rest = sorted((e for e in items if e["id"] not in have), key=lambda e: -len(q & _toks(e["text"])))
    ep.evidence = have + [e["id"] for e in rest[:max(0, k - len(have))]]


def fix_plan(plan: SeriesPlan, items: list[dict], eps: int) -> list[str]:
    problems = []
    ids = {e["id"] for e in items}
    if len(plan.episodes) < 2:
        problems.append("write at least 2 episodes")
    seen, cast = set(), []
    for m in plan.cast:
        m.look.id = F._id(m.look.id)
        if m.look.id and m.look.id not in seen and m.look.id not in ("hero", "host"):
            seen.add(m.look.id)
            cast.append(m)
    plan.cast = cast[:6]
    if len(plan.cast) < 2:
        problems.append("write at least 2 recurring characters with different ids")
    ko = F.canon(plan.key_object)
    plan.key_object = ko if ko in known_objects() else "scroll"
    for ep in plan.episodes:
        ep.evidence = [e for e in dict.fromkeys(ep.evidence) if e in ids]
        supplement(ep, items)
    sets, seen_s = [], set()
    for s in plan.sets:
        s.id = F._id(s.id)
        if s.id and s.id not in seen_s and s.id != "study":
            seen_s.add(s.id)
            sets.append(s)
    plan.sets = sets[:4] or [F.SetDef(id="main", kind="field", time="day", sign="", deck=False, dress=[])]
    return problems


def make_plan(topic: str, items: list[dict], eps: int) -> SeriesPlan:
    dig = "\n".join(f"{e['id']} [{e['title']}] {e['text'][:150]}" for e in items)
    base = f"TOPIC: {topic}\nEPISODES: exactly {eps}\n\nEVIDENCE:\n{dig}\n\nWrite the series plan."
    prompt, problems = base, []
    for _ in range(2):
        plan = generate_structured(prompt, SeriesPlan, system=plan_system(eps), temperature=0.6, task="script")
        problems = fix_plan(plan, items, eps)
        if not problems:
            return plan
        prompt = base + "\n\nYour previous plan had these problems:\n- " + "\n- ".join(problems) + "\nReturn the full corrected plan."
    raise RuntimeError("Could not plan the series:\n- " + "\n- ".join(problems))


def create_series(topic: str, eps: int | None = None, source: str = "") -> int:
    c = cfg()
    topic = topic.strip()
    if len(topic) < 8:
        raise ValueError("the topic is too short")
    items = gather(topic)
    plan = make_plan(topic, items, eps or c["eps"])
    bible = {"title": plan.title.strip()[:60], "logline": plan.logline.strip(), "place": plan.place.strip()[:18], "date": plan.date.strip()[:14],
             "key_object": plan.key_object, "sets": [s.model_dump() for s in plan.sets],
             "cast": [{"role": m.role.strip()[:60], "look": m.look.model_dump()} for m in plan.cast],
             "episodes": [{"title": e.title.strip()[:50], "summary": e.summary.strip(), "reveals": [r.strip() for r in e.reveals[:4]],
                           "cliffhanger": e.cliffhanger.strip(), "evidence": e.evidence} for e in plan.episodes],
             "evidence": items, "minutes": c["minutes"], "topic": topic}
    con, now = store.db(), time.time()
    cur = con.execute("INSERT INTO series(title, topic, status, bible, created, updated) VALUES(?,?,?,?,?,?)",
                      (bible["title"], topic, "active", json.dumps(bible, ensure_ascii=False), now, now))
    con.commit()
    sid = cur.lastrowid
    for n, e in enumerate(bible["episodes"], 1):
        jid = store.add_job(f"{bible['title']}: {e['title']}", styles.default_key())
        store.set_job(jid, series_id=sid, ep_no=n, kind="episode", **({"source": source} if source else {}))
    return sid


# ───────────── 2. an episode: chapters, each written from its own evidence ─────────────
class Chapter(BaseModel):
    title: str
    purpose: str
    evidence: list[str]


class ChapterList(BaseModel):
    chapters: list[Chapter]


class CLine(BaseModel):
    text: str
    evidence: list[str]
    numbers: list[str]


class ChapterText(BaseModel):
    lines: list[CLine]


CH_SYSTEM = """You split ONE episode of a real-mystery series into chapters. You get the episode plan and its evidence (ids E1...).
Return exactly @K@ chapters in story order: title (2-4 words), purpose (one sentence: what the viewer learns or feels), evidence (2-4 ids of the episode evidence that state it; use each id in one chapter when possible).
Chapter 1 is the cold open: the strangest concrete moment of this episode, then the recap. The last chapter gives the last reveal and ends on the cliffhanger. The middle chapters tell the reveals in order and raise one question each."""

EP_SYSTEM = """You write one chapter of an episode of a real-mystery documentary series, narrated by a calm, curious investigator. Hushed storyteller tone: the suspense comes from the facts, never from shouting.
Use ONLY facts stated in the EVIDENCE of this chapter. Each line lists the evidence ids that state its facts (`evidence`) and every number or year it speaks, as digits, in `numbers`; in `text` write numbers as spoken words.
Each line is one spoken CUT of 6-13 words. Never state a theory as fact: say 'investigators believed' or 'one theory says'. Never accuse a living person or anyone who was never convicted.
Respect victims: nothing graphic. No invented quotes, dialogue, thoughts or feelings of real people. No supernatural events. Never start a line with a year. Short spoken sentences, no filler."""


def default_chapters(ep: dict, k: int) -> list[dict]:
    ids = ep["evidence"] or []
    size = max(2, -(-len(ids) // k))
    out = []
    for i in range(k):
        grp = ids[i * size:(i + 1) * size] or ids[-size:]
        purpose = ("Cold open on the strangest moment, then the recap." if i == 0 else
                   "Give the last reveal and end on the open question." if i == k - 1 else
                   (ep["reveals"][i - 1] if i - 1 < len(ep["reveals"]) else "Tell the next step of the story."))
        out.append({"title": f"Part {i + 1}", "purpose": purpose, "evidence": grp})
    return out


def plan_chapters(b: dict, n: int, ev: dict, k: int) -> list[dict]:
    ep = b["episodes"][n - 1]
    try:
        dig = "\n".join(f"{i} [{ev[i]['title']}] {ev[i]['text'][:170]}" for i in ep["evidence"] if i in ev)
        r = generate_structured(f"SERIES: {b['title']}\nEPISODE {n} of {len(b['episodes'])}: {ep['title']}\nSUMMARY: {ep['summary']}\nREVEALS: {' | '.join(ep['reveals'])}\n"
                                f"CLIFFHANGER: {ep['cliffhanger']}\n\nEVIDENCE:\n{dig}\n\nPlan the chapters.", ChapterList,
                                system=CH_SYSTEM.replace("@K@", str(k)), temperature=0.5, task="script")
        cards = [{"title": c.title.strip()[:40], "purpose": c.purpose.strip()[:200], "evidence": [e for e in c.evidence if e in ev]} for c in r.chapters][:k + 2]
        if len(cards) >= 3 and all(c["evidence"] for c in cards):
            return cards
    except BudgetExceeded:
        raise
    except Exception as e:
        print(f"[series] the chapter plan failed ({type(e).__name__}): using an even split")
    return default_chapters(ep, k)


def write_chapter(b: dict, n: int, ci: int, k: int, card: dict, ev: dict, prev: list[str], recap: str, nxt: str, words: int, blob: str) -> list[dict]:
    ep, eps_n = b["episodes"][n - 1], len(b["episodes"])
    if ci == 0:
        role = ("COLD OPEN. The first two lines are the HOOK: 3-10 words each, start inside the strangest concrete moment (an object, a place, a number) with a contradiction; "
                "never start with a year, a greeting or 'Did you know'; do not give the answer. "
                + (f"Then recap in 2-4 lines the story so far: {recap}" if n > 1 else "Then say in one or two lines what this case is and why it still matters."))
    elif ci == k - 1:
        role = (f"FINAL CHAPTER. Tell this last reveal, then close on this open question in the narrator's words: {ep['cliffhanger']}. "
                + (f"The last line is short, unfinished and points to {nxt}." if nxt else "The last line leaves the viewer with the biggest question that is still open."))
    else:
        role = "Tell this part of the story in order, one picture per line, with a turn (But, Then, Until) every 2-3 lines."
    paras = "\n".join(f"{i} [{ev[i]['title']}]\n{ev[i]['text'][:600]}" for i in card["evidence"] if i in ev)
    before = ("The chapter before ended with: " + " / ".join(prev) + "\n") if prev else ""
    base = (f"SERIES: {b['title']} ({b['logline']})\nEPISODE {n} of {eps_n}: {ep['title']}\nCHAPTER {ci + 1} of {k}: {card['title']}: {card['purpose']}\n{role}\n"
            f"Write about {words} words ({max(6, words // 11)}-{max(8, words // 8)} lines).\n{before}\nEVIDENCE:\n{paras}\n\nWrite the chapter.")
    prompt, kept = base, []
    for attempt in range(2):
        out = generate_structured(prompt, ChapterText, system=EP_SYSTEM, temperature=0.7, task="script")
        kept, problems = [], []
        for cl in out.lines:
            text = speak_numbers(cl.text).strip()
            ids = [e for e in dict.fromkeys(cl.evidence) if e in ev]
            if not text or len(text.split()) > 22:
                continue
            bad = []
            if not ids:
                bad.append("no valid evidence id")
            else:
                cited = " ".join(ev[e]["text"] for e in ids).replace(",", "")
                for num in cl.numbers:
                    n2 = num.replace(",", "").strip()
                    if n2 and not re.search(rf"(?<!\d){re.escape(n2)}(?!\d)", cited):
                        bad.append(f"the number {num} is not in the cited evidence")
            names = ungrounded_names(text, blob)
            if names:
                bad.append("name not in the evidence: " + ", ".join(names))
            if bad:
                problems.append(f"'{text[:50]}': {'; '.join(bad)}")
            else:
                kept.append({"text": text, "evidence": ids, "numbers": list(cl.numbers)})
        if len(kept) >= 4 and (not problems or attempt == 1):
            break
        prompt = base + "\n\nYour previous chapter had these problems; fix them and return the whole chapter:\n- " + "\n- ".join(problems[:8] or ["write at least 6 lines"])
    if len(kept) < 3:
        raise RuntimeError(f"chapter {ci + 1} of episode {n} could not be written from its evidence")
    return kept


def ensure_hook(lines: list[dict], b: dict, ep: dict, ev: dict) -> None:
    if len(lines) < 3 or not hooks.hook_ok(lines[0]["text"], lines[1]["text"]):
        return
    from .script_agent import pick_hook
    h = pick_hook(b["topic"], [ev[i] for i in ep["evidence"] if i in ev][:10])
    if h:
        for l, t in zip(lines[:2], (h.line0, h.line1)):
            l["text"], l["evidence"], l["numbers"] = t, list(h.evidence), list(h.numbers)


def prepare(project: Path) -> None:
    st = styles.active()
    if not project.exists():
        shutil.copytree(SKILL_DIR / "styles" / (st.engine or st.key) / "example", project)
        shutil.rmtree(project / "data", ignore_errors=True)
        (project / "data").mkdir(exist_ok=True)
    F.sync_overlay(project, st)


def write_episode(job: dict, project: Path) -> None:
    b = bible_of(job)
    n, eps_n = int(job["ep_no"]), len(b["episodes"])
    ep = b["episodes"][n - 1]
    ev = {e["id"]: e for e in b["evidence"]}
    k = max(4, min(8, round(b["minutes"] * 0.75)))
    words = int(b["minutes"] * 140)
    cards = plan_chapters(b, n, ev, k)
    k = len(cards)
    blob = (" ".join(ev[i]["text"] + " " + ev[i]["title"] for i in ep["evidence"] if i in ev) + " "
            + " ".join([b["title"], b["place"], b["date"], b["logline"], ep["title"], ep["summary"], " ".join(ep["reveals"]), ep["cliffhanger"]]
                       + [m["look"]["id"].replace("_", " ") + " " + m["role"] for m in b["cast"]])).lower()
    recap = " ".join(f"Episode {i + 1}: {b['episodes'][i]['summary']}" for i in range(n - 1))[:600]
    nxt = f"episode {n + 1}, '{b['episodes'][n]['title']}'" if n < eps_n else ""
    lines, prev = [], []
    for ci, card in enumerate(cards):
        got = write_chapter(b, n, ci, k, card, ev, prev, recap, nxt, words // k, blob)
        for g in got:
            g["ch"] = ci
        lines += got
        prev = [g["text"] for g in got][-3:]
        print(f"[series] episode {n}, chapter {ci + 1}/{k}: {len(got)} lines")
    ensure_hook(lines, b, ep, ev)
    used = sorted({e for l in lines for e in l["evidence"]}, key=lambda x: int(x[1:]))
    sources, seen = [], set()
    for i in used:
        e = ev[i]
        if e["url"] not in seen:
            seen.add(e["url"])
            sources.append(f"{e['title']} ({e['source']}): {e['url']}")
    prepare(project)
    st = styles.active()
    draft = ScriptDraft(title=f"{b['title']}: Episode {n}", sources=sources or ["Wikipedia"], lines=[Line(text=l["text"], caps="") for l in lines])
    sj = to_script_json(draft, st, "mystery" if "mystery" in st.music_options else st.music)
    sj["lines"] = [{"text": l["text"], "ch": l["ch"]} for l in lines]
    nxt_title = b["episodes"][n]["title"] if n < eps_n else ""
    sj["series"] = {"id": job["series_id"], "title": b["title"], "logline": b["logline"], "ep": n, "eps": eps_n, "ep_title": ep["title"],
                    "recap": recap[:300], "next_title": nxt_title}
    sj["hook"] = {"type": "series", "text": ep["title"].upper()[:30], "end_type": "cliffhanger", "candidates": [],
                  "end_question": (f"NEXT: {nxt_title}" if nxt_title else "WHAT DO YOU THINK?").upper()[:26]}
    (project / "script.json").write_text(json.dumps(sj, indent=2, ensure_ascii=False), encoding="utf-8")
    (project / "research.json").write_text(json.dumps({"topic": b["topic"], "style": st.key, "evidence": b["evidence"],
                                                       "lines": [{"text": l["text"], "evidence": l["evidence"], "numbers": l["numbers"]} for l in lines]},
                                                      indent=2, ensure_ascii=False), encoding="utf-8")
    total = sum(len(l["text"].split()) for l in lines)
    print(f"[series] episode {n}: {len(lines)} lines, {total} words (about {total / 140:.1f} minutes)")


# ───────────── 3. the film: one scene card per chapter, shots made by code ─────────────
class Reveal(BaseModel):
    line: int
    word: str
    object: str
    move: str


class Beat2(BaseModel):
    line: int
    word: str
    mood: str


class CCall(BaseModel):
    line: int
    word: str
    text: str


class SceneCard(BaseModel):
    set: str
    time: str
    cast: list[str]
    object: str
    mood: str
    reveals: list[Reveal]
    beats: list[Beat2]
    callouts: list[CCall]
    effect: str
    fx: str


SCENE_SYSTEM = """You direct ONE chapter of an animated mystery film (flat cartoon people in layered sets). You get the chapter's spoken lines (with their numbers), the recurring cast, the sets and the objects. Return ONE scene card:
set (one id from the list), time (@TIMES@), cast (1-3 ids from the list who are in the scene), object (the ONE object this chapter is about, from the objects list), mood (@MOODS@: the people's feeling at the start),
reveals (0-4): moments when an object appears on a spoken word: line (the line number), word (a word really spoken in that line), object (from the list), move (rise, drop, slide_l, slide_r, grow, shake),
beats (0-4): mood changes of the people on a spoken word: line, word, mood,
callouts (0-3): a year, a number, a name or a sign shown on screen on a spoken word: line, word, text (max 24 characters, digits allowed, for example '1872' or '10 DAYS'),
effect (none, shake, flash, dutch: a tilted camera for the moment something does not add up) and fx (none, dust, rain, snow, embers, fireflies).
Show only what the lines say. Nothing supernatural, nothing graphic. Night, dusk, storm and sepia suit mystery moods; use day for facts and records."""


def clean_card(raw: dict, b: dict, lo: int, hi: int) -> dict:
    cast_ids = [m["look"]["id"] for m in b["cast"]]
    set_ids = [s["id"] for s in b["sets"]]
    known = known_objects()
    obj = F.canon(raw.get("object"))
    chars = [x for x in (F._id(i) for i in (raw.get("cast") or [])) if x in cast_ids][:3] or cast_ids[:2]
    sid = F._id(raw.get("set"))
    inr = lambda x: isinstance(x.get("line"), int) and lo <= x["line"] < hi
    return {"set_id": sid if sid in set_ids else set_ids[0], "time": F._pick(raw.get("time"), F.TIMES, ""), "cast": list(dict.fromkeys(chars)),
            "object": obj if obj in known else b["key_object"], "mood": F._pick(raw.get("mood"), F.MOODS, "think"),
            "effect": F._pick(raw.get("effect"), F.EFFECTS, "none"), "fx": F._pick(raw.get("fx"), F.FXS, "none"),
            "reveals": [{"line": r["line"], "word": str(r.get("word", "")), "object": F.canon(r.get("object")), "move": F._pick(r.get("move"), F.MOVES, "pop")}
                        for r in (raw.get("reveals") or []) if inr(r) and F.canon(r.get("object")) in known][:4],
            "beats": [{"line": r["line"], "word": str(r.get("word", "")), "mood": F._pick(r.get("mood"), F.MOODS, "shock")} for r in (raw.get("beats") or []) if inr(r)][:4],
            "callouts": [{"line": r["line"], "word": str(r.get("word", "")), "text": re.sub(r"\s+", " ", str(r.get("text", ""))).strip()[:24]}
                         for r in (raw.get("callouts") or []) if inr(r) and str(r.get("text", "")).strip()][:3]}


def default_card(b: dict, ci: int, k: int) -> dict:
    ids = [m["look"]["id"] for m in b["cast"]]
    return clean_card({"set": b["sets"][ci % len(b["sets"])]["id"], "cast": ids[:2], "object": b["key_object"],
                       "mood": "think" if ci == 0 else ("worried" if ci == k - 1 else "neutral")}, b, 0, 10 ** 9)


def scene_card(b: dict, rng: list[int], texts: list[str], ci: int, k: int) -> dict:
    sysmsg = SCENE_SYSTEM.replace("@TIMES@", ", ".join(F.TIMES)).replace("@MOODS@", ", ".join(F.MOODS))
    prompt = (f"SERIES: {b['title']}\nCAST: " + "; ".join(f"{m['look']['id']} = {m['role']}" for m in b["cast"])
              + "\nSETS: " + "; ".join(f"{s['id']} ({s['kind']}, {s['time']})" for s in b["sets"])
              + f"\nKEY OBJECT OF THE CASE: {b['key_object']}\nOBJECTS: " + ", ".join(F.PROPS + sorted(F.EXTRA_PROPS))
              + f"\n\nCHAPTER {ci + 1} of {k}, spoken lines:\n" + "\n".join(f"{i}: {texts[i]}" for i in rng))
    try:
        raw = generate_structured(prompt, SceneCard, system=sysmsg, temperature=0.6, task="storyboard").model_dump()
    except BudgetExceeded:
        raise
    except Exception as e:
        print(f"[series] scene card {ci + 1} failed ({type(e).__name__}): a plain scene is used")
        return default_card(b, ci, k)
    return clean_card(raw, b, rng[0], rng[-1] + 1)


GEST = ["present", "point", "chin", "hip", "shrug", "hold"]
FRAMES = ["wide", "medium", "full", "medium", "close"]
CAMS = ["push_in", "pan_right", "pull_out", "pan_left", "drift", "crane_down"]
XS = {1: [45], 2: [32, 66], 3: [24, 50, 76]}


def scene_shots(card: dict, rng: list[int], ci: int, sid: str, first_tr: str) -> list[dict]:
    """One shot per spoken line: the chapter's cast, its object on the stage, reveals on their words, a different camera and framing every time."""
    chars = card["cast"][:3]
    xs = XS[len(chars)]
    rev = {r["line"]: r for r in card["reveals"]}
    beats, calls = {}, {}
    for bt in card["beats"]:
        beats.setdefault(bt["line"], []).append(bt)
    for c in card["callouts"]:
        calls.setdefault(c["line"], []).append(c)
    out, fx_done = [], False
    for j, i in enumerate(rng):
        acts = []
        for k, who in enumerate(chars):
            bl = []
            if k == 0:
                bl += [F._beat(bt["word"], mood=bt["mood"], arms=GEST[(i + 2) % 6]) for bt in beats.get(i, [])]
            if i in rev and k < 2:
                bl.append(F._beat(rev[i]["word"], "shock", "both_up" if k == 0 else "", "jump" if k == 0 else ""))
            x0 = xs[k]
            x1 = x0 + 9 if (j % 3 == 2 and k == 0) else x0
            acts.append(F._actor(who, x0, x1, d=1 if k < 2 else 0, face="r" if x0 < 50 else "l", mood=card["mood"], arms=GEST[(i + k) % 6],
                                 legs="walk" if x1 != x0 else "stand", beats=bl))
        props = [F._prop(card["object"], 58, 1, 1.4, "", "drop" if j == 0 else "pop")]
        if i in rev:
            r = rev[i]
            props.append(F._prop(r["object"], 20 if i % 2 else 82, 2, 1.1, r["word"], r["move"]))
        cl = [{"text": c["text"], "word": c["word"], "style": "pop" if c["text"].replace(",", "").isdigit() else "label"} for c in calls.get(i, [])]
        eff = card["effect"] if (i in rev and not fx_done) else "none"
        fx_done = fx_done or i in rev
        out.append(F._shot(i, "", sid, FRAMES[(i + ci) % 5], CAMS[(i + ci) % 6], 50, first_tr if j == 0 else "cut", eff, card["fx"], acts, props, cl, ""))
    return out


def chapters_of(script: dict) -> list[tuple[int, list[int]]]:
    out: dict[int, list[int]] = {}
    for i, l in enumerate(script["lines"]):
        out.setdefault(int(l.get("ch", 0)), []).append(i)
    return sorted(out.items())


def compile_draft(b: dict, script: dict, chapters: list, intro: int, outro: int, stamp: str):
    """chapters = [(chapter number, line numbers, scene card)] -> a StoryDraft for filmboard.build (the same checks as any other film)."""
    n = len(script["lines"])
    sets: dict[str, dict] = {}

    def set_for(card: dict) -> str:
        base = next((s for s in b["sets"] if s["id"] == card["set_id"]), b["sets"][0])
        t = card["time"] if card["time"] in F.TIMES else base["time"]
        sid = base["id"] if t == base["time"] else f"{base['id']}_{t}"
        if sid not in sets and len(sets) >= 7:
            sid, t = base["id"], base["time"]
        sets.setdefault(sid, {"id": sid, "kind": base["kind"], "time": t, "sign": base["sign"], "deck": base["deck"], "dress": base["dress"]})
        return sid

    shots, prev = [], None
    for ci, idxs, card in chapters:
        rng = [i for i in idxs if intro <= i < n - outro]
        if not rng:
            continue
        sid = set_for(card)
        shots += scene_shots(card, rng, ci, sid, "dissolve" if sid == prev else "fade")
        prev = sid
    return F.StoryDraft.model_validate({"title": script["title"], "place": b["place"], "date": b["date"], "intro_lines": intro, "outro_lines": outro,
                                        "intro_prop": b["key_object"], "outro_stamp": stamp, "cast": [m["look"] for m in b["cast"]],
                                        "sets": list(sets.values()), "custom_props": [], "shots": shots})


def build_story(project: Path, job: dict) -> None:
    st = styles.active()
    F.sync_overlay(project, st)
    script = json.loads((project / "script.json").read_text(encoding="utf-8"))
    b = bible_of(job)
    tm = Timing.load(project)
    n = len(script["lines"])
    texts = [l["text"] for l in script["lines"]]
    try:
        appear = brand.appear()
    except ValueError:
        appear = "first_last"
    intro, outro = F.host_lines(2, 1, appear, n)
    groups = chapters_of(script)
    cc = []
    for ci, idxs in groups:
        rng = [i for i in idxs if intro <= i < n - outro]
        if not rng:
            continue
        card = scene_card(b, rng, texts, ci, len(groups))
        cc.append((ci, idxs, card))
        print(f"[series] scene {len(cc)}/{len(groups)}: {card['set_id']}, {card['object']}, {len(card['reveals'])} reveal(s)")
    stamp = "CONTINUED" if int(job["ep_no"]) < len(b["episodes"]) else "THE END"
    draft = compile_draft(b, script, cc, intro, outro, stamp)
    story, problems, warns = F.build(draft, tm, hook=script.get("hook") or {}, appear=appear, plan=load_plan(project),
                                     cold=float(os.getenv("FILM_COLD_OPEN") or 2), loop=False)
    for w in warns[:12]:
        print("   warning:", w)
    if problems:
        raise RuntimeError("the film plan has problems:\n- " + "\n- ".join(problems))
    (project / "data").mkdir(exist_ok=True)
    (project / "data" / "story.json").write_text(json.dumps(story, indent=1, ensure_ascii=False), encoding="utf-8")
    from .storyboard_agent import run_check
    ok, out = run_check(project)
    (project / "logs").mkdir(exist_ok=True)
    (project / "logs" / "check_series.txt").write_text(out, encoding="utf-8")
    print(f"[series] render check {'OK' if ok else 'FAILED'}")
    if not ok:
        raise RuntimeError("the film engine could not draw the story:\n" + out[-800:])
    (project / "story.json").write_text(json.dumps(story, indent=1, ensure_ascii=False), encoding="utf-8")
    F.write_props_json(project, story)
    F.write_metrics(project, story, 1, False)


# ───────────── upload, assistant, overview ─────────────
def after_upload(svc, sid: int, ep_no: int, video_id: str) -> None:
    """Every episode goes into the series' own playlist (created with the first one)."""
    s = get_series(sid)
    b = json.loads(s["bible"])
    pid = s.get("playlist_id")
    if not pid:
        r = svc.playlists().insert(part="snippet,status", body={"snippet": {"title": b["title"][:100], "description": b["logline"][:500]},
                                                                "status": {"privacyStatus": "public"}}).execute()
        pid = r["id"]
        con = store.db()
        con.execute("UPDATE series SET playlist_id=? WHERE id=?", (pid, sid))
        con.commit()
    snip = {"playlistId": pid, "resourceId": {"kind": "youtube#video", "videoId": video_id}}
    try:
        svc.playlistItems().insert(part="snippet", body={"snippet": {**snip, "position": max(0, ep_no - 1)}}).execute()
    except Exception:
        svc.playlistItems().insert(part="snippet", body={"snippet": snip}).execute()
    print(f"  (added to the playlist '{b['title']}')")


def next_for_assistant(cfg_: dict, notes: list[str]):
    """Called by the assistant when no work is waiting: plan a new series from a fresh topic and return its first episode job."""
    from . import topics
    for _ in range(max(1, int(cfg_.get("topic_tries", 3)))):
        try:
            ideas = topics.suggest(1)
        except BudgetExceeded as e:
            notes.append(f"No series: the AI budget is used up ({str(e)[:80]}).")
            return None
        except (Exception, SystemExit) as e:
            notes.append(f"The topic agent failed: {str(e)[:150]}")
            continue
        if not ideas:
            continue
        try:
            sid = create_series(ideas[0].topic, source="assistant")
        except BudgetExceeded as e:
            notes.append(f"No series: the AI budget is used up ({str(e)[:80]}).")
            return None
        except (Exception, SystemExit) as e:
            notes.append(f"Planning '{ideas[0].topic}' failed: {str(e)[:150]}")
            jid = store.add_job(ideas[0].topic, styles.default_key())          # remembered as used: it is not suggested again
            store.set_job(jid, status="rejected", error="series planning failed: " + str(e)[:200])
            continue
        row = store.db().execute("SELECT id FROM jobs WHERE series_id=? ORDER BY ep_no LIMIT 1", (sid,)).fetchone()
        b = json.loads(get_series(sid)["bible"])
        notes.append(f"New series: {b['title']} ({len(b['episodes'])} episodes)")
        return row[0] if row else None
    notes.append("No suitable series was found this run.")
    return None


def overview() -> list[dict]:
    out = []
    for r in store.db().execute("SELECT * FROM series ORDER BY id DESC").fetchall():
        b = json.loads(r["bible"])
        jobs = {j["ep_no"]: dict(j) for j in store.db().execute(
            "SELECT id, ep_no, status, score, note, error, publish_at, youtube_id FROM jobs WHERE series_id=?", (r["id"],)).fetchall()}
        out.append({"id": r["id"], "title": b["title"], "logline": b["logline"], "topic": r["topic"], "place": b["place"], "date": b["date"],
                    "key_object": b["key_object"], "playlist_id": r["playlist_id"], "cast": [{"id": m["look"]["id"], "role": m["role"]} for m in b["cast"]],
                    "episodes": [{"no": i + 1, "title": e["title"], "cliffhanger": e["cliffhanger"], "job": jobs.get(i + 1)} for i, e in enumerate(b["episodes"])]})
    return out


def remove(sid: int) -> int:
    """Rejects (deletes) the episodes that were not uploaded; a series with uploaded episodes stays as 'done'."""
    con = store.db()
    rows = [dict(r) for r in con.execute("SELECT id, status FROM jobs WHERE series_id=?", (sid,))]
    drop = [r["id"] for r in rows if r["status"] != "uploaded"]
    store.delete_jobs(drop)
    if len(drop) == len(rows):
        con.execute("DELETE FROM series WHERE id=?", (sid,))
    else:
        con.execute("UPDATE series SET status='done' WHERE id=?", (sid,))
    con.commit()
    return len(drop)


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--topic", required=True)
    p.add_argument("--eps", type=int, default=None)
    sub.add_parser("list")
    a = ap.parse_args()
    if a.cmd == "plan":
        sid = create_series(a.topic, a.eps)
        s = [x for x in overview() if x["id"] == sid][0]
        print(f"\nSeries {sid}: {s['title']}: {s['logline']}")
        print("cast: " + ", ".join(f"{c['id']} ({c['role']})" for c in s["cast"]) + f" | key object: {s['key_object']}")
        for e in s["episodes"]:
            print(f"  Episode {e['no']} (job {e['job']['id']}): {e['title']}  ->  {e['cliffhanger']}")
        print("\nMake an episode:  python -m shorts_agent.pipeline run --job <job id>")
    else:
        for s in overview():
            print(f"{s['id']}: {s['title']} ({len(s['episodes'])} episodes)")
            for e in s["episodes"]:
                j = e["job"] or {}
                print(f"   {e['no']}. {e['title']}  [job {j.get('id', '-')}: {j.get('status', '-')}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())