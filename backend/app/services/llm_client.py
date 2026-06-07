import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings


class LLMClientError(RuntimeError):
    pass


class MissingLLMAPIKeyError(LLMClientError):
    pass


class LLMProviderError(LLMClientError):
    pass


class LLMTimeoutError(LLMClientError):
    pass


@dataclass(frozen=True)
class LLMResponse:
    content: str
    model: str
    provider: str
    raw: dict[str, Any] | None = None
    parsed_json: Any | None = None


class LLMClient:
    def __init__(
        self,
        provider: str | None = None,
        api_base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
        retry_backoff_seconds: float | None = None,
    ) -> None:
        self.provider = provider or settings.llm_provider
        self.api_base_url = api_base_url if api_base_url is not None else settings.llm_api_base_url
        self.api_key = api_key if api_key is not None else settings.llm_api_key
        self.model = model or settings.llm_model
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else settings.llm_timeout_seconds
        self.max_retries = max_retries if max_retries is not None else settings.llm_max_retries
        self.retry_backoff_seconds = (
            retry_backoff_seconds
            if retry_backoff_seconds is not None
            else settings.llm_retry_backoff_seconds
        )

        if self.timeout_seconds <= 0:
            raise LLMClientError("LLM timeout must be greater than 0")
        if self.max_retries < 0:
            raise LLMClientError("LLM max retries must be greater than or equal to 0")
        if self.retry_backoff_seconds < 0:
            raise LLMClientError("LLM retry backoff must be greater than or equal to 0")

    def chat_completion(
        self,
        prompt: str,
        system_prompt: str | None = None,
        json_mode: bool = False,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        if self.provider == "mock":
            return self._mock_chat_completion(prompt, system_prompt, json_mode)
        if self.provider in {"openai", "openai_compatible"}:
            return self._openai_compatible_chat_completion(
                prompt=prompt,
                system_prompt=system_prompt,
                json_mode=json_mode,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        raise LLMClientError(f"Unsupported LLM provider: {self.provider}")

    def extract_json(self, content: str) -> Any:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        decoder = json.JSONDecoder()
        for index, character in enumerate(content):
            if character not in "{[":
                continue
            try:
                parsed, _ = decoder.raw_decode(content[index:])
                return parsed
            except json.JSONDecodeError:
                continue

        raise LLMProviderError("LLM response does not contain valid JSON")

    def _mock_chat_completion(
        self,
        prompt: str,
        system_prompt: str | None,
        json_mode: bool,
    ) -> LLMResponse:
        if json_mode:
            payload = {
                "provider": "mock",
                "model": self.model,
                "system_prompt_received": bool(system_prompt),
                "message": prompt,
            }
            content = json.dumps(payload, ensure_ascii=False)
            return LLMResponse(
                content=content,
                model=self.model,
                provider=self.provider,
                raw={"mock": True},
                parsed_json=payload,
            )

        content = f"Mock LLM response for: {prompt}"
        return LLMResponse(
            content=content,
            model=self.model,
            provider=self.provider,
            raw={"mock": True, "system_prompt_received": bool(system_prompt)},
        )

    def _openai_compatible_chat_completion(
        self,
        prompt: str,
        system_prompt: str | None,
        json_mode: bool,
        temperature: float,
        max_tokens: int | None,
    ) -> LLMResponse:
        self._validate_external_provider_config()

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self._build_messages(prompt, system_prompt),
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        raw = self._post_chat_completion(payload)
        content = self._extract_openai_content(raw)
        parsed_json = None
        if json_mode:
            parsed_json = self.extract_json(content)

        return LLMResponse(
            content=content,
            model=self.model,
            provider=self.provider,
            raw=raw,
            parsed_json=parsed_json,
        )

    def _validate_external_provider_config(self) -> None:
        if not self.api_base_url:
            raise LLMClientError("LLM_API_BASE_URL is required for external LLM providers")
        if not self.api_key:
            raise MissingLLMAPIKeyError("LLM_API_KEY is required for external LLM providers")

    def _build_messages(self, prompt: str, system_prompt: str | None) -> list[dict[str, str]]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _post_chat_completion(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.api_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.post(url, json=payload, headers=headers)
                    response.raise_for_status()
                    return response.json()
            except httpx.TimeoutException as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise LLMTimeoutError("LLM request timed out") from exc
            except httpx.HTTPStatusError as exc:
                last_error = exc
                if attempt >= self.max_retries or 400 <= exc.response.status_code < 500:
                    raise LLMProviderError(
                        f"LLM provider returned HTTP {exc.response.status_code}: {exc.response.text}"
                    ) from exc
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise LLMProviderError(f"LLM provider request failed: {exc}") from exc

            time.sleep(self.retry_backoff_seconds * (attempt + 1))

        raise LLMProviderError("LLM provider request failed") from last_error

    def _extract_openai_content(self, raw: dict[str, Any]) -> str:
        try:
            return raw["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError("LLM provider response does not contain message content") from exc


def create_llm_client() -> LLMClient:
    return LLMClient()
