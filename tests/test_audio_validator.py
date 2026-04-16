"""Tests for audio validation."""
import struct
import wave

import pytest

from ace_music.tools.audio_validator import AudioValidator, ValidationResult


@pytest.fixture
def validator():
    return AudioValidator()


@pytest.fixture
def valid_wav(tmp_path):
    """Create a valid 48kHz stereo 16-bit WAV."""
    filepath = tmp_path / "valid.wav"
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
    return str(filepath)


@pytest.fixture
def short_wav(tmp_path):
    """Create a very short WAV (< 1 second)."""
    filepath = tmp_path / "short.wav"
    with wave.open(str(filepath), "w") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(48000)
        for _ in range(480):  # 0.01s
            wf.writeframesraw(struct.pack("<h", 1000) * 2)
    return str(filepath)


class TestAudioValidator:
    def test_valid_wav_passes(self, validator, valid_wav):
        result = validator.validate(valid_wav)
        assert result.is_valid is True
        assert result.format == "wav"
        assert result.sample_rate == 48000
        assert result.channels == 2
        assert result.duration_seconds >= 0.9
        assert result.errors == []

    def test_short_wav_flagged(self, validator, short_wav):
        result = validator.validate(short_wav, min_duration_seconds=1.0)
        assert result.is_valid is False
        assert any("duration" in e.lower() for e in result.errors)

    def test_wrong_sample_rate_flagged(self, validator, tmp_path):
        filepath = tmp_path / "low_sr.wav"
        with wave.open(str(filepath), "w") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(22050)
            for _ in range(22050):
                wf.writeframesraw(struct.pack("<h", 1000) * 2)
        result = validator.validate(str(filepath), expected_sample_rate=48000)
        assert result.is_valid is False
        assert any("sample rate" in e.lower() for e in result.errors)

    def test_nonexistent_file_fails(self, validator):
        result = validator.validate("/nonexistent/file.wav")
        assert result.is_valid is False
        assert any("not found" in e.lower() for e in result.errors)

    def test_not_a_wav_fails(self, validator, tmp_path):
        filepath = tmp_path / "fake.wav"
        filepath.write_text("this is not a wav file")
        result = validator.validate(str(filepath))
        assert result.is_valid is False

    def test_validation_result_dict(self, validator, valid_wav):
        result = validator.validate(valid_wav)
        d = result.to_dict()
        assert d["is_valid"] is True
        assert "file_path" in d
        assert "duration_seconds" in d


class TestValidationResult:
    def test_valid_result(self):
        result = ValidationResult(file_path="/tmp/test.wav", is_valid=True, format="wav", sample_rate=48000, channels=2, duration_seconds=30.0, errors=[])
        assert result.is_valid is True

    def test_invalid_result_with_errors(self):
        result = ValidationResult(file_path="/tmp/bad.wav", is_valid=False, format="wav", sample_rate=22050, channels=2, duration_seconds=0.5, errors=["Sample rate 22050 != expected 48000", "Duration 0.5s < minimum 5.0s"])
        assert len(result.errors) == 2
