"""Tests for StylePlanner."""

import pytest

from ace_music.schemas.style import StyleInput, StyleOutput
from ace_music.tools.style_planner import StylePlanner


@pytest.fixture
def planner():
    return StylePlanner()


class TestStylePlannerProperties:
    def test_name(self, planner):
        assert planner.name == "style_planner"

    def test_schemas(self, planner):
        assert planner.input_schema is StyleInput
        assert planner.output_schema is StyleOutput


class TestTagExtraction:
    @pytest.mark.asyncio
    async def test_genre_from_description(self, planner):
        result = await planner.execute(
            StyleInput(description="a dreamy synthwave track with heavy bass")
        )
        assert "synthwave" in result.prompt
        assert "retro" in result.prompt

    @pytest.mark.asyncio
    async def test_mood_tags(self, planner):
        result = await planner.execute(
            StyleInput(description="upbeat pop song", mood="happy")
        )
        tags = result.prompt.split(", ")
        assert any("upbeat" in t for t in tags)

    @pytest.mark.asyncio
    async def test_pre_known_tags(self, planner):
        result = await planner.execute(
            StyleInput(description="music", reference_tags=["electronic", "ambient"])
        )
        assert "electronic" in result.prompt
        assert "ambient" in result.prompt

    @pytest.mark.asyncio
    async def test_fallback_to_description(self, planner):
        result = await planner.execute(
            StyleInput(description="something completely unique and unprecedented")
        )
        assert result.prompt != ""


class TestTempoParsing:
    @pytest.mark.asyncio
    async def test_fast_tempo(self, planner):
        result = await planner.execute(
            StyleInput(description="pop", tempo_preference="fast and energetic")
        )
        assert result.omega_scale == 12.0

    @pytest.mark.asyncio
    async def test_slow_tempo(self, planner):
        result = await planner.execute(
            StyleInput(description="ambient", tempo_preference="slow ballad")
        )
        assert result.omega_scale == 8.0

    @pytest.mark.asyncio
    async def test_explicit_bpm(self, planner):
        result = await planner.execute(
            StyleInput(description="electronic", tempo_preference="160 bpm")
        )
        assert result.omega_scale == 12.0

    @pytest.mark.asyncio
    async def test_no_tempo(self, planner):
        result = await planner.execute(StyleInput(description="pop"))
        assert result.guidance_scale == 15.0  # default


class TestDefaults:
    @pytest.mark.asyncio
    async def test_default_values(self, planner):
        result = await planner.execute(StyleInput(description="pop"))
        assert result.scheduler_type == "euler"
        assert result.cfg_type == "apg"
        assert result.infer_step == 60
        assert result.use_erg_tag is True
