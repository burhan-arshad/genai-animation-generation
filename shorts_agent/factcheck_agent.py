"""Automatic fact-check: extract claims -> fetch evidence -> judge with verifiable quotes -> auto-trim the script."""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import replace
from pathlib import Path

from pydantic import BaseModel

from . import styles
from .llm import generate_structured
from .retrieval import collect_evidence
from .schemas import Line, ScriptDraft, check_script, repair_caps
from .script_agent import system_prompt

VALID = {"SUPPORTED", "PARTIAL", "CONTRADICTED", "NO_EVIDENCE"}
MAX_WEAK = 1   # unverified claims tolerated after the auto-trim rounds


class Claim(BaseModel):
    line: int
    narration_quote: str
    claim: str
    queries: list[str]


class ClaimList(BaseModel):
    claims: list[Claim]


class Verdict(BaseModel):
    id: int
    verdict: str
    reason: str
    quote: str
    source_url: str


class VerdictList(BaseModel):
    verdicts: list[Verdict]


class FactCheckFailed(RuntimeError):
    pass


EXTRACT_SYSTEM = """Extract 4-8 distinct, checkable factual claims from the narration (numbers, durations, causes, 'myth' statements, comparisons).
Keep EVERY specific detail exactly as the narration states it: numbers, durations ('three days'), qualifiers ('significantly', 'always', 'only'), named examples. Never generalize, soften or merge claims.
`narration_quote` = the exact words from the narration. `claim` = that statement made self-contained (no pronouns). `queries` = 1-2 short encyclopedic search queries (2-5 words). `line` = narration line index."""

JUDGE_SYSTEM = """You judge claims ONLY against the evidence provided for each claim. Never use your own knowledge.
SUPPORTED = the evidence states the claim INCLUDING every specific detail in it (numbers, durations such as 'three days', words like 'significantly' or 'always', named examples).
PARTIAL = the evidence supports only the general idea, but at least one specific detail of the claim is NOT in the evidence.
CONTRADICTED = the evidence states otherwise, or shows the claim is wrong or misleading.
NO_EVIDENCE = the evidence is irrelevant or silent on the claim.
When unsure between SUPPORTED and PARTIAL, choose PARTIAL.
For SUPPORTED, PARTIAL and CONTRADICTED you MUST give `quote`: a verbatim passage (max 25 words) copied exactly from the evidence text that decides the verdict, and `source_url`: the url of the evidence item containing it. For NO_EVIDENCE leave both empty.
`reason` = one short sentence (never empty), naming the missing or wrong detail."""


