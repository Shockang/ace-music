"""DirectorBridge adapter helpers.

Converts `DirectorBridge.Request` into `PipelineInput` and
`PipelineOutput` into `DirectorBridge.Response`.
"""

from ace_music.bridge import DirectorBridge
from ace_music.schemas.audio_contract import (
    AudioLayerPolicy,
    AudioSceneContract,
    MixPolicy,
    TransitionPolicy,
    TTSSegment,
)
from ace_music.schemas.pipeline import PipelineInput, PipelineOutput


def request_to_pipeline_input(req: DirectorBridge.Request) -> PipelineInput:
    """Convert a scene-oriented bridge request into pipeline input."""
    description_parts: list[str] = []
    if req.style_reference:
        description_parts.append(req.style_reference)
    elif req.scene_description:
        description_parts.append(req.scene_description)
    else:
        description_parts.append(f"{req.mood} background music")

    if req.scene_description and req.style_reference:
        description_parts.append(req.scene_description)

    mix_updates: dict[str, float] = {}
    if req.target_lufs is not None:
        mix_updates["target_lufs"] = req.target_lufs
    if req.max_true_peak_db is not None:
        mix_updates["max_true_peak_db"] = req.max_true_peak_db
    mix = MixPolicy().model_copy(update=mix_updates)

    transition_updates: dict[str, float] = {}
    if req.crossfade_seconds is not None:
        transition_updates["crossfade_seconds"] = req.crossfade_seconds
    transition = TransitionPolicy().model_copy(update=transition_updates)

    tts_segments = [TTSSegment.model_validate(segment) for segment in req.tts_segments or []]
    contract = AudioSceneContract(
        scene_id=req.scene_id,
        duration_seconds=req.duration_seconds,
        mood=req.mood,
        scene_description=req.scene_description,
        valence=req.valence,
        arousal=req.arousal,
        intensity=req.intensity if req.intensity is not None else 0.5,
        shot_count=req.shot_count,
        dialogue_density=req.dialogue_density,
        layers=AudioLayerPolicy(tts_present=req.tts_present),
        transition=transition,
        mix=mix,
        tts_segments=tts_segments,
    )

    return PipelineInput(
        description=" ".join(description_parts),
        lyrics=req.lyrics_hint,
        duration_seconds=req.duration_seconds,
        mood=req.mood,
        tempo_preference=req.tempo_preference,
        output_format=req.output_format,
        seed=req.seed,
        preset_name=req.preset_name,
        is_instrumental=req.is_instrumental,
        audio_contract=contract,
    )


def pipeline_output_to_response(
    output: PipelineOutput, req: DirectorBridge.Request
) -> DirectorBridge.Response:
    """Convert pipeline output back into the public bridge response."""
    return DirectorBridge.Response(
        audio_path=output.audio_path,
        duration_seconds=output.duration_seconds,
        format=output.format,
        metadata=output.metadata,
        scene_id=req.scene_id,
        success=True,
    )
