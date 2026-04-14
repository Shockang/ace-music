"""Schema models for ace-music pipeline."""

from .audio import AudioOutput, ProcessedAudio
from .lyrics import LyricSegment, LyricsInput, LyricsOutput, SegmentType
from .pipeline import PipelineInput, PipelineOutput
from .preset import PresetFile, PresetStyleOverrides, StylePreset
from .repair import PIPELINE_STAGES, ArtifactRecord, ArtifactStatus, RepairTicket, RunManifest
from .style import StyleInput, StyleOutput

__all__ = [
    "ArtifactRecord",
    "ArtifactStatus",
    "AudioOutput",
    "LyricSegment",
    "LyricsInput",
    "LyricsOutput",
    "PIPELINE_STAGES",
    "PipelineInput",
    "PipelineOutput",
    "PresetFile",
    "PresetStyleOverrides",
    "ProcessedAudio",
    "RepairTicket",
    "RunManifest",
    "SegmentType",
    "StyleInput",
    "StyleOutput",
    "StylePreset",
]
