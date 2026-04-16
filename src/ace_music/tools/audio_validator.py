"""AudioValidator: verify WAV file format, sample rate, duration, and playability."""

import logging
import wave
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ValidationResult(BaseModel):
    """Result of audio file validation."""
    file_path: str
    is_valid: bool
    format: str = "unknown"
    sample_rate: int = 0
    channels: int = 0
    duration_seconds: float = 0.0
    file_size_bytes: int = 0
    errors: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict:
        return self.model_dump()


class AudioValidator:
    """Validate WAV audio files against required specifications."""

    def validate(
        self,
        file_path: str,
        expected_sample_rate: int = 48000,
        min_duration_seconds: float = 1.0,
    ) -> ValidationResult:
        path = Path(file_path)
        errors: list[str] = []

        if not path.exists():
            return ValidationResult(
                file_path=file_path,
                is_valid=False,
                errors=[f"File not found: {file_path}"],
            )

        file_size = path.stat().st_size

        try:
            with wave.open(str(path), "r") as wf:
                channels = wf.getnchannels()
                sample_width = wf.getsampwidth()
                sample_rate = wf.getframerate()
                num_frames = wf.getnframes()
                duration = num_frames / sample_rate if sample_rate > 0 else 0.0
        except wave.Error as e:
            return ValidationResult(
                file_path=file_path,
                is_valid=False,
                format="unknown",
                file_size_bytes=file_size,
                errors=[f"Not a valid WAV file: {e}"],
            )
        except Exception as e:
            return ValidationResult(
                file_path=file_path,
                is_valid=False,
                format="unknown",
                file_size_bytes=file_size,
                errors=[f"Failed to read audio: {e}"],
            )

        if sample_rate != expected_sample_rate:
            errors.append(f"Sample rate {sample_rate} != expected {expected_sample_rate}")

        if duration < min_duration_seconds:
            errors.append(f"Duration {duration:.1f}s < minimum {min_duration_seconds:.1f}s")

        if file_size < 1024:
            errors.append(f"File too small ({file_size} bytes), likely empty or corrupt")

        return ValidationResult(
            file_path=file_path,
            is_valid=len(errors) == 0,
            format="wav",
            sample_rate=sample_rate,
            channels=channels,
            duration_seconds=round(duration, 2),
            file_size_bytes=file_size,
            errors=errors,
        )
