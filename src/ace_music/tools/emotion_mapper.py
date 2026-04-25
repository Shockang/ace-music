"""Deterministic mapping from audio scene contracts to generation hints."""

from pydantic import BaseModel, Field

from ace_music.schemas.audio_contract import (
    AudioQATargets,
    AudioSceneContract,
    MixPolicy,
    TransitionPolicy,
)

MOOD_STYLE_TAGS: dict[str, list[str]] = {
    "tense": ["tense", "cinematic", "suspense", "pulsing"],
    "urgent": ["urgent", "tense", "driving", "percussion"],
    "melancholic": ["melancholic", "emotional", "minor", "ambient"],
    "calm": ["calm", "ambient", "soft", "minimal"],
    "hopeful": ["hopeful", "uplifting", "warm", "cinematic"],
}


class MappedAudioParameters(BaseModel):
    """Mapped generation, mix, and QA guidance derived from a scene contract."""

    style_tags: list[str] = Field(default_factory=list)
    tempo_preference: str
    guidance_scale: float
    prompt_suffix: str
    mix: MixPolicy
    transition: TransitionPolicy
    qa_targets: AudioQATargets

    def to_metadata(self) -> dict:
        """Return JSON-safe metadata for downstream pipeline consumers."""

        return self.model_dump(mode="json")


def map_scene_contract(contract: AudioSceneContract) -> MappedAudioParameters:
    """Map a scene contract to deterministic music and mix parameters."""

    normalized_mood = _normalize_mood(contract.mood)
    pace = _estimate_pace(contract)
    mix = _derive_mix(contract)
    style_tags = _derive_style_tags(contract, pace, normalized_mood)
    guidance_scale = _derive_guidance_scale(contract, pace)

    return MappedAudioParameters(
        style_tags=style_tags,
        tempo_preference=pace,
        guidance_scale=guidance_scale,
        prompt_suffix=_build_prompt_suffix(contract, pace, normalized_mood),
        mix=mix,
        transition=contract.transition.model_copy(deep=True),
        qa_targets=contract.qa_targets.model_copy(deep=True),
    )


def _estimate_pace(contract: AudioSceneContract) -> str:
    if contract.arousal is not None and contract.arousal >= 0.75:
        return "fast"
    if contract.shot_count is not None and contract.duration_seconds > 0:
        shots_per_10_seconds = contract.shot_count / (contract.duration_seconds / 10.0)
        if shots_per_10_seconds >= 3.0:
            return "fast"
    if contract.arousal is not None and contract.arousal <= 0.35:
        return "slow"
    return "moderate"


def _derive_mix(contract: AudioSceneContract) -> MixPolicy:
    bgm_gain_db = max(-30.0, contract.mix.bgm_gain_db - (contract.dialogue_density * 4.0))
    sidechain_source = "tts" if contract.layers.tts_present else "none"
    ducking_db = contract.mix.ducking_db
    if contract.layers.tts_present:
        ducking_db = min(24.0, ducking_db + (contract.dialogue_density * 4.0))

    return contract.mix.model_copy(
        update={
            "bgm_gain_db": bgm_gain_db,
            "ducking_db": ducking_db,
            "sidechain_source": sidechain_source,
        }
    )


def _build_prompt_suffix(
    contract: AudioSceneContract,
    pace: str,
    normalized_mood: str,
) -> str:
    parts = [
        f"Mood: {normalized_mood}.",
        f"Intensity: {contract.intensity:.2f}.",
        f"Pace: {pace}.",
    ]

    if contract.scene_description:
        parts.append(f"Scene: {contract.scene_description}.")
    elif contract.narrative_beat:
        parts.append(f"Beat: {contract.narrative_beat}.")

    crossfade = contract.transition.crossfade_seconds
    transition_requirement = (
        "seamless tail required"
        if contract.transition.require_seamless_tail
        else "standard tail allowed"
    )
    parts.append(f"Transition: {crossfade:.1f}s crossfade, {transition_requirement}.")
    return " ".join(parts)


def _derive_style_tags(
    contract: AudioSceneContract,
    pace: str,
    normalized_mood: str,
) -> list[str]:
    tags: list[str] = []
    tags.extend(MOOD_STYLE_TAGS.get(normalized_mood, [normalized_mood]))

    if contract.arousal is not None and contract.arousal >= 0.75 and "tense" not in tags:
        tags.append("tense")

    if pace not in tags:
        tags.append(pace)

    if contract.role_theme:
        tags.append(contract.role_theme.lower())

    seen: set[str] = set()
    unique_tags: list[str] = []
    for tag in tags:
        normalized = tag.strip().lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique_tags.append(normalized)
    return unique_tags


def _normalize_mood(mood: str) -> str:
    return mood.strip().lower()


def _derive_guidance_scale(contract: AudioSceneContract, pace: str) -> float:
    guidance_scale = 12.0 + (contract.intensity * 4.0)
    if pace == "fast":
        guidance_scale += 1.0
    return min(20.0, max(8.0, guidance_scale))
