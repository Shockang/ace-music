"""Unified MusicTool interface for all pipeline tools.

Design inspired by cc-haha's Tool interface pattern:
- Generic abstract base class parameterized by Input/Output types
- Pydantic BaseModel schemas for structured validation
- Async-first execution
- Read-only / concurrency-safe metadata for orchestration
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from pydantic import BaseModel

InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)


class MusicTool(ABC, Generic[InputT, OutputT]):
    """Abstract base class for all music pipeline tools.

    Each tool declares its input/output schemas as Pydantic models and
    implements async execute(). The planner orchestrates tools by calling
    execute() in sequence, passing outputs forward.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool identifier used in planning and logging."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what this tool does."""
        ...

    @property
    @abstractmethod
    def input_schema(self) -> type[InputT]:
        """Pydantic model class for input validation."""
        ...

    @property
    @abstractmethod
    def output_schema(self) -> type[OutputT]:
        """Pydantic model class for output validation."""
        ...

    @abstractmethod
    async def execute(self, input_data: InputT) -> OutputT:
        """Execute the tool and return structured output.

        Args:
            input_data: Validated input matching input_schema.

        Returns:
            Structured output matching output_schema.
        """
        ...

    @property
    def is_read_only(self) -> bool:
        """Whether this tool only reads data without side effects."""
        return True

    @property
    def is_concurrency_safe(self) -> bool:
        """Whether this tool can run in parallel with other tools."""
        return False

    def validate_input(self, data: dict) -> InputT:
        """Parse and validate raw dict input into the typed schema."""
        return self.input_schema.model_validate(data)

    def validate_output(self, data: dict) -> OutputT:
        """Parse and validate raw dict into the typed output schema."""
        return self.output_schema.model_validate(data)
