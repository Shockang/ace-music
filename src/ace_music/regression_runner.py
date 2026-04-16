"""RegressionRunner: execute N consecutive generations with full evidence."""

import json
import logging
import time
from pathlib import Path

from pydantic import BaseModel, Field

from ace_music.agent import MusicAgent
from ace_music.schemas.material import MaterialContext
from ace_music.schemas.pipeline import PipelineInput
from ace_music.tools.audio_validator import AudioValidator
from ace_music.tools.generator import GeneratorConfig

logger = logging.getLogger(__name__)


class RegressionResult(BaseModel):
    """Result of a single regression run."""

    run_number: int
    success: bool
    audio_path: str | None = None
    duration_seconds: float = 0.0
    sample_rate: int = 0
    format: str = "wav"
    seed: int = 0
    elapsed_seconds: float = 0.0
    description: str = ""
    material_provenance: dict | None = None
    validation_errors: list[str] = Field(default_factory=list)
    error_message: str | None = None

    def to_dict(self) -> dict:
        return self.model_dump()


class RegressionRunner:
    """Run multiple pipeline generations for regression testing."""

    def __init__(
        self,
        generator_config: GeneratorConfig | None = None,
        output_dir: str = "./output/regression",
    ) -> None:
        self._config = generator_config or GeneratorConfig(mock_mode=True)
        self._output_dir = output_dir
        self._validator = AudioValidator()
        Path(output_dir).mkdir(parents=True, exist_ok=True)

    async def run_single(
        self,
        description: str,
        material: MaterialContext | None = None,
        duration_seconds: float = 5.0,
        seed: int | None = None,
    ) -> RegressionResult:
        """Execute a single generation run with validation."""
        import random

        actual_seed = seed if seed is not None else random.randint(0, 2**32 - 1)
        start_time = time.time()

        try:
            agent = MusicAgent(generator_config=self._config)
            result = await agent.run(
                PipelineInput(
                    description=description,
                    material_context=material,
                    duration_seconds=duration_seconds,
                    seed=actual_seed,
                    output_dir=self._output_dir,
                )
            )
            elapsed = time.time() - start_time

            validation = self._validator.validate(result.audio_path)

            return RegressionResult(
                run_number=0,
                success=validation.is_valid,
                audio_path=result.audio_path,
                duration_seconds=result.duration_seconds,
                sample_rate=result.sample_rate,
                format=result.format,
                seed=actual_seed,
                elapsed_seconds=round(elapsed, 2),
                description=description,
                material_provenance=material.to_provenance_dict()
                if material and not material.is_empty
                else None,
                validation_errors=validation.errors,
            )

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error("Run failed: %s", e)
            return RegressionResult(
                run_number=0,
                success=False,
                seed=actual_seed,
                elapsed_seconds=round(elapsed, 2),
                description=description,
                material_provenance=material.to_provenance_dict()
                if material and not material.is_empty
                else None,
                error_message=str(e),
            )

    async def run_regression(
        self,
        description: str,
        material: MaterialContext | None = None,
        num_runs: int = 3,
        duration_seconds: float = 5.0,
        base_seed: int = 42,
    ) -> list[RegressionResult]:
        """Execute N consecutive regression runs."""
        results: list[RegressionResult] = []

        for i in range(num_runs):
            logger.info("=== Regression run %d/%d ===", i + 1, num_runs)
            result = await self.run_single(
                description=description,
                material=material,
                duration_seconds=duration_seconds,
                seed=base_seed + i,
            )
            result = result.model_copy(update={"run_number": i + 1})
            results.append(result)

            status = "PASS" if result.success else "FAIL"
            logger.info(
                "Run %d: %s (%.1fs, seed=%d)",
                i + 1,
                status,
                result.elapsed_seconds,
                result.seed,
            )

        return results

    def save_results(
        self, results: list[RegressionResult], output_path: str
    ) -> None:
        """Save regression results to a JSON file."""
        successful = [r for r in results if r.success]
        report = {
            "summary": {
                "total_runs": len(results),
                "successful_runs": len(successful),
                "failed_runs": len(results) - len(successful),
                "all_passed": len(successful) == len(results),
            },
            "runs": [r.to_dict() for r in results],
        }

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(
            json.dumps(report, indent=2, ensure_ascii=False)
        )
        logger.info("Regression results saved to %s", output_path)
