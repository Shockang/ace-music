"""Audio output models."""

from pydantic import BaseModel, Field


class AudioOutput(BaseModel):
    """Audio generation result."""

    file_path: str = Field(description="Path to the generated audio file")
    duration_seconds: float = Field(description="Actual duration of generated audio")
    sample_rate: int = Field(default=48000)
    format: str = Field(default="wav")
    channels: int = Field(default=2)


class ProcessedAudio(BaseModel):
    """Post-processed audio with normalization applied."""

    file_path: str
    duration_seconds: float
    sample_rate: int = 48000
    format: str = Field(default="wav")
    channels: int = Field(default=2)
    loudness_lufs: float | None = Field(
        default=None, description="Integrated loudness in LUFS after normalization"
    )
    peak_db: float | None = Field(default=None, description="True peak in dB")
