"""Line-by-line fact-check. Every line of the script is judged against the evidence the writer cited for THAT line (research.json).
A line the evidence does not support is rescued with a second source (Tavily, reliable sites), else rewritten, and as the last resort removed.
Two or three small calls instead of dozens, and no new claims to chase."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from pydantic import BaseModel

from .factcheck_agent import FactCheckFailed
from .llm import generate_structured
from .retrieval import web_evidence
from .schemas import speak_numbers


class LineVerdict(BaseModel):
    i: int
    ok: bool
    issue: str


class LineVerdicts(BaseModel):
    lines: list[LineVerdict]


class Fix(BaseModel):
    i: int
    text: str


class Fixes(BaseModel):
    lines: list[Fix]


JUDGE_SYSTEM = """You check the lines of a short documentary script against the evidence the writer cited for each line. Never use your own knowledge.
You get a JSON list; every item has `i` (the line number), `line` and `evidence` (the paragraphs the line was written from).
For every item return `i`, `ok` and `issue`.
ok = true when every factual statement in the line (who, what, where, when, how many, why) is stated in the evidence or follows directly from it, in any wording. Numbers and dates match in any form (21 = twenty-one, 1919 = nineteen nineteen). A statement marked as a belief or theory ('investigators believed', 'one theory says', 'some suspected') is ok when the evidence mentions that belief or theory. A line that only sets the mood or asks a question and adds no new fact is ok.
ok = false when the line states a fact (a name, number, date, place, cause or event) that the evidence does not contain, or when the evidence says otherwise.
`issue` = one short sentence naming the unsupported or wrong part (empty when ok)."""

FIX_SYSTEM = """You repair lines of a short documentary script. You get JSON: the `topic`, the `evidence` (paragraphs with ids), and `lines`, each with its number `i`, the `issue` found, the `line`, the line `before` and the line `after`.
For every line return `i` and a new `text` that states ONLY what the evidence supports, keeps the line's job in the story and the tone of its neighbours, and has 5-11 words. Write numbers and years as spoken words. Mark beliefs and theories as such ('investigators believed', 'one theory says'). If the evidence offers nothing that fits, write a short neutral line that links `before` and `after` without any new fact. No quotes, no dialogue."""

SKIP = set("the and but then until yet still even now today what why how one some this that these those their his her its after before when while "
           "if not only every each in on at by for with from to of as it he she they we you i so no".split())
MONTHS = set("january february march april may june july august september october november december monday tuesday wednesday thursday friday saturday sunday".split())


def read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def usable(project: Path) -> bool:
    r, s = read_json(project / "research.json"), read_json(project / "script.json")
    return bool(r and s and r.get("evidence") and r.get("lines") and not any("caps" in l for l in s.get("lines", [])))


def ungrounded_names(text: str, blob: str) -> list[str]:
    """Capitalised words (not at the start of a sentence) that appear nowhere in the evidence: most likely invented names."""
    out = []
    for sent in re.split(r"(?<=[.!?])\s+", text.strip()):
        for w in sent.split()[1:]:
            c = re.sub(r"^\W+|\W+$", "", w)
            c = re.sub(r"['’]s$", "", c)
            if len(c) >= 3 and c[0].isupper() and c.lower() not in SKIP and c.lower() not in MONTHS and c.lower() not in blob:
                out.append(c)
    return list(dict.fromkeys(out))


def packets(idx, lines, ev, cites, extra=None, limit=550) -> list[dict]:
    out = []
    for i in idx:
        ids = [e for e in (cites[i] if i < len(cites) else []) if e in ev]
        items = [{"id": e, "text": ev[e]["text"][:limit]} for e in ids]
        items += (extra or {}).get(i, [])
        out.append({"i": i, "line": lines[i], "evidence": items})
    return out


def judge(packs: list[dict]) -> dict:
    """{line number: LineVerdict}. Small batches (a free Groq model takes about 8K tokens a minute); a line the model skipped is asked once more."""
    out: dict = {}
    limit = int(os.getenv("JUDGE_BATCH_CHARS", "9000"))
    for _ in range(2):
        todo = [p for p in packs if p["i"] not in out]
        if not todo:
            break
        batches, batch, size = [], [], 0
        for p in todo:
            n = len(json.dumps(p, ensure_ascii=False))
            if batch and size + n > limit:
                batches.append(batch)
                batch, size = [], 0
            batch.append(p)
            size += n
        if batch:
            batches.append(batch)
        for b in batches:
            r = generate_structured(json.dumps(b, ensure_ascii=False), LineVerdicts, system=JUDGE_SYSTEM, temperature=0.0, task="judge")
            asked = {p["i"] for p in b}
            for v in r.lines:
                if v.i in asked:
                    out[v.i] = v
    return out


