"""LyricsPlanner: parse raw text into structured lyrics segments.

Supports:
- Raw lyrics with [verse]/[chorus]/[bridge] tags already present
- Natural language descriptions → instrumental mode
- Plain text lyrics → auto-segmentation
- Multi-language support
"""

import re

from ace_music.schemas.lyrics import LyricSegment, LyricsInput, LyricsOutput, SegmentType
from ace_music.tools.base import MusicTool

# Regex to match ACE-Step segment tags like [verse], [chorus], etc.
_SEGMENT_TAG_RE = re.compile(
    r"^\s*\[(intro|verse|chorus|bridge|outro)\]\s*$", re.IGNORECASE | re.MULTILINE
)

# Estimated seconds per line of lyrics (varies by tempo, but a reasonable default)
_SECONDS_PER_LINE: dict[SegmentType, float] = {
    SegmentType.INTRO: 4.0,
    SegmentType.VERSE: 3.5,
    SegmentType.CHORUS: 3.0,
    SegmentType.BRIDGE: 3.5,
    SegmentType.OUTRO: 4.0,
}


def _parse_tagged_lyrics(text: str) -> list[LyricSegment]:
    """Parse lyrics that already contain [verse], [chorus], etc. tags."""
    segments: list[LyricSegment] = []
    current_type: SegmentType | None = None
    current_lines: list[str] = []

    for line in text.split("\n"):
        match = _SEGMENT_TAG_RE.match(line)
        if match:
            if current_type is not None:
                segments.append(LyricSegment(segment_type=current_type, lines=current_lines))
            current_type = SegmentType(match.group(1).lower())
            current_lines = []
        elif current_type is not None and line.strip():
            current_lines.append(line.strip())

    if current_type is not None and current_lines:
        segments.append(LyricSegment(segment_type=current_type, lines=current_lines))

    return segments


def _auto_segment(text: str) -> list[LyricSegment]:
    """Auto-segment plain text lyrics into verse/chorus/bridge."""
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines:
        return []

    total = len(lines)
    segments: list[LyricSegment] = []

    # Simple heuristic: first 4 lines = verse, next 4 = chorus, etc.
    if total <= 4:
        return [LyricSegment(segment_type=SegmentType.VERSE, lines=lines)]

    chunk_size = max(4, total // 3)
    segment_types = [SegmentType.VERSE, SegmentType.CHORUS, SegmentType.BRIDGE]

    for i, seg_type in enumerate(segment_types):
        start = i * chunk_size
        end = start + chunk_size if i < len(segment_types) - 1 else total
        chunk = lines[start:end]
        if chunk:
            segments.append(LyricSegment(segment_type=seg_type, lines=chunk))

    return segments


def _estimate_durations(segments: list[LyricSegment]) -> list[LyricSegment]:
    """Add estimated time annotations to segments."""
    result = []
    current_time = 0.0
    for seg in segments:
        duration = len(seg.lines) * _SECONDS_PER_LINE.get(seg.segment_type, 3.5)
        result.append(
            seg.model_copy(
                update={"time_start": current_time, "time_end": current_time + duration}
            )
        )
        current_time += duration
    return result


def _format_for_ace_step(segments: list[LyricSegment]) -> str:
    """Format segments into ACE-Step compatible lyrics string."""
    parts = []
    for seg in segments:
        parts.append(f"[{seg.segment_type.value}]")
        parts.extend(seg.lines)
        parts.append("")  # blank line between segments
    return "\n".join(parts).strip()


class LyricsPlanner(MusicTool[LyricsInput, LyricsOutput]):
    """Parse and structure raw lyrics for ACE-Step generation."""

    @property
    def name(self) -> str:
        return "lyrics_planner"

    @property
    def description(self) -> str:
        return "Parse raw lyrics text into structured segments with time estimates"

    @property
    def input_schema(self) -> type[LyricsInput]:
        return LyricsInput

    @property
    def output_schema(self) -> type[LyricsOutput]:
        return LyricsOutput

    async def execute(self, input_data: LyricsInput) -> LyricsOutput:
        if input_data.is_instrumental:
            return LyricsOutput(
                segments=[],
                formatted_lyrics="",
                language=input_data.language,
                is_instrumental=True,
                total_estimated_duration=None,
            )

        text = input_data.raw_text.strip()
        if not text:
            return LyricsOutput(
                segments=[],
                formatted_lyrics="",
                language=input_data.language,
                is_instrumental=False,
                total_estimated_duration=None,
            )

        # If text already has segment tags, parse them directly
        if _SEGMENT_TAG_RE.search(text):
            segments = _parse_tagged_lyrics(text)
        else:
            segments = _auto_segment(text)

        segments = _estimate_durations(segments)
        formatted = _format_for_ace_step(segments)
        total_duration = (
            segments[-1].time_end if segments and segments[-1].time_end else None
        )

        return LyricsOutput(
            segments=segments,
            formatted_lyrics=formatted,
            language=input_data.language,
            is_instrumental=False,
            total_estimated_duration=total_duration,
        )
