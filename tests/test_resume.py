"""Tests for run manifest, repair tickets, and resume functionality."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from ace_music.schemas.repair import (
    ArtifactStatus,
    ArtifactRecord,
    RunManifest,
    RepairTicket,
)


class TestArtifactRecord:
    def test_artifact_record_creation(self):
        record = ArtifactRecord(
            stage="generator",
            status=ArtifactStatus.COMPLETED,
            file_path="/tmp/output/mock_42.wav",
        )
        assert record.stage == "generator"
        assert record.status == ArtifactStatus.COMPLETED

    def test_artifact_record_with_error(self):
        record = ArtifactRecord(
            stage="generator",
            status=ArtifactStatus.FAILED,
            file_path=None,
            error_message="CUDA out of memory",
        )
        assert record.status == ArtifactStatus.FAILED
        assert record.error_message == "CUDA out of memory"


class TestRunManifest:
    def test_minimal_manifest(self):
        manifest = RunManifest(
            run_id="run_20260414_120000",
            description="test run",
        )
        assert manifest.run_id == "run_20260414_120000"
        assert manifest.artifacts == {}

    def test_manifest_with_artifacts(self):
        manifest = RunManifest(
            run_id="run_1",
            description="test",
            artifacts={
                "lyrics_planner": ArtifactRecord(
                    stage="lyrics_planner",
                    status=ArtifactStatus.COMPLETED,
                    file_path="/tmp/lyrics.json",
                ),
                "generator": ArtifactRecord(
                    stage="generator",
                    status=ArtifactStatus.FAILED,
                    error_message="GPU OOM",
                ),
            },
        )
        assert len(manifest.artifacts) == 2
        assert manifest.failed_stages == ["generator"]

    def test_manifest_completed_stages(self):
        manifest = RunManifest(
            run_id="run_1",
            description="test",
            artifacts={
                "lyrics_planner": ArtifactRecord(stage="lyrics_planner", status=ArtifactStatus.COMPLETED),
                "style_planner": ArtifactRecord(stage="style_planner", status=ArtifactStatus.COMPLETED),
                "generator": ArtifactRecord(stage="generator", status=ArtifactStatus.FAILED),
            },
        )
        assert manifest.completed_stages == ["lyrics_planner", "style_planner"]

    def test_manifest_next_stage(self):
        manifest = RunManifest(
            run_id="run_1",
            description="test",
            artifacts={
                "lyrics_planner": ArtifactRecord(stage="lyrics_planner", status=ArtifactStatus.COMPLETED),
                "style_planner": ArtifactRecord(stage="style_planner", status=ArtifactStatus.COMPLETED),
                "generator": ArtifactRecord(stage="generator", status=ArtifactStatus.FAILED),
            },
        )
        assert manifest.next_stage == "generator"

    def test_manifest_next_stage_all_completed(self):
        manifest = RunManifest(
            run_id="run_1",
            description="test",
            artifacts={
                s: ArtifactRecord(stage=s, status=ArtifactStatus.COMPLETED)
                for s in ["lyrics_planner", "style_planner", "generator", "post_processor", "output"]
            },
        )
        assert manifest.next_stage is None

    def test_manifest_json_roundtrip(self, tmp_path):
        manifest = RunManifest(
            run_id="run_test",
            description="roundtrip test",
            artifacts={
                "generator": ArtifactRecord(stage="generator", status=ArtifactStatus.COMPLETED),
            },
        )
        path = tmp_path / "manifest.json"
        path.write_text(manifest.model_dump_json(indent=2))
        loaded = RunManifest.model_validate_json(path.read_text())
        assert loaded.run_id == "run_test"
        assert loaded.artifacts["generator"].status == ArtifactStatus.COMPLETED


class TestRepairTicket:
    def test_repair_ticket_creation(self):
        ticket = RepairTicket(
            stage="generator",
            error_type="gpu_oom",
            message="CUDA out of memory. Try reducing batch_size or infer_step.",
            recoverable=True,
        )
        assert ticket.recoverable is True
        assert ticket.stage == "generator"

    def test_repair_ticket_defaults(self):
        ticket = RepairTicket(
            stage="generator",
            error_type="unknown",
            message="Something went wrong",
        )
        assert ticket.recoverable is False
        assert ticket.suggested_fix is None
