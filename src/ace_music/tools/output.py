"""OutputWorker: finalize output with metadata JSON."""

import json
import logging
import re
import time
from pathlib import Path

from pydantic import BaseModel, Field

from ace_music.schemas.audio import ProcessedAudio
from ace_music.schemas.style import StyleOutput
from ace_music.tools.base import MusicTool

logger = logging.getLogger(__name__)


class OutputInput(BaseModel):
    """Input for the output worker."""

    audio: ProcessedAudio
    style: StyleOutput
    seed: int | None = None
    lyrics_text: str = ""
    description: str = ""
    output_dir: str = "./output"


class OutputResult(BaseModel):
    """Final output with metadata file."""

    audio_path: str
    metadata_path: str | None = None
    duration_seconds: float
    format: str
    sample_rate: int
    metadata: dict = Field(default_factory=dict)


class OutputWorker(MusicTool[OutputInput, OutputResult]):
    """Write final audio file and metadata JSON."""

    @property
    def name(self) -> str:
        return "output"

    @property
    def description(self) -> str:
        return "Write final audio file with metadata JSON"

    @property
    def input_schema(self) -> type[OutputInput]:
        return OutputInput

    @property
    def output_schema(self) -> type[OutputResult]:
        return OutputResult

    @property
    def is_read_only(self) -> bool:
        return False

    def _slugify(self, text: str) -> str:
        """Convert text to a filesystem-safe slug."""
        text = text.lower().strip()
        # Take first tag if comma-separated
        text = text.split(",")[0].strip() if "," in text else text
        text = re.sub(r"[^\w\s-]", "", text)
        text = re.sub(r"[\s_]+", "_", text)
        return text[:50].strip("_") or "untitled"

    async def execute(self, input_data: OutputInput) -> OutputResult:
        base_dir = Path(input_data.output_dir)
        style_slug = self._slugify(input_data.style.prompt)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        out_dir = base_dir / style_slug / timestamp
        out_dir.mkdir(parents=True, exist_ok=True)

        # Copy audio file into structured directory
        src = Path(input_data.audio.file_path)
        dest = out_dir / src.name
        if src.resolve() != dest.resolve():
            import shutil
            shutil.copy2(str(src), str(dest))
        final_path = str(dest)

        # Build metadata
        metadata = {
            "generator": "ace-music",
            "version": "0.1.0",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "description": input_data.description,
            "style": {
                "prompt": input_data.style.prompt,
                "guidance_scale": input_data.style.guidance_scale,
                "scheduler_type": input_data.style.scheduler_type,
                "infer_step": input_data.style.infer_step,
            },
            "audio": {
                "duration_seconds": input_data.audio.duration_seconds,
                "format": input_data.audio.format,
                "sample_rate": input_data.audio.sample_rate,
                "loudness_lufs": input_data.audio.loudness_lufs,
                "peak_db": input_data.audio.peak_db,
            },
            "seed": input_data.seed,
            "lyrics": input_data.lyrics_text if input_data.lyrics_text else None,
        }

        # Write metadata JSON
        meta_file = out_dir / f"{src.stem}_metadata.json"
        meta_file.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))

        logger.info("Output written: %s", final_path)

        return OutputResult(
            audio_path=final_path,
            metadata_path=str(meta_file),
            duration_seconds=input_data.audio.duration_seconds,
            format=input_data.audio.format,
            sample_rate=input_data.audio.sample_rate,
            metadata=metadata,
        )
