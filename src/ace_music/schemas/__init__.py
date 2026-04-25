"""Schema models for ace-music pipeline."""

from .audio import AudioOutput, ProcessedAudio
from .lyrics import LyricSegment, LyricsInput, LyricsOutput, SegmentType
from .material import MaterialContext, MaterialEntry, MaterialSource
from .output_config import OutputConfig
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
    "MaterialContext",
    "MaterialEntry",
    "MaterialSource",
    "PIPELINE_STAGES",
    "PipelineInput",
    "OutputConfig",
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
