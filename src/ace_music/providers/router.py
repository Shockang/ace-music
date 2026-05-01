"""FeatureRouter: route LLM requests to the appropriate provider.

Each pipeline feature (lyrics_planning, style_planning, etc.) can be
bound to a specific provider. Unbound features fall back to the default.
"""

import logging

from .base import ChatMessage, ChatProvider, ChatResponse

logger = logging.getLogger(__name__)


class FeatureRouter:
    """Route LLM completion requests to providers based on feature name."""

    def __init__(
        self,
        default: ChatProvider,
        feature_providers: dict[str, ChatProvider] | None = None,
    ) -> None:
        self._default = default
        self._feature_providers = feature_providers or {}

    @property
    def default_provider(self) -> ChatProvider:
        return self._default

    def _resolve(self, feature: str) -> ChatProvider:
        """Resolve a feature name to its provider."""
        provider = self._feature_providers.get(feature)
        if provider:
            return provider
        return self._default

    async def complete(self, feature: str, messages: list[ChatMessage], **kwargs) -> ChatResponse:
        """Generate a completion using the provider bound to the feature."""
        provider = self._resolve(feature)
        logger.debug("Routing feature '%s' to provider '%s'", feature, provider.name)
        return await provider.complete(messages, **kwargs)

    def list_providers(self) -> list[str]:
        """List all registered provider names."""
        names = {self._default.name}
        for provider in self._feature_providers.values():
            names.add(provider.name)
        return sorted(names)
