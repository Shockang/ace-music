"""Tests for PostProcessor."""

import os
import sys
import types
from pathlib import Path

import pytest

from ace_music.schemas.audio import AudioOutput, ProcessedAudio
from ace_music.schemas.audio_contract import AudioSceneContract, TTSSegment
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

    @pytest.mark.asyncio
    async def test_dynamic_ducking_only_hits_tts_ranges(self, tmp_path):
        np = pytest.importorskip("numpy")
        sf = pytest.importorskip("soundfile")

        filepath = tmp_path / "dynamic.wav"
        sample_rate = 48000
        duration = 5.0
        data = np.full((int(sample_rate * duration), 2), 0.5, dtype=np.float32)
        sf.write(filepath, data, sample_rate)

        audio = AudioOutput(
            file_path=str(filepath),
            duration_seconds=duration,
            sample_rate=sample_rate,
            format="wav",
            channels=2,
        )
        contract = AudioSceneContract(
            scene_id="scene_dynamic",
            duration_seconds=duration,
            mood="calm",
            tts_segments=[TTSSegment(start_seconds=0.2, end_seconds=0.4)],
        )

        processor = PostProcessor()
        result = await processor.execute(
            PostProcessInput(
                audio=audio,
                target_format="wav",
                normalize_loudness=False,
                trim_silence=False,
                output_dir=str(tmp_path / "output"),
                audio_contract=contract,
            )
        )

        processed, _ = sf.read(result.file_path)
        pre_rms = np.sqrt(np.mean(processed[: int(0.15 * sample_rate)] ** 2))
        ducked_rms = np.sqrt(
            np.mean(processed[int(0.25 * sample_rate) : int(0.35 * sample_rate)] ** 2)
        )
        post_rms = np.sqrt(np.mean(processed[int(0.6 * sample_rate) :] ** 2))

        assert ducked_rms < pre_rms * 0.7
        assert post_rms == pytest.approx(pre_rms, rel=0.05)

    @pytest.mark.asyncio
    async def test_empty_tts_segments_falls_back_to_static_ducking(self, tmp_path):
        np = pytest.importorskip("numpy")
        sf = pytest.importorskip("soundfile")

        filepath = tmp_path / "static.wav"
        sample_rate = 48000
        duration = 5.0
        data = np.full((int(sample_rate * duration), 2), 0.5, dtype=np.float32)
        sf.write(filepath, data, sample_rate)

        audio = AudioOutput(
            file_path=str(filepath),
            duration_seconds=duration,
            sample_rate=sample_rate,
            format="wav",
            channels=2,
        )
        contract = AudioSceneContract(
            scene_id="scene_static",
            duration_seconds=duration,
            mood="calm",
        )

        processor = PostProcessor()
        result = await processor.execute(
            PostProcessInput(
                audio=audio,
                target_format="wav",
                normalize_loudness=False,
                trim_silence=False,
                output_dir=str(tmp_path / "output_static"),
                audio_contract=contract,
            )
        )

        processed, _ = sf.read(result.file_path)
        rms = np.sqrt(np.mean(processed**2))
        assert rms < 0.5 * 0.7

    @pytest.mark.asyncio
    async def test_dynamic_ducking_uses_50ms_crossfade(self, tmp_path):
        np = pytest.importorskip("numpy")
        sf = pytest.importorskip("soundfile")

        filepath = tmp_path / "crossfade.wav"
        sample_rate = 48000
        duration = 5.0
        data = np.full((int(sample_rate * duration), 2), 0.5, dtype=np.float32)
        sf.write(filepath, data, sample_rate)

        audio = AudioOutput(
            file_path=str(filepath),
            duration_seconds=duration,
            sample_rate=sample_rate,
            format="wav",
            channels=2,
        )
        contract = AudioSceneContract(
            scene_id="scene_crossfade",
            duration_seconds=duration,
            mood="calm",
            tts_segments=[TTSSegment(start_seconds=0.2, end_seconds=0.4)],
        )

        processor = PostProcessor()
        result = await processor.execute(
            PostProcessInput(
                audio=audio,
                target_format="wav",
                normalize_loudness=False,
                trim_silence=False,
                output_dir=str(tmp_path / "output_xfade"),
                audio_contract=contract,
            )
        )

        processed, _ = sf.read(result.file_path)
        just_before = np.sqrt(
            np.mean(processed[int(0.18 * sample_rate) : int(0.19 * sample_rate)] ** 2)
        )
        ramp_down = np.sqrt(
            np.mean(processed[int(0.205 * sample_rate) : int(0.215 * sample_rate)] ** 2)
        )
        full_duck = np.sqrt(
            np.mean(processed[int(0.3 * sample_rate) : int(0.31 * sample_rate)] ** 2)
        )

        assert just_before > ramp_down > full_duck


