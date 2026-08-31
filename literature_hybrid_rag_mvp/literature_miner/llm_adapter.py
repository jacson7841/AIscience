"""OpenAI-compatible LLM adapter.

The business code depends on this adapter, not on any vendor-specific API.
For MVP testing set LLM_PROVIDER=deepseek and LLM_API_KEY/DEEPSEEK_API_KEY.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

try:
    import requests
except ImportError:  # pragma: no cover - exercised only in minimal envs
    requests = None

from .config import Settings


class LLMUnavailableError(RuntimeError):
    pass


@dataclass
class LLMAdapter:
    settings: Settings

    @property
    def available(self) -> bool:
        return bool(requests and self.settings.llm_api_key)

    def _endpoint(self) -> str:
        base = self.settings.llm_base_url.rstrip("/")
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        return f"{base}/chat/completions"

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.llm_api_key}",
            "Content-Type": "application/json",
        }

    def generate_text(
        self,
        prompt: str,
        system: str = "You are a careful academic literature mining assistant.",
        temperature: float = 0.2,
        max_tokens: int = 2000,
    ) -> str:
        if not self.available:
            raise LLMUnavailableError("LLM API key or requests package is unavailable.")
        payload: Dict[str, Any] = {
            "model": self.settings.llm_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if self.settings.llm_provider.lower() == "deepseek":
            payload["thinking"] = {"type": "disabled"}
        response = requests.post(
            self._endpoint(),
            headers=self._headers(),
            json=payload,
            timeout=self.settings.llm_timeout,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    def generate_json(
        self,
        prompt: str,
        system: str = "Return strict JSON only. Do not include markdown fences.",
        temperature: float = 0.1,
        max_tokens: int = 4000,
        retries: int = 1,
    ) -> Dict[str, Any]:
        last_error: Optional[Exception] = None
        for attempt in range(retries + 1):
            try:
                text = self._generate_json_text(prompt, system, temperature, max_tokens)
                return self._parse_json(text)
            except Exception as exc:  # noqa: BLE001 - retry and report final failure
                last_error = exc
                prompt = (
                    f"{prompt}\n\nYour previous response was not valid JSON. "
                    "Return one JSON object that matches the requested schema."
                )
        raise LLMUnavailableError(f"Failed to generate valid JSON: {last_error}")

    def _generate_json_text(
        self,
        prompt: str,
        system: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        if not self.available:
            raise LLMUnavailableError("LLM API key or requests package is unavailable.")
        payload: Dict[str, Any] = {
            "model": self.settings.llm_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        if self.settings.llm_provider.lower() == "deepseek":
            payload["thinking"] = {"type": "disabled"}
        response = requests.post(
            self._endpoint(),
            headers=self._headers(),
            json=payload,
            timeout=self.settings.llm_timeout,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    @staticmethod
    def _parse_json(text: str) -> Dict[str, Any]:
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, flags=re.S)
            if not match:
                raise
            return json.loads(match.group(0))
