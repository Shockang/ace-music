"""Tests for the full pipeline (MusicAgent)."""

import os

import pytest

from ace_music.agent import MusicAgent
from ace_music.bridge import DirectorBridge
from ace_music.bridge.director_bridge import pipeline_output_to_response, request_to_pipeline_input
from ace_music.schemas.pipeline import PipelineInput, PipelineOutput
from ace_music.tools.generator import GeneratorConfig


@pytest.fixture
def agent():
    config = GeneratorConfig(mock_mode=True)
    return MusicAgent(generator_config=config)


class TestMusicAgentPipeline:
    @pytest.mark.asyncio
    async def test_full_pipeline_with_lyrics(self, agent, tmp_path):
        result = await agent.run(
            PipelineInput(
                description="A dreamy synthwave track about neon cities",
                lyrics="[verse]\nNeon lights in the rain\nCity calls my name",
                duration_seconds=5.0,
                seed=42,
                output_dir=str(tmp_path),
            )
        )
        assert isinstance(result, PipelineOutput)
        assert result.audio_path
        assert os.path.exists(result.audio_path)
        assert result.duration_seconds > 0
        assert result.format == "wav"
        assert result.metadata.get("seed") == 42

    @pytest.mark.asyncio
    async def test_instrumental_pipeline(self, agent, tmp_path):
        result = await agent.run(
            PipelineInput(
                description="Ambient chill background music",
                duration_seconds=5.0,
                is_instrumental=True,
                seed=100,
                output_dir=str(tmp_path),
            )
        )
        assert isinstance(result, PipelineOutput)
        assert result.audio_path
        assert result.segments == []  # no lyrics segments for instrumental

    @pytest.mark.asyncio
    async def test_pipeline_with_style_overrides(self, agent, tmp_path):
        result = await agent.run(
            PipelineInput(
                description="electronic dance music",
                style_tags=["electronic", "dance"],
                duration_seconds=5.0,
                guidance_scale=20.0,
                infer_step=27,
                seed=1,
                output_dir=str(tmp_path),
            )
        )
        assert isinstance(result, PipelineOutput)
        assert result.metadata["style"]["guidance_scale"] == 20.0
        assert result.metadata["style"]["infer_step"] == 27

    @pytest.mark.asyncio
    async def test_pipeline_plan_building(self, agent, tmp_path):
        """Verify the plan includes the right stages."""
        # Instrumental should skip lyrics_planner
        input_no_lyrics = PipelineInput(
            description="instrumental",
            is_instrumental=True,
            output_dir=str(tmp_path),
        )
        plan = agent._build_plan(input_no_lyrics)
        assert "lyrics_planner" not in plan
        assert "style_planner" in plan
        assert "generator" in plan

        # With lyrics should include lyrics_planner
        input_with_lyrics = PipelineInput(
            description="pop song",
            lyrics="some lyrics",
            output_dir=str(tmp_path),
        )
        plan = agent._build_plan(input_with_lyrics)
        assert "lyrics_planner" in plan


class TestDirectorBridge:
    def test_request_to_pipeline_input(self):
        req = DirectorBridge.Request(
            scene_id="scene_001",
            mood="melancholic",
            duration_seconds=60.0,
            style_reference="dark ambient electronic",
            tempo_preference="slow",
        )
        pipeline_input = request_to_pipeline_input(req)
        assert pipeline_input.description == "dark ambient electronic"
        assert pipeline_input.mood == "melancholic"
        assert pipeline_input.duration_seconds == 60.0
        assert pipeline_input.tempo_preference == "slow"

    def test_pipeline_output_to_response(self):
        output = PipelineOutput(
            audio_path="/tmp/test.wav",
            duration_seconds=55.0,
            format="wav",
            metadata={"seed": 42, "style": {"prompt": "ambient"}},
        )
        req = DirectorBridge.Request(
            scene_id="scene_002",
            mood="calm",
            duration_seconds=60.0,
        )
        response = pipeline_output_to_response(output, req)
        assert response.audio_path == "/tmp/test.wav"
        assert response.duration_seconds == 55.0
        assert response.scene_id == "scene_002"
        assert response.metadata["seed"] == 42

    def test_bridge_request_defaults(self):
        req = DirectorBridge.Request(
            scene_id="s1",
            mood="upbeat",
            duration_seconds=30.0,
        )
        assert req.style_reference is None
        assert req.lyrics_hint is None
        assert req.seed is None
        assert req.output_format == "wav"


class TestBuildPlan:
    def test_full_plan_with_lyrics(self, agent, tmp_path):
        inp = PipelineInput(
            description="pop song",
            lyrics="la la la",
            output_dir=str(tmp_path),
        )
        plan = agent._build_plan(inp)
        assert plan == [
            "lyrics_planner",
            "style_planner",
            "generator",
            "post_processor",
            "output",
        ]

    def test_plan_without_lyrics(self, agent, tmp_path):
        inp = PipelineInput(
            description="instrumental",
            is_instrumental=True,
            output_dir=str(tmp_path),
        )
        plan = agent._build_plan(inp)
        assert "lyrics_planner" not in plan

    def test_plan_with_description_no_lyrics(self, agent, tmp_path):
        """Description without lyrics should still plan lyrics."""
        inp = PipelineInput(
            description="pop song",
            output_dir=str(tmp_path),
        )
        plan = agent._build_plan(inp)
        assert "lyrics_planner" in plan