class TestDuckingHelpers:
    def test_apply_ducking_only_hits_tts_ranges(self):
        np = pytest.importorskip("numpy")

        processor = PostProcessor()
        sample_rate = 48000
        duration = 5.0
        data = np.full((int(sample_rate * duration), 2), 0.5, dtype=np.float32)
        contract = AudioSceneContract(
            scene_id="scene_dynamic",
            duration_seconds=duration,
            mood="calm",
            tts_segments=[TTSSegment(start_seconds=0.2, end_seconds=0.4)],
        )

        processed = processor._apply_ducking(data.copy(), sample_rate, contract)

        pre_rms = np.sqrt(np.mean(processed[: int(0.15 * sample_rate)] ** 2))
        ducked_rms = np.sqrt(
            np.mean(processed[int(0.25 * sample_rate) : int(0.35 * sample_rate)] ** 2)
        )
        post_rms = np.sqrt(np.mean(processed[int(0.6 * sample_rate) :] ** 2))

        assert ducked_rms < pre_rms * 0.7
        assert post_rms == pytest.approx(pre_rms, rel=0.05)

    def test_apply_ducking_falls_back_to_static_when_tts_segments_empty(self):
        np = pytest.importorskip("numpy")

        processor = PostProcessor()
        sample_rate = 48000
        duration = 5.0
        data = np.full((int(sample_rate * duration), 2), 0.5, dtype=np.float32)
        contract = AudioSceneContract(
            scene_id="scene_static",
            duration_seconds=duration,
            mood="calm",
        )

        processed = processor._apply_ducking(data.copy(), sample_rate, contract)
        rms = np.sqrt(np.mean(processed**2))

        assert rms < 0.5 * 0.7

    def test_apply_ducking_uses_50ms_crossfade(self):
        np = pytest.importorskip("numpy")

        processor = PostProcessor()
        sample_rate = 48000
        duration = 5.0
        data = np.full((int(sample_rate * duration), 2), 0.5, dtype=np.float32)
        contract = AudioSceneContract(
            scene_id="scene_crossfade",
            duration_seconds=duration,
            mood="calm",
            tts_segments=[TTSSegment(start_seconds=0.2, end_seconds=0.4)],
        )

        processed = processor._apply_ducking(data.copy(), sample_rate, contract)
        just_before = np.sqrt(
            np.mean(processed[int(0.18 * sample_rate) : int(0.19 * sample_rate)] ** 2)
        )
        ramp_down = np.sqrt(
            np.mean(processed[int(0.205 * sample_rate) : int(0.215 * sample_rate)] ** 2)
        )
        full_duck = np.sqrt(
            np.mean(processed[int(0.3 * sample_rate) : int(0.31 * sample_rate)] ** 2)
        )
        ramp_up = np.sqrt(
            np.mean(processed[int(0.415 * sample_rate) : int(0.425 * sample_rate)] ** 2)
        )
        after = np.sqrt(np.mean(processed[int(0.46 * sample_rate) : int(0.47 * sample_rate)] ** 2))
        full_recovered = np.sqrt(
            np.mean(processed[int(0.451 * sample_rate) : int(0.459 * sample_rate)] ** 2)
        )

        assert just_before > ramp_down > full_duck
        assert full_duck < ramp_up < after
        assert full_recovered == pytest.approx(after, rel=0.02)

    def test_apply_ducking_keeps_full_50ms_crossfades_for_short_segments(self):
        np = pytest.importorskip("numpy")

        processor = PostProcessor()
        sample_rate = 48000
        duration = 5.0
        data = np.full((int(sample_rate * duration), 2), 0.5, dtype=np.float32)
        contract = AudioSceneContract(
            scene_id="scene_short_crossfade",
            duration_seconds=duration,
            mood="calm",
            tts_segments=[TTSSegment(start_seconds=0.2, end_seconds=0.26)],
        )

        processed = processor._apply_ducking(data.copy(), sample_rate, contract)

        pre = np.sqrt(np.mean(processed[int(0.19 * sample_rate) : int(0.2 * sample_rate)] ** 2))
        inside_start = np.sqrt(
            np.mean(processed[int(0.205 * sample_rate) : int(0.215 * sample_rate)] ** 2)
        )
        inside_end = np.sqrt(
            np.mean(processed[int(0.245 * sample_rate) : int(0.255 * sample_rate)] ** 2)
        )
        recovered = np.sqrt(
            np.mean(processed[int(0.311 * sample_rate) : int(0.319 * sample_rate)] ** 2)
        )
        near_exit = np.sqrt(
            np.mean(processed[int(0.258 * sample_rate) : int(0.268 * sample_rate)] ** 2)
        )

        assert pre > inside_start
        assert inside_end < near_exit < recovered

    def test_apply_ducking_keeps_adjacent_tts_segments_continuously_ducked(self):
        np = pytest.importorskip("numpy")

        processor = PostProcessor()
        sample_rate = 48000
        duration = 5.0
        data = np.full((int(sample_rate * duration), 2), 0.5, dtype=np.float32)
        contract = AudioSceneContract(
            scene_id="scene_adjacent",
            duration_seconds=duration,
            mood="calm",
            tts_segments=[
                TTSSegment(start_seconds=1.0, end_seconds=1.2),
                TTSSegment(start_seconds=1.2, end_seconds=1.4),
            ],
        )

        processed = processor._apply_ducking(data.copy(), sample_rate, contract)
        first_end = np.sqrt(
            np.mean(processed[int(1.15 * sample_rate) : int(1.19 * sample_rate)] ** 2)
        )
        join = np.sqrt(np.mean(processed[int(1.195 * sample_rate) : int(1.205 * sample_rate)] ** 2))
        second_start = np.sqrt(
            np.mean(processed[int(1.21 * sample_rate) : int(1.24 * sample_rate)] ** 2)
        )

        assert join <= first_end * 1.05
        assert second_start <= first_end * 1.05

    def test_apply_ducking_preserves_small_positive_gap_between_tts_segments(self):
        np = pytest.importorskip("numpy")

        processor = PostProcessor()
        sample_rate = 48000
        duration = 5.0
        data = np.full((int(sample_rate * duration), 2), 0.5, dtype=np.float32)
        contract = AudioSceneContract(
            scene_id="scene_small_gap",
            duration_seconds=duration,
            mood="calm",
            tts_segments=[
                TTSSegment(start_seconds=1.0, end_seconds=1.2),
                TTSSegment(start_seconds=1.24, end_seconds=1.44),
            ],
        )

        processed = processor._apply_ducking(data.copy(), sample_rate, contract)
        gap_rms = np.sqrt(
            np.mean(processed[int(1.215 * sample_rate) : int(1.225 * sample_rate)] ** 2)
        )
        ducked_rms = np.sqrt(
            np.mean(processed[int(1.15 * sample_rate) : int(1.19 * sample_rate)] ** 2)
        )

        assert gap_rms > ducked_rms * 1.2


