"""Tests for PresetResolver tool."""

import pytest

from ace_music.schemas.preset import PresetFile, StylePreset
from ace_music.tools.preset_resolver import PresetMatch, PresetResolver


@pytest.fixture
def resolver_with_presets(tmp_path):
    """Create a resolver with test preset files."""
    import yaml

    presets_dir = tmp_path / "presets"
    presets_dir.mkdir()

    default_presets = PresetFile(
        version="1.0",
        presets=[
            StylePreset(
                id="ambient_chill",
                name="Ambient Chill",
                description="Relaxed ambient atmosphere",
                prompt="ambient, atmospheric, chill, relaxed",
                genres=["ambient"],
                mood=["calm"],
            ),
            StylePreset(
                id="electronic_fast",
                name="Fast Electronic",
                description="High-energy electronic",
                prompt="electronic, synth, fast, driving",
                guidance_scale=18.0,
                omega_scale=12.0,
                genres=["electronic"],
                mood=["energetic"],
            ),
            StylePreset(
                id="pop_standard",
                name="Pop Standard",
                description="Mainstream pop",
                prompt="pop, catchy, mainstream",
                genres=["pop"],
            ),
        ],
    )

    (presets_dir / "default.yaml").write_text(
        yaml.dump(default_presets.model_dump(), allow_unicode=True)
    )

    return PresetResolver(presets_dir=str(presets_dir))


class TestPresetResolverLoading:
    def test_loads_presets_from_directory(self, resolver_with_presets):
        presets = resolver_with_presets.list_presets()
        assert len(presets) >= 3

    def test_list_presets_returns_all(self, resolver_with_presets):
        ids = [p.id for p in resolver_with_presets.list_presets()]
        assert "ambient_chill" in ids
        assert "electronic_fast" in ids
        assert "pop_standard" in ids


class TestPresetResolverExactMatch:
    @pytest.mark.asyncio
    async def test_match_by_id(self, resolver_with_presets):
        match = await resolver_with_presets.resolve("ambient_chill")
        assert match is not None
        assert match.preset.id == "ambient_chill"
        assert match.confidence == 1.0

    @pytest.mark.asyncio
    async def test_match_by_name(self, resolver_with_presets):
        match = await resolver_with_presets.resolve("Ambient Chill")
        assert match is not None
        assert match.preset.id == "ambient_chill"

    @pytest.mark.asyncio
    async def test_no_match_returns_none(self, resolver_with_presets):
        match = await resolver_with_presets.resolve("nonexistent_preset_xyz")
        assert match is None


class TestPresetResolverFuzzyMatch:
    @pytest.mark.asyncio
    async def test_fuzzy_match_by_genre(self, resolver_with_presets):
        match = await resolver_with_presets.resolve("some electronic music")
        assert match is not None
        assert match.preset.id == "electronic_fast"

    @pytest.mark.asyncio
    async def test_fuzzy_match_by_description_keywords(self, resolver_with_presets):
        match = await resolver_with_presets.resolve("I want something calm and ambient")
        assert match is not None
        assert match.preset.id == "ambient_chill"

    @pytest.mark.asyncio
    async def test_fuzzy_match_confidence_below_threshold(self, resolver_with_presets):
        match = await resolver_with_presets.resolve("xyz123 completely unrelated")
        assert match is None


class TestPresetMatch:
    def test_preset_match_model(self):
        preset = StylePreset(id="test", name="Test", description="Test", prompt="test")
        match = PresetMatch(preset=preset, confidence=0.8, match_method="keyword")
        assert match.confidence == 0.8
        assert match.match_method == "keyword"


class TestDarkSuspensePreset:
    @pytest.mark.asyncio
    async def test_dark_suspense_resolves_by_id(self):
        """dark_suspense preset should be resolvable by exact ID."""
        resolver = PresetResolver()
        match = await resolver.resolve("dark_suspense")
        assert match is not None
        assert match.preset.id == "dark_suspense"
        assert match.confidence == 1.0
        assert match.match_method == "exact_id"

    @pytest.mark.asyncio
    async def test_dark_suspense_has_correct_params(self):
        """dark_suspense should have 40 infer steps and electronic genre."""
        resolver = PresetResolver()
        match = await resolver.resolve("dark_suspense")
        assert match is not None
        preset = match.preset
        assert preset.infer_step == 40
        assert preset.guidance_scale == 15.0
        assert "electronic" in preset.genres

    @pytest.mark.asyncio
    async def test_dark_suspense_fuzzy_match(self):
        """Searching for suspense/dark keywords should find dark_suspense."""
        resolver = PresetResolver()
        match = await resolver.resolve("dark suspense thriller")
        assert match is not None
        assert match.preset.id == "dark_suspense"
