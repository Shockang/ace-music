"""Configuration loader for ace-music."""

import logging
from pathlib import Path

import yaml

from ace_music.mcp.config import ModelConfig
from ace_music.tools.generator import GeneratorConfig

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "configs" / "default.yaml"


def load_config(config_path: str | Path | None = None) -> dict:
    """Load YAML configuration file."""
    path = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH

    if not path.exists():
        logger.warning("Config file not found: %s, using defaults", path)
        return {}

    with open(path) as f:
        return yaml.safe_load(f) or {}


def load_model_config(config_path: str | Path | None = None) -> ModelConfig:
    """Load ModelConfig from YAML config."""
    cfg = load_config(config_path)
    model_section = cfg.get("model", {})
    return ModelConfig(
        checkpoint_dir=model_section.get("checkpoint_dir"),
        device_id=model_section.get("device_id", 0),
        dtype=model_section.get("dtype", "bfloat16"),
        torch_compile=model_section.get("torch_compile", False),
        cpu_offload=model_section.get("cpu_offload", False),
        overlapped_decode=model_section.get("overlapped_decode", False),
        model_variant=model_section.get("model_variant", "2b"),
        mock_mode=model_section.get("mock_mode", False),
    )


def load_generator_config(config_path: str | Path | None = None) -> GeneratorConfig:
    """Load GeneratorConfig from YAML config."""
    model_cfg = load_model_config(config_path)
    return GeneratorConfig(
        checkpoint_dir=model_cfg.checkpoint_dir,
        device_id=model_cfg.device_id,
        dtype=model_cfg.dtype,
        torch_compile=model_cfg.torch_compile,
        cpu_offload=model_cfg.cpu_offload,
        overlapped_decode=model_cfg.overlapped_decode,
        model_variant=model_cfg.model_variant,
        mock_mode=model_cfg.mock_mode,
    )
