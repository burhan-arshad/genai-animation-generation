import time

import httpx
import pytest
from pydantic import BaseModel

from shorts_agent import llm


class Out(BaseModel):
    x: int


@pytest.fixture(autouse=True)
def fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "DB", tmp_path / "usage.db")
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    llm._cool.clear()
    llm._bad.clear()
    monkeypatch.setenv("DEFAULT_RPM_LIMIT", "100")
    monkeypatch.setenv("DEFAULT_DAILY_LIMIT", "100")
    monkeypatch.setenv("GEMINI_MODEL_TESTTASK", "fake:small,B")
    monkeypatch.setenv("PROVIDER_FAKE_URL", "https://example.test/v1")
    monkeypatch.setenv("PROVIDER_FAKE_KEY", "k")
    monkeypatch.delenv("DAILY_LIMITS", raising=False)
    monkeypatch.setattr(llm, "_gemini", lambda m, r: ("ok", (1, 1), "STOP"))


def test_big_request_goes_to_the_next_model_and_the_first_is_not_punished(monkeypatch):
    monkeypatch.setenv("PROVIDER_FAKE_MAX_INPUT_TOKENS", "100")
    def never(*a, **k):
        raise AssertionError("the small model must not be called")
    monkeypatch.setattr(llm.httpx, "post", never)
    assert llm.generate_text("x" * 2000, task="testtask") == "ok"
    assert "fake:small" not in llm._bad


def test_413_is_not_held_against_the_model(monkeypatch):
    monkeypatch.setattr(llm.httpx, "post", lambda url, headers, json, timeout: httpx.Response(413, text="too large"))
    assert llm.generate_text("hi", task="testtask") == "ok"
    assert "fake:small" not in llm._bad and llm._unhealthy_until("fake:small") == 0.0


def test_retry_after_sets_the_cooldown(monkeypatch):
    monkeypatch.setattr(llm.httpx, "post", lambda url, headers, json, timeout: httpx.Response(429, text="slow", headers={"retry-after": "600"}))
    assert llm.generate_text("hi", task="testtask") == "ok"
    assert llm._cool["fake:small"] - time.time() > 500


def test_extra_body_and_json_mode_switch(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL_TESTTASK", "fake:small")
    monkeypatch.setenv("PROVIDER_FAKE_EXTRA", '{"reasoning_effort":"low"}')
    monkeypatch.setenv("PROVIDER_FAKE_JSON_MODE", "0")
    seen = {}

    def fake_post(url, headers, json, timeout):
        seen.update(json)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"x": 1}'}, "finish_reason": "stop"}], "usage": {}})

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    assert llm.generate_structured("hi", Out, task="testtask").x == 1
    assert seen["reasoning_effort"] == "low" and "response_format" not in seen

def test_two_rate_limits_in_a_row_do_not_open_the_breaker(monkeypatch):
    monkeypatch.setattr(llm.httpx, "post", lambda url, headers, json, timeout: httpx.Response(429, text="slow", headers={"retry-after": "1"}))
    req = llm._req("hi", None, 0.0, 100, None, None, False)
    for _ in range(3):
        llm._try_model("fake:small", req, "t")
    assert llm._unhealthy_until("fake:small") == 0.0