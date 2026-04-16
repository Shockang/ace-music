"""MaterialLoader: read daily music material from a directory."""

import json
import logging
from pathlib import Path

from ace_music.schemas.material import MaterialContext, MaterialEntry

logger = logging.getLogger(__name__)


class MaterialLoader:
    """Load structured music material from JSON files."""

    def __init__(self, directory: str = "./materials") -> None:
        self._directory = Path(directory)

    def load(self) -> MaterialContext:
        """Load all material files from the directory, merged into one context."""
        if not self._directory.exists():
            logger.warning("Material directory not found: %s", self._directory)
            return MaterialContext()

        json_files = sorted(self._directory.glob("*.json"))
        if not json_files:
            logger.info("No material files found in %s", self._directory)
            return MaterialContext()

        all_entries: list[MaterialEntry] = []
        for json_file in json_files:
            entries = self._parse_file(json_file)
            all_entries.extend(entries)

        logger.info("Loaded %d material entries from %d files", len(all_entries), len(json_files))
        return MaterialContext(entries=all_entries)

    def load_latest(self) -> MaterialContext:
        """Load only the most recently modified material file."""
        if not self._directory.exists():
            return MaterialContext()

        json_files = sorted(
            self._directory.glob("*.json"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        if not json_files:
            return MaterialContext()

        latest = json_files[0]
        entries = self._parse_file(latest)
        logger.info("Loaded latest material: %s (%d entries)", latest.name, len(entries))
        return MaterialContext(entries=entries)

    def load_file(self, filename: str) -> MaterialContext:
        """Load a specific material file by name or path."""
        path = Path(filename)
        if not path.is_absolute():
            path = self._directory / filename

        if not path.exists():
            path = Path(filename)

        if not path.exists():
            logger.warning("Material file not found: %s", filename)
            return MaterialContext()

        entries = self._parse_file(path)
        return MaterialContext(entries=entries)

    def _parse_file(self, path: Path) -> list[MaterialEntry]:
        """Parse a single JSON material file into MaterialEntry list."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to parse material file %s: %s", path.name, e)
            return []

        raw_entries = data.get("entries", [])
        if not raw_entries:
            return []

        entries: list[MaterialEntry] = []
        for raw in raw_entries:
            try:
                entries.append(
                    MaterialEntry(
                        source_file=path.name,
                        content=raw.get("content", ""),
                        category=raw.get("category", "unknown"),
                        tags=raw.get("tags", []),
                        mood=raw.get("mood"),
                        style=raw.get("style"),
                    )
                )
            except Exception as e:
                logger.warning("Skipping invalid material entry in %s: %s", path.name, e)

        return entries
