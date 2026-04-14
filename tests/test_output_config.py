"""Tests for OutputConfig schema."""

import pytest

from ace_music.schemas.output_config import OutputConfig


class TestOutputConfigDefaults:
    def test_default_values(self):
        config = OutputConfig()
        assert config.base_dir == "./output"
        assert config.naming == "nested"
        assert config.create_metadata is True

    def test_custom_values(self):
        config = OutputConfig(
            base_dir="/tmp/music",
            naming="flat",
            filename_template="{slug}_{date}",
        )
        assert config.base_dir == "/tmp/music"
        assert config.naming == "flat"

    def test_invalid_naming_rejected(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            OutputConfig(naming="invalid")


class TestOutputConfigObsidianFactory:
    def test_obsidian_factory_sets_flat_naming(self):
        config = OutputConfig.for_obsidian(base="/tmp/test_output")
        assert config.naming == "flat"
        assert config.base_dir == "/tmp/test_output"

    def test_obsidian_factory_default_path_contains_music(self):
        config = OutputConfig.for_obsidian()
        assert "outputs/music" in config.base_dir

    def test_obsidian_factory_custom_base(self):
        config = OutputConfig.for_obsidian(base="/custom/path")
        assert config.base_dir == "/custom/path"
        assert config.naming == "flat"
