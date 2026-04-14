"""Run manifest and repair ticket models for pipeline error recovery."""

from enum import Enum

from pydantic import BaseModel, Field

PIPELINE_STAGES = [
    "lyrics_planner",
    "style_planner",
    "generator",
    "post_processor",
    "output",
]


class ArtifactStatus(str, Enum):
    """Status of a pipeline stage artifact."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ArtifactRecord(BaseModel):
    """Record of a single pipeline stage's execution result."""

    stage: str
    status: ArtifactStatus
    file_path: str | None = None
    error_message: str | None = None
    duration_seconds: float | None = None


class RunManifest(BaseModel):
    """Manifest tracking the state of a pipeline run."""

    run_id: str
    description: str = ""
    seed: int | None = None
    preset_name: str | None = None
    artifacts: dict[str, ArtifactRecord] = Field(default_factory=dict)

    @property
    def completed_stages(self) -> list[str]:
        """List of stages that completed successfully, in pipeline order."""
        return [
            name
            for name in PIPELINE_STAGES
            if name in self.artifacts and self.artifacts[name].status == ArtifactStatus.COMPLETED
        ]

    @property
    def failed_stages(self) -> list[str]:
        """List of stages that failed."""
        return [
            name
            for name in PIPELINE_STAGES
            if name in self.artifacts and self.artifacts[name].status == ArtifactStatus.FAILED
        ]

    @property
    def next_stage(self) -> str | None:
        """The next stage to execute (first non-completed stage in pipeline order)."""
        completed = set(self.completed_stages)
        for stage in PIPELINE_STAGES:
            if stage not in completed:
                return stage
        return None


class RepairTicket(BaseModel):
    """A repair ticket describing a failure and how to fix it."""

    stage: str
    error_type: str
    message: str
    recoverable: bool = False
    suggested_fix: str | None = None
