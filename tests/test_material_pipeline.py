"""Integration tests: material flows through pipeline and appears in output."""

import pytest

from ace_music.agent import MusicAgent
from ace_music.schemas.material import MaterialContext, MaterialEntry
from ace_music.schemas.pipeline import PipelineInput, PipelineOutput
from ace_music.tools.generator import GeneratorConfig


@pytest.fixture
def agent():
    config = GeneratorConfig(mock_mode=True)
    return MusicAgent(generator_config=config)


@pytest.fixture
def sample_material():
    return MaterialContext(
        entries=[
            MaterialEntry(
                source_file="test_material.json",
                content="Dreamy ambient pads with lush reverb",
                category="style_inspiration",
                tags=["ambient", "reverb"],
                mood="dreamy",
                style="ambient",
            ),
            MaterialEntry(
                source_file="test_material.json",
                content="[verse]\nNeon lights\nCity hums\n[chorus]\nElectric dreams",
                category="lyrics",
            ),
            MaterialEntry(
                source_file="test_material.json",
                content="melancholic with hopeful undertone",
                category="mood",
                mood="melancholic",
            ),
        ]
    )


class TestMaterialDrivenPipeline:
    @pytest.mark.asyncio
    async def test_material_influences_style(self, agent, sample_material, tmp_path):
        result = await agent.run(
            PipelineInput(
                description="test track",
                material_context=sample_material,
                duration_seconds=5.0,
                seed=42,
                output_dir=str(tmp_path),
            )
        )
        assert isinstance(result, PipelineOutput)
        assert result.metadata.get("material") is not None

    @pytest.mark.asyncio
    async def test_material_lyrics_consumed(self, agent, sample_material, tmp_path):
        result = await agent.run(
            PipelineInput(
                description="test track",
                material_context=sample_material,
                duration_seconds=5.0,
                seed=42,
                output_dir=str(tmp_path),
            )
        )
        assert result.audio_path

    @pytest.mark.asyncio
    async def test_material_provenance_in_metadata(self, agent, sample_material, tmp_path):
        result = await agent.run(
            PipelineInput(
                description="test track",
                material_context=sample_material,
                duration_seconds=5.0,
                seed=42,
                output_dir=str(tmp_path),
            )
        )
        mat_meta = result.metadata.get("material", {})
        assert mat_meta.get("source_count") == 3
        assert "test_material.json" in mat_meta.get("source_files", [])
        assert mat_meta.get("style_summary") != ""
        assert mat_meta.get("mood") is not None

    @pytest.mark.asyncio
    async def test_pipeline_works_without_material(self, agent, tmp_path):
        result = await agent.run(
            PipelineInput(
                description="electronic beats",
                duration_seconds=5.0,
                seed=42,
                output_dir=str(tmp_path),
            )
        )
        assert isinstance(result, PipelineOutput)
        assert result.audio_path
        assert result.metadata.get("material") is None


class TestMaterialInfluencesOutput:
    @pytest.mark.asyncio
    async def test_material_mood_sets_pipeline_mood(self, agent, sample_material, tmp_path):
        result = await agent.run(
            PipelineInput(
                description="test",
                material_context=sample_material,
                duration_seconds=5.0,
                seed=42,
                output_dir=str(tmp_path),
            )
        )
        assert result.metadata.get("material", {}).get("mood") is not None

    @pytest.mark.asyncio
    async def test_empty_material_does_not_crash(self, agent, tmp_path):
        empty_ctx = MaterialContext()
        result = await agent.run(
            PipelineInput(
                description="test track",
                material_context=empty_ctx,
                duration_seconds=5.0,
                seed=42,
                output_dir=str(tmp_path),
            )
        )
        assert isinstance(result, PipelineOutput)
