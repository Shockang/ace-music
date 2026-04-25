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

import inspect
import logging
import random
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

from ace_music.errors import OutputValidationError, PipelineTimeoutError
from ace_music.providers.router import FeatureRouter
from ace_music.resume import stages_to_run
from ace_music.schemas.audio import AudioOutput, ProcessedAudio
from ace_music.schemas.pipeline import PipelineInput, PipelineOutput
from ace_music.schemas.repair import ArtifactStatus
from ace_music.tools.audio_validator import AudioValidator
from ace_music.tools.emotion_mapper import map_scene_contract
from ace_music.tools.generator import ACEStepGenerator, GenerationInput, GeneratorConfig
from ace_music.tools.lyrics_planner import LyricsPlanner
from ace_music.tools.minimax_generator import MiniMaxMusicGenerator
from ace_music.tools.output import OutputInput, OutputWorker
from ace_music.tools.post_processor import PostProcessInput, PostProcessor
from ace_music.tools.preset_resolver import PresetResolver
from ace_music.tools.style_planner import StylePlanner
from ace_music.workspace import WorkspaceManager

logger = logging.getLogger(__name__)
StageResult = TypeVar("StageResult")


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
        feature_router: FeatureRouter | None = None,
    ) -> None:
        self._lyrics_planner = LyricsPlanner()
        self._style_planner = StylePlanner()
        self._generator = ACEStepGenerator(generator_config)
        self._minimax_generator: MiniMaxMusicGenerator | None = None
        self._post_processor = PostProcessor()
        self._output_worker = OutputWorker()
        self._audio_validator = AudioValidator()
        self._preset_resolver = preset_resolver or PresetResolver()
        # TODO: Wire FeatureRouter into lyrics_planner/style_planner for LLM-assisted planning
        self._feature_router = feature_router

    def _build_plan(self, input_data: PipelineInput) -> list[str]:
        """Build execution plan from input. Returns list of tool names to execute."""
        if input_data.backend == "minimax":
            return ["minimax_generator", "output"]

        plan = []

        # Step 1: Lyrics planning (skip if instrumental)
        if not input_data.is_instrumental and (input_data.lyrics or input_data.description):
            plan.append("lyrics_planner")

        # Step 2: Style planning (always needed for ACEStep)
        plan.append("style_planner")

        # Step 3: Generation
        plan.append("generator")

        # Step 4: Post-processing
        plan.append("post_processor")

        # Step 5: Output
        plan.append("output")

        return plan

    async def _run_stage(
        self,
        stage: str,
        operation: Awaitable[StageResult] | Callable[[], StageResult],
        timeout_seconds: float | None,
        workspace: WorkspaceManager | None,
        run_id: str | None,
    ) -> StageResult:
        """Run one pipeline stage with consistent logs, timeout, and manifest errors."""
        import asyncio

        logger.info("Stage start: %s", stage)
        started_at = time.monotonic()
        try:
            if inspect.isawaitable(operation):
                awaitable = operation
            else:
                awaitable = asyncio.to_thread(operation)
            if timeout_seconds is not None and timeout_seconds > 0:
                result = await asyncio.wait_for(awaitable, timeout=timeout_seconds)
            else:
                result = await awaitable
        except TimeoutError as exc:
            elapsed = time.monotonic() - started_at
            message = f"Stage {stage!r} timed out after {timeout_seconds:g}s"
            logger.error("%s (elapsed %.2fs)", message, elapsed)
            if workspace and run_id:
                workspace.update_artifact(
                    run_id, stage, ArtifactStatus.FAILED, error_message=message
                )
            raise PipelineTimeoutError(message) from exc
        except Exception as exc:
            elapsed = time.monotonic() - started_at
            logger.error("Stage failed: %s (elapsed %.2fs): %s", stage, elapsed, exc)
            logger.debug("Stage failure traceback", exc_info=True)
            if workspace and run_id:
                workspace.update_artifact(
                    run_id, stage, ArtifactStatus.FAILED, error_message=str(exc)
                )
            raise

        logger.info("Stage complete: %s (%.2fs)", stage, time.monotonic() - started_at)
        return result

    async def _run_minimax_pipeline(
        self,
        input_data: PipelineInput,
        workspace: WorkspaceManager | None,
        run_id: str | None,
    ) -> PipelineOutput:
        """Simplified pipeline for MiniMax cloud API backend."""
        from pathlib import Path

        from ace_music.schemas.style import StyleOutput
        from ace_music.tools.minimax_generator import MiniMaxMusicInput

        pipeline_started_at = time.monotonic()
        seed = input_data.seed if input_data.seed is not None else random.randint(0, 2**32 - 1)
        stage_timeout = input_data.stage_timeout_seconds

        if self._minimax_generator is None:
            self._minimax_generator = MiniMaxMusicGenerator()

        if workspace and run_id and not workspace.manifest_exists(run_id):
            workspace.create_run(run_id, description=input_data.description, seed=seed)

        Path(input_data.output_dir).mkdir(parents=True, exist_ok=True)

        # Stage 1: MiniMax generation
        minimax_input = MiniMaxMusicInput(
            description=input_data.description,
            mode=input_data.mode,
            lyrics=input_data.lyrics,
            ref_audio=input_data.ref_audio,
            output_dir=input_data.output_dir,
            seed=seed,
        )
        audio_output = await self._run_stage(
            "minimax_generator",
            self._minimax_generator.execute(minimax_input),
            input_data.generation_timeout_seconds or stage_timeout,
            workspace,
            run_id,
        )
        logger.info(
            "MiniMax generated: %s (%.1fs)",
            audio_output.file_path,
            audio_output.duration_seconds,
        )
        if workspace and run_id:
            workspace.update_artifact(
                run_id,
                "minimax_generator",
                ArtifactStatus.COMPLETED,
                file_path=audio_output.file_path,
            )

        # Stage 2: Output (skip post-processing — MiniMax outputs processed MP3)
        dummy_style = StyleOutput(prompt=input_data.description)
        out_input = OutputInput(
            audio=ProcessedAudio(
                file_path=audio_output.file_path,
                duration_seconds=audio_output.duration_seconds,
                sample_rate=audio_output.sample_rate,
                format=audio_output.format,
                channels=audio_output.channels,
            ),
            style=dummy_style,
            seed=seed,
            lyrics_text=input_data.lyrics or "",
            description=input_data.description,
            output_dir=input_data.output_dir,
            output_config=input_data.output_config,
            extra_metadata={"backend": "minimax", "mode": input_data.mode},
        )
        result = await self._run_stage(
            "output",
            self._output_worker.execute(out_input),
            stage_timeout,
            workspace,
            run_id,
        )
        if workspace and run_id:
            workspace.update_artifact(
                run_id,
                "output",
                ArtifactStatus.COMPLETED,
                file_path=result.audio_path,
            )

        result.metadata["backend"] = "minimax"
        result.metadata["elapsed_seconds"] = round(time.monotonic() - pipeline_started_at, 2)

        return PipelineOutput(
            audio_path=result.audio_path,
            duration_seconds=result.duration_seconds,
            format=result.format or "mp3",
            sample_rate=result.sample_rate,
            metadata=result.metadata,
        )

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
        pipeline_started_at = time.monotonic()
        stage_timeout = input_data.stage_timeout_seconds
        seed = input_data.seed if input_data.seed is not None else random.randint(
            0, 2**32 - 1
        )
        contract = input_data.audio_contract
        mapped_audio = map_scene_contract(contract) if contract else None

        # MiniMax backend: simplified pipeline
        if input_data.backend == "minimax":
            return await self._run_minimax_pipeline(input_data, workspace, run_id)

        # Extract material context for pipeline enrichment
        material = input_data.material_context
        material_description = ""
        material_mood = None
        material_lyrics = None
        material_style_tags: list[str] = []

        if material and not material.is_empty:
            material_description = material.style_summary
            material_mood = material.first_mood
            material_lyrics = material.lyrics_summary or None
            for entry in material.entries:
                for tag in entry.tags:
                    if tag not in material_style_tags:
                        material_style_tags.append(tag)
            logger.info(
                "Material consumed: %d entries from %s",
                len(material.entries),
                material.source_files,
            )
        elif material and material.is_empty:
            logger.warning(
                "Material context provided but contains 0 entries — treating as no material"
            )

        effective_description = input_data.description
        effective_style_tags = list(input_data.style_tags)
        effective_tempo = input_data.tempo_preference
        effective_mood = input_data.mood
        effective_guidance = input_data.guidance_scale

        if mapped_audio:
            for tag in mapped_audio.style_tags:
                if tag not in effective_style_tags:
                    effective_style_tags.append(tag)
            effective_tempo = effective_tempo or mapped_audio.tempo_preference
            effective_guidance = effective_guidance or mapped_audio.guidance_scale
            if mapped_audio.prompt_suffix:
                effective_description = (
                    f"{effective_description}. {mapped_audio.prompt_suffix}"
                )

        if workspace and run_id and not workspace.manifest_exists(run_id):
            workspace.create_run(run_id, description=input_data.description, seed=seed)

        # Stage 1: Lyrics planning
        lyrics_output = None
        if "lyrics_planner" in plan:
            from ace_music.schemas.lyrics import LyricsInput

            lyrics_input = LyricsInput(
                raw_text=material_lyrics or input_data.lyrics or input_data.description,
                language=input_data.language,
                is_instrumental=input_data.is_instrumental,
            )
            lyrics_output = await self._run_stage(
                "lyrics_planner",
                self._lyrics_planner.execute(lyrics_input),
                stage_timeout,
                workspace,
                run_id,
            )
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
            description=material_description or effective_description,
            reference_tags=effective_style_tags + material_style_tags,
            tempo_preference=effective_tempo,
            mood=material_mood or effective_mood,
        )
        style_output = await self._run_stage(
            "style_planner",
            self._style_planner.execute(style_input, preset=preset),
            stage_timeout,
            workspace,
            run_id,
        )

        # Apply user overrides
        if effective_guidance is not None:
            style_output = style_output.model_copy(
                update={"guidance_scale": effective_guidance}
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
        audio_output = await self._run_stage(
            "generator",
            lambda: self._generator.execute_sync(gen_input),
            input_data.generation_timeout_seconds or stage_timeout,
            workspace,
            run_id,
        )
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
        processed = await self._run_stage(
            "post_processor",
            self._post_processor.execute(pp_input),
            stage_timeout,
            workspace,
            run_id,
        )
        logger.info("Post-processed: %s", processed.file_path)
        if workspace and run_id:
            workspace.update_artifact(run_id, "post_processor", ArtifactStatus.COMPLETED)

        processed_validation = self._audio_validator.validate(
            processed.file_path,
            expected_sample_rate=input_data.expected_sample_rate,
            min_duration_seconds=input_data.min_valid_duration_seconds,
            expected_duration_seconds=input_data.duration_seconds,
            duration_tolerance_seconds=input_data.duration_tolerance_seconds,
        )
        if not processed_validation.is_valid:
            message = "Post-processed audio failed validation: " + "; ".join(
                processed_validation.errors
            )
            logger.error(message)
            if workspace and run_id:
                workspace.update_artifact(
                    run_id,
                    "post_processor",
                    ArtifactStatus.FAILED,
                    file_path=processed.file_path,
                    error_message=message,
                )
            raise OutputValidationError(message, processed_validation.errors)

        # Stage 5: Output
        extra_metadata: dict = {}
        if contract:
            extra_metadata["audio_contract"] = contract.model_dump(mode="json")
        if mapped_audio:
            mapped_metadata = mapped_audio.to_metadata()
            extra_metadata["mapped_audio"] = mapped_metadata
            extra_metadata["mix"] = mapped_metadata["mix"]
            extra_metadata["transition"] = mapped_metadata["transition"]
            extra_metadata["qa_targets"] = mapped_metadata["qa_targets"]

        out_input = OutputInput(
            audio=processed,
            style=style_output,
            seed=seed,
            lyrics_text=lyrics_output.formatted_lyrics if lyrics_output else "",
            description=input_data.description,
            output_dir=input_data.output_dir,
            output_config=input_data.output_config,
            extra_metadata=extra_metadata or None,
            material_provenance=(
                material.to_provenance_dict() if material and not material.is_empty else None
            ),
        )
        result = await self._run_stage(
            "output",
            self._output_worker.execute(out_input),
            stage_timeout,
            workspace,
            run_id,
        )
        final_validation = self._audio_validator.validate(
            result.audio_path,
            expected_sample_rate=input_data.expected_sample_rate,
            min_duration_seconds=input_data.min_valid_duration_seconds,
            expected_duration_seconds=input_data.duration_seconds,
            duration_tolerance_seconds=input_data.duration_tolerance_seconds,
        )
        if not final_validation.is_valid:
            message = "Final audio failed validation: " + "; ".join(final_validation.errors)
            logger.error(message)
            if workspace and run_id:
                workspace.update_artifact(
                    run_id,
                    "output",
                    ArtifactStatus.FAILED,
                    file_path=result.audio_path,
                    error_message=message,
                )
            raise OutputValidationError(message, final_validation.errors)

        result.metadata["validation"] = final_validation.model_dump()
        result.metadata["elapsed_seconds"] = round(time.monotonic() - pipeline_started_at, 2)
        logger.info("Output: %s", result.audio_path)
        if workspace and run_id:
            workspace.update_artifact(
                run_id, "output", ArtifactStatus.COMPLETED, file_path=result.audio_path
            )

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
        stage_timeout = input_data.stage_timeout_seconds

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
                lyrics_output = await self._run_stage(
                    "lyrics_planner",
                    self._lyrics_planner.execute(lyrics_input),
                    stage_timeout,
                    workspace,
                    run_id,
                )
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
                style_output = await self._run_stage(
                    "style_planner",
                    self._style_planner.execute(style_input, preset=preset),
                    stage_timeout,
                    workspace,
                    run_id,
                )
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
                audio_output = await self._run_stage(
                    "generator",
                    lambda: self._generator.execute_sync(gen_input),
                    input_data.generation_timeout_seconds or stage_timeout,
                    workspace,
                    run_id,
                )
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
                # NOTE: Resume does not restore output_config from the manifest;
                # resumed runs always use workspace-stage output dirs.
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
