"""Schema models for ace-music pipeline."""

from .audio import AudioOutput, ProcessedAudio
from .lyrics import LyricSegment, LyricsInput, LyricsOutput, SegmentType
from .pipeline import PipelineInput, PipelineOutput
from .preset import PresetFile, PresetStyleOverrides, StylePreset
from .style import StyleInput, StyleOutput

__all__ = [
    "AudioOutput",
    "LyricSegment",
    "LyricsInput",
    "LyricsOutput",
    "PipelineInput",
    "PipelineOutput",
    "PresetFile",
    "PresetStyleOverrides",
    "ProcessedAudio",
    "SegmentType",
    "StyleInput",
    "StyleOutput",
    "StylePreset",
]
