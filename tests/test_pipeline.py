"""Tests for the full pipeline (MusicAgent)."""

import os
from pathlib import Path

import pytest

from ace_music.agent import MusicAgent
from ace_music.bridge import DirectorBridge
from ace_music.bridge.director_bridge import pipeline_output_to_response, request_to_pipeline_input
from ace_music.providers.deepseek import DeepSeekProvider
from ace_music.providers.router import FeatureRouter
from ace_music.schemas.output_config import OutputConfig
from ace_music.schemas.pipeline import PipelineInput, PipelineOutput
from ace_music.tools.generator import GeneratorConfig
from ace_music.tools.preset_resolver import PresetResolver


@pytest.fixture
def agent():
    config = GeneratorConfig(mock_mode=True)
    presets_dir = str(Path(__file__).parent.parent / "configs" / "presets")
    resolver = PresetResolver(presets_dir=presets_dir)
    return MusicAgent(generator_config=config, preset_resolver=resolver)


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


class TestPipelineWithPreset:
    @pytest.mark.asyncio
    async def test_pipeline_with_preset_name(self, agent, tmp_path):
        """Pipeline should accept preset_name and apply preset parameters."""
        result = await agent.run(
            PipelineInput(
                description="some music",
                preset_name="ambient_chill",
                duration_seconds=5.0,
                seed=42,
                output_dir=str(tmp_path),
            )
        )
        assert isinstance(result, PipelineOutput)
        assert result.audio_path
        assert result.metadata.get("style") is not None

    @pytest.mark.asyncio
    async def test_pipeline_with_unknown_preset_falls_back(self, agent, tmp_path):
        """Unknown preset name should fall back to heuristic style planning."""
        result = await agent.run(
            PipelineInput(
                description="electronic music",
                preset_name="nonexistent_preset_xyz",
                duration_seconds=5.0,
                seed=42,
                output_dir=str(tmp_path),
            )
        )
        assert isinstance(result, PipelineOutput)
        assert result.audio_path


class TestPipelineManifest:
    @pytest.mark.asyncio
    async def test_run_creates_manifest(self, agent, tmp_path):
        """Normal run() should create a manifest with all stages completed."""
        from ace_music.workspace import WorkspaceManager

        wm = WorkspaceManager(base_dir=str(tmp_path / "output"))
        run_id = "test_manifest_run"
        wm.create_run(run_id, description="manifest test")

        result = await agent.run(
            PipelineInput(
                description="ambient chill",
                duration_seconds=5.0,
                seed=42,
                output_dir=str(tmp_path / "output"),
            ),
            workspace=wm,
            run_id=run_id,
        )
        assert result is not None

        manifest = wm.load_manifest(run_id)
        for stage in ["style_planner", "generator", "post_processor", "output"]:
            assert manifest.artifacts[stage].status.value == "completed"


class TestPipelineWithOutputConfig:
    @pytest.mark.asyncio
    async def test_pipeline_passes_output_config_to_worker(self, tmp_path):
        """MusicAgent should pass OutputConfig through to OutputWorker."""
        agent = MusicAgent(generator_config=GeneratorConfig(mock_mode=True))
        config = OutputConfig(base_dir=str(tmp_path / "flat_output"), naming="flat")
        result = await agent.run(
            PipelineInput(
                description="test flat output",
                duration_seconds=5.0,
                output_config=config,
            )
        )
        assert Path(result.audio_path).parent == tmp_path / "flat_output"
        assert Path(result.audio_path).exists()


class TestAgentWithFeatureRouter:
    def test_agent_accepts_feature_router(self):
        """MusicAgent should accept an optional FeatureRouter."""
        provider = DeepSeekProvider(api_key="test-key")
        router = FeatureRouter(default=provider)
        agent = MusicAgent(
            generator_config=GeneratorConfig(mock_mode=True),
            feature_router=router,
        )
        assert agent._feature_router is not None

    def test_agent_works_without_feature_router(self):
        """MusicAgent should work without a FeatureRouter (backward compatible)."""
        agent = MusicAgent(generator_config=GeneratorConfig(mock_mode=True))
        assert agent._feature_router is None

    @pytest.mark.asyncio
    async def test_pipeline_runs_with_router(self, tmp_path):
        """Pipeline should work end-to-end with a FeatureRouter configured."""
        provider = DeepSeekProvider(api_key="test-key")
        router = FeatureRouter(default=provider)
        agent = MusicAgent(
            generator_config=GeneratorConfig(mock_mode=True),
            feature_router=router,
        )
        result = await agent.run(
            PipelineInput(
                description="test with router",
                duration_seconds=5.0,
                output_dir=str(tmp_path),
            )
        )
        assert result.audio_path
        assert Path(result.audio_path).exists()
