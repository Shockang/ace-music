"""Base types for the LLM provider abstraction."""

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """A single message in a chat conversation."""

    role: str = Field(description="Message role: system, user, or assistant")
    content: str = Field(description="Message content")


class ChatResponse(BaseModel):
    """Response from an LLM completion."""

    content: str = Field(description="Generated text response")
    model: str = Field(description="Model used for generation")
    usage: dict = Field(default_factory=dict, description="Token usage stats")


@runtime_checkable
class ChatProvider(Protocol):
    """Protocol for LLM chat completion providers."""

    @property
    def name(self) -> str: ...

    async def complete(self, messages: list[ChatMessage], **kwargs) -> ChatResponse: ...
