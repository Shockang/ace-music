"""Tests for regression runner."""

import json

import pytest

from ace_music.regression_runner import RegressionResult, RegressionRunner
from ace_music.schemas.material import MaterialContext, MaterialEntry
from ace_music.tools.generator import GeneratorConfig


@pytest.fixture
def runner(tmp_path):
    config = GeneratorConfig(mock_mode=True)
    return RegressionRunner(
        generator_config=config,
        output_dir=str(tmp_path / "regression"),
    )


@pytest.fixture
def sample_material():
    return MaterialContext(
        entries=[
            MaterialEntry(
                source_file="test.json",
                content="ambient electronic, dreamy pads",
                category="style_inspiration",
                mood="dreamy",
                style="ambient",
            ),
            MaterialEntry(
                source_file="test.json",
                content="[verse]\nTest lyrics line",
                category="lyrics",
            ),
        ]
    )


class TestRegressionRunner:
    @pytest.mark.asyncio
    async def test_single_run_succeeds(self, runner, sample_material):
        result = await runner.run_single(
            description="test track",
            material=sample_material,
            duration_seconds=5.0,
            seed=42,
        )
        assert isinstance(result, RegressionResult)
        assert result.success is True
        assert result.audio_path is not None
        assert result.duration_seconds > 0
        assert result.material_provenance is not None

    @pytest.mark.asyncio
    async def test_three_runs_all_succeed(self, runner, sample_material):
        results = await runner.run_regression(
            description="regression test",
            material=sample_material,
            num_runs=3,
            duration_seconds=5.0,
            base_seed=100,
        )
        assert len(results) == 3
        assert all(r.success for r in results)
        seeds = [r.seed for r in results]
        assert len(set(seeds)) == 3

    @pytest.mark.asyncio
    async def test_regression_results_have_material_provenance(self, runner, sample_material):
        results = await runner.run_regression(
            description="provenance test",
            material=sample_material,
            num_runs=2,
            duration_seconds=5.0,
        )
        for result in results:
            assert result.material_provenance is not None
            assert result.material_provenance.get("source_count", 0) > 0

    @pytest.mark.asyncio
    async def test_save_results_json(self, runner, sample_material, tmp_path):
        results = await runner.run_regression(
            description="save test",
            material=sample_material,
            num_runs=2,
            duration_seconds=5.0,
        )
        output_file = tmp_path / "regression_results.json"
        runner.save_results(results, str(output_file))

        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert len(data["runs"]) == 2
        assert data["summary"]["total_runs"] == 2
        assert data["summary"]["successful_runs"] == 2

    @pytest.mark.asyncio
    async def test_run_without_material(self, runner):
        result = await runner.run_single(
            description="no material test",
            duration_seconds=5.0,
            seed=1,
        )
        assert result.success is True
        assert result.material_provenance is None


class TestRegressionResult:
    def test_result_fields(self):
        result = RegressionResult(
            run_number=1,
            success=True,
            audio_path="/tmp/test.wav",
            duration_seconds=5.0,
            sample_rate=48000,
            format="wav",
            seed=42,
            elapsed_seconds=12.5,
            description="test",
            material_provenance={"source_count": 2},
            validation_errors=[],
        )
        assert result.success is True
        assert result.run_number == 1

    def test_result_to_dict(self):
        result = RegressionResult(
            run_number=1,
            success=True,
            audio_path="/tmp/test.wav",
            duration_seconds=5.0,
            sample_rate=48000,
            format="wav",
            seed=42,
            elapsed_seconds=10.0,
            description="test",
        )
        d = result.model_dump()
        assert d["run_number"] == 1
        assert d["success"] is True
