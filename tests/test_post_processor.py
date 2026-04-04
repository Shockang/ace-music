"""Tests for PostProcessor."""

import os

import pytest

from ace_music.schemas.audio import AudioOutput, ProcessedAudio
from ace_music.tools.post_processor import PostProcessInput, PostProcessor


@pytest.fixture
def processor():
    return PostProcessor()


@pytest.fixture
def mock_audio(tmp_path):
    """Create a minimal WAV file for testing."""
    import struct
    import wave

    filepath = tmp_path / "test_audio.wav"
    sample_rate = 48000
    duration = 1.0
    num_samples = int(sample_rate * duration)

    with wave.open(str(filepath), "w") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        for i in range(num_samples):
            val = int(32767 * 0.5 * (i % 100) / 100)
            wf.writeframesraw(struct.pack("<h", val) * 2)

    return AudioOutput(
        file_path=str(filepath),
        duration_seconds=duration,
        sample_rate=sample_rate,
        format="wav",
        channels=2,
    )


class TestPostProcessorProperties:
    def test_name(self, processor):
        assert processor.name == "post_processor"

    def test_is_not_read_only(self, processor):
        assert processor.is_read_only is False


class TestMockProcessing:
    @pytest.mark.asyncio
    async def test_mock_process_no_deps(self, mock_audio, tmp_path):
        """Test with mock fallback when soundfile is not available."""
        processor = PostProcessor()
        inp = PostProcessInput(
            audio=mock_audio,
            target_format="wav",
            output_dir=str(tmp_path / "output"),
        )
        # This will use mock processing if soundfile/numpy aren't available
        result = await processor.execute(inp)
        assert isinstance(result, ProcessedAudio)
        assert result.format == "wav"

    @pytest.mark.asyncio
    async def test_process_with_soundfile(self, mock_audio, tmp_path):
        """Test real processing if soundfile + numpy are available."""
        pytest.importorskip("soundfile")
        pytest.importorskip("numpy")

        processor = PostProcessor()
        inp = PostProcessInput(
            audio=mock_audio,
            target_format="wav",
            normalize_loudness=True,
            output_dir=str(tmp_path / "output"),
        )
        result = await processor.execute(inp)
        assert os.path.exists(result.file_path)
        assert result.peak_db == -1.0  # normalized to -1 dB


class TestInputValidation:
    def test_validate_post_process_input(self, processor, mock_audio):
        data = {
            "audio": mock_audio.model_dump(),
            "target_format": "mp3",
            "normalize_loudness": True,
        }
        result = processor.validate_input(data)
        assert result.target_format == "mp3"
