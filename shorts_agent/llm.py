"""Thin LLM wrapper. Swap providers here without touching the agents."""
from __future__ import annotations

import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
_client = None


def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


def _call(prompt: str, cfg, retries: int = 3):
    model = os.getenv("GEMINI_MODEL")
    if not model:
        raise RuntimeError("Set GEMINI_MODEL in .env")
    for attempt in range(retries):
        try:
            return _get_client().models.generate_content(model=model, contents=prompt, config=cfg)
        except Exception as e:  # rate limit / transient
            if attempt == retries - 1:
                raise
            wait = 30 * (attempt + 1)
            print(f"[llm] error ({type(e).__name__}): retrying in {wait}s")
            time.sleep(wait)


def generate_structured(prompt: str, schema, system: str | None = None, temperature: float = 0.8):
    cfg = types.GenerateContentConfig(
        system_instruction=system, response_mime_type="application/json",
        response_schema=schema, temperature=temperature)
    return schema.model_validate_json(_call(prompt, cfg).text)


def generate_text(prompt: str, system: str | None = None, temperature: float = 0.6,
                  max_output_tokens: int = 16000) -> str:
    cfg = types.GenerateContentConfig(
        system_instruction=system, temperature=temperature, max_output_tokens=max_output_tokens)
    return _call(prompt, cfg).text or ""