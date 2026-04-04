"""DirectorBridge: auto-director integration adapter.

Converts DirectorBridge.Request into PipelineInput and
PipelineOutput into DirectorBridge.Response.
"""

from ace_music.bridge import DirectorBridge
from ace_music.schemas.pipeline import PipelineInput, PipelineOutput


def request_to_pipeline_input(req: DirectorBridge.Request) -> PipelineInput:
    """Convert a DirectorBridge.Request to PipelineInput."""
    return PipelineInput(
        description=req.style_reference or f"{req.mood} background music",
        lyrics=req.lyrics_hint,
        duration_seconds=req.duration_seconds,
        mood=req.mood,
        tempo_preference=req.tempo_preference,
        output_format=req.output_format,
        seed=req.seed,
    )


def pipeline_output_to_response(
    output: PipelineOutput, req: DirectorBridge.Request
) -> DirectorBridge.Response:
    """Convert PipelineOutput to DirectorBridge.Response."""
    return DirectorBridge.Response(
        audio_path=output.audio_path,
        duration_seconds=output.duration_seconds,
        format=output.format,
        metadata=output.metadata,
        scene_id=req.scene_id,
    )
