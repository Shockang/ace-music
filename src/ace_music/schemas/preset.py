"""Style preset models for predefined music generation configurations."""

from pydantic import BaseModel, Field


class PresetStyleOverrides(BaseModel):
    """Style parameters extracted from a preset, ready to apply to StyleOutput."""

    guidance_scale: float = 15.0
    omega_scale: float = 10.0
    infer_step: int = 60
    scheduler_type: str = "euler"
    cfg_type: str = "apg"
    guidance_interval: float = 0.5
    guidance_interval_decay: float = 0.0
    min_guidance_scale: float = 3.0
    use_erg_tag: bool = True
    use_erg_lyric: bool = True
    use_erg_diffusion: bool = True


class StylePreset(BaseModel):
    """A single style preset defining music generation parameters."""

    id: str = Field(description="Unique preset identifier (e.g. 'electronic_fast')")
    name: str = Field(description="Human-readable preset name")
    description: str = Field(description="What this preset sounds like")
    prompt: str = Field(
        description="Comma-separated ACE-Step style tags (e.g. 'ambient, atmospheric, chill')"
    )
    guidance_scale: float = Field(default=15.0, ge=1.0, le=30.0)
    omega_scale: float = Field(default=10.0, ge=0.0, le=20.0)
    infer_step: int = Field(default=60, ge=1, le=200)
    scheduler_type: str = Field(default="euler")
    cfg_type: str = Field(default="apg")
    guidance_interval: float = Field(default=0.5, ge=0.0, le=1.0)
    guidance_interval_decay: float = Field(default=0.0, ge=0.0, le=1.0)
    min_guidance_scale: float = Field(default=3.0)
    use_erg_tag: bool = True
    use_erg_lyric: bool = True
    use_erg_diffusion: bool = True
    tempo_range: tuple[int, int] | None = Field(
        default=None, description="(min_bpm, max_bpm) if applicable"
    )
    mood: list[str] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)

    def to_style_overrides(self) -> PresetStyleOverrides:
        """Convert preset to style overrides that can be applied to StyleOutput."""
        return PresetStyleOverrides(
            guidance_scale=self.guidance_scale,
            omega_scale=self.omega_scale,
            infer_step=self.infer_step,
            scheduler_type=self.scheduler_type,
            cfg_type=self.cfg_type,
            guidance_interval=self.guidance_interval,
            guidance_interval_decay=self.guidance_interval_decay,
            min_guidance_scale=self.min_guidance_scale,
            use_erg_tag=self.use_erg_tag,
            use_erg_lyric=self.use_erg_lyric,
            use_erg_diffusion=self.use_erg_diffusion,
        )


class PresetFile(BaseModel):
    """A YAML-loadable file containing multiple style presets."""

    version: str = Field(default="1.0", description="Preset file format version")
    presets: list[StylePreset] = Field(min_length=1)
