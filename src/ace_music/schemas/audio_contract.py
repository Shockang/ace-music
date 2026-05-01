"""Narrative and mix contract models for contract-driven audio generation."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class AudioLayerPolicy(BaseModel):
    """Which audio layers are present in the final composition."""

    tts_present: bool = True
    bgm_present: bool = True
    ambience_present: bool = False
    effects_present: bool = False


class TransitionPolicy(BaseModel):
    """Transition constraints for adjacent musical sections."""

    crossfade_seconds: float = Field(default=1.5, ge=0.0, le=10.0)
    allow_looping: bool = True
    require_seamless_tail: bool = True


class MixPolicy(BaseModel):
    """Mixing targets for downstream composition and mastering."""

    target_lufs: float = Field(default=-18.0, ge=-30.0, le=-10.0)
    max_true_peak_db: float = Field(default=-1.5, ge=-6.0, le=0.0)
    bgm_gain_db: float = Field(default=-14.0, ge=-30.0, le=0.0)
    ducking_db: float = Field(default=8.0, ge=0.0, le=24.0)
    sidechain_source: Literal["tts", "none"] = "tts"


class AudioQATargets(BaseModel):
    """Machine-checkable quality targets for audio delivery."""

    duration_tolerance_seconds: float = Field(default=1.0, ge=0.0, le=10.0)
    min_emotion_match_score: float = Field(default=0.75, ge=0.0, le=1.0)
    max_dialogue_conflict_rate: float = Field(default=0.05, ge=0.0, le=1.0)
    min_composition_success_rate: float = Field(default=0.98, ge=0.0, le=1.0)


class AudioSegmentCue(BaseModel):
    """Boundary cue for an optional sub-segment within a scene contract."""

    segment_id: str
    start_seconds: float = Field(ge=0.0)
    end_seconds: float = Field(gt=0.0)
    mood: str | None = None
    intensity: float | None = Field(default=None, ge=0.0, le=1.0)
    transition: TransitionPolicy | None = None

    @model_validator(mode="after")
    def validate_range(self) -> "AudioSegmentCue":
        if self.end_seconds <= self.start_seconds:
            raise ValueError("end_seconds must be greater than start_seconds")
        return self


class TTSSegment(BaseModel):
    """TTS timing window used for ducking the background music."""

    start_seconds: float = Field(ge=0.0)
    end_seconds: float = Field(gt=0.0)

    @model_validator(mode="after")
    def validate_range(self) -> "TTSSegment":
        if self.end_seconds <= self.start_seconds:
            raise ValueError("end_seconds must be greater than start_seconds")
        return self


class AudioSceneContract(BaseModel):
    """Structured scene-level audio request from upstream orchestration."""

    scene_id: str
    duration_seconds: float = Field(ge=5.0, le=240.0)
    mood: str
    scene_description: str | None = None
    narrative_beat: str | None = None
    valence: float | None = Field(default=None, ge=-1.0, le=1.0)
    arousal: float | None = Field(default=None, ge=0.0, le=1.0)
    intensity: float = Field(default=0.5, ge=0.0, le=1.0)
    shot_count: int | None = Field(default=None, ge=0)
    dialogue_density: float = Field(default=0.5, ge=0.0, le=1.0)
    role_theme: str | None = None
    layers: AudioLayerPolicy = Field(default_factory=AudioLayerPolicy)
    transition: TransitionPolicy = Field(default_factory=TransitionPolicy)
    mix: MixPolicy = Field(default_factory=MixPolicy)
    qa_targets: AudioQATargets = Field(default_factory=AudioQATargets)
    segments: list[AudioSegmentCue] = Field(default_factory=list)
    tts_segments: list[TTSSegment] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_segments(self) -> "AudioSceneContract":
        previous_segment: AudioSegmentCue | None = None

        for segment in self.segments:
            if segment.end_seconds > self.duration_seconds:
                raise ValueError(
                    f"segment '{segment.segment_id}' end_seconds must be <= duration_seconds"
                )

            if previous_segment is None:
                previous_segment = segment
                continue

            if segment.start_seconds < previous_segment.start_seconds:
                raise ValueError("segments must be ordered by start_seconds")

            if segment.start_seconds < previous_segment.end_seconds:
                raise ValueError(
                    f"segments must not overlap: '{previous_segment.segment_id}' "
                    f"and '{segment.segment_id}'"
                )

            previous_segment = segment

        previous_tts_segment: TTSSegment | None = None

        for tts_segment in self.tts_segments:
            if tts_segment.end_seconds > self.duration_seconds:
                raise ValueError("tts_segments end_seconds must be <= duration_seconds")

            if previous_tts_segment is None:
                previous_tts_segment = tts_segment
                continue

            if tts_segment.start_seconds < previous_tts_segment.start_seconds:
                raise ValueError("tts_segments must be ordered by start_seconds")

            if tts_segment.start_seconds < previous_tts_segment.end_seconds:
                raise ValueError("tts_segments must not overlap")

            previous_tts_segment = tts_segment

        return self
