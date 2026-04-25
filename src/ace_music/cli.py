"""Command-line entry point for ace-music automation."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import multiprocessing
import os
import queue
import time
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ace_music.agent import MusicAgent
from ace_music.errors import AceMusicError
from ace_music.mcp.loader import load_generator_config
from ace_music.schemas.pipeline import PipelineInput
from ace_music.tools.audio_validator import AudioValidator
from ace_music.tools.generator import GeneratorConfig

logger = logging.getLogger(__name__)


def _configure_logging(quiet: bool, verbose: bool) -> None:
    if quiet:
        level = logging.WARNING
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )


def _write_summary(summary: dict[str, Any], summary_json: str | None) -> None:
    payload = json.dumps(summary, ensure_ascii=False, indent=2)
    if summary_json:
        path = Path(summary_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload)
    print(payload)


def _summary_for_error(error: Exception, elapsed: float) -> dict[str, Any]:
    category = "validation_error" if isinstance(error, ValidationError) else "runtime_error"
    exit_code = 2 if isinstance(error, ValidationError) else 1
    if isinstance(error, AceMusicError):
        category = error.category
        exit_code = error.exit_code

    return {
        "status": "failed",
        "category": category,
        "exit_code": exit_code,
        "error": str(error),
        "elapsed_seconds": round(elapsed, 2),
    }


def _generator_config_from_args(args: argparse.Namespace) -> GeneratorConfig:
    config = load_generator_config(args.config) if args.config else GeneratorConfig()

    return config.model_copy(
        update={
            "mock_mode": args.mock,
            "allow_mock_fallback": args.allow_mock_fallback,
            "require_cuda": not args.no_require_cuda,
            "cpu_offload": args.cpu_offload or config.cpu_offload,
        }
    )


async def _run_generate(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    started_at = time.monotonic()
    agent = MusicAgent(generator_config=_generator_config_from_args(args))
    result = await agent.run(
        PipelineInput(
            description=args.description,
            lyrics=args.lyrics,
            style_tags=args.style_tag,
            duration_seconds=args.duration,
            language=args.language,
            is_instrumental=args.instrumental,
            seed=args.seed,
            output_format=args.format,
            output_dir=args.output_dir,
            preset_name=args.preset,
            guidance_scale=args.guidance_scale,
            infer_step=args.infer_step,
            stage_timeout_seconds=args.stage_timeout,
            generation_timeout_seconds=args.generation_timeout,
            expected_sample_rate=args.expected_sample_rate,
            min_valid_duration_seconds=args.min_valid_duration,
            duration_tolerance_seconds=args.duration_tolerance,
        )
    )
    elapsed = time.monotonic() - started_at
    validation = result.metadata.get("validation") or {}

    summary = {
        "status": "success",
        "audio_path": result.audio_path,
        "duration_seconds": result.duration_seconds,
        "sample_rate": result.sample_rate,
        "format": result.format,
        "seed": result.metadata.get("seed"),
        "elapsed_seconds": round(elapsed, 2),
        "validation": validation,
    }
    return 0, summary


def _child_context_name() -> str:
    return "fork" if hasattr(os, "fork") and os.name != "nt" else "spawn"


def _generate_child(args: argparse.Namespace, result_queue: multiprocessing.Queue) -> None:
    _configure_logging(args.quiet, args.verbose)
    started_at = time.monotonic()
    try:
        exit_code, summary = asyncio.run(_run_generate(args))
    except Exception as exc:
        summary = _summary_for_error(exc, time.monotonic() - started_at)
        exit_code = int(summary["exit_code"])
    result_queue.put({"exit_code": exit_code, "summary": summary})


def _generate_wall_timeout(args: argparse.Namespace) -> float:
    if args.total_timeout is not None:
        return args.total_timeout
    generation_timeout = args.generation_timeout or 600.0
    stage_timeout = args.stage_timeout or 120.0
    return generation_timeout + (stage_timeout * 4) + 30.0


def _run_generate_with_watchdog(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    ctx = multiprocessing.get_context(_child_context_name())
    result_queue = ctx.Queue(maxsize=1)
    process = ctx.Process(target=_generate_child, args=(args, result_queue))
    timeout_seconds = _generate_wall_timeout(args)
    started_at = time.monotonic()

    process.start()
    process.join(timeout_seconds)

    if process.is_alive():
        process.terminate()
        process.join(5)
        if process.is_alive():
            process.kill()
            process.join()
        elapsed = time.monotonic() - started_at
        return 40, {
            "status": "failed",
            "category": "timeout",
            "exit_code": 40,
            "error": f"Command timed out after {timeout_seconds:g}s",
            "elapsed_seconds": round(elapsed, 2),
        }

    try:
        payload = result_queue.get_nowait()
    except queue.Empty:
        elapsed = time.monotonic() - started_at
        return 1, {
            "status": "failed",
            "category": "runtime_error",
            "exit_code": 1,
            "error": f"Generation worker exited without a summary (code={process.exitcode})",
            "elapsed_seconds": round(elapsed, 2),
        }

    return int(payload["exit_code"]), payload["summary"]


def _run_validate(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    started_at = time.monotonic()
    validator = AudioValidator()
    result = validator.validate(
        args.audio_path,
        expected_sample_rate=args.expected_sample_rate,
        min_duration_seconds=args.min_valid_duration,
        expected_duration_seconds=args.expected_duration,
        duration_tolerance_seconds=args.duration_tolerance,
    )
    elapsed = time.monotonic() - started_at
    summary = {
        "status": "success" if result.is_valid else "failed",
        "category": "ok" if result.is_valid else "output_validation_failed",
        "elapsed_seconds": round(elapsed, 2),
        "validation": result.model_dump(),
    }
    return (0 if result.is_valid else 50), summary


def _add_common_runtime_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--quiet", action="store_true", help="Only emit warnings/errors plus JSON summary"
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--summary-json", help="Write machine-readable run summary JSON to this path"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ace-music",
        description="Generate and validate AI music outputs with automation-friendly diagnostics.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser(
        "generate", help="Run the music generation pipeline"
    )
    generate.add_argument(
        "--description", required=True, help="Natural language music description"
    )
    generate.add_argument("--lyrics", help="Optional raw lyrics text")
    generate.add_argument(
        "--style-tag", action="append", default=[], help="Style tag; repeatable"
    )
    generate.add_argument(
        "--duration", type=float, default=30.0, help="Target duration seconds, 5-240"
    )
    generate.add_argument("--language", default="en", help="Lyrics language code")
    generate.add_argument("--instrumental", action="store_true", help="Generate instrumental audio")
    generate.add_argument("--seed", type=int, help="Generation seed")
    generate.add_argument("--format", default="wav", help="Output audio format")
    generate.add_argument("--output-dir", default="./output", help="Output directory")
    generate.add_argument("--preset", help="Preset name to apply")
    generate.add_argument("--guidance-scale", type=float, help="Override guidance scale")
    generate.add_argument("--infer-step", type=int, help="Override diffusion steps")
    generate.add_argument("--config", help="YAML config path")
    generate.add_argument(
        "--mock", action="store_true", help="Use deterministic local WAV generation"
    )
    generate.add_argument(
        "--allow-mock-fallback",
        action="store_true",
        help="Explicitly fall back to mock mode if ACE-Step is unavailable",
    )
    generate.add_argument(
        "--no-require-cuda",
        action="store_true",
        help="Skip CUDA preflight before production model load",
    )
    generate.add_argument(
        "--cpu-offload", action="store_true", help="Request ACE-Step CPU offload"
    )
    generate.add_argument(
        "--stage-timeout", type=float, default=120.0, help="Per-stage timeout seconds"
    )
    generate.add_argument(
        "--generation-timeout",
        type=float,
        default=600.0,
        help="Generation-stage timeout seconds",
    )
    generate.add_argument(
        "--total-timeout",
        type=float,
        help="Wall-clock command timeout; kills the generation worker process if exceeded",
    )
    generate.add_argument("--expected-sample-rate", type=int, default=48000)
    generate.add_argument("--min-valid-duration", type=float, default=1.0)
    generate.add_argument("--duration-tolerance", type=float, default=5.0)
    _add_common_runtime_options(generate)

    validate = subparsers.add_parser("validate", help="Validate an existing audio file")
    validate.add_argument("audio_path", help="Audio file path to validate")
    validate.add_argument("--expected-sample-rate", type=int, default=48000)
    validate.add_argument("--min-valid-duration", type=float, default=1.0)
    validate.add_argument("--expected-duration", type=float)
    validate.add_argument("--duration-tolerance", type=float, default=5.0)
    _add_common_runtime_options(validate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.quiet, args.verbose)
    started_at = time.monotonic()

    try:
        if args.command == "generate":
            exit_code, summary = _run_generate_with_watchdog(args)
        elif args.command == "validate":
            exit_code, summary = _run_validate(args)
        else:
            parser.error(f"Unknown command: {args.command}")
    except Exception as exc:
        elapsed = time.monotonic() - started_at
        logger.error("Command failed: %s", exc)
        logger.debug("Command failure traceback", exc_info=True)
        summary = _summary_for_error(exc, elapsed)
        exit_code = int(summary["exit_code"])

    _write_summary(summary, args.summary_json)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
