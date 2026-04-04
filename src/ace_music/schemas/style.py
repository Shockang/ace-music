"""Style parameter models."""

from pydantic import BaseModel, Field


class StyleInput(BaseModel):
    """Input for style planning."""

    description: str = Field(
        description="Natural language style description (e.g. 'dreamy synthwave with heavy bass')"
    )
    reference_tags: list[str] = Field(
        default_factory=list,
        description="Pre-known style tags (e.g. ['pop', 'electronic', 'synthwave'])",
    )
    reference_audio_path: str | None = Field(
        default=None, description="Path to reference audio file for style matching"
    )
    tempo_preference: str | None = Field(
        default=None, description="Tempo preference (e.g. 'fast', '120 bpm', 'slow ballad')"
    )
    mood: str | None = Field(default=None, description="Mood descriptor (e.g. 'melancholic', 'upbeat')")


# Predefined style tag mappings for common genres
GENRE_TAG_MAP: dict[str, list[str]] = {
    "pop": ["pop", "catchy", "mainstream"],
    "rock": ["rock", "guitar", "drums"],
    "electronic": ["electronic", "synth", "digital"],
    "hip-hop": ["hip-hop", "rap", "beats"],
    "jazz": ["jazz", "smooth", "improvisation"],
    "classical": ["classical", "orchestral", "acoustic"],
    "r&b": ["r&b", "soul", "rhythm and blues"],
    "country": ["country", "folk", "acoustic guitar"],
    "metal": ["metal", "heavy", "distorted"],
    "blues": ["blues", "guitar", "soulful"],
    "reggae": ["reggae", "dub", "chill"],
    "latin": ["latin", "rhythmic", "dance"],
    "synthwave": ["synthwave", "retro", "electronic", "80s"],
    "ambient": ["ambient", "atmospheric", "chill"],
    "lo-fi": ["lo-fi", "chill", "relaxed"],
}

MOOD_TAG_MAP: dict[str, list[str]] = {
    "happy": ["upbeat", "cheerful", "bright"],
    "sad": ["melancholic", "dark", "emotional"],
    "energetic": ["energetic", "powerful", "driving"],
    "calm": ["calm", "peaceful", "serene"],
    "dark": ["dark", "moody", "intense"],
    "dreamy": ["dreamy", "ethereal", "atmospheric"],
    "aggressive": ["aggressive", "hard", "intense"],
}


class StyleOutput(BaseModel):
    """ACE-Step compatible style parameters."""

    prompt: str = Field(
        description="Comma-separated style tags for ACE-Step (e.g. 'pop, electronic, synthwave')"
    )
    guidance_scale: float = Field(default=15.0, ge=1.0, le=30.0)
    scheduler_type: str = Field(default="euler")
    cfg_type: str = Field(default="apg")
    omega_scale: float = Field(default=10.0)
    infer_step: int = Field(default=60, ge=1, le=200)
    guidance_interval: float = Field(default=0.5, ge=0.0, le=1.0)
    guidance_interval_decay: float = Field(default=0.0, ge=0.0, le=1.0)
    min_guidance_scale: float = Field(default=3.0)
    use_erg_tag: bool = True
    use_erg_lyric: bool = True
    use_erg_diffusion: bool = True
