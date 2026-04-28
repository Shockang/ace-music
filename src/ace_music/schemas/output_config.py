"""Output configuration for music generation pipeline."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class OutputConfig(BaseModel):
    """Configuration for output file management.

    Controls how output files are named and organized:
    - "nested": {base_dir}/{style_slug}/{timestamp}/audio.wav (default, development)
    - "flat": {base_dir}/{slug}_{date}_{seq}.wav (production-friendly flat layout)
    """

    base_dir: str = Field(
        default="./output",
        description="Base output directory for generated audio files",
    )
    naming: Literal["nested", "flat"] = Field(
        default="nested",
        description=(
            "File naming strategy: 'nested' creates subdirectories, "
            "'flat' uses descriptive filenames"
        ),
    )
    filename_template: str = Field(
        default="{slug}_{date}_{seq:03d}",
        description="Filename template for flat naming mode. Available vars: slug, date, seq",
    )
    create_metadata: bool = Field(
        default=True,
        description="Write sidecar metadata JSON alongside audio files",
    )

    @classmethod
    def for_flat_output(cls, base: str) -> OutputConfig:
        """Create config targeting a caller-provided flat output directory."""
        return cls(base_dir=base, naming="flat")
