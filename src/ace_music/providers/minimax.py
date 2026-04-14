"""MiniMax LLM provider implementation.

Uses the OpenAI-compatible API format for MiniMax models.
"""

import logging
import os
from typing import Any

import httpx

from .base import ChatMessage, ChatResponse

logger = logging.getLogger(__name__)

MINIMAX_API_URL = "https://api.minimax.chat/v1/chat/completions"
MINIMAX_DEFAULT_MODEL = "MiniMax-Text-01"


class MiniMaxProvider:
    """MiniMax LLM provider using OpenAI-compatible API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = MINIMAX_DEFAULT_MODEL,
        base_url: str = MINIMAX_API_URL,
        timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key or os.environ.get("MINIMAX_API_KEY")
        if not self._api_key:
            raise ValueError(
                "MiniMax API key required. Pass api_key or set MINIMAX_API_KEY env var."
            )
        self._model = model
        self._base_url = base_url
        self._timeout = timeout

    @property
    def name(self) -> str:
        return "minimax"

    async def _call_api(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Make the actual HTTP call to the MiniMax API."""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(self._base_url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()

    async def complete(self, messages: list[ChatMessage], **kwargs) -> ChatResponse:
        """Generate a chat completion via MiniMax API."""
        payload = {
            "model": kwargs.get("model", self._model),
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 2048),
        }

        try:
            result = await self._call_api(payload)
        except Exception as e:
            raise RuntimeError(f"MiniMax API request failed: {e}") from e

        choices = result.get("choices")
        if not choices or not isinstance(choices, list):
            raise RuntimeError(f"MiniMax returned unexpected response: {result}")

        message = choices[0].get("message", {})
        content = message.get("content")
        if not content:
            raise RuntimeError(f"MiniMax returned empty content: {result}")

        return ChatResponse(
            content=content,
            model=result.get("model", self._model),
            usage=result.get("usage", {}),
        )
