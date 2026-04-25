"""Typed exceptions for diagnosable ace-music failures."""

from __future__ import annotations


class AceMusicError(Exception):
    """Base class for ace-music operational failures."""

    exit_code = 1
    category = "runtime_error"


class DependencyUnavailableError(AceMusicError):
    """Required runtime dependency is unavailable."""

    exit_code = 20
    category = "dependency_unavailable"


class GPUUnavailableError(AceMusicError):
    """GPU runtime is required but unavailable."""

    exit_code = 21
    category = "gpu_unavailable"


class GenerationFailedError(AceMusicError):
    """Music generation failed after dependencies were available."""

    exit_code = 30
    category = "generation_failed"


class PipelineTimeoutError(AceMusicError):
    """Pipeline or stage exceeded its configured timeout."""

    exit_code = 40
    category = "timeout"


class OutputValidationError(AceMusicError):
    """Generated output failed audio validation."""

    exit_code = 50
    category = "output_validation_failed"

    def __init__(self, message: str, errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or []
