"""Research-first writer: topic -> Wikipedia evidence -> script written ONLY from that evidence."""
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

from pydantic import BaseModel

from . import brand, niche, styles
from .config import REPO, SKILL_DIR
from .llm import generate_structured
from .retrieval import wikipedia_facts
from .schemas import Line, ScriptDraft, check_script, repair_caps, to_script_json


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
    lines: list[RLine]


PLAN_SYSTEM = """You plan research for a 40-second educational short. Return 3-5 short search queries (2-6 words) that find
encyclopedic Wikipedia pages with the key dated, numeric, well-documented facts about the topic. Prefer the specific
event/person/place page over generic ones."""


def caption_rules(st: styles.Style) -> str:
    return (f"In `caps`, split the line into chunks separated by ' | ', each chunk 1-{st.caps_max_words} words, EXACTLY one "
            "*highlighted word per chunk. Each chunk's first word must be a word actually spoken in that line "
            f"(digits may stand for spoken numbers). Example:\n{st.caps_example}")


def system_prompt() -> str:
    """Style-aware prompt for plain script rewrites (used by the fact-check auto-trim)."""
    st = styles.active()
    return f"You edit scripts for 40-second faceless Shorts in the '{st.key}' style.\n{st.write_rules}\n{caption_rules(st)}"


def writer_system(st: styles.Style) -> str:
    return (f"You write scripts for 40-second faceless YouTube Shorts in the '{st.key}' style.\n{st.write_rules}\n"
            f"{caption_rules(st)}\nSOURCE RULES (strict):\n"
            "- Use ONLY facts stated in the EVIDENCE. Never add facts, numbers, names or dates from memory. "
            "If the evidence lacks a detail, leave it out.\n"
            "- Every line lists the evidence ids that state its facts in `evidence`.\n"
            "- List every number or year you speak, written as digits, in `numbers` (e.g. \"1666\"). Each must appear exactly "
            "in the cited evidence: do not round or estimate.\n"
            f"- `music`: one of {list(st.music_options)} ('tension' only for disasters or dark events).")


def plan_system() -> str:
    st = styles.active()
    hint = niche.load(st.niche).get("research", {}).get("plan_hint", "") if st.niche else ""
    return PLAN_SYSTEM + ("\n" + hint if hint else "")


def gather(topic: str) -> list[dict]:
    plan = generate_structured(f"Topic: {topic}", Plan, system=plan_system(), temperature=0.2, task="research")
    seen, items = set(), []
    for q in plan.queries[:5]:
        for ev in wikipedia_facts(q):
            key = (ev["url"], ev["text"][:60])
            if key not in seen:
                seen.add(key)
                items.append(ev)
    items = items[:16]
    for i, ev in enumerate(items, 1):
        ev["id"] = f"E{i}"
    print(f"[research] {len(items)} evidence items from {len({e['url'] for e in items})} pages")
    return items


def evidence_block(items: list[dict]) -> str:
    return "\n".join(f"{e['id']} [{e['title']} | {e['source']}]\n{e['text']}\n" for e in items)


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
    if len(urls) < 2:
        problems.append("Cite evidence from at least 2 DIFFERENT pages (different titles/urls), not just 2 items of the same page.")
    return problems


def write_from_evidence(topic: str, items: list[dict]) -> tuple[RScript, ScriptDraft]:
    st, ev = styles.active(), {e["id"]: e for e in items}
    base = f"Topic: {topic}\n\nEVIDENCE:\n{evidence_block(items)}\nWrite the script."
    prompt, problems = base, []
    for attempt in range(1, 6):
        task = "script" if attempt <= 3 else "script_hard"
        r = generate_structured(prompt, RScript, system=writer_system(st), task=task)
        draft = repair_caps(ScriptDraft(title=r.title, sources=sources_for(r, ev),
                                        lines=[Line(text=l.text, caps=l.caps) for l in r.lines]))
        problems = check_research(r, ev) + check_script(draft)
        print(f"[script] attempt {attempt} ({task}): {len(problems)} problem(s)")
        if not problems:
            return r, draft
        prompt = (f"{base}\n\nYour previous attempt:\n{r.model_dump_json(indent=1)}\n\n"
                  "Fix ALL of these problems and return the full corrected script:\n- " + "\n- ".join(problems))
    raise RuntimeError("Could not write a valid script:\n- " + "\n- ".join(problems))


def generate(topic: str, project: Path) -> None:
    st = styles.active()
    items = gather(topic)
    if len(items) < 4:
        raise RuntimeError("Research found too little evidence: try a more specific, well-known topic.")
    r, draft = write_from_evidence(topic, items)
    if not project.exists():
        shutil.copytree(SKILL_DIR / "styles" / (st.engine or st.key) / "example", project)
    overlay = REPO / "overlay" / (st.niche or st.key)
    if not overlay.exists():
        overlay = REPO / "overlay" / "history"          # every niche shares the same scenery and host code by default
    if overlay.exists():
        shutil.copytree(overlay, project, dirs_exist_ok=True)
    brand.write_js(project)
    music = r.music if r.music in st.music_options else st.music
    (project / "script.json").write_text(
        json.dumps(to_script_json(draft, st, music), indent=2, ensure_ascii=False), encoding="utf-8")
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
