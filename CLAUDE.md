# ace-music — AI Music Generation Agent

ACE-Step 1.5 powered Planning-mode music generation.

## Project Structure

- `src/ace_music/agent.py` — MusicAgent planner, orchestrates the pipeline
- `src/ace_music/tools/` — Tool implementations (MusicTool interface)
- `src/ace_music/schemas/` — Pydantic models for all pipeline stages
- `src/ace_music/mcp/` — Model and GPU configuration
- `src/ace_music/bridge/` — auto-director integration (DirectorBridge)
- `tests/` — Unit and integration tests

## Conventions

- Python 3.12 + Pydantic 2
- All tools implement `MusicTool[InputT, OutputT]` from `tools/base.py`
- Immutable data flow: tools return new objects, never mutate inputs
- Async-first: all `execute()` methods are async
- ACE-Step model calls are isolated in `tools/generator.py`

## Commands

```bash
pytest                          # run tests
pytest -m "not integration"     # skip GPU-required tests
ruff check src/ tests/          # lint
```
