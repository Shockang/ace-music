"""Material context models for daily music material integration."""

from pydantic import BaseModel, Field


class MaterialEntry(BaseModel):
    """A single piece of material consumed by the pipeline."""

    source_file: str = Field(description="Filename the material was loaded from")
    content: str = Field(description="The actual material content")
    category: str = Field(
        description="Category: 'style', 'lyrics', 'mood', 'style_inspiration', 'genre'"
    )
    tags: list[str] = Field(default_factory=list)
    mood: str | None = None
    style: str | None = None


class MaterialContext(BaseModel):
    """Container for all material consumed in a single generation run."""

    entries: list[MaterialEntry] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return len(self.entries) == 0

    def entries_by_category(self, category: str) -> list[MaterialEntry]:
        return [e for e in self.entries if e.category == category]

    @property
    def style_summary(self) -> str:
        entries = self.entries_by_category("style") + self.entries_by_category(
            "style_inspiration"
        )
        return " ".join(e.content for e in entries)

    @property
    def lyrics_summary(self) -> str:
        entries = self.entries_by_category("lyrics")
        return "\n".join(e.content for e in entries)

    @property
    def source_files(self) -> list[str]:
        return [e.source_file for e in self.entries]

    def to_provenance_dict(self) -> dict:
        return {
            "source_count": len(self.entries),
            "source_files": self.source_files,
            "style_summary": self.style_summary,
            "lyrics_summary": self.lyrics_summary[:200] if self.lyrics_summary else None,
            "mood": self._collect_moods(),
        }

    def _collect_moods(self) -> list[str]:
        return [e.mood for e in self.entries if e.mood]


class MaterialSource(BaseModel):
    """Configuration for where to load material from."""

    directory: str = Field(description="Directory containing material JSON files")
