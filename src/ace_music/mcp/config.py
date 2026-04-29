"""Model and GPU configuration."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    """ACE-Step model loading configuration."""

    checkpoint_dir: str | None = Field(
        default=None,
        description="Path to model checkpoints. None = ~/.cache/ace-step/checkpoints",
    )
    device_id: int = Field(default=0, description="CUDA device ID")
    dtype: str = Field(default="bfloat16", description="Model dtype: bfloat16 or float32")
    torch_compile: bool = Field(
        default=False, description="Enable torch.compile for faster inference"
    )
    cpu_offload: bool = Field(default=False, description="Offload model to CPU to save VRAM (~8GB)")
    overlapped_decode: bool = Field(default=False, description="Overlapped vocoder decoding")
    model_variant: Literal["2b", "xl-base", "xl-sft", "xl-turbo"] = Field(
        default="2b",
        description="ACE-Step model variant to load",
    )
    mock_mode: bool = Field(default=False, description="Mock mode for testing without GPU")

    @property
    def resolved_checkpoint_dir(self) -> str:
        if self.checkpoint_dir:
            return self.checkpoint_dir
        return str(Path.home() / ".cache" / "ace-step" / "checkpoints")


class GPUInfo(BaseModel):
    """GPU hardware information."""

    name: str
    vram_total_gb: float
    vram_available_gb: float
    device_id: int = 0

    @property
    def supports_bf16(self) -> bool:
        """RTX 3090 Ti and newer support bf16."""
        return (
            self.vram_total_gb >= 24.0
            or "3090" in self.name.lower()
            or "40" in self.name
        )
