"""PostProcessor: audio normalization, format conversion, trimming."""

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ace_music.schemas.audio import AudioOutput, ProcessedAudio
from ace_music.schemas.audio_contract import AudioSceneContract
from ace_music.tools.base import MusicTool

logger = logging.getLogger(__name__)


class PostProcessInput(BaseModel):
    """Input for post-processing."""

    audio: AudioOutput
    target_format: str = Field(default="wav")
    normalize_loudness: bool = True
    target_lufs: float = Field(default=-14.0, description="EBU R128 target loudness")
    trim_silence: bool = True
    silence_threshold_db: float = Field(default=-60.0)
    output_dir: str | None = Field(default=None)
    audio_contract: AudioSceneContract | None = Field(
        default=None, description="Scene contract for mix parameters (overrides defaults)"
    )


class PostProcessor(MusicTool[PostProcessInput, ProcessedAudio]):
    """Post-process generated audio: format conversion, loudness normalization, trimming."""

    @property
    def name(self) -> str:
        return "post_processor"

    @property
    def description(self) -> str:
        return "Normalize loudness, convert format, and trim silence from generated audio"

    @property
    def input_schema(self) -> type[PostProcessInput]:
        return PostProcessInput

    @property
    def output_schema(self) -> type[ProcessedAudio]:
        return ProcessedAudio

    @property
    def is_read_only(self) -> bool:
        return False

    def _apply_contract_overrides(self, input_data: PostProcessInput) -> PostProcessInput:
        """Override post-process parameters from audio contract if present."""
        if not input_data.audio_contract:
            return input_data
        contract = input_data.audio_contract
        updates: dict[str, Any] = {}
        if contract.mix:
            updates["target_lufs"] = contract.mix.target_lufs
        if not updates:
            return input_data
        return input_data.model_copy(update=updates)

    def _build_ducking_envelope(
        self,
        sample_count: int,
        sr: int,
        contract: AudioSceneContract,
    ) -> Any:
        """Build a vectorized ducking envelope for TTS windows."""
        import numpy as np

        envelope = np.ones(sample_count, dtype=np.float32)
        duck_gain = 10 ** (-contract.mix.ducking_db / 20.0)
        fade_samples = max(1, int(sr * 0.05))

        merged_ranges: list[tuple[int, int]] = []
        for segment in contract.tts_segments:
            start = min(sample_count, int(segment.start_seconds * sr))
            end = min(sample_count, int(segment.end_seconds * sr))
            if start >= end:
                continue
            if not merged_ranges:
                merged_ranges.append((start, end))
                continue

            previous_start, previous_end = merged_ranges[-1]
            if start <= previous_end:
                merged_ranges[-1] = (previous_start, max(previous_end, end))
            else:
                merged_ranges.append((start, end))

        for start, end in merged_ranges:
            entry_end = min(sample_count, start + fade_samples)
            if start < entry_end:
                entry_ramp = np.linspace(1.0, duck_gain, entry_end - start, endpoint=False)
                envelope[start:entry_end] = np.minimum(envelope[start:entry_end], entry_ramp)

            if entry_end < end:
                envelope[entry_end:end] = np.minimum(envelope[entry_end:end], duck_gain)

            exit_end = min(sample_count, end + fade_samples)
            exit_start_value = duck_gain
            if end <= entry_end:
                progress_at_end = (end - start) / fade_samples
                exit_start_value = 1.0 - ((1.0 - duck_gain) * progress_at_end)

            if end < exit_end:
                exit_ramp = np.linspace(
                    exit_start_value,
                    1.0,
                    exit_end - end,
                    endpoint=False,
                )
                envelope[end:exit_end] = np.minimum(envelope[end:exit_end], exit_ramp)

        return envelope

    def _apply_ducking(self, data: Any, sr: int, contract: AudioSceneContract) -> Any:
        """Apply dynamic or static ducking based on the contract."""
        mix = contract.mix
        layers = contract.layers
        if not layers or not layers.tts_present or mix.sidechain_source != "tts":
            return data

        if contract.tts_segments:
            envelope = self._build_ducking_envelope(len(data), sr, contract)
            if data.ndim == 2:
                return data * envelope[:, None]
            return data * envelope

        ducking_gain = 10 ** (-mix.ducking_db / 20.0)
        return data * ducking_gain

    def _process_with_soundfile(self, input_data: PostProcessInput) -> ProcessedAudio:
        """Process audio using soundfile + numpy (with optional LUFS normalization)."""
        import numpy as np
        import soundfile as sf

        data, sr = sf.read(input_data.audio.file_path)

        # Trim silence
        if input_data.trim_silence and len(data) > 0:
            threshold = 10 ** (input_data.silence_threshold_db / 20.0)
            energy = np.max(np.abs(data), axis=1) if data.ndim == 2 else np.abs(data)

            above = np.where(energy > threshold)[0]
            if len(above) > 0:
                start = above[0]
                end = above[-1] + 1
                data = data[start:end]
            else:
                logger.info("No non-silent audio found, keeping original")

        peak = np.max(np.abs(data)) if len(data) > 0 else 1.0
        peak_db = 20.0 * np.log10(peak) if peak > 0 else -float("inf")
        loudness_lufs = None

        if input_data.normalize_loudness and peak > 0:
            # Attempt LUFS-based normalization with pyloudnorm
            try:
                import pyloudnorm as pyln

                meter = pyln.Meter(sr)
                current_lufs = meter.integrated_loudness(data)
                gain_db = input_data.target_lufs - current_lufs
                gain_linear = 10 ** (gain_db / 20.0)

                data = data * gain_linear
                new_peak = np.max(np.abs(data))

                # Peak limit to prevent clipping
                if new_peak > 0.999:
                    limit_gain = 0.999 / new_peak
                    data = data * limit_gain
                    peak_db = 20.0 * np.log10(0.999)
                    logger.info("Peak limited after LUFS gain")
                else:
                    peak_db = 20.0 * np.log10(new_peak) if new_peak > 0 else -float("inf")

                logger.info(
                    "LUFS normalized: %.1f -> %.1f LUFS (gain %.1f dB)",
                    current_lufs,
                    input_data.target_lufs,
                    gain_db,
                )
            except ImportError:
                # Fallback to peak normalization
                target_peak = 10 ** (-1.0 / 20.0)
                data = data * (target_peak / peak)
                peak_db = -1.0

        if input_data.audio_contract and input_data.audio_contract.mix:
            mix = input_data.audio_contract.mix
            layers = input_data.audio_contract.layers
            if layers and layers.tts_present and mix.sidechain_source == "tts":
                data = self._apply_ducking(data, sr, input_data.audio_contract)
                peak = np.max(np.abs(data)) if len(data) > 0 else 0.0
                peak_db = 20.0 * np.log10(peak) if peak > 0 else -float("inf")
                if input_data.audio_contract.tts_segments:
                    logger.info(
                        "Dynamic ducking applied to %d TTS segments",
                        len(input_data.audio_contract.tts_segments),
                    )
                else:
                    logger.info(
                        "Static ducking applied: -%.1f dB (TTS present, sidechain=%s)",
                        mix.ducking_db,
                        mix.sidechain_source,
                    )

        # Determine output path
        out_dir = Path(input_data.output_dir or Path(input_data.audio.file_path).parent)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = Path(input_data.audio.file_path).stem + "_processed"
        out_path = out_dir / f"{stem}.{input_data.target_format}"

        sf.write(str(out_path), data, sr)

        duration = len(data) / sr

        # Re-measure LUFS if pyloudnorm is available so metadata reflects final post-ducking audio.
        try:
            import pyloudnorm as pyln

            meter = pyln.Meter(sr)
            loudness_lufs = meter.integrated_loudness(data)
        except ImportError:
            pass

        return ProcessedAudio(
            file_path=str(out_path),
            duration_seconds=duration,
            sample_rate=sr,
            format=input_data.target_format,
            channels=data.ndim if data.ndim <= 2 else 1,
            loudness_lufs=loudness_lufs,
            peak_db=peak_db,
        )

    def _process_mock(self, input_data: PostProcessInput) -> ProcessedAudio:
        """Mock processing: just copy metadata without real audio processing."""
        out_dir = Path(input_data.output_dir or Path(input_data.audio.file_path).parent)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = Path(input_data.audio.file_path).stem + "_processed"
        out_path = out_dir / f"{stem}.{input_data.target_format}"

        # In mock mode, just reference the same file
        import shutil

        if Path(input_data.audio.file_path).exists():
            shutil.copy2(input_data.audio.file_path, str(out_path))
        else:
            # Create a dummy file
            out_path.write_bytes(b"")

        return ProcessedAudio(
            file_path=str(out_path),
            duration_seconds=input_data.audio.duration_seconds,
            sample_rate=input_data.audio.sample_rate,
            format=input_data.target_format,
            channels=input_data.audio.channels,
            loudness_lufs=input_data.target_lufs if input_data.normalize_loudness else None,
            peak_db=-1.0 if input_data.normalize_loudness else None,
        )

    async def execute(self, input_data: PostProcessInput) -> ProcessedAudio:
        effective_input = self._apply_contract_overrides(input_data)
        try:
            return self._process_with_soundfile(effective_input)
        except ImportError:
            logger.info("soundfile/numpy not available, using mock post-processing")
            return self._process_mock(effective_input)