def repair(bad: dict, lines: list[str], ev: dict, topic: str) -> dict:
    payload = {"topic": topic, "evidence": [{"id": e, "text": v["text"][:300]} for e, v in list(ev.items())[:12]],
               "lines": [{"i": i, "issue": issue, "line": lines[i], "before": lines[i - 1] if i > 0 else "",
                          "after": lines[i + 1] if i + 1 < len(lines) else ""} for i, issue in bad.items()]}
    r = generate_structured(json.dumps(payload, ensure_ascii=False), Fixes, system=FIX_SYSTEM, temperature=0.3, task="script")
    return {f.i: f.text for f in r.lines if f.i in bad and f.text.strip()}


def verify_project(project: Path) -> str:
    script, research = read_json(project / "script.json"), read_json(project / "research.json")
    lines = [l["text"] for l in script["lines"]]
    n = len(lines)
    ev = {e["id"]: e for e in research["evidence"]}
    cites = [l.get("evidence", []) for l in research["lines"]]
    topic = research.get("topic") or script.get("title", "")
    blob = (" ".join(e["text"] + " " + e.get("title", "") for e in ev.values()) + " " + topic + " " + script.get("title", "")).lower()
    rounds = max(0, int(os.getenv("FACT_REPAIR_ROUNDS", "2")))
    web_left = int(os.getenv("FACT_WEB_MAX", "3")) if (os.getenv("FACT_WEB", "1") != "0" and os.getenv("TAVILY_API_KEY")) else 0
    sources = script.setdefault("sources", [])
    history, edited, unchecked, rescued = [], set(), set(), 0
    bad: dict[int, str] = {}
    todo = list(range(n))
    for rnd in range(rounds + 1):
        verdicts = judge(packets(todo, lines, ev, cites))
        for i in todo:
            v, issues = verdicts.get(i), []
            if v is None:
                unchecked.add(i)
            elif not v.ok:
                issues.append(v.issue or "not supported by the evidence")
            names = ungrounded_names(lines[i], blob)
            if names:
                issues.append("name not in the evidence: " + ", ".join(names))
            if issues:
                bad[i] = "; ".join(issues)
            else:
                bad.pop(i, None)
        for i in [i for i in todo if i in bad]:                     # a second source before the line is rewritten
            if web_left <= 0:
                break
            web_left -= 1
            more = web_evidence(f"{topic}: {lines[i]}", n=3)
            if not more:
                continue
            extra = {i: [{"id": f"W{k + 1}", "text": m["text"][:550]} for k, m in enumerate(more)]}
            v2 = judge(packets([i], lines, ev, cites, extra)).get(i)
            webtxt = " ".join(m["text"] for m in more).lower()
            if v2 is not None and v2.ok and not ungrounded_names(lines[i], blob + " " + webtxt):
                bad.pop(i)
                rescued += 1
                for m in more[:2]:
                    src = f"{m['title']} ({m['source']}): {m['url']}"
                    if src not in sources:
                        sources.append(src)
        history.append({"round": rnd, "claims": [{"id": i, "line": i, "narration_quote": lines[i], "claim": lines[i],
                                                  "verdict": "NO_EVIDENCE" if i in bad else "SUPPORTED", "reason": bad.get(i, ""),
                                                  "quote": "", "source_url": ""} for i in todo]})
        for i in todo:
            if i in bad:
                print(f"[factcheck]   line {i}: {lines[i][:70]} -> {bad[i][:150]}")
        if not bad or rnd == rounds:
            break
        fixes = repair(bad, lines, ev, topic)
        if not fixes:
            break
        for i, t in fixes.items():
            lines[i] = speak_numbers(t).strip()
            edited.add(i)
        todo = sorted(fixes)
    leftover = sorted(bad)
    final = [{"id": i, "line": i, "narration_quote": lines[i], "claim": lines[i],
              "verdict": "NO_EVIDENCE" if i in bad else ("PARTIAL" if i in edited else "SUPPORTED"),
              "reason": bad.get(i, "rewritten after the check" if i in edited else ""), "quote": "", "source_url": ""} for i in range(n)]
    history.append({"round": "final", "claims": final})
    fail = ""
    if 0 in leftover or (n - 1) in leftover:
        fail = "the first or the last line could not be supported"
    elif n - len(leftover) < 6:
        fail = f"only {n - len(leftover)} supported lines are left"
    status = "failed" if fail else ("verified" if not edited and not leftover and not unchecked else "verified_with_notes")
    (project / "factcheck.json").write_text(json.dumps({"status": status, "mode": "line", "history": history}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[factcheck] line check: {n} lines, {len(edited)} rewritten, {len(leftover)} removed, {rescued} confirmed by a second source -> {status}")
    if fail:
        raise FactCheckFailed("Line check failed: " + fail + "; see factcheck.json")
    keep = [i for i in range(n) if i not in bad]
    script["lines"] = [dict(script["lines"][i], text=lines[i]) for i in keep]
    (project / "script.json").write_text(json.dumps(script, indent=2, ensure_ascii=False), encoding="utf-8")
    if len(research["lines"]) == n:
        research["lines"] = [dict(research["lines"][i], text=lines[i]) for i in keep]
        (project / "research.json").write_text(json.dumps(research, indent=2, ensure_ascii=False), encoding="utf-8")
    return status