"""Tests for LLM provider abstraction."""

import os
from unittest.mock import AsyncMock, patch

import pytest

from ace_music.providers.base import ChatMessage, ChatResponse
from ace_music.providers.deepseek import DeepSeekProvider
from ace_music.providers.router import FeatureRouter


class FakeProvider:
    """Minimal provider for testing the protocol."""

    @property
    def name(self) -> str:
        return "fake"

    async def complete(self, messages: list[ChatMessage], **kwargs) -> ChatResponse:
        return ChatResponse(
            content="fake response", model="fake-1.0", usage={"total_tokens": 10}
        )


class TestChatProviderProtocol:
    @pytest.mark.asyncio
    async def test_fake_provider_satisfies_protocol(self):
        provider = FakeProvider()
        assert provider.name == "fake"
        response = await provider.complete(
            [ChatMessage(role="user", content="hello")]
        )
        assert response.content == "fake response"

    def test_chat_message_model(self):
        msg = ChatMessage(role="system", content="You are a music expert.")
        assert msg.role == "system"

    def test_chat_response_model(self):
        resp = ChatResponse(content="test", model="test-model")
        assert resp.content == "test"
        assert resp.usage == {}


class TestDeepSeekProvider:
    def test_provider_name(self):
        provider = DeepSeekProvider(api_key="test-key")
        assert provider.name == "deepseek"

    @pytest.mark.asyncio
    async def test_complete_calls_api(self):
        provider = DeepSeekProvider(api_key="test-key", model="deepseek-chat")

        mock_response = {
            "choices": [{"message": {"content": "Generated lyrics"}}],
            "model": "deepseek-chat",
            "usage": {"total_tokens": 100},
        }

        with patch.object(provider, "_call_api", new_callable=AsyncMock) as mock_api:
            mock_api.return_value = mock_response
            response = await provider.complete(
                [ChatMessage(role="user", content="Write lyrics")]
            )
            assert response.content == "Generated lyrics"
            assert response.model == "deepseek-chat"

    def test_missing_api_key_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("DEEPSEEK_API_KEY", None)
            with pytest.raises(ValueError, match="api_key"):
                DeepSeekProvider()


class FakeProviderA:
    @property
    def name(self) -> str:
        return "provider_a"

    async def complete(self, messages: list[ChatMessage], **kwargs):
        return ChatResponse(content="response from A", model="a-model")


class FakeProviderB:
    @property
    def name(self) -> str:
        return "provider_b"

    async def complete(self, messages: list[ChatMessage], **kwargs):
        return ChatResponse(content="response from B", model="b-model")


class TestFeatureRouter:
    def test_default_provider(self):
        router = FeatureRouter(default=FakeProviderA())
        assert router.default_provider.name == "provider_a"

    @pytest.mark.asyncio
    async def test_route_to_default(self):
        router = FeatureRouter(default=FakeProviderA())
        response = await router.complete(
            "lyrics_planning", [ChatMessage(role="user", content="test")]
        )
        assert response.content == "response from A"

    @pytest.mark.asyncio
    async def test_route_to_feature_specific_provider(self):
        router = FeatureRouter(
            default=FakeProviderA(),
            feature_providers={"style_planning": FakeProviderB()},
        )
        response = await router.complete(
            "style_planning", [ChatMessage(role="user", content="test")]
        )
        assert response.content == "response from B"

    @pytest.mark.asyncio
    async def test_unknown_feature_uses_default(self):
        router = FeatureRouter(
            default=FakeProviderA(),
            feature_providers={"style_planning": FakeProviderB()},
        )
        response = await router.complete(
            "unknown_feature", [ChatMessage(role="user", content="test")]
        )
        assert response.content == "response from A"

    def test_list_providers(self):
        router = FeatureRouter(
            default=FakeProviderA(),
            feature_providers={"style_planning": FakeProviderB()},
        )
        providers = router.list_providers()
        assert "provider_a" in providers
        assert "provider_b" in providers
