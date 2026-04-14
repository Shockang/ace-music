"""Resume logic: determine which stages to skip when resuming a failed run."""

from ace_music.schemas.repair import PIPELINE_STAGES, RunManifest


def stages_to_run(manifest: RunManifest) -> list[str]:
    """Return the list of stages that still need to execute.

    A stage is skipped if it is already COMPLETED in the manifest.
    FAILED stages are re-run.
    """
    completed = set(manifest.completed_stages)
    return [s for s in PIPELINE_STAGES if s not in completed]
