"""Tests for the ace-music CLI."""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from ace_music import cli


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
