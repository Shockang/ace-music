"""Tests for WorkspaceManager."""

import json
from pathlib import Path

import pytest

from ace_music.schemas.repair import ArtifactRecord, ArtifactStatus, RunManifest
from ace_music.workspace import WorkspaceManager


class TestWorkspaceManager:
    def test_create_run_directory(self, tmp_path):
        wm = WorkspaceManager(base_dir=str(tmp_path / "output"))
        run_dir = wm.create_run("run_001", description="test run")
        assert Path(run_dir).exists()
        assert Path(run_dir).is_dir()

    def test_manifest_written_on_create(self, tmp_path):
        wm = WorkspaceManager(base_dir=str(tmp_path / "output"))
        run_dir = wm.create_run("run_001", description="test run")
        manifest_path = Path(run_dir) / "manifest.json"
        assert manifest_path.exists()
        data = json.loads(manifest_path.read_text())
        assert data["run_id"] == "run_001"

    def test_update_artifact(self, tmp_path):
        wm = WorkspaceManager(base_dir=str(tmp_path / "output"))
        run_dir = wm.create_run("run_001", description="test")
        wm.update_artifact(
            run_id="run_001",
            stage="generator",
            status=ArtifactStatus.COMPLETED,
            file_path="/tmp/output/test.wav",
        )
        manifest = wm.load_manifest("run_001")
        assert manifest.artifacts["generator"].status == ArtifactStatus.COMPLETED

    def test_load_manifest_roundtrip(self, tmp_path):
        wm = WorkspaceManager(base_dir=str(tmp_path / "output"))
        run_dir = wm.create_run("run_001", description="roundtrip test", seed=42)
        wm.update_artifact("run_001", "style_planner", ArtifactStatus.COMPLETED)

        loaded = wm.load_manifest("run_001")
        assert loaded.run_id == "run_001"
        assert loaded.seed == 42
        assert loaded.artifacts["style_planner"].status == ArtifactStatus.COMPLETED

    def test_list_runs(self, tmp_path):
        wm = WorkspaceManager(base_dir=str(tmp_path / "output"))
        wm.create_run("run_001", description="first")
        wm.create_run("run_002", description="second")
        runs = wm.list_runs()
        assert len(runs) == 2
        assert "run_001" in runs
        assert "run_002" in runs

    def test_run_dir_structure(self, tmp_path):
        wm = WorkspaceManager(base_dir=str(tmp_path / "output"))
        run_dir = wm.create_run("run_001", description="structure test")
        for stage in ["lyrics", "style", "audio", "post", "final"]:
            assert (Path(run_dir) / stage).exists()
