"""Tests for material context schemas."""

import pytest

from ace_music.schemas.material import MaterialContext, MaterialEntry, MaterialSource


class TestMaterialEntry:
    def test_minimal_entry(self):
        entry = MaterialEntry(
            source_file="inspiration_2026-04-16.json",
            content="Dreamy ambient pads with reverb",
            category="style_inspiration",
        )
        assert entry.source_file == "inspiration_2026-04-16.json"
        assert entry.category == "style_inspiration"

    def test_entry_with_metadata(self):
        entry = MaterialEntry(
            source_file="lyrics_2026-04-16.json",
            content="Neon lights reflecting in puddles",
            category="lyrics",
            tags=["neon", "urban", "night"],
            mood="melancholic",
            style="synthwave",
        )
        assert entry.tags == ["neon", "urban", "night"]
        assert entry.mood == "melancholic"
        assert entry.style == "synthwave"


class TestMaterialContext:
    def test_empty_context(self):
        ctx = MaterialContext()
        assert ctx.entries == []
        assert ctx.is_empty is True

    def test_context_with_entries(self):
        ctx = MaterialContext(
            entries=[
                MaterialEntry(
                    source_file="a.json",
                    content="ambient",
                    category="style_inspiration",
                ),
                MaterialEntry(
                    source_file="b.json", content="neon dreams", category="lyrics"
                ),
            ]
        )
        assert len(ctx.entries) == 2
        assert ctx.is_empty is False

    def test_entries_by_category(self):
        ctx = MaterialContext(
            entries=[
                MaterialEntry(
                    source_file="a.json", content="ambient", category="style"
                ),
                MaterialEntry(
                    source_file="b.json", content="neon", category="lyrics"
                ),
                MaterialEntry(
                    source_file="c.json", content="dark", category="style"
                ),
            ]
        )
        assert len(ctx.entries_by_category("style")) == 2

    def test_style_summary(self):
        ctx = MaterialContext(
            entries=[
                MaterialEntry(
                    source_file="a.json", content="ambient chill", category="style"
                ),
                MaterialEntry(
                    source_file="b.json", content="synthwave retro", category="style"
                ),
            ]
        )
        assert "ambient" in ctx.style_summary

    def test_lyrics_summary(self):
        ctx = MaterialContext(
            entries=[
                MaterialEntry(
                    source_file="a.json", content="Neon lights\nCity rain", category="lyrics"
                ),
            ]
        )
        assert "Neon lights" in ctx.lyrics_summary

    def test_source_files(self):
        ctx = MaterialContext(
            entries=[
                MaterialEntry(
                    source_file="a.json", content="x", category="style"
                ),
                MaterialEntry(
                    source_file="b.json", content="y", category="lyrics"
                ),
            ]
        )
        assert ctx.source_files == ["a.json", "b.json"]

    def test_provenance_dict(self):
        ctx = MaterialContext(
            entries=[
                MaterialEntry(
                    source_file="a.json", content="ambient", category="style"
                ),
            ]
        )
        prov = ctx.to_provenance_dict()
        assert prov["source_count"] == 1
        assert prov["source_files"] == ["a.json"]
        assert "style_summary" in prov


class TestMaterialSource:
    def test_material_source_with_path(self):
        source = MaterialSource(directory="/path/to/materials")
        assert source.directory == "/path/to/materials"


import json
from pathlib import Path

from ace_music.tools.material_loader import MaterialLoader


FIXTURE_DIR = Path(__file__).resolve().parent.parent


class TestMaterialLoader:
    def _write_material_file(self, tmp_path, filename, data):
        materials_dir = tmp_path / "materials"
        materials_dir.mkdir(exist_ok=True)
        (materials_dir / filename).write_text(json.dumps(data, ensure_ascii=False))
        return str(materials_dir)

    def test_load_from_json_file(self, tmp_path):
        data = {
            "date": "2026-04-16",
            "entries": [
                {"category": "style", "content": "ambient electronic", "tags": ["ambient"], "mood": "calm", "style": "ambient"}
            ],
        }
        mat_dir = self._write_material_file(tmp_path, "material_2026-04-16.json", data)
        loader = MaterialLoader(directory=mat_dir)
        ctx = loader.load()
        assert len(ctx.entries) == 1
        assert ctx.entries[0].source_file == "material_2026-04-16.json"
        assert ctx.entries[0].content == "ambient electronic"
        assert ctx.entries[0].mood == "calm"

    def test_load_latest_only(self, tmp_path):
        old_data = {"date": "2026-04-15", "entries": [{"category": "style", "content": "old style"}]}
        new_data = {"date": "2026-04-16", "entries": [{"category": "style", "content": "new style"}]}
        mat_dir = self._write_material_file(tmp_path, "material_2026-04-15.json", old_data)
        self._write_material_file(tmp_path, "material_2026-04-16.json", new_data)
        loader = MaterialLoader(directory=mat_dir)
        ctx = loader.load_latest()
        assert len(ctx.entries) == 1
        assert ctx.entries[0].content == "new style"

    def test_empty_directory_returns_empty_context(self, tmp_path):
        mat_dir = tmp_path / "empty_materials"
        mat_dir.mkdir()
        loader = MaterialLoader(directory=str(mat_dir))
        ctx = loader.load()
        assert ctx.is_empty is True

    def test_load_from_sample_fixture(self):
        loader = MaterialLoader(directory=str(FIXTURE_DIR))
        ctx = loader.load_file("sample-music-material.json")
        assert len(ctx.entries) == 4
        assert ctx.entries[0].category == "style_inspiration"
        assert ctx.style_summary != ""
        assert ctx.lyrics_summary != ""

    def test_nonexistent_directory_returns_empty(self):
        loader = MaterialLoader(directory="/nonexistent/path")
        ctx = loader.load()
        assert ctx.is_empty is True

    def test_load_preserves_source_file(self, tmp_path):
        data = {"entries": [{"category": "mood", "content": "happy"}]}
        mat_dir = self._write_material_file(tmp_path, "test_mat.json", data)
        loader = MaterialLoader(directory=mat_dir)
        ctx = loader.load()
        assert ctx.entries[0].source_file == "test_mat.json"
