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
    monkeypatch.setenv("GEMINI_MODEL_TESTTASK", "A,B")
    monkeypatch.delenv("DAILY_LIMITS", raising=False)


def script(monkeypatch, behaviour):
    calls = []

    def fake(spec, req):
        calls.append(spec)
        r = behaviour[spec]
        r = r(len(calls)) if callable(r) else r
        if isinstance(r, Exception):
            raise r
        return r, (10, 5), "STOP"

    monkeypatch.setattr(llm, "_dispatch", fake)
    return calls


def test_split_and_limits(monkeypatch):
    assert llm._split("gemini-3.8-flash") == ("gemini", "gemini-3.8-flash")
    assert llm._split("openrouter:meta/llama:free") == ("openrouter", "meta/llama:free")
    monkeypatch.setenv("DAILY_LIMITS", "gemini-3.8-flash:20,openrouter:meta/llama:free:50")
    assert llm._daily_limit("gemini-3.8-flash") == 20
    assert llm._daily_limit("openrouter:meta/llama:free") == 50


def test_fails_over_on_5xx_and_opens_the_breaker(monkeypatch):
    calls = script(monkeypatch, {"A": llm.ProviderError(503, "overloaded"), "B": "ok"})
    assert llm.generate_text("hi", task="testtask") == "ok"
    assert calls == ["A", "A", "B"]                      # two quick tries, then the next model
    calls.clear()
    assert llm.generate_text("hi", task="testtask") == "ok"
    assert calls == ["B"]                                # A is skipped while its breaker is open


def test_quota_error_cools_the_model_down(monkeypatch):
    calls = script(monkeypatch, {"A": llm.ProviderError(429, "slow down"), "B": "ok"})
    assert llm.generate_text("hi", task="testtask") == "ok"
    assert calls == ["A", "B"]                           # a 429 is not retried on the same model
    assert llm._cool["A"] > 0


def test_fatal_error_skips_the_model_but_not_the_chain(monkeypatch):
    calls = script(monkeypatch, {"A": llm.ProviderError(401, "bad key"), "B": "ok"})
    assert llm.generate_text("hi", task="testtask") == "ok"
    assert calls == ["A", "B"] and "A" in llm._bad


def test_invalid_json_moves_on_to_the_next_model(monkeypatch):
    calls = script(monkeypatch, {"A": "not json at all", "B": '```json\n{"x": 7}\n```'})
    assert llm.generate_structured("hi", Out, task="testtask").x == 7
    assert calls == ["A", "B"]


def test_all_models_down_raises_the_last_error(monkeypatch):
    script(monkeypatch, {"A": llm.ProviderError(503, "a"), "B": llm.ProviderError(500, "b")})
    with pytest.raises(llm.ProviderError):
        llm.generate_text("hi", task="testtask")


def test_daily_budget_guard(monkeypatch):
    monkeypatch.setenv("DAILY_LIMITS", "A:3,B:3")        # limit 3 minus safety margin 2 = one call
    script(monkeypatch, {"A": "a", "B": "b"})
    assert llm.generate_text("hi", task="testtask") == "a"
    assert llm.generate_text("hi", task="testtask") == "b"
    with pytest.raises(llm.BudgetExceeded):
        llm.generate_text("hi", task="testtask")


def test_unconfigured_provider_is_skipped(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL_TESTTASK", "nope:model,B")
    monkeypatch.delenv("PROVIDER_NOPE_URL", raising=False)
    calls = []

    def fake(spec, req):
        calls.append(spec)
        if spec.startswith("nope"):
            raise llm.Skip("not configured")
        return "ok", (1, 1), "STOP"

    monkeypatch.setattr(llm, "_dispatch", fake)
    assert llm.generate_text("hi", task="testtask") == "ok"
    assert calls == ["nope:model", "B"]


def test_openai_compatible_adapter(monkeypatch):
    import httpx
    monkeypatch.setenv("GEMINI_MODEL_TESTTASK", "fake:some-model")
    monkeypatch.setenv("PROVIDER_FAKE_URL", "https://example.test/v1")
    monkeypatch.setenv("PROVIDER_FAKE_KEY", "k")
    seen = {}

    def fake_post(url, headers, json, timeout):
        seen.update(url=url, auth=headers["Authorization"], body=json)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"x": 3}'}, "finish_reason": "stop"}],
                                         "usage": {"prompt_tokens": 11, "completion_tokens": 4}})

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    assert llm.generate_structured("hi", Out, system="sys", task="testtask").x == 3
    assert seen["url"] == "https://example.test/v1/chat/completions" and seen["auth"] == "Bearer k"
    assert seen["body"]["response_format"] == {"type": "json_object"} and "JSON schema" in seen["body"]["messages"][0]["content"]
    assert llm._used_today("fake:some-model") == 1
