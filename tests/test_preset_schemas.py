"""Tests for preset schema models."""

import pytest
from pydantic import ValidationError

from ace_music.schemas.preset import PresetFile, StylePreset


class TestStylePreset:
    def test_minimal_preset(self):
        preset = StylePreset(
            id="ambient_chill",
            name="Ambient Chill",
            description="Relaxed ambient atmosphere",
            prompt="ambient, atmospheric, chill, relaxed",
        )
        assert preset.id == "ambient_chill"
        assert preset.prompt == "ambient, atmospheric, chill, relaxed"
        assert preset.guidance_scale == 15.0  # default

    def test_preset_with_full_overrides(self):
        preset = StylePreset(
            id="electronic_fast",
            name="Fast Electronic",
            description="High-energy electronic music",
            prompt="electronic, synth, fast, driving",
            guidance_scale=18.0,
            omega_scale=12.0,
            infer_step=40,
            scheduler_type="euler",
            cfg_type="apg",
            tempo_range=(130, 170),
            mood=["energetic", "driving"],
            genres=["electronic", "synthwave"],
        )
        assert preset.guidance_scale == 18.0
        assert preset.omega_scale == 12.0
        assert preset.infer_step == 40
        assert preset.tempo_range == (130, 170)

    def test_preset_validates_guidance_range(self):
        with pytest.raises(ValidationError):
            StylePreset(
                id="bad",
                name="Bad",
                description="Invalid guidance",
                prompt="test",
                guidance_scale=50.0,
            )

    def test_preset_validates_infer_step_range(self):
        with pytest.raises(ValidationError):
            StylePreset(
                id="bad",
                name="Bad",
                description="Invalid steps",
                prompt="test",
                infer_step=500,
            )


class TestPresetFile:
    def test_preset_file_structure(self):
        pf = PresetFile(
            version="1.0",
            presets=[
                StylePreset(
                    id="test",
                    name="Test",
                    description="Test preset",
                    prompt="test, tags",
                )
            ],
        )
        assert len(pf.presets) == 1
        assert pf.version == "1.0"

    def test_preset_file_requires_at_least_one_preset(self):
        with pytest.raises(ValidationError):
            PresetFile(version="1.0", presets=[])


class TestPresetResolution:
    def test_preset_style_overrides_applied(self):
        preset = StylePreset(
            id="electronic_fast",
            name="Fast Electronic",
            description="High-energy",
            prompt="electronic, synth",
            guidance_scale=18.0,
            omega_scale=12.0,
            infer_step=40,
        )
        overrides = preset.to_style_overrides()
        assert overrides.guidance_scale == 18.0
        assert overrides.omega_scale == 12.0
        assert overrides.infer_step == 40
