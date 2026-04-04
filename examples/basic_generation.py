"""Basic usage example for ace-music."""

import asyncio

from ace_music.agent import MusicAgent
from ace_music.schemas.pipeline import PipelineInput
from ace_music.tools.generator import GeneratorConfig


async def main():
    # Use mock mode (no GPU required for this example)
    config = GeneratorConfig(mock_mode=True)
    agent = MusicAgent(generator_config=config)

    # Example 1: Full song with lyrics
    print("=== Generating song with lyrics ===")
    result = await agent.run(
        PipelineInput(
            description="A dreamy synthwave track about neon cities at night",
            lyrics="""[verse]
Neon lights reflecting in the rain
City streets calling out my name
Midnight drives on empty lanes
Lost in digital domains

[chorus]
We are the neon dreamers
Running through the laser beams
Nothing's quite as it seems
In this city of extremes""",
            duration_seconds=30.0,
            style_tags=["synthwave", "retro", "electronic"],
            mood="dreamy",
            seed=42,
            output_dir="./output",
        )
    )
    print(f"Output: {result.audio_path}")
    print(f"Duration: {result.duration_seconds}s")
    print(f"Metadata: {result.metadata}")

    # Example 2: Instrumental background
    print("\n=== Generating instrumental ===")
    result2 = await agent.run(
        PipelineInput(
            description="Calm ambient piano with soft strings",
            duration_seconds=15.0,
            is_instrumental=True,
            mood="calm",
            output_dir="./output",
        )
    )
    print(f"Output: {result2.audio_path}")

    # Example 3: DirectorBridge integration
    print("\n=== DirectorBridge integration ===")
    from ace_music.bridge import DirectorBridge
    from ace_music.bridge.director_bridge import request_to_pipeline_input

    request = DirectorBridge.Request(
        scene_id="scene_001",
        mood="melancholic",
        duration_seconds=20.0,
        style_reference="dark ambient electronic",
        tempo_preference="slow",
    )
    pipeline_input = request_to_pipeline_input(request)
    print(f"Bridge request -> pipeline input: {pipeline_input.description}")


if __name__ == "__main__":
    asyncio.run(main())