def _squash(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def quote_ok(quote: str, url: str, evidence: list[dict]) -> bool:
    """Deterministic proof check: every piece of the quote must appear in the cited evidence."""
    segs = [_squash(s) for s in re.split(r"\.{3}|…", quote)]
    segs = [s for s in segs if len(s) >= 12]
    if not segs or sum(len(s) for s in segs) < 20:
        return False
    texts = [_squash(e["text"]) for e in evidence if e["url"] == url]
    return any(all(s in t for s in segs) for t in texts)


def check_once(draft: ScriptDraft) -> list[dict]:
    narration = "\n".join(f"{i}: {l.text}" for i, l in enumerate(draft.lines))
    claims = generate_structured(f"Title: {draft.title}\nNarration:\n{narration}", ClaimList,
                                 system=EXTRACT_SYSTEM, temperature=0.2, task="factcheck").claims[:8]
    packed = []
    for i, c in enumerate(claims):
        ev = collect_evidence(c.claim, c.queries)
        print(f"[factcheck] claim {i}: {len(ev)} evidence item(s) for: {c.claim[:70]}")
        packed.append({"id": i, "claim": c.claim, "evidence": ev})
    judged = {}
    if any(p["evidence"] for p in packed):
        judged = {v.id: v for v in generate_structured(json.dumps(packed, ensure_ascii=False), VerdictList,
                                                      system=JUDGE_SYSTEM, temperature=0.0, task="factcheck").verdicts}
    report = []
    for i, c in enumerate(claims):
        v, ev = judged.get(i), packed[i]["evidence"]
        verdict = v.verdict.strip().upper() if v else "NO_EVIDENCE"
        reason = (v.reason if v else "") or "no reason given"
        if verdict not in VALID or not ev:
            verdict = "NO_EVIDENCE"
        if verdict != "NO_EVIDENCE" and not quote_ok(v.quote, v.source_url, ev):
            reason = f"downgraded: quote not found in cited evidence ({reason})"
            verdict = "NO_EVIDENCE"
        report.append({"id": i, "line": c.line, "narration_quote": c.narration_quote, "claim": c.claim,
                       "verdict": verdict, "reason": reason,
                       "quote": v.quote if v else "", "source_url": v.source_url if v else "", "evidence": ev})
    return report


def rewrite(draft: ScriptDraft, bad: list[dict], weak: list[dict]) -> ScriptDraft:
    asks = []
    if bad:
        asks.append("CONTRADICTED claims: correct each to match the evidence, or delete it:\n" + "\n".join(
            f"- {b['narration_quote']} | evidence says: {b['quote'] or b['reason']} ({b['source_url']})" for b in bad))
    if weak:
        asks.append("UNVERIFIED claims (the retrieved evidence does not fully support them): rewrite each so it states ONLY what "
                    "the evidence supports, or delete it. Never add new facts, never guess:\n" + "\n".join(
            f"- {w['narration_quote']} | {w['verdict']}: {w['reason']}"
            + (f" | supported part: {w['quote']}" if w["quote"] else "") for w in weak))
    base = ("Edit this script.\n\n" + "\n\n".join(asks) +
            "\n\nKeep the topic, tone and exact caption format. Keep 8-14 lines and 75-115 words in total "
            "(smooth the flow after deleting a claim).\n\nScript:\n" + draft.model_dump_json(indent=1))
    st = replace(styles.active(), min_words=70)
    prompt, problems = base, []
    for _ in range(3):
        new = repair_caps(generate_structured(prompt, ScriptDraft, system=system_prompt(), task="script"))
        problems = check_script(new, st)
        if not problems:
            return new
        prompt = base + "\n\nYour previous edit had problems:\n- " + "\n- ".join(problems) + "\nReturn the full corrected script."
    raise FactCheckFailed("Could not edit the script cleanly:\n- " + "\n- ".join(problems))


def verify_script(draft: ScriptDraft, rounds: int = 2) -> tuple[ScriptDraft, list[dict], str]:
    history: list[dict] = []
    bad: list[dict] = []
    weak: list[dict] = []
    for r in range(rounds + 1):
        report = check_once(draft)
        history.append({"round": r, "claims": report})
        bad = [c for c in report if c["verdict"] == "CONTRADICTED"]
        weak = [c for c in report if c["verdict"] in ("NO_EVIDENCE", "PARTIAL")]
        print(f"[factcheck] round {r}: {len(report)} claims | contradicted {len(bad)} | unverified {len(weak)}")
        if not bad and not weak:
            return draft, history, "verified"
        if r == rounds:
            break
        draft = rewrite(draft, bad, weak)
    if bad or len(weak) > MAX_WEAK:
        return draft, history, "failed"
    return draft, history, "verified_with_notes"


def load_draft(project: Path) -> tuple[dict, ScriptDraft]:
    data = json.loads((project / "script.json").read_text(encoding="utf-8"))
    return data, ScriptDraft(title=data["title"], sources=data["sources"],
                             lines=[Line(text=l["text"], caps=l["caps"]) for l in data["lines"]])


def verify_project(project: Path) -> str:
    data, draft = load_draft(project)
    draft, history, status = verify_script(draft)
    (project / "factcheck.json").write_text(
        json.dumps({"status": status, "history": history}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[factcheck] status: {status}")
    if status == "failed":
        raise FactCheckFailed("Unresolved claims after auto-trim; see factcheck.json")
    data["title"], data["sources"] = draft.title, draft.sources
    data["lines"] = [l.model_dump() for l in draft.lines]
    (project / "script.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return status


if __name__ == "__main__":  # report only: no rewrite, nothing saved
    ap = argparse.ArgumentParser()
    ap.add_argument("project", type=Path)
    _, d = load_draft(ap.parse_args().project)
    for c in check_once(d):
        print(f"\n{c['verdict']:<13} {c['claim']}\n  why: {c['reason']}\n  quote: {c['quote'] or '-'}\n  src: {c['source_url'] or '-'}")