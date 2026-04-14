"""WorkspaceManager: structured output directories with run manifests.

Creates and manages the output directory layout:
    output/{run_id}/
        manifest.json
        lyrics/     -- lyrics planning output
        style/      -- style planning output
        audio/      -- raw generated audio
        post/       -- post-processed audio
        final/      -- final output + metadata JSON
"""

import logging
import time
from pathlib import Path

from ace_music.schemas.repair import ArtifactRecord, ArtifactStatus, RunManifest

logger = logging.getLogger(__name__)

STAGE_DIRS = {
    "lyrics_planner": "lyrics",
    "style_planner": "style",
    "generator": "audio",
    "post_processor": "post",
    "output": "final",
}


class WorkspaceManager:
    """Manage structured output directories and run manifests."""

    def __init__(self, base_dir: str = "./output") -> None:
        self._base_dir = Path(base_dir)

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def _run_dir(self, run_id: str) -> Path:
        return self._base_dir / run_id

    def _manifest_path(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "manifest.json"

    def create_run(
        self,
        run_id: str | None = None,
        description: str = "",
        seed: int | None = None,
    ) -> str:
        """Create a new run directory with stage subdirectories and manifest."""
        if not run_id:
            run_id = f"run_{time.strftime('%Y%m%d_%H%M%S')}"

        run_dir = self._run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)

        for stage_dir in STAGE_DIRS.values():
            (run_dir / stage_dir).mkdir(exist_ok=True)

        manifest = RunManifest(
            run_id=run_id,
            description=description,
            seed=seed,
        )
        self._write_manifest(manifest)

        logger.info("Created run directory: %s", run_dir)
        return str(run_dir)

    def update_artifact(
        self,
        run_id: str,
        stage: str,
        status: ArtifactStatus,
        file_path: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Update an artifact's status in the manifest."""
        manifest = self.load_manifest(run_id)
        manifest.artifacts[stage] = ArtifactRecord(
            stage=stage,
            status=status,
            file_path=file_path,
            error_message=error_message,
        )
        self._write_manifest(manifest)

    def load_manifest(self, run_id: str) -> RunManifest:
        """Load the manifest for a run."""
        path = self._manifest_path(run_id)
        if not path.exists():
            raise FileNotFoundError(f"Manifest not found: {path}")
        return RunManifest.model_validate_json(path.read_text())

    def list_runs(self) -> list[str]:
        """List all run IDs in the base directory."""
        if not self._base_dir.exists():
            return []
        return sorted(
            d.name
            for d in self._base_dir.iterdir()
            if d.is_dir() and (d / "manifest.json").exists()
        )

    def stage_dir(self, run_id: str, stage: str) -> str:
        """Get the output directory for a specific stage within a run."""
        dir_name = STAGE_DIRS.get(stage, stage)
        path = self._run_dir(run_id) / dir_name
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def _write_manifest(self, manifest: RunManifest) -> None:
        """Write manifest to disk."""
        path = self._manifest_path(manifest.run_id)
        path.write_text(manifest.model_dump_json(indent=2))
