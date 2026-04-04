"""Lyrics structure models."""

from enum import Enum

from pydantic import BaseModel, Field


class SegmentType(str, Enum):
    """Song segment types recognized by ACE-Step."""

    INTRO = "intro"
    VERSE = "verse"
    CHORUS = "chorus"
    BRIDGE = "bridge"
    OUTRO = "outro"


class LyricSegment(BaseModel):
    """A single segment of structured lyrics."""

    segment_type: SegmentType
    lines: list[str] = Field(default_factory=list)
    time_start: float | None = Field(default=None, description="Estimated start time in seconds")
    time_end: float | None = Field(default=None, description="Estimated end time in seconds")


class LyricsInput(BaseModel):
    """Input for lyrics planning."""

    raw_text: str = Field(description="Raw lyrics text or natural language description")
    language: str = Field(default="en", description="Language code (en, zh, ja, ko, etc.)")
    is_instrumental: bool = Field(
        default=False, description="True if no lyrics needed (instrumental track)"
    )


class LyricsOutput(BaseModel):
    """Structured lyrics output from LyricsPlanner."""

    segments: list[LyricSegment] = Field(default_factory=list)
    formatted_lyrics: str = Field(description="ACE-Step compatible formatted lyrics string")
    language: str = "en"
    is_instrumental: bool = False
    total_estimated_duration: float | None = None

    def to_ace_step_format(self) -> str:
        """Return the formatted lyrics string ready for ACE-Step."""
        return self.formatted_lyrics
