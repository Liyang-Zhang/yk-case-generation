"""LLM client wrapper (OpenAI-compatible chat completion API)."""
from __future__ import annotations
import json
from typing import Any, Dict
import os

import httpx
from tenacity import retry, stop_after_attempt, wait_fixed

from yk_case_generation.config import settings


class LLMClient:
    def __init__(
        self,
        endpoint: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
    ):
        self.endpoint = endpoint or settings.llm_endpoint
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model
        self.timeout = timeout or int(os.environ.get("LLM_TIMEOUT", "120"))

    @retry(stop=stop_after_attempt(2), wait=wait_fixed(2))
    def generate_json(self, system_prompt: str, user_prompt: str, temperature: float = 0.0) -> Dict[str, Any]:
        if not self.endpoint or not self.api_key:
            raise ValueError("LLM endpoint/api key not configured")
        payload = {
            "model": self.model,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(self.endpoint, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)
