"""Research-first writer: topic -> Wikipedia evidence -> script written ONLY from that evidence."""
from __future__ import annotations

import argparse
import json
import re
import os
import shutil
from pathlib import Path

from pydantic import BaseModel

from . import brand, hooks, niche, store, styles
from .config import REPO, SKILL_DIR
from .llm import generate_structured
from .retrieval import wikipedia_facts
from .schemas import Line, ScriptDraft, check_script, repair_caps, repair_numbers, to_script_json


class Plan(BaseModel):
    queries: list[str]


class RLine(BaseModel):
    text: str
    caps: str
    evidence: list[str]
    numbers: list[str]


class RScript(BaseModel):
    title: str
    music: str
    hook_type: str
    end_type: str
    hook_text: str
    end_question: str
    hook_candidates: list[str]
    lines: list[RLine]


PLAN_SYSTEM = """You plan research for a 40-second educational short. Return 3-5 short search queries (2-6 words) that find
encyclopedic Wikipedia pages with the key dated, numeric, well-documented facts about the topic. Prefer the specific
event/person/place page over generic ones."""


def caption_rules(st: styles.Style) -> str:
    if st.caps_mode == "auto":
        return "CAPTIONS: the engine makes them (one word at a time). Always return an empty string for `caps`."
    return (f"In `caps`, split the line into chunks separated by ' | ', each chunk 1-{st.caps_max_words} words, EXACTLY one "
            "*highlighted word per chunk. Each chunk's first word must be a word actually spoken in that line "
            f"(digits may stand for spoken numbers). Example:\n{st.caps_example}")


def system_prompt() -> str:
    """Style-aware prompt for plain script rewrites (used by the fact-check auto-trim)."""
    st = styles.active()
    return f"You edit scripts for 40-second faceless Shorts in the '{st.key}' style.\n{st.write_rules}\n{caption_rules(st)}"


def writer_system(st: styles.Style, plan: tuple[str, str] | None = None) -> str:
    return (f"You write scripts for 40-second faceless YouTube Shorts in the '{st.key}' style.\n{st.write_rules}\n"
            f"{caption_rules(st)}\nSOURCE RULES (strict):\n"
            "- Use ONLY facts stated in the EVIDENCE. Never add facts, numbers, names or dates from memory. "
            "If the evidence lacks a detail, leave it out.\n"
            "- Use evidence from at least TWO different pages (the page title is in brackets in the list): never cite only one page.\n"
            "- List every number or year you speak, written as digits, in `numbers` (e.g. \"1666\"). Each must appear exactly "
            "in the cited evidence: do not round or estimate.\n"
            f"- `music`: one of {list(st.music_options)} (bounce = funny, ragtime = old-timey, mystery = hoaxes and puzzles, "
            "tension = disasters only, bed = calm).\n"
            + hooks.RULES + ("\n" + hooks.formula_text(*plan) if plan else "") + "\n"
            "HOOK OUTPUT: `hook_candidates` = three different possible first lines (different formulas) written BEFORE the script; use the best one as lines[0]. "
            "`hook_type` = the hook formula you used, `end_type` = the ending formula you used. "
            "`hook_text` = 3-6 words shown on screen in the first second as a claim or a question (digits are allowed here, e.g. A 10-FOOT STONE MAN?). "
            "`end_question` = a short question to the viewer shown on screen at the end (26 characters at most, e.g. WOULD YOU HAVE PAID?).")


def plan_system() -> str:
    st = styles.active()
    hint = niche.load(st.niche).get("research", {}).get("plan_hint", "") if st.niche else ""
    return PLAN_SYSTEM + ("\n" + hint if hint else "")

def interleave(items: list[dict]) -> list[dict]:
    """E1, E2, E3 come from different pages, so a writer that cites the first ones already uses several sources."""
    pages: dict[str, list[dict]] = {}
    for e in items:
        pages.setdefault(e["url"], []).append(e)
    out: list[dict] = []
    while any(pages.values()):
        for u in list(pages):
            if pages[u]:
                out.append(pages[u].pop(0))
    return out

def gather(topic: str) -> list[dict]:
    from . import topicgate
    hint, score = "", 0.0
    for attempt in (1, 2):
        plan = generate_structured(f"Topic: {topic}{hint}", Plan, system=plan_system(), temperature=0.2, task="research")
        seen, items = set(), []
        for q in (([topic] if attempt == 2 else []) + plan.queries)[:6]:
            for ev in wikipedia_facts(q):
                key = (ev["url"], ev["text"][:60])
                if key not in seen:
                    seen.add(key)
                    items.append(ev)
        items = interleave(items)[:int(os.getenv("EVIDENCE_ITEMS", "16"))]
        for i, ev in enumerate(items, 1):
            ev["id"] = f"E{i}"
        ok, score = topicgate.evidence_ok(topic, items)
        print(f"[research] {len(items)} evidence items from {len({e['url'] for e in items})} pages, topic match {score:.0%}")
        if ok:
            return items
        hint = "\nThe pages found so far were about something else. Put the exact names and the year from the topic into the queries."
    raise RuntimeError(f"The research does not match the topic '{topic}' (match {score:.0%}): the topic is too vague or not well documented.")

def evidence_block(items: list[dict]) -> str:
    n = int(os.getenv("EVIDENCE_CHARS", "900"))
    return "\n".join(f"{e['id']} [{e['title']} | {e['source']}]\n{e['text'][:n]}\n" for e in items)

def sources_for(r: RScript, ev: dict[str, dict]) -> list[str]:
    seen, out = set(), []
    for l in r.lines:
        for e in l.evidence:
            if e in ev and ev[e]["url"] not in seen:
                seen.add(ev[e]["url"])
                out.append(f"{ev[e]['title']} ({ev[e]['source']}): {ev[e]['url']}")
    return out


def check_research(r: RScript, ev: dict[str, dict]) -> list[str]:
    problems = []
    for i, l in enumerate(r.lines):
        ids = [e for e in l.evidence if e in ev]
        if not ids:
            problems.append(f"Line {i}: cite at least one valid evidence id (E1..E{len(ev)}).")
            continue
        blob = " ".join(ev[e]["text"] for e in ids).replace(",", "")
        for n in l.numbers:
            n2 = n.replace(",", "").strip()
            if n2 and not re.search(rf"(?<!\d){re.escape(n2)}(?!\d)", blob):
                problems.append(f"Line {i}: number {n} is not stated in cited evidence {ids}. "
                                "Use only numbers present in the evidence, or leave the number out.")
    urls = {ev[e]["url"] for l in r.lines for e in l.evidence if e in ev}
    need = int(os.getenv("MIN_SOURCES", "2"))
    if len(urls) < need:
        problems.append(f"Cite evidence from at least {need} DIFFERENT pages (see the title in brackets before each evidence text), not just items of one page.")
    return problems

SOFT = ("Narration has", "lines, got", "turn line", "The last line", "Line 0 has", "Lines 0-1 give", "DIFFERENT pages",
        "Need at least", "generic opener", "is vague")


def acceptable(draft: ScriptDraft, problems: list[str]) -> bool:
    """Only style notes are left (length a little off, no turn line, weak ending). The fact-check still guards the facts."""
    words = sum(len(l.text.split()) for l in draft.lines)
    return bool(draft.lines) and all(any(m in p for m in SOFT) for p in problems) and 60 <= words <= 170 and 6 <= len(draft.lines) <= 28

