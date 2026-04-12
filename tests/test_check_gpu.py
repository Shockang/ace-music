"""Tests for scripts/check_windows_gpu.py — GPU status checker.

Tests mock SSH subprocess calls to verify parsing and logic.
"""
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add scripts/ to path so we can import check_windows_gpu as a module
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from check_windows_gpu import GPUStatus, check_gpu, parse_nvidia_smi


class TestParseNvidiaSmi:
    """Test nvidia-smi CSV output parsing."""

    def test_parse_rtx_3090ti_idle(self):
        output = "NVIDIA GeForce RTX 3090 Ti, 24576, 2048, 22528, 2"
        status = parse_nvidia_smi(output)
        assert status.name == "NVIDIA GeForce RTX 3090 Ti"
        assert status.vram_total_mb == 24576
        assert status.vram_used_mb == 2048
        assert status.vram_free_mb == 22528
        assert status.utilization_pct == 2

    def test_parse_rtx_3090ti_busy(self):
        output = "NVIDIA GeForce RTX 3090 Ti, 24576, 22528, 2048, 97"
        status = parse_nvidia_smi(output)
        assert status.vram_used_mb == 22528
        assert status.vram_free_mb == 2048
        assert status.utilization_pct == 97

    def test_parse_raises_on_bad_format(self):
        with pytest.raises(ValueError, match="Unexpected nvidia-smi output"):
            parse_nvidia_smi("not enough fields")

    def test_parse_raises_on_empty(self):
        with pytest.raises(ValueError):
            parse_nvidia_smi("")


class TestGPUStatus:
    """Test GPUStatus data class and derived properties."""

    def test_vram_conversions(self):
        status = GPUStatus(
            name="RTX 3090 Ti",
            vram_total_mb=24576,
            vram_used_mb=8192,
            vram_free_mb=16384,
            utilization_pct=15,
        )
        assert status.vram_used_gb == pytest.approx(8.0)
        assert status.vram_free_gb == pytest.approx(16.0)

    def test_can_generate_when_under_threshold(self):
        status = GPUStatus(
            name="RTX 3090 Ti",
            vram_total_mb=24576,
            vram_used_mb=8192,
            vram_free_mb=16384,
            utilization_pct=15,
        )
        assert status.can_generate is True

    def test_cannot_generate_when_over_threshold(self):
        status = GPUStatus(
            name="RTX 3090 Ti",
            vram_total_mb=24576,
            vram_used_mb=22528,
            vram_free_mb=2048,
            utilization_pct=95,
        )
        assert status.can_generate is False

    def test_can_generate_at_boundary(self):
        """Exactly 20 GB used should still allow generation (< not <=)."""
        status = GPUStatus(
            name="RTX 3090 Ti",
            vram_total_mb=24576,
            vram_used_mb=20480,  # exactly 20 GB
            vram_free_mb=4096,
            utilization_pct=50,
        )
        assert status.can_generate is True


class TestCheckGpu:
    """Test the SSH-based GPU check with mocked subprocess."""

    @patch("check_windows_gpu.subprocess.run")
    def test_check_gpu_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="NVIDIA GeForce RTX 3090 Ti, 24576, 4096, 20480, 5\n",
            stderr="",
        )
        status = check_gpu()
        assert isinstance(status, GPUStatus)
        assert status.name == "NVIDIA GeForce RTX 3090 Ti"
        assert status.vram_used_mb == 4096
        assert status.can_generate is True

    @patch("check_windows_gpu.subprocess.run")
    def test_check_gpu_ssh_failure(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=255,
            stdout="",
            stderr="Connection refused",
        )
        with pytest.raises(RuntimeError, match="SSH command failed"):
            check_gpu()

    @patch("check_windows_gpu.subprocess.run")
    def test_check_gpu_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ssh", timeout=30)
        with pytest.raises(subprocess.TimeoutExpired):
            check_gpu()

    @patch("check_windows_gpu.subprocess.run")
    def test_check_gpu_uses_correct_ssh_args(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="RTX 3090 Ti, 24576, 4096, 20480, 5\n",
            stderr="",
        )
        check_gpu()

        call_args = mock_run.call_args
        cmd = call_args[0][0] if call_args[0] else call_args[1].get("args", [])
        assert cmd[0] == "ssh"
        assert "-i" in cmd
        assert "shockang@100.69.202.122" in cmd
        assert "nvidia-smi" in " ".join(cmd)
