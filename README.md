# ace-music

AI music generation agent powered by ACE-Step 1.5.

Planning-mode architecture: LyricsPlanner → StylePlanner → GenerationWorker → PostProcessor → OutputWorker.

## Setup

```bash
# Create venv and install
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# With model support (GPU required)
pip install -e ".[dev,model]"
```

## Usage

```python
from ace_music.agent import MusicAgent
from ace_music.schemas.pipeline import PipelineInput

agent = MusicAgent()
result = await agent.run(PipelineInput(
    description="A dreamy synthwave track about neon cities",
    duration_seconds=60.0,
))
print(result.audio_path)
```

## Architecture

```
MusicAgent (planner)
  ├── LyricsPlanner   — parse & structure lyrics
  ├── StylePlanner    — map style description to ACE-Step params
  ├── Generator       — call ACE-Step model (or mock)
  ├── PostProcessor   — format conversion, loudness normalization
  └── OutputWorker    — final file + metadata
```

## Contract-Driven Audio Engine

`ace-music` can also consume `AudioSceneContract` for narrative and video workflows.
See `docs/audio-engine-architecture.md` for the structured input contract,
emotion mapping, mix policy, transition rules, and QA acceptance criteria.

## License

MIT
