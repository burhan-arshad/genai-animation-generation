import time

import httpx
import pytest
from pydantic import BaseModel

from shorts_agent import autopilot, llm


@pytest.fixture(autouse=True)
def fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "DB", tmp_path / "usage.db")
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    llm._cool.clear()
    llm._bad.clear()
    llm._warned.clear()
    monkeypatch.setenv("DEFAULT_RPM_LIMIT", "100")
    monkeypatch.setenv("DEFAULT_DAILY_LIMIT", "100")
    monkeypatch.setenv("PROVIDER_FAKE_URL", "https://example.test/v1")
    monkeypatch.setenv("PROVIDER_FAKE_KEY", "k")
    monkeypatch.delenv("DAILY_LIMITS", raising=False)
    monkeypatch.delenv("DAILY_TOKENS", raising=False)


def test_durations_are_read():
    assert llm._seconds("6m30s") == 390 and abs(llm._seconds("2m59.56s") - 179.56) < 1e-6
    assert llm._seconds("1h2m3s") == 3723 and abs(llm._seconds("448ms") - 0.448) < 1e-6


def test_a_gemini_daily_limit_waits_for_the_pacific_midnight():
    kind, wait = llm._quota_wait("gemini-3.5-flash-lite", llm.ProviderError(429, "Quota exceeded: GenerateRequestsPerDayPerProjectPerModel-FreeTier"))
    assert kind == "day" and 60 <= wait <= 86400 + 300


def test_limit_zero_means_no_quota_on_the_plan():
    assert llm._quota_wait("gemini-2.5-pro-preview-tts", llm.ProviderError(429, "limit: 0, model: gemini-2.5-pro-tts"))[0] == "none"


def test_a_short_wait_is_read_from_the_message():
    assert llm._quota_wait("gemini-x", llm.ProviderError(429, "{'retryDelay': '35s'}")) == ("minute", 36.0)


def test_a_daily_limit_is_remembered_between_runs(monkeypatch):
    msg = "Rate limit reached on tokens per day (TPD): Limit 200000, Used 199900, Requested 600. Please try again in 6m30s."
    monkeypatch.setattr(llm.httpx, "post", lambda url, headers, json, timeout: httpx.Response(429, text=msg, headers={"retry-after": "390"}))
    llm._try_model("fake:small", llm._req("hi", None, 0.0, 100, None, None, False), "t")
    assert 380 < llm._blocked_until("fake:small") - time.time() < 400
    llm._cool.clear()                                   # a new process knows nothing in memory: the database remembers
    assert llm._blocked_until("fake:small") > 0
    llm.clear_blocks()
    assert llm._blocked_until("fake:small") == 0


