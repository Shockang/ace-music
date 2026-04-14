"""MusicAgent: Planning-mode orchestrator for the music generation pipeline.

Orchestrates the five-stage pipeline:
1. LyricsPlanner  — parse/structure lyrics
2. StylePlanner   — map style to ACE-Step params
3. Generator      — call ACE-Step model
4. PostProcessor  — normalize and convert
5. OutputWorker   — write final files + metadata

Design follows the Planning pattern: the agent prepares a plan (which tools
to run in what order), then executes sequentially, passing outputs forward.
"""

import logging
import random

from ace_music.resume import stages_to_run
from ace_music.schemas.audio import AudioOutput, ProcessedAudio
from ace_music.schemas.pipeline import PipelineInput, PipelineOutput
from ace_music.schemas.repair import ArtifactStatus
from ace_music.tools.generator import ACEStepGenerator, GenerationInput, GeneratorConfig
from ace_music.tools.lyrics_planner import LyricsPlanner
from ace_music.tools.output import OutputInput, OutputWorker
from ace_music.tools.post_processor import PostProcessInput, PostProcessor
from ace_music.tools.preset_resolver import PresetResolver
from ace_music.tools.style_planner import StylePlanner
from ace_music.workspace import WorkspaceManager

logger = logging.getLogger(__name__)


class MusicAgent:
    """Planning-mode music generation agent.

    Usage:
        agent = MusicAgent()
        result = await agent.run(PipelineInput(
            description="A dreamy synthwave track about neon cities",
            duration_seconds=60.0,
        ))
    """

    def __init__(
        self,
        generator_config: GeneratorConfig | None = None,
        preset_resolver: PresetResolver | None = None,
    ) -> None:
        self._lyrics_planner = LyricsPlanner()
        self._style_planner = StylePlanner()
        self._generator = ACEStepGenerator(generator_config)
        self._post_processor = PostProcessor()
        self._output_worker = OutputWorker()
        self._preset_resolver = preset_resolver or PresetResolver()

    def _build_plan(self, input_data: PipelineInput) -> list[str]:
        """Build execution plan from input. Returns list of tool names to execute."""
        plan = []

        # Step 1: Lyrics planning (skip if instrumental)
        if not input_data.is_instrumental and (input_data.lyrics or input_data.description):
            plan.append("lyrics_planner")

        # Step 2: Style planning (always needed)
        plan.append("style_planner")

        # Step 3: Generation (always needed)
        plan.append("generator")

        # Step 4: Post-processing (always needed)
        plan.append("post_processor")

        # Step 5: Output (always needed)
        plan.append("output")

        return plan

    async def run(
        self,
        input_data: PipelineInput,
        workspace: WorkspaceManager | None = None,
        run_id: str | None = None,
    ) -> PipelineOutput:
        """Execute the full music generation pipeline.

        Args:
            input_data: Pipeline input with description, style, duration, etc.
            workspace: Optional workspace for manifest tracking.
            run_id: Optional run ID for manifest tracking.

        Returns:
            PipelineOutput with final audio path and metadata.
        """
        plan = self._build_plan(input_data)
        logger.info("Pipeline plan: %s", " -> ".join(plan))
        seed = input_data.seed if input_data.seed is not None else random.randint(
            0, 2**32 - 1
        )

        if workspace and run_id and not workspace.manifest_exists(run_id):
            workspace.create_run(run_id, description=input_data.description, seed=seed)

        # Stage 1: Lyrics planning
        lyrics_output = None
        if "lyrics_planner" in plan:
            from ace_music.schemas.lyrics import LyricsInput

            lyrics_input = LyricsInput(
                raw_text=input_data.lyrics or input_data.description,
                language=input_data.language,
                is_instrumental=input_data.is_instrumental,
            )
            lyrics_output = await self._lyrics_planner.execute(lyrics_input)
            logger.info(
                "Lyrics: %d segments, instrumental=%s",
                len(lyrics_output.segments),
                lyrics_output.is_instrumental,
            )
            if workspace and run_id:
                workspace.update_artifact(run_id, "lyrics_planner", ArtifactStatus.COMPLETED)

        # Stage 2: Style planning
        from ace_music.schemas.style import StyleInput

        # Resolve preset if specified
        preset = None
        if input_data.preset_name:
            match = await self._preset_resolver.resolve(input_data.preset_name)
            if match:
                preset = match.preset
                logger.info("Resolved preset: %s (confidence=%.2f)", preset.id, match.confidence)
            else:
                logger.warning(
                    "Preset '%s' not found, using heuristic style",
                    input_data.preset_name,
                )

        style_input = StyleInput(
            description=input_data.description,
            reference_tags=input_data.style_tags,
            tempo_preference=input_data.tempo_preference,
            mood=input_data.mood,
        )
        style_output = await self._style_planner.execute(style_input, preset=preset)

        # Apply user overrides
        if input_data.guidance_scale is not None:
            style_output = style_output.model_copy(
                update={"guidance_scale": input_data.guidance_scale}
            )
        if input_data.infer_step is not None:
            style_output = style_output.model_copy(update={"infer_step": input_data.infer_step})

        logger.info("Style: prompt=%r, guidance=%.1f, steps=%d",
                     style_output.prompt, style_output.guidance_scale, style_output.infer_step)
        if workspace and run_id:
            workspace.update_artifact(run_id, "style_planner", ArtifactStatus.COMPLETED)

        # Stage 3: Generation
        from ace_music.schemas.lyrics import LyricsOutput

        gen_input = GenerationInput(
            lyrics=lyrics_output or LyricsOutput(
                formatted_lyrics="",
                is_instrumental=input_data.is_instrumental,
            ),
            style=style_output,
            audio_duration=input_data.duration_seconds,
            seed=seed,
            output_dir=input_data.output_dir,
            format=input_data.output_format,
        )
        audio_output = await self._generator.execute(gen_input)
        logger.info("Generated: %s (%.1fs)", audio_output.file_path, audio_output.duration_seconds)
        if workspace and run_id:
            workspace.update_artifact(
                run_id, "generator", ArtifactStatus.COMPLETED,
                file_path=audio_output.file_path,
            )

        # Stage 4: Post-processing
        pp_input = PostProcessInput(
            audio=audio_output,
            target_format=input_data.output_format,
            output_dir=input_data.output_dir,
        )
        processed = await self._post_processor.execute(pp_input)
        logger.info("Post-processed: %s", processed.file_path)
        if workspace and run_id:
            workspace.update_artifact(run_id, "post_processor", ArtifactStatus.COMPLETED)

        # Stage 5: Output
        out_input = OutputInput(
            audio=processed,
            style=style_output,
            seed=seed,
            lyrics_text=lyrics_output.formatted_lyrics if lyrics_output else "",
            description=input_data.description,
            output_dir=input_data.output_dir,
            output_config=input_data.output_config,
        )
        result = await self._output_worker.execute(out_input)
        logger.info("Output: %s", result.audio_path)
        if workspace and run_id:
            workspace.update_artifact(run_id, "output", ArtifactStatus.COMPLETED)

        # Build pipeline output
        segments_info = []
        if lyrics_output and lyrics_output.segments:
            for seg in lyrics_output.segments:
                segments_info.append({
                    "type": seg.segment_type.value,
                    "lines": seg.lines,
                    "time_start": seg.time_start,
                    "time_end": seg.time_end,
                })

        return PipelineOutput(
            audio_path=result.audio_path,
            duration_seconds=result.duration_seconds,
            format=result.format,
            sample_rate=result.sample_rate,
            metadata=result.metadata,
            segments=segments_info,
        )

    async def resume(
        self,
        run_id: str,
        workspace: WorkspaceManager,
    ) -> PipelineOutput | None:
        """Resume a pipeline run from the last completed stage."""
        from ace_music.schemas.lyrics import LyricsInput, LyricsOutput
        from ace_music.schemas.style import StyleInput, StyleOutput
        from ace_music.tools.generator import GenerationInput
        from ace_music.tools.post_processor import PostProcessInput

        manifest = workspace.load_manifest(run_id)
        remaining = stages_to_run(manifest)

        if not remaining:
            logger.info("Run %s is already complete", run_id)
            return None

        logger.info("Resuming run %s from stage: %s", run_id, remaining[0])

        input_data = PipelineInput(
            description=manifest.description,
            seed=manifest.seed,
            preset_name=manifest.preset_name,
            output_dir=workspace.stage_dir(run_id, "final"),
        )

        seed = manifest.seed or random.randint(0, 2**32 - 1)

        # Load intermediate outputs from completed stages
        lyrics_output = None
        style_output = None
        audio_output = None
        processed = None

        completed = set(manifest.completed_stages)

        if "lyrics_planner" in completed:
            lyrics_output = LyricsOutput(
                formatted_lyrics="", is_instrumental=input_data.is_instrumental
            )

        if "style_planner" in completed:
            style_output = StyleOutput(prompt=input_data.description)

        if "generator" in completed:
            gen_record = manifest.artifacts.get("generator")
            if gen_record and gen_record.file_path:
                audio_output = AudioOutput(
                    file_path=gen_record.file_path,
                    duration_seconds=input_data.duration_seconds,
                    sample_rate=48000,
                    format="wav",
                    channels=2,
                )

        if "post_processor" in completed:
            pp_record = manifest.artifacts.get("post_processor")
            if pp_record and pp_record.file_path:
                processed = ProcessedAudio(
                    file_path=pp_record.file_path,
                    duration_seconds=input_data.duration_seconds,
                    sample_rate=48000,
                    format="wav",
                    channels=2,
                    loudness_lufs=-14.0,
                    peak_db=-1.0,
                )

        # Stage 1: Lyrics planning
        if "lyrics_planner" in remaining:
            try:
                lyrics_input = LyricsInput(
                    raw_text=input_data.description,
                    is_instrumental=input_data.is_instrumental,
                )
                lyrics_output = await self._lyrics_planner.execute(lyrics_input)
                workspace.update_artifact(run_id, "lyrics_planner", ArtifactStatus.COMPLETED)
            except Exception as e:
                workspace.update_artifact(
                    run_id, "lyrics_planner", ArtifactStatus.FAILED,
                    error_message=str(e),
                )
                raise

        # Stage 2: Style planning
        if "style_planner" in remaining:
            try:
                preset = None
                if input_data.preset_name:
                    match = await self._preset_resolver.resolve(input_data.preset_name)
                    if match:
                        preset = match.preset

                style_input = StyleInput(description=input_data.description)
                style_output = await self._style_planner.execute(style_input, preset=preset)
                workspace.update_artifact(run_id, "style_planner", ArtifactStatus.COMPLETED)
            except Exception as e:
                workspace.update_artifact(
                    run_id, "style_planner", ArtifactStatus.FAILED,
                    error_message=str(e),
                )
                raise

        # Stage 3: Generation
        if "generator" in remaining:
            try:
                gen_input = GenerationInput(
                    lyrics=lyrics_output or LyricsOutput(
                        formatted_lyrics="", is_instrumental=True
                    ),
                    style=style_output or StyleOutput(prompt=input_data.description),
                    audio_duration=input_data.duration_seconds,
                    seed=seed,
                    output_dir=workspace.stage_dir(run_id, "generator"),
                )
                audio_output = await self._generator.execute(gen_input)
                workspace.update_artifact(
                    run_id, "generator", ArtifactStatus.COMPLETED,
                    file_path=audio_output.file_path,
                )
            except Exception as e:
                workspace.update_artifact(
                    run_id, "generator", ArtifactStatus.FAILED,
                    error_message=str(e),
                )
                raise

        # Stage 4: Post-processing
        if "post_processor" in remaining and audio_output:
            try:
                pp_input = PostProcessInput(
                    audio=audio_output,
                    output_dir=workspace.stage_dir(run_id, "post_processor"),
                )
                processed = await self._post_processor.execute(pp_input)
                workspace.update_artifact(run_id, "post_processor", ArtifactStatus.COMPLETED)
            except Exception as e:
                workspace.update_artifact(
                    run_id, "post_processor", ArtifactStatus.FAILED,
                    error_message=str(e),
                )
                raise

        # Stage 5: Output
        if "output" in remaining and processed:
            try:
                out_input = OutputInput(
                    audio=processed,
                    style=style_output or StyleOutput(prompt=input_data.description),
                    seed=seed,
                    description=input_data.description,
                    output_dir=workspace.stage_dir(run_id, "output"),
                )
                result = await self._output_worker.execute(out_input)
                workspace.update_artifact(run_id, "output", ArtifactStatus.COMPLETED)

                return PipelineOutput(
                    audio_path=result.audio_path,
                    duration_seconds=result.duration_seconds,
                    format=result.format,
                    sample_rate=result.sample_rate,
                    metadata=result.metadata,
                )
            except Exception as e:
                workspace.update_artifact(
                    run_id, "output", ArtifactStatus.FAILED,
                    error_message=str(e),
                )
                raise

        return None
