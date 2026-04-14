"""PresetResolver: match natural language descriptions to style presets.

Supports:
- Exact match by preset ID
- Exact match by preset name (case-insensitive)
- Fuzzy match by genre/mood keyword overlap
- Configurable confidence threshold
"""

import logging
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from ace_music.schemas.preset import PresetFile, StylePreset

logger = logging.getLogger(__name__)

FUZZY_MATCH_THRESHOLD = 0.3


class PresetMatch(BaseModel):
    """Result of a preset resolution attempt."""

    preset: StylePreset
    confidence: float = Field(ge=0.0, le=1.0)
    match_method: str = Field(description="How the match was found: exact_id, exact_name, keyword")


class PresetResolver:
    """Load and resolve style presets from YAML configuration files."""

    def __init__(self, presets_dir: str = "configs/presets") -> None:
        self._presets_dir = Path(presets_dir)
        self._presets: list[StylePreset] = []
        self._loaded = False

    def _load(self) -> None:
        """Load all preset YAML files from the configured directory."""
        if self._loaded:
            return

        if not self._presets_dir.exists():
            logger.warning("Presets directory not found: %s", self._presets_dir)
            self._loaded = True
            return

        for yaml_file in sorted(self._presets_dir.glob("*.yaml")):
            try:
                data = yaml.safe_load(yaml_file.read_text())
                pf = PresetFile.model_validate(data)
                self._presets.extend(pf.presets)
                logger.info("Loaded %d presets from %s", len(pf.presets), yaml_file.name)
            except Exception as e:
                logger.error("Failed to load preset file %s: %s", yaml_file.name, e)

        self._loaded = True

    def list_presets(self) -> list[StylePreset]:
        """Return all loaded presets."""
        self._load()
        return list(self._presets)

    def get_by_id(self, preset_id: str) -> StylePreset | None:
        """Look up a preset by its exact ID."""
        self._load()
        for preset in self._presets:
            if preset.id == preset_id:
                return preset
        return None

    async def resolve(
        self, query: str, threshold: float = FUZZY_MATCH_THRESHOLD
    ) -> PresetMatch | None:
        """Resolve a natural language query to the best matching preset."""
        self._load()
        query_lower = query.lower().strip()

        # Strategy 1: exact ID match
        for preset in self._presets:
            if preset.id == query_lower:
                return PresetMatch(preset=preset, confidence=1.0, match_method="exact_id")

        # Strategy 2: exact name match
        for preset in self._presets:
            if preset.name.lower() == query_lower:
                return PresetMatch(preset=preset, confidence=1.0, match_method="exact_name")

        # Strategy 3: fuzzy keyword match
        query_words = set(query_lower.split())
        best_match: PresetMatch | None = None
        best_score = 0.0

        for preset in self._presets:
            keywords: set[str] = set()
            for genre in preset.genres:
                keywords.update(genre.lower().replace("-", " ").split())
            for mood_word in preset.mood:
                keywords.update(mood_word.lower().split())
            keywords.update(preset.description.lower().split())
            keywords.update(preset.prompt.lower().replace(",", " ").split())
            keywords.update(preset.name.lower().split())

            overlap = query_words & keywords
            if not overlap:
                continue
            score = len(overlap) / max(len(query_words), 1)

            if score > best_score and score >= threshold:
                best_score = score
                best_match = PresetMatch(
                    preset=preset, confidence=round(score, 3), match_method="keyword"
                )

        return best_match