def test_every_model_out_of_quota_stops_at_once(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL_TESTTASK", "fake:small,B")
    llm._block("fake:small", time.time() + 3 * 3600, "day", "x")
    llm._block("B", time.time() + 3 * 3600, "day", "x")
    monkeypatch.setattr(llm, "_dispatch", lambda s, r: (_ for _ in ()).throw(AssertionError("must not be called")))
    with pytest.raises(llm.BudgetExceeded) as e:
        llm.generate_text("hi", task="testtask")
    assert "usable again" in str(e.value)


def test_the_token_budget_skips_a_model_before_it_fails(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL_TESTTASK", "fake:small,B")
    monkeypatch.setenv("DAILY_TOKENS", "fake:small:1000")
    llm._log("fake:small", "t", 900, 90, True)
    seen = []
    monkeypatch.setattr(llm, "_dispatch", lambda s, r: seen.append(s) or ("ok", (1, 1), "STOP"))
    assert llm.generate_text("hi" * 50, task="testtask") == "ok" and seen == ["B"]


def test_provider_headers_are_stored(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL_TESTTASK", "fake:small")
    h = {"x-ratelimit-remaining-requests": "970", "x-ratelimit-limit-requests": "1000", "x-ratelimit-remaining-tokens": "7000", "x-ratelimit-limit-tokens": "8000"}
    monkeypatch.setattr(llm.httpx, "post", lambda url, headers, json, timeout: httpx.Response(
        200, json={"choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}], "usage": {}}, headers=h))
    assert llm.generate_text("hi", task="testtask") == "hi"
    row = [r for r in llm.usage_rows() if r["model"] == "fake:small"][0]
    assert "970/1000 requests left today" in row["provider"] and "7000/8000 tokens left this minute" in row["provider"]


class Out(BaseModel):
    x: int


def test_extra_can_differ_per_model(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL_TESTTASK", "fake:m1")
    monkeypatch.setenv("PROVIDER_FAKE_EXTRA", '{"m1":{"reasoning_effort":"none"},"m2":{"x":1},"keep":true}')
    seen = {}

    def fake_post(url, headers, json, timeout):
        seen.update(json)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"x": 1}'}, "finish_reason": "stop"}], "usage": {}})

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    assert llm.generate_structured("hi", Out, task="testtask").x == 1
    assert seen["reasoning_effort"] == "none" and "x" not in seen


def test_the_budget_counts_only_models_with_a_token_limit(monkeypatch):
    for t in ("RESEARCH", "TOPICS", "FACTCHECK", "JUDGE", "HOOK", "SCRIPT", "STORYBOARD"):
        monkeypatch.delenv(f"GEMINI_MODEL_{t}", raising=False)
    monkeypatch.setenv("GEMINI_MODEL", "g:a,g:b")
    assert autopilot.budget_left() is None
    monkeypatch.setenv("DAILY_TOKENS", "g:a:1000")
    llm._log("g:a", "t", 300, 100, True)
    b = autopilot.budget_left()
    assert b["left"] == 600 and b["models"] == 1 and b["resets"] > time.time()
    llm._block("g:a", time.time() + 7200, "day", "x")
    assert autopilot.budget_left()["left"] == 0


def test_a_429_after_almost_all_daily_calls_means_the_day_is_over(monkeypatch):
    monkeypatch.setenv("DAILY_LIMITS", "fake:small:20")
    for _ in range(19):
        llm._log("fake:small", "t", 10, 10, True)
    kind, wait = llm._quota_wait("fake:small", llm.ProviderError(429, "Too Many Requests"))
    assert kind == "day" and wait >= 60


def test_cloudflare_style_daily_message():
    e = llm.ProviderError(429, "you have used up your daily free allocation of 10,000 neurons")
    assert llm._quota_wait("cloudflare:@cf/x", e)[0] == "day"


def test_sambanova_day_headers_are_preferred(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL_TESTTASK", "fake:small")
    h = {"x-ratelimit-remaining-requests-day": "17", "x-ratelimit-limit-requests-day": "20", "x-ratelimit-remaining-requests": "19"}
    monkeypatch.setattr(llm.httpx, "post", lambda url, headers, json, timeout: httpx.Response(
        200, json={"choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}], "usage": {}}, headers=h))
    assert llm.generate_text("hi", task="testtask") == "hi"
    row = [r for r in llm.usage_rows() if r["model"] == "fake:small"][0]
    assert "17/20 requests left today" in row["provider"]


def test_a_model_whose_calls_are_used_counts_as_zero_in_the_budget(monkeypatch):
    for t in ("RESEARCH", "TOPICS", "FACTCHECK", "JUDGE", "HOOK", "SCRIPT", "STORYBOARD"):
        monkeypatch.delenv(f"GEMINI_MODEL_{t}", raising=False)
    monkeypatch.setenv("GEMINI_MODEL", "g:a")
    monkeypatch.setenv("DAILY_TOKENS", "g:a:100000")
    monkeypatch.setenv("DAILY_LIMITS", "g:a:3")
    assert autopilot.budget_left()["left"] == 100000
    llm._log("g:a", "t", 10, 10, True)                 # 1 call used of 3, minus the safety margin of 2: the calls are used up
    assert autopilot.budget_left()["left"] == 0

def test_a_payment_error_is_remembered_for_hours(monkeypatch):
    monkeypatch.setattr(llm.httpx, "post", lambda url, headers, json, timeout: httpx.Response(402, text="PAYMENT_METHOD_REQUIRED"))
    llm._try_model("fake:small", llm._req("hi", None, 0.0, 100, None, None, False), "t")
    assert llm._blocked_until("fake:small") - time.time() > 5 * 3600 and llm._block_kind("fake:small") == "account"