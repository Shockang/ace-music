"""StylePlanner: map style descriptions to ACE-Step parameters.

Supports:
- Natural language style descriptions → tag extraction
- Pre-defined genre/mood tag mappings
- Tempo preference parsing
- Reference audio style hints (future)
"""

import re

from ace_music.schemas.audio_contract import AudioSceneContract
from ace_music.schemas.preset import StylePreset
from ace_music.schemas.style import (
    GENRE_TAG_MAP,
    MOOD_TAG_MAP,
    StyleInput,
    StyleOutput,
)
from ace_music.tools.base import MusicTool


def _extract_tags_from_description(description: str) -> list[str]:
    """Extract known genre and mood tags from a natural language description."""
    tags: list[str] = []
    desc_lower = description.lower()

    # Match genre keywords
    for genre, genre_tags in GENRE_TAG_MAP.items():
        if genre in desc_lower or genre.replace("-", " ") in desc_lower:
            tags.extend(genre_tags)

    # Match mood keywords
    for mood, mood_tags in MOOD_TAG_MAP.items():
        if mood in desc_lower:
            tags.extend(mood_tags)

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            unique.append(tag)

    return unique


def _parse_tempo(preference: str | None) -> dict:
    """Parse tempo preference into style parameter adjustments."""
    if not preference:
        return {}

    pref_lower = preference.lower()

    # Check for explicit BPM
    bpm_match = re.search(r"(\d+)\s*bpm", pref_lower)
    if bpm_match:
        bpm = int(bpm_match.group(1))
        if bpm > 140:
            return {"guidance_scale": 15.0, "omega_scale": 12.0}
        elif bpm > 100:
            return {"guidance_scale": 15.0, "omega_scale": 10.0}
        else:
            return {"guidance_scale": 12.0, "omega_scale": 8.0}

    # Qualitative tempo
    if any(w in pref_lower for w in ["fast", "uptempo", "driving"]):
        return {"guidance_scale": 15.0, "omega_scale": 12.0}
    if any(w in pref_lower for w in ["slow", "ballad", "gentle"]):
        return {"guidance_scale": 12.0, "omega_scale": 8.0}

    return {}


class StylePlanner(MusicTool[StyleInput, StyleOutput]):
    """Map style descriptions to ACE-Step generation parameters."""

    @property
    def name(self) -> str:
        return "style_planner"

    @property
    def description(self) -> str:
        return "Map style descriptions and tags to ACE-Step generation parameters"

    @property
    def input_schema(self) -> type[StyleInput]:
        return StyleInput

    @property
    def output_schema(self) -> type[StyleOutput]:
        return StyleOutput

    def _plan_single(
        self, input_data: StyleInput, preset: StylePreset | None = None
    ) -> StyleOutput:
        # Start with user-provided tags
        all_tags = list(input_data.reference_tags)

        # Extract tags from description
        extracted = _extract_tags_from_description(input_data.description)
        for tag in extracted:
            if tag not in all_tags:
                all_tags.append(tag)

        # Extract mood tags
        if input_data.mood:
            mood_tags = _extract_tags_from_description(input_data.mood)
            for tag in mood_tags:
                if tag not in all_tags:
                    all_tags.append(tag)

        # Build prompt
        if preset:
            preset_tags = [t.strip() for t in preset.prompt.split(",") if t.strip()]
            for tag in preset_tags:
                if tag not in all_tags:
                    all_tags.append(tag)
            prompt = ", ".join(all_tags) if all_tags else preset.prompt
        else:
            prompt = ", ".join(all_tags) if all_tags else input_data.description

        # Parse tempo preference
        tempo_overrides = _parse_tempo(input_data.tempo_preference)

        # Determine parameters
        if preset:
            overrides = preset.to_style_overrides()
            guidance_scale = tempo_overrides.get(
                "guidance_scale", overrides.guidance_scale
            )
            omega_scale = tempo_overrides.get("omega_scale", overrides.omega_scale)
            return StyleOutput(
                prompt=prompt,
                guidance_scale=guidance_scale,
                omega_scale=omega_scale,
                infer_step=overrides.infer_step,
                scheduler_type=overrides.scheduler_type,
                cfg_type=overrides.cfg_type,
                guidance_interval=overrides.guidance_interval,
                guidance_interval_decay=overrides.guidance_interval_decay,
                min_guidance_scale=overrides.min_guidance_scale,
                use_erg_tag=overrides.use_erg_tag,
                use_erg_lyric=overrides.use_erg_lyric,
                use_erg_diffusion=overrides.use_erg_diffusion,
            )

        return StyleOutput(
            prompt=prompt,
            guidance_scale=tempo_overrides.get("guidance_scale", 15.0),
            omega_scale=tempo_overrides.get("omega_scale", 10.0),
        )

    def plan_sequence(
        self,
        contracts: list[AudioSceneContract],
        presets: list[StylePreset | None] | None = None,
    ) -> list[StyleOutput]:
        outputs: list[StyleOutput] = []
        for idx, contract in enumerate(contracts):
            preset = presets[idx] if presets else None
            outputs.append(
                self._plan_single(
                    StyleInput(
                        description=contract.scene_description or contract.mood,
                        mood=contract.mood,
                    ),
                    preset=preset,
                )
            )

        for idx in range(1, len(outputs)):
            previous = contracts[idx - 1]
            current = contracts[idx]
            previous_arousal = previous.arousal
            current_arousal = current.arousal
            if previous_arousal is None or current_arousal is None:
                continue
            if abs(current_arousal - previous_arousal) > 0.5:
                outputs[idx] = outputs[idx].model_copy(
                    update={
                        "guidance_scale": min(
                            outputs[idx].guidance_scale,
                            outputs[idx - 1].guidance_scale + 0.5,
                        ),
                        "omega_scale": min(outputs[idx].omega_scale, 10.0),
                    }
                )

        for idx in range(2, len(outputs)):
            if contracts[idx - 2].mood == contracts[idx - 1].mood == contracts[idx].mood:
                outputs[idx] = outputs[idx].model_copy(
                    update={"guidance_scale": min(outputs[idx].guidance_scale + 0.75, 20.0)}
                )

        opposing_pairs = {("dark", "upbeat"), ("upbeat", "dark")}
        for idx in range(1, len(outputs)):
            previous_mood = (contracts[idx - 1].mood or "").strip().lower()
            current_mood = (contracts[idx].mood or "").strip().lower()
            if (previous_mood, current_mood) in opposing_pairs:
                previous_energy = contracts[idx - 1].arousal or 0.0
                current_energy = contracts[idx].arousal or 0.0
                target_idx = idx - 1 if previous_energy <= current_energy else idx
                prompt_tags = outputs[target_idx].prompt.split(", ")
                filtered_tags = list(prompt_tags)
                if "moderate" not in filtered_tags and "neutral" not in filtered_tags:
                    target_arousal = contracts[target_idx].arousal or 0.0
                    filtered_tags.append(
                        "moderate" if target_arousal > 0.3 else "neutral"
                    )
                outputs[target_idx] = outputs[target_idx].model_copy(
                    update={"prompt": ", ".join(filtered_tags)}
                )

        return outputs

    async def execute(
        self, input_data: StyleInput, preset: StylePreset | None = None
    ) -> StyleOutput:
        return self._plan_single(input_data, preset=preset)