def write_from_evidence(topic: str, items: list[dict], plan: tuple[str, str] | None = None) -> tuple[RScript, ScriptDraft]:
    st, ev = styles.active(), {e["id"]: e for e in items}
    base = f"Topic: {topic}\n\nEVIDENCE:\n{evidence_block(items)}\nWrite the script."
    prompt, problems = base, []
    tries = max(2, int(os.getenv("SCRIPT_TRIES", "4")))
    for attempt in range(1, tries + 1):
        task = "script" if attempt <= 2 else "script_hard"
        r = generate_structured(prompt, RScript, system=writer_system(st, plan), task=task)
        draft = ScriptDraft(title=r.title, sources=sources_for(r, ev),
                            lines=[Line(text=l.text, caps=l.caps if st.caps_mode == "chunks" else "") for l in r.lines])
        draft = repair_numbers(draft)                         # digits in the spoken text become words, in code
        if st.caps_mode == "chunks":
            draft = repair_caps(draft)
        problems = check_research(r, ev) + check_script(draft) + hooks.check([l.text for l in draft.lines])
        from . import topicgate
        miss = topicgate.script_misses(topic, " ".join(l.text for l in draft.lines))
        if miss:
            problems.append(f"The script must be about '{topic}': it never mentions {', '.join(miss)}.")
        print(f"[script] attempt {attempt} ({task}): {len(problems)} problem(s)")
        for p in problems:
            print("   -", p[:200])
        if not problems:
            return r, draft
        if attempt >= min(3, tries) and os.getenv("SCRIPT_ACCEPT_SOFT", "1") != "0" and acceptable(draft, problems):
            print("[script] using this script: the notes above are only about style, the fact-check comes next")
            return r, draft
        prompt = (f"{base}\n\nYour previous attempt:\n{r.model_dump_json()}\n\n"
                  "Fix ALL of these problems and return the full corrected script:\n- " + "\n- ".join(problems))
    raise RuntimeError("Could not write a valid script:\n- " + "\n- ".join(problems))

def generate(topic: str, project: Path) -> None:
    st = styles.active()
    items = gather(topic)
    if len(items) < 4:
        raise RuntimeError("Research found too little evidence: try a more specific, well-known topic.")
    job_id = hooks.job_id_of(project)
    recent_h, recent_e = store.recent_hooks()
    plan = hooks.pick(recent_h, recent_e, seed=job_id or len(topic))
    print(f"[hook] formula: {plan[0]} / ending: {plan[1]} (recent: {recent_h[:4]})")
    r, draft = write_from_evidence(topic, items, plan)
    if not project.exists():
        shutil.copytree(SKILL_DIR / "styles" / (st.engine or st.key) / "example", project)
        shutil.rmtree(project / "data", ignore_errors=True)       # the example's timing must never be mistaken for ours
        (project / "data").mkdir(exist_ok=True)
    overlay = REPO / "overlay" / (st.overlay or st.niche or st.key)
    if overlay.exists():
        shutil.copytree(overlay, project, dirs_exist_ok=True)
    brand.write_js(project)
    music = r.music if r.music in st.music_options else st.music
    sj = to_script_json(draft, st, music)
    hook_type = r.hook_type if r.hook_type in hooks.HOOKS else plan[0]
    end_type = r.end_type if r.end_type in hooks.ENDINGS else plan[1]
    sj["hook"] = {"type": hook_type, "text": re.sub(r"\s+", " ", r.hook_text).strip()[:30].upper(), "end_type": end_type,
                  "end_question": re.sub(r"\s+", " ", r.end_question).strip()[:26].upper(), "candidates": [c[:140] for c in r.hook_candidates[:3]]}
    (project / "script.json").write_text(json.dumps(sj, indent=2, ensure_ascii=False), encoding="utf-8")
    if job_id:
        try:
            store.set_job(job_id, hook_type=hook_type, end_type=end_type)
        except Exception as e:                                 # the hook log is a convenience: never break the video
            print(f"[hook] not logged: {e}")
    (project / "research.json").write_text(json.dumps({
        "topic": topic, "style": st.key, "evidence": items,
        "lines": [{"text": d.text, "evidence": l.evidence, "numbers": l.numbers}
                  for d, l in zip(draft.lines, r.lines)]}, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("topic")
    ap.add_argument("--project", type=Path, required=True)
    ap.add_argument("--style", "--niche", dest="style", default=None)
    a = ap.parse_args()
    if a.style:
        styles.set_active(a.style)
    generate(a.topic, a.project)
    print("Wrote", a.project / "script.json", "and research.json")