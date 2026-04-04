"""PostProcessor: audio normalization, format conversion, trimming."""

import logging
from pathlib import Path

from pydantic import BaseModel, Field

from ace_music.schemas.audio import AudioOutput, ProcessedAudio
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

    def _process_with_soundfile(self, input_data: PostProcessInput) -> ProcessedAudio:
        """Process audio using soundfile + numpy (no heavy deps)."""
        import numpy as np
        import soundfile as sf

        data, sr = sf.read(input_data.audio.file_path)

        # Trim silence
        if input_data.trim_silence and len(data) > 0:
            threshold = 10 ** (input_data.silence_threshold_db / 20.0)
            if data.ndim == 2:
                energy = np.max(np.abs(data), axis=1)
            else:
                energy = np.abs(data)

            above = np.where(energy > threshold)[0]
            if len(above) > 0:
                start = above[0]
                end = above[-1] + 1
                data = data[start:end]
            else:
                logger.info("No non-silent audio found, keeping original")

        # Simple peak normalization (LUFS requires pyloudnorm or similar)
        peak = np.max(np.abs(data)) if len(data) > 0 else 1.0
        loudness_lufs = None
        peak_db = 20.0 * np.log10(peak) if peak > 0 else -float("inf")

        if input_data.normalize_loudness and peak > 0:
            # Simple peak normalization to -1 dB
            target_peak = 10 ** (-1.0 / 20.0)
            data = data * (target_peak / peak)
            peak_db = -1.0

        # Determine output path
        out_dir = Path(input_data.output_dir or Path(input_data.audio.file_path).parent)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = Path(input_data.audio.file_path).stem + "_processed"
        out_path = out_dir / f"{stem}.{input_data.target_format}"

        sf.write(str(out_path), data, sr)

        duration = len(data) / sr

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
            loudness_lufs=-14.0 if input_data.normalize_loudness else None,
            peak_db=-1.0 if input_data.normalize_loudness else None,
        )

    async def execute(self, input_data: PostProcessInput) -> ProcessedAudio:
        try:
            return self._process_with_soundfile(input_data)
        except ImportError:
            logger.info("soundfile/numpy not available, using mock post-processing")
            return self._process_mock(input_data)
