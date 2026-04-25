"""Tests for the full pipeline (MusicAgent)."""

import json
import os
from pathlib import Path

import pytest

from ace_music.agent import MusicAgent
from ace_music.bridge import DirectorBridge
from ace_music.bridge.director_bridge import pipeline_output_to_response, request_to_pipeline_input
from ace_music.providers.deepseek import DeepSeekProvider
from ace_music.providers.router import FeatureRouter
from ace_music.schemas.audio_contract import AudioSceneContract
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

    @pytest.mark.asyncio
    async def test_pipeline_metadata_includes_audio_contract(self, agent, tmp_path):
        contract = AudioSceneContract(
            scene_id="scene_meta",
            mood="urgent",
            duration_seconds=5.0,
            intensity=0.85,
            arousal=0.9,
            dialogue_density=0.8,
        )

        result = await agent.run(
            PipelineInput(
                description="background music",
                duration_seconds=5.0,
                is_instrumental=True,
                audio_contract=contract,
                output_dir=str(tmp_path),
            )
        )

        assert result.metadata["audio_contract"]["scene_id"] == "scene_meta"
        assert result.metadata["mapped_audio"]["tempo_preference"] == "fast"
        assert result.metadata["mix"]["ducking_db"] >= 8.0
        assert result.metadata["qa_targets"]["min_composition_success_rate"] == 0.98

        metadata_path = next(Path(result.audio_path).parent.glob("*_metadata.json"))
        persisted = json.loads(metadata_path.read_text())
        assert persisted["audio_contract"]["scene_id"] == "scene_meta"


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


class TestDirectorBridgeEnhanced:
    def test_request_accepts_scene_description(self):
        req = DirectorBridge.Request(
            scene_id="scene_001",
            mood="suspenseful",
            duration_seconds=30.0,
            scene_description="A detective examines evidence in a dimly lit room",
        )
        assert req.scene_description == "A detective examines evidence in a dimly lit room"

    def test_request_accepts_intensity(self):
        req = DirectorBridge.Request(
            scene_id="scene_002",
            mood="tense",
            duration_seconds=30.0,
            intensity=0.8,
        )
        assert req.intensity == 0.8

    def test_request_accepts_preset_name(self):
        req = DirectorBridge.Request(
            scene_id="scene_003",
            mood="dark",
            duration_seconds=30.0,
            preset_name="dark_suspense",
        )
        assert req.preset_name == "dark_suspense"

    def test_request_accepts_is_instrumental(self):
        req = DirectorBridge.Request(
            scene_id="scene_004",
            mood="calm",
            duration_seconds=60.0,
            is_instrumental=True,
        )
        assert req.is_instrumental is True

    def test_response_includes_success_field(self):
        resp = DirectorBridge.Response(
            audio_path="/tmp/test.wav",
            duration_seconds=30.0,
            scene_id="scene_001",
            success=True,
        )
        assert resp.success is True

    def test_response_includes_error_field(self):
        resp = DirectorBridge.Response(
            audio_path="",
            duration_seconds=0.0,
            scene_id="scene_001",
            success=False,
            error="Generation failed: GPU out of memory",
        )
        assert resp.success is False
        assert resp.error == "Generation failed: GPU out of memory"

    def test_request_to_pipeline_maps_new_fields(self):
        req = DirectorBridge.Request(
            scene_id="scene_005",
            mood="dark",
            duration_seconds=30.0,
            preset_name="dark_suspense",
            is_instrumental=True,
            scene_description="Night cityscape with rain",
        )
        pipeline_input = request_to_pipeline_input(req)
        assert pipeline_input.preset_name == "dark_suspense"
        assert pipeline_input.is_instrumental is True
        assert "rain" in pipeline_input.description

    def test_request_accepts_contract_mapping_fields(self):
        req = DirectorBridge.Request(
            scene_id="scene_contract",
            mood="tense",
            duration_seconds=30.0,
            scene_description="A chase through a narrow alley",
            intensity=0.9,
            arousal=0.95,
            valence=-0.4,
            shot_count=16,
            dialogue_density=0.7,
            tts_present=True,
            crossfade_seconds=2.0,
            target_lufs=-17.0,
            max_true_peak_db=-1.0,
        )

        pipeline_input = request_to_pipeline_input(req)

        assert pipeline_input.audio_contract is not None
        assert pipeline_input.audio_contract.scene_id == "scene_contract"
        assert pipeline_input.audio_contract.intensity == 0.9
        assert pipeline_input.audio_contract.arousal == 0.95
        assert pipeline_input.audio_contract.transition.crossfade_seconds == 2.0
        assert pipeline_input.audio_contract.mix.target_lufs == -17.0
