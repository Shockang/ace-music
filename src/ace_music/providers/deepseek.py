"""DeepSeek LLM provider implementation.

Uses the OpenAI-compatible API format for DeepSeek models.
"""

import logging
import os
from typing import Any

import httpx

from .base import ChatMessage, ChatResponse

logger = logging.getLogger(__name__)

DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_DEFAULT_MODEL = "deepseek-chat"


class DeepSeekProvider:
    """DeepSeek LLM provider using OpenAI-compatible API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEEPSEEK_DEFAULT_MODEL,
        base_url: str = DEEPSEEK_API_URL,
        timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not self._api_key:
            raise ValueError(
                "DeepSeek API key required. Pass api_key or set DEEPSEEK_API_KEY env var."
            )
        self._model = model
        self._base_url = base_url
        self._timeout = timeout

    @property
    def name(self) -> str:
        return "deepseek"

    async def _call_api(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Make the actual HTTP call to the DeepSeek API."""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(self._base_url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()

    async def complete(self, messages: list[ChatMessage], **kwargs) -> ChatResponse:
        """Generate a chat completion via DeepSeek API."""
        payload = {
            "model": kwargs.get("model", self._model),
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 2048),
        }

        result = await self._call_api(payload)
        content = result["choices"][0]["message"]["content"]
        usage = result.get("usage", {})

        return ChatResponse(
            content=content,
            model=result.get("model", self._model),
            usage=usage,
        )
