"""Automatic fact-check: extract claims -> fetch evidence -> judge with verifiable quotes -> auto-trim the script."""
from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import replace
from pathlib import Path

from pydantic import BaseModel

from . import styles
from .llm import generate_structured
from .retrieval import collect_evidence, web_evidence
from .schemas import Line, ScriptDraft, check_script, repair_caps, repair_numbers
from .script_agent import system_prompt

VALID = {"SUPPORTED", "PARTIAL", "CONTRADICTED", "NO_EVIDENCE"}
MAX_WEAK = int(os.getenv("FACT_MAX_WEAK", "1"))   # unverified claims tolerated after the auto-trim rounds


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
`narration_quote` = the exact words from the narration. `claim` = that statement made self-contained (no pronouns) with EVERY number, year and date written as DIGITS, because the evidence uses digits ('twenty-five feet' -> '25 feet', 'nineteen nineteen' -> '1919', 'two point three million' -> '2.3 million'). `queries` = 1-2 short encyclopedic search queries (2-5 words). `line` = narration line index."""


JUDGE_SYSTEM = """You judge claims ONLY against the evidence provided for each claim. Never use your own knowledge.
SUPPORTED = the evidence states the claim INCLUDING every specific detail in it (numbers, durations such as 'three days', words like 'significantly' or 'always', named examples).
PARTIAL = the evidence supports only the general idea, but at least one specific detail of the claim is NOT in the evidence.
CONTRADICTED = the evidence states otherwise, or shows the claim is wrong or misleading.
NO_EVIDENCE = the evidence is irrelevant or silent on the claim.
When unsure between SUPPORTED and PARTIAL, choose PARTIAL.
Numbers and dates match in any form (21 = twenty-one, 2.3 million = two point three million, 1919 = nineteen nineteen): that is not a missing detail. Different wording of the same fact is the same fact.
For SUPPORTED, PARTIAL and CONTRADICTED you MUST give `quote`: a verbatim passage (max 25 words) copied exactly from the evidence text that decides the verdict, and `source_url`: the url of the evidence item containing it. For NO_EVIDENCE leave both empty.
`reason` = one short sentence (never empty), naming the missing or wrong detail."""


def _squash(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _words(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", s.lower())


def quote_ok(quote: str, url: str, evidence: list[dict]) -> bool:
    """Deterministic proof check. Word for word first; else at least 80% of the quote's 3-word groups must appear in the cited evidence."""
    segs = [_squash(s) for s in re.split(r"\.{3}|…", quote)]
    segs = [s for s in segs if len(s) >= 12]
    texts = [_squash(e["text"]) for e in evidence if e["url"] == url]
    if segs and sum(len(s) for s in segs) >= 20 and any(all(s in t for s in segs) for t in texts):
        return True
    qw = _words(quote)
    if len(qw) < 6:
        return False
    grams = {tuple(qw[i:i + 3]) for i in range(len(qw) - 2)}
    for e in evidence:
        if e["url"] == url:
            ew = _words(e["text"])
            if len(grams & {tuple(ew[i:i + 3]) for i in range(len(ew) - 2)}) / len(grams) >= 0.8:
                return True
    return False


def grade(v, ev: list[dict]) -> tuple[str, str]:
    verdict = v.verdict.strip().upper() if v else "NO_EVIDENCE"
    reason = (v.reason if v else "") or "no reason given"
    if verdict not in VALID or not ev:
        verdict = "NO_EVIDENCE"
    if verdict != "NO_EVIDENCE" and not quote_ok(v.quote, v.source_url, ev):
        reason = f"downgraded: quote not found in cited evidence ({reason})"
        verdict = "NO_EVIDENCE"
    return verdict, reason


def judge_batches(items: list[dict]) -> dict:
    """Judge in small batches (a free Groq model takes about 8K tokens a minute)."""
    out, batch, size = {}, [], 0
    limit = int(os.getenv("JUDGE_BATCH_CHARS", "9000"))

    def flush():
        nonlocal batch, size
        if batch:
            r = generate_structured(json.dumps(batch, ensure_ascii=False), VerdictList, system=JUDGE_SYSTEM, temperature=0.0, task="judge")
            out.update({v.id: v for v in r.verdicts})
        batch, size = [], 0

    for p in items:
        n = len(json.dumps(p, ensure_ascii=False))
        if batch and size + n > limit:
            flush()
        batch.append(p)
        size += n
    flush()
    return out


def check_once(draft: ScriptDraft) -> list[dict]:
    narration = "\n".join(f"{i}: {l.text}" for i, l in enumerate(draft.lines))
    claims = generate_structured(f"Title: {draft.title}\nNarration:\n{narration}", ClaimList,
                                 system=EXTRACT_SYSTEM, temperature=0.2, task="factcheck").claims[:8]
    packed = []
    for i, c in enumerate(claims):
        ev = collect_evidence(c.claim, c.queries)
        print(f"[factcheck] claim {i}: {len(ev)} evidence item(s) for: {c.claim[:70]}")
        packed.append({"id": i, "claim": c.claim, "evidence": ev})
    judged = judge_batches([p for p in packed if p["evidence"]])
    grades = {p["id"]: grade(judged.get(p["id"]), p["evidence"]) for p in packed}
    # a second, independent source for the claims Wikipedia could not settle
    weak = [i for i, (vd, _) in grades.items() if vd in ("NO_EVIDENCE", "PARTIAL")][:int(os.getenv("FACT_WEB_MAX", "4"))]
    extra = []
    for i in weak:
        more = web_evidence(claims[i].claim)
        if more:
            packed[i]["evidence"] = packed[i]["evidence"] + more
            extra.append(packed[i])
    if extra:
        print(f"[factcheck] second source (reliable sites) for {len(extra)} claim(s)")
        judged2 = judge_batches(extra)
        for p in extra:
            if judged2.get(p["id"]) is not None:
                judged[p["id"]] = judged2[p["id"]]
                grades[p["id"]] = grade(judged2[p["id"]], p["evidence"])
    report = []
    for i, c in enumerate(claims):
        verdict, reason = grades[i]
        v, ev = judged.get(i), packed[i]["evidence"]
        if verdict != "SUPPORTED":
            print(f"[factcheck]   {verdict:<12} {c.claim[:80]} -> {reason[:170]}")
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
    st = replace(styles.active(), min_words=70)
    base = ("Edit this script.\n\n" + "\n\n".join(asks) +
            f"\n\nKeep the topic, tone and caption rules. Keep {st.min_lines}-{st.max_lines} lines and {st.min_words}-{st.max_words} words "
            "in total (smooth the flow after deleting a claim). Numbers stay spoken words.\n\nScript:\n" + draft.model_dump_json(indent=1))
    prompt, problems = base, []
    for _ in range(3):
        new = repair_numbers(generate_structured(prompt, ScriptDraft, system=system_prompt(), task="script"))
        if st.caps_mode == "chunks":
            new = repair_caps(new)
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
                             lines=[Line(text=l["text"], caps=l.get("caps", "")) for l in data["lines"]])


def verify_project(project: Path) -> str:
    if os.getenv("FACT_MODE", "line") != "claims":
        from . import linecheck
        if linecheck.usable(project):
            return linecheck.verify_project(project)
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