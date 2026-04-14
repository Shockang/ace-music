"""ACE-Step model generator wrapper.

Encapsulates ACE-Step pipeline invocation with:
- Singleton model loading (load once, generate many)
- Async execution with progress callbacks
- Seed management for reproducibility
- Mock mode for testing without GPU
"""

import logging
import random
import time
from pathlib import Path

from pydantic import BaseModel, Field

from ace_music.schemas.audio import AudioOutput
from ace_music.schemas.lyrics import LyricsOutput
from ace_music.schemas.style import StyleOutput
from ace_music.tools.base import MusicTool

logger = logging.getLogger(__name__)


class GenerationInput(BaseModel):
    """Input for the ACE-Step generator."""

    lyrics: LyricsOutput = Field(description="Structured lyrics from LyricsPlanner")
    style: StyleOutput = Field(description="Style parameters from StylePlanner")
    audio_duration: float = Field(default=60.0, ge=5.0, le=240.0)
    seed: int | None = Field(default=None, description="Random seed for reproducibility")
    batch_size: int = Field(default=1, ge=1, le=4)
    output_dir: str = Field(default="./output")
    format: str = Field(default="wav")


class GeneratorConfig(BaseModel):
    """Configuration for ACE-Step model loading."""

    checkpoint_dir: str | None = Field(
        default=None, description="Model checkpoint path (None = HuggingFace cache)"
    )
    device_id: int = Field(default=0)
    dtype: str = Field(default="bfloat16")
    torch_compile: bool = False
    cpu_offload: bool = False
    overlapped_decode: bool = False
    mock_mode: bool = Field(
        default=False, description="Use mock generator (no GPU required)"
    )


class ACEStepGenerator(MusicTool[GenerationInput, AudioOutput]):
    """ACE-Step 1.5 model generation wrapper.

    In mock_mode, generates silence WAV files for testing.
    In production mode, calls ACEStepPipeline.__call__().
    """

    def __init__(self, config: GeneratorConfig | None = None) -> None:
        self._config = config or GeneratorConfig()
        self._pipeline = None

    @property
    def name(self) -> str:
        return "generator"

    @property
    def description(self) -> str:
        return "Generate music using ACE-Step 1.5 model"

    @property
    def input_schema(self) -> type[GenerationInput]:
        return GenerationInput

    @property
    def output_schema(self) -> type[AudioOutput]:
        return AudioOutput

    @property
    def is_read_only(self) -> bool:
        return False

    @property
    def is_concurrency_safe(self) -> bool:
        return False

    def _ensure_pipeline(self):
        """Load the ACE-Step pipeline (singleton pattern)."""
        if self._pipeline is not None:
            return

        if self._config.mock_mode:
            logger.info("Generator running in mock mode (no model loaded)")
            self._pipeline = "mock"
            return

        # Lazy import to avoid requiring torch at module level
        try:
            from acestep.pipeline_ace_step import ACEStepPipeline

            self._pipeline = ACEStepPipeline(
                checkpoint_dir=self._config.checkpoint_dir,
                device_id=self._config.device_id,
                dtype=self._config.dtype,
                torch_compile=self._config.torch_compile,
                cpu_offload=self._config.cpu_offload,
                overlapped_decode=self._config.overlapped_decode,
            )
            logger.info("ACE-Step pipeline loaded successfully")
        except ImportError:
            logger.warning("ACE-Step not installed, falling back to mock mode")
            self._pipeline = "mock"

    def _mock_generate(self, input_data: GenerationInput) -> AudioOutput:
        """Generate a mock WAV file for testing."""
        import struct
        import wave

        output_dir = Path(input_data.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        seed = input_data.seed or random.randint(0, 2**32 - 1)
        filename = f"mock_{seed}_{int(time.time())}.wav"
        filepath = output_dir / filename

        sample_rate = 48000
        num_channels = 2
        num_samples = int(sample_rate * input_data.audio_duration)

        # Generate simple sine wave as mock audio
        with wave.open(str(filepath), "w") as wf:
            wf.setnchannels(num_channels)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(sample_rate)
            for i in range(num_samples):
                value = int(32767 * 0.1 * (i % 1000) / 1000)  # quiet sawtooth
                wf.writeframesraw(struct.pack("<h", value) * num_channels)

        return AudioOutput(
            file_path=str(filepath),
            duration_seconds=input_data.audio_duration,
            sample_rate=sample_rate,
            format="wav",
            channels=num_channels,
        )

    async def execute(self, input_data: GenerationInput) -> AudioOutput:
        self._ensure_pipeline()

        seed = input_data.seed if input_data.seed is not None else random.randint(0, 2**32 - 1)

        if self._pipeline == "mock":
            return self._mock_generate(input_data)

        # Production: call ACEStepPipeline
        output_dir = Path(input_data.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        result = self._pipeline(
            audio_duration=input_data.audio_duration,
            prompt=input_data.style.prompt,
            lyrics=input_data.lyrics.to_ace_step_format(),
            infer_step=input_data.style.infer_step,
            guidance_scale=input_data.style.guidance_scale,
            scheduler_type=input_data.style.scheduler_type,
            cfg_type=input_data.style.cfg_type,
            omega_scale=input_data.style.omega_scale,
            manual_seeds=[seed],
            batch_size=input_data.batch_size,
            save_path=str(output_dir),
            format=input_data.format,
            guidance_interval=input_data.style.guidance_interval,
            guidance_interval_decay=input_data.style.guidance_interval_decay,
            min_guidance_scale=input_data.style.min_guidance_scale,
            use_erg_tag=input_data.style.use_erg_tag,
            use_erg_lyric=input_data.style.use_erg_lyric,
            use_erg_diffusion=input_data.style.use_erg_diffusion,
        )

        # Pipeline returns (file_paths, params_dict)
        file_paths = result[0] if isinstance(result, tuple) else result
        audio_path = file_paths[0] if isinstance(file_paths, list) else str(file_paths)

        # Get actual duration from file
        duration = input_data.audio_duration
        try:
            import soundfile as sf

            info = sf.info(audio_path)
            duration = info.duration
        except Exception:
            pass

        return AudioOutput(
            file_path=audio_path,
            duration_seconds=duration,
            sample_rate=48000,
            format=input_data.format,
            channels=2,
        )
