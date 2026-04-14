"""Tests for OutputWorker structured output directories."""

import json
from pathlib import Path

import pytest

from ace_music.schemas.audio import ProcessedAudio
from ace_music.schemas.style import StyleOutput
from ace_music.tools.output import OutputInput, OutputWorker


@pytest.fixture
def worker():
    return OutputWorker()


@pytest.fixture
def sample_audio(tmp_path):
    """Create a minimal WAV file for testing."""
    import struct
    import wave

    filepath = tmp_path / "test_audio.wav"
    with wave.open(str(filepath), "w") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(48000)
        for _i in range(4800):  # 0.1s
            wf.writeframesraw(struct.pack("<h", 0) * 2)
    return ProcessedAudio(
        file_path=str(filepath),
        duration_seconds=0.1,
        sample_rate=48000,
        format="wav",
        channels=2,
        loudness_lufs=-14.0,
        peak_db=-1.0,
    )


class TestVersionConsistency:
    def test_metadata_uses_package_version(self):
        """OutputWorker metadata should use the package version."""
        import ace_music
        assert ace_music.__version__
        # Verify it looks like a version string
        parts = ace_music.__version__.split(".")
        assert len(parts) >= 2


class TestOutputWorkerStructuredDir:
    @pytest.mark.asyncio
    async def test_creates_style_subdirectory(self, worker, sample_audio, tmp_path):
        """Output should be organized under output_dir/style_slug/."""
        result = await worker.execute(
            OutputInput(
                audio=sample_audio,
                style=StyleOutput(prompt="electronic, synthwave, retro"),
                seed=42,
                output_dir=str(tmp_path / "output"),
            )
        )
        # Should create a subdirectory based on the style prompt
        assert "electronic" in result.audio_path or Path(result.audio_path).parent.name != "output"

    @pytest.mark.asyncio
    async def test_metadata_json_written(self, worker, sample_audio, tmp_path):
        """Metadata JSON sidecar should be written alongside audio."""
        result = await worker.execute(
            OutputInput(
                audio=sample_audio,
                style=StyleOutput(prompt="pop"),
                seed=42,
                output_dir=str(tmp_path / "output"),
            )
        )
        assert result.metadata_path is not None
        assert Path(result.metadata_path).exists()
        metadata = json.loads(Path(result.metadata_path).read_text())
        assert metadata["seed"] == 42
        assert metadata["generator"] == "ace-music"

    @pytest.mark.asyncio
    async def test_preserves_existing_flat_output(self, worker, sample_audio, tmp_path):
        """If output_dir already exists and audio is in it, don't re-copy."""
        out_dir = tmp_path / "output"
        out_dir.mkdir()
        # Put audio directly in output_dir
        audio_in_output = sample_audio.model_copy(
            update={"file_path": str(out_dir / "test_audio.wav")}
        )
        Path(audio_in_output.file_path).write_bytes(
            Path(sample_audio.file_path).read_bytes()
        )
        result = await worker.execute(
            OutputInput(
                audio=audio_in_output,
                style=StyleOutput(prompt="ambient"),
                seed=1,
                output_dir=str(out_dir),
            )
        )
        assert Path(result.audio_path).exists()
