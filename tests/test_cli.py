"""Tests for the ace-music CLI."""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from ace_music import cli
from ace_music.schemas.pipeline import PipelineOutput


def test_cli_help_exits_successfully():
    result = subprocess.run(
        [sys.executable, "-m", "ace_music.cli", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert "generate" in result.stdout


def test_cli_mock_generation_writes_summary(tmp_path):
    summary_path = tmp_path / "summary.json"
    output_dir = tmp_path / "out"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ace_music.cli",
            "generate",
            "--mock",
            "--description",
            "short jazz smoke test",
            "--duration",
            "5",
            "--output-dir",
            str(output_dir),
            "--summary-json",
            str(summary_path),
            "--quiet",
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
    assert summary_path.exists()
    summary = json.loads(summary_path.read_text())
    assert summary["status"] == "success"
    assert Path(summary["audio_path"]).exists()
    assert summary["validation"]["is_valid"] is True


def test_cli_generation_timeout_returns_structured_error(tmp_path):
    summary_path = tmp_path / "timeout-summary.json"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ace_music.cli",
            "generate",
            "--mock",
            "--description",
            "timeout smoke test",
            "--duration",
            "5",
            "--output-dir",
            str(tmp_path / "out"),
            "--generation-timeout",
            "10",
            "--total-timeout",
            "0.001",
            "--summary-json",
            str(summary_path),
            "--quiet",
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 40
    summary = json.loads(summary_path.read_text())
    assert summary["status"] == "failed"
    assert summary["category"] == "timeout"


def test_child_context_name_uses_spawn_on_darwin():
    with patch.object(cli.sys, "platform", "darwin"):
        assert cli._child_context_name() == "spawn"


@pytest.mark.asyncio
async def test_run_generate_passes_model_variant_from_cli(tmp_path):
    args = cli.build_parser().parse_args(
        [
            "generate",
            "--description",
            "variant passthrough",
            "--output-dir",
            str(tmp_path),
            "--model-variant",
            "xl-turbo",
        ]
    )
    captured: dict[str, object] = {}
    mock_result = PipelineOutput(
        audio_path=str(tmp_path / "mock.wav"),
        duration_seconds=5.0,
        format="wav",
        sample_rate=48000,
        metadata={"validation": {}},
    )

    async def fake_run(input_data):
        captured["input"] = input_data
        return mock_result

    with patch.object(cli.MusicAgent, "run", new=AsyncMock(side_effect=fake_run)):
        exit_code, summary = await cli._run_generate(args)

    assert exit_code == 0
    assert summary["status"] == "success"
    assert captured["input"].model_variant == "xl-turbo"
    assert captured["input"].audio_contract is None


@pytest.mark.asyncio
async def test_run_generate_builds_audio_contract_only_when_contract_flags_present(tmp_path):
    args = cli.build_parser().parse_args(
        [
            "generate",
            "--description",
            "contract passthrough",
            "--duration",
            "12",
            "--output-dir",
            str(tmp_path),
            "--target-lufs",
            "-17",
            "--tts-present",
            "--crossfade",
            "2.25",
        ]
    )
    captured: dict[str, object] = {}
    mock_result = PipelineOutput(
        audio_path=str(tmp_path / "mock.wav"),
        duration_seconds=12.0,
        format="wav",
        sample_rate=48000,
        metadata={"validation": {}},
    )

    async def fake_run(input_data):
        captured["input"] = input_data
        return mock_result

    with patch.object(cli.MusicAgent, "run", new=AsyncMock(side_effect=fake_run)):
        exit_code, summary = await cli._run_generate(args)

    assert exit_code == 0
    assert summary["status"] == "success"
    contract = captured["input"].audio_contract
    assert contract is not None
    assert contract.duration_seconds == 12.0
    assert contract.mix.target_lufs == -17.0
    assert contract.layers.tts_present is True
    assert contract.transition.crossfade_seconds == 2.25


@pytest.mark.asyncio
async def test_run_generate_defaults_contract_target_lufs_to_minus_14_when_omitted(tmp_path):
    args = cli.build_parser().parse_args(
        [
            "generate",
            "--description",
            "contract default lufs",
            "--duration",
            "12",
            "--output-dir",
            str(tmp_path),
            "--tts-present",
            "--crossfade",
            "2.25",
        ]
    )
    captured: dict[str, object] = {}
    mock_result = PipelineOutput(
        audio_path=str(tmp_path / "mock.wav"),
        duration_seconds=12.0,
        format="wav",
        sample_rate=48000,
        metadata={"validation": {}},
    )

    async def fake_run(input_data):
        captured["input"] = input_data
        return mock_result

    with patch.object(cli.MusicAgent, "run", new=AsyncMock(side_effect=fake_run)):
        exit_code, summary = await cli._run_generate(args)

    assert exit_code == 0
    assert summary["status"] == "success"
    contract = captured["input"].audio_contract
    assert contract is not None
    assert contract.mix.target_lufs == -14.0
    assert contract.layers.tts_present is True
    assert contract.transition.crossfade_seconds == 2.25