class TestLoudnessMetadata:
    def test_post_ducking_requires_remeasured_loudness(self):
        np = pytest.importorskip("numpy")

        processor = PostProcessor()
        sample_rate = 48000
        duration = 5.0
        data = np.full((int(sample_rate * duration), 2), 0.5, dtype=np.float32)
        contract = AudioSceneContract(
            scene_id="scene_lufs",
            duration_seconds=duration,
            mood="calm",
            tts_segments=[TTSSegment(start_seconds=0.2, end_seconds=0.4)],
        )

        processed = processor._apply_ducking(data.copy(), sample_rate, contract)
        baseline_rms = np.sqrt(np.mean(data**2))
        ducked_rms = np.sqrt(np.mean(processed**2))

        assert ducked_rms < baseline_rms

    def test_process_with_soundfile_remeasures_loudness_after_ducking(self, tmp_path, monkeypatch):
        np = pytest.importorskip("numpy")

        sample_rate = 48000
        duration = 5.0
        data = np.ones((int(sample_rate * duration), 2), dtype=np.float32)
        written: dict[str, np.ndarray] = {}

        def fake_read(_path):
            return data.copy(), sample_rate

        def fake_write(path, processed_data, _sr):
            written["data"] = processed_data
            Path(path).write_bytes(b"")

        class FakeMeter:
            def __init__(self, _sr):
                pass

            def integrated_loudness(self, processed_data):
                return float(np.mean(np.abs(processed_data)))

        monkeypatch.setitem(
            sys.modules,
            "soundfile",
            types.SimpleNamespace(read=fake_read, write=fake_write),
        )
        monkeypatch.setitem(
            sys.modules,
            "pyloudnorm",
            types.SimpleNamespace(Meter=FakeMeter),
        )

        processor = PostProcessor()
        contract = AudioSceneContract(
            scene_id="scene_lufs",
            duration_seconds=duration,
            mood="calm",
        )
        result = processor._process_with_soundfile(
            PostProcessInput(
                audio=AudioOutput(
                    file_path=str(tmp_path / "input.wav"),
                    duration_seconds=duration,
                    sample_rate=sample_rate,
                    format="wav",
                    channels=2,
                ),
                target_format="wav",
                normalize_loudness=True,
                target_lufs=0.0,
                trim_silence=False,
                output_dir=str(tmp_path),
                audio_contract=contract,
            )
        )

        expected_loudness = float(np.mean(np.abs(written["data"])))
        assert result.loudness_lufs == pytest.approx(expected_loudness)


class TestInputValidation:
    def test_validate_post_process_input(self, processor, mock_audio):
        data = {
            "audio": mock_audio.model_dump(),
            "target_format": "mp3",
            "normalize_loudness": True,
        }
        result = processor.validate_input(data)
        assert result.target_format == "mp3"
