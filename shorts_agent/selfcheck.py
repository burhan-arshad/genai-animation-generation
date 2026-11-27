"""Which of the patches are in your code?   python -m shorts_agent.selfcheck"""
from __future__ import annotations

from .config import REPO

PKG = REPO / "shorts_agent"
HAS = [
    ("llm.py", "class TooBig", "size guard for small free models"),
    ("llm.py", "LLM_ROUNDS", "waiting rounds setting"),
    ("llm.py", "NOT LIKE '%:429'", "429 does not open the breaker"),
    ("llm.py", "_warned", "message when a daily budget is used"),
    ("retrieval.py", "def web_evidence", "second source (Tavily)"),
    ("retrieval.py", r"\d{2,}", "numbers count when finding evidence"),
    ("retrieval.py", 'os.getenv("PUBMED"', "PubMed switch"),
    ("factcheck_agent.py", "def judge_batches", "judge in small batches"),
    ("factcheck_agent.py", "def grade", "claim grading + second source"),
    ("factcheck_agent.py", "FACT_MAX_WEAK", "unverified claims setting"),
    ("factcheck_agent.py", 'task="judge"', "judge has its own model chain"),
    ("topics.py", "def feed_candidates", "topics from real events"),
    ("topics.py", "TOPIC_MIN_FACTS", "researchable topics only"),
    ("filmboard.py", "def draft_in_parts", "storyboard in small calls"),
    ("filmboard.py", "def fill_gaps", "forgotten lines are filled in code"),
    ("filmboard.py", "parts = max(2", "long shots are split"),
    ("filmboard.py", "STORYBOARD_ACCEPT_SOFT", "quality notes do not fail the storyboard"),
    ("gemini_voice.py", "x-goog-api-key", "Gemini voice over REST"),
    ("gemini_voice.py", '"limit: 0" in str(e)', "voice model with limit 0 is dropped at once"),
    ("gemini_voice.py", 'task="voice"', "voice director has its own chain"),
    ("script_agent.py", "EVIDENCE_CHARS", "smaller evidence for the writer"),
    ("config.py", "RENDER_FPS", "render at 15 fps"),
    ("doctor.py", '"judge"', "doctor knows the judge chain"),
    ("settings.py", '"JUDGE"', "dashboard knows the judge chain"),
    ("pipeline.py", "failed = True", "worker reports a failed run"),
    ("bench.py", "--big", "model test tool"),
    ("script_agent.py", "def interleave", "evidence from different pages first"),
    ("script_agent.py", "SCRIPT_ACCEPT_SOFT", "style notes do not fail the script"),
    ("schemas.py", "MIN_SOURCES", "sources setting"),
    ("topics.py", "def seed_candidates", "curated mysteries list"),
    ("styles.py", "min_lines=int(w.get", "niche can set its own line limits"),
    ("brandkit.py", "SAFE_W", "channel kit with the banner safe area"),
    ("hooks.py", "len(body) // 5", "turn lines rule is lighter"),
    ("autopilot.py", "def run_once", "the assistant"),
    ("schedule.py", "def next_slots", "next free slot"),
    ("quality.py", "def score", "quality score"),
    ("linecheck.py", "def verify_project", "line-by-line fact-check"),
    ("factcheck_agent.py", "linecheck", "fact-check mode switch"),
    ("uploader.py", 'mode == "schedule"', "upload now / schedule"),
    ("store.py", "publish_at", "job columns for the assistant"),
    ("llm.py", "def tokens_between", "token counting"),
    ("filmboard.py", "def polish", "quality notes fixed in code"),
    ("script_agent.py", "def pick_hook", "separate hook step"),
    ("hooks.py", "def score_hook", "hook score"),
    ("analytics.py", "def hints", "learning from the stats"),
    ("analytics.py", "def export_csv", "analytics export"),
    ("topics.py", "TOPIC_MIN_PAGES", "stricter research check for topics"),
    ("llm.py", "def usage_rows", "limits table with reset times"),
    ("llm.py", "def _quota_wait", "429 understood and remembered"),
    ("autopilot.py", "def budget_left", "budget gate for new videos"),
    ("filmboard.py", "EXTRA_PROPS", "ready-made mystery objects"),
    ("schedule.py", "def _fill", "publish times spread over the day"),
    ("propsheet.py", "def main", "picture sheet of the extra objects"),
    ("llm.py", "def _block_kind", "key and plan errors remembered"),
    ("series.py", "def create_series", "mystery series planning"),
    ("series.py", "def build_story", "episode film from scene cards"),
    ("pipeline.py", "series.write_episode", "pipeline makes episodes"),
    ("finalize.py", "LONGFORM_WIDE", "widescreen option"),
    ("qa.py", "QA_MIN_DUR", "duration limits per kind of video"),
]
GONE = [
    ("filmboard.py", "has no shot of its own", "the old line check (must be deleted)"),
    ("filmboard.py", "SAFE MODE (plain scenes", "the safe-mode fallback (must be deleted)"),
    ("daily.py", "run_once", "daily.py (must be deleted)"),
    ("api.py", "class Auto", "the old automation endpoint (must be deleted)"),
    ("launch.py", "CHECKLIST", "the old launch checklist (must be deleted)"),
    ("uploader.py", "REQUIRE_APPROVAL", "the old approval switch (must be deleted)"),
]


def read(name: str) -> str | None:
    p = PKG / name
    return p.read_text(encoding="utf-8", errors="ignore") if p.exists() else None


def main() -> None:
    bad = 0
    for f, marker, what in HAS:
        t = read(f)
        ok = t is not None and marker in t
        bad += not ok
        print(f"[{'OK     ' if ok else 'MISSING'}] {f}: {what}")
    for f, marker, what in GONE:
        t = read(f)
        ok = t is None or marker not in t
        bad += not ok
        print(f"[{'OK     ' if ok else 'STILL IN'}] {f}: {what}")
    t = read("pipeline.py") or ""
    n = t.count("def _stale_storyboard")
    bad += n != 1
    print(f"[{'OK     ' if n == 1 else 'DOUBLE '}] pipeline.py: _stale_storyboard is defined {n} time(s) (must be 1)")
    print(f"\n{bad} thing(s) to fix." if bad else "\nEverything is in place.")


if __name__ == "__main__":
    main()