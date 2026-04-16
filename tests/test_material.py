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
