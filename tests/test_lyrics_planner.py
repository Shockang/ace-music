"""Tests for LyricsPlanner."""

import pytest

from ace_music.schemas.lyrics import LyricsInput, LyricsOutput, SegmentType
from ace_music.tools.lyrics_planner import LyricsPlanner, _auto_segment, _format_for_ace_step


@pytest.fixture
def planner():
    return LyricsPlanner()


class TestLyricsPlannerProperties:
    def test_name(self, planner):
        assert planner.name == "lyrics_planner"

    def test_description(self, planner):
        assert "lyrics" in planner.description.lower()

    def test_schemas(self, planner):
        assert planner.input_schema is LyricsInput
        assert planner.output_schema is LyricsOutput

    def test_is_read_only(self, planner):
        assert planner.is_read_only is True


class TestInstrumentalMode:
    @pytest.mark.asyncio
    async def test_instrumental_returns_empty(self, planner):
        result = await planner.execute(
            LyricsInput(raw_text="ambient background", is_instrumental=True)
        )
        assert result.is_instrumental is True
        assert result.segments == []
        assert result.formatted_lyrics == ""


class TestTaggedLyricsParsing:
    @pytest.mark.asyncio
    async def test_parse_verse_chorus(self, planner):
        raw = "[verse]\nWalking through the neon lights\nCity dreams in black and white\n\n[chorus]\nWe are the night\nShining so bright"

        result = await planner.execute(LyricsInput(raw_text=raw))
        assert not result.is_instrumental
        assert len(result.segments) == 2
        assert result.segments[0].segment_type == SegmentType.VERSE
        assert result.segments[0].lines == [
            "Walking through the neon lights",
            "City dreams in black and white",
        ]
        assert result.segments[1].segment_type == SegmentType.CHORUS
        assert result.segments[1].lines == ["We are the night", "Shining so bright"]

    @pytest.mark.asyncio
    async def test_parse_all_segment_types(self, planner):
        raw = "[verse]\nLine one\n[chorus]\nLine two\n[bridge]\nLine three"

        result = await planner.execute(LyricsInput(raw_text=raw))
        types = [s.segment_type for s in result.segments]
        assert SegmentType.VERSE in types
        assert SegmentType.CHORUS in types
        assert SegmentType.BRIDGE in types

    @pytest.mark.asyncio
    async def test_time_estimates(self, planner):
        raw = """[verse]
Line one
Line two
[chorus]
Line three"""

        result = await planner.execute(LyricsInput(raw_text=raw))
        assert result.segments[0].time_start == 0.0
        assert result.segments[0].time_end is not None
        assert result.segments[1].time_start is not None
        assert result.total_estimated_duration is not None


class TestAutoSegmentation:
    @pytest.mark.asyncio
    async def test_auto_segment_short_text(self, planner):
        result = await planner.execute(
            LyricsInput(raw_text="Short lyrics here\nJust two lines")
        )
        assert len(result.segments) >= 1
        assert result.formatted_lyrics != ""

    @pytest.mark.asyncio
    async def test_auto_segment_long_text(self, planner):
        lines = [f"Line number {i}" for i in range(20)]
        text = "\n".join(lines)
        result = await planner.execute(LyricsInput(raw_text=text))
        assert len(result.segments) >= 2  # verse + chorus at minimum

    @pytest.mark.asyncio
    async def test_empty_input(self, planner):
        result = await planner.execute(LyricsInput(raw_text=""))
        assert result.segments == []
        assert result.formatted_lyrics == ""


class TestFormatForAceStep:
    def test_format_output(self):
        from ace_music.schemas.lyrics import LyricSegment

        segments = [
            LyricSegment(segment_type=SegmentType.VERSE, lines=["Hello", "World"]),
            LyricSegment(segment_type=SegmentType.CHORUS, lines=["Yeah"]),
        ]
        formatted = _format_for_ace_step(segments)
        assert "[verse]" in formatted
        assert "[chorus]" in formatted
        assert "Hello" in formatted


class TestValidateInput:
    def test_validate_dict_input(self, planner):
        data = {"raw_text": "test lyrics", "language": "en"}
        result = planner.validate_input(data)
        assert result.raw_text == "test lyrics"
        assert result.language == "en"
