# Audio Engine Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `ace-music` from a description-only music generator into a contract-driven audio engine slice that can consume narrative/video cues, derive stable music/mix parameters, and expose verifiable QA targets for downstream MP4 composition.

**Architecture:** Add a narrow contract layer beside the existing `PipelineInput`, not a replacement for the current five-stage pipeline. A deterministic mapper converts emotion/scene cues into style tags, tempo/guidance hints, mix rules, transition rules, and QA targets; `MusicAgent` and `DirectorBridge` then pass those hints through to existing planners and metadata.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, existing `MusicAgent` pipeline, no new dependencies.

---

## Context and Research Notes

- Current pipeline is `LyricsPlanner -> StylePlanner -> Generator -> PostProcessor -> OutputWorker` in `src/ace_music/agent.py`.
- Current integration contract is `DirectorBridge.Request` / `DirectorBridge.Response` in `src/ace_music/bridge/__init__.py` and adapter functions in `src/ace_music/bridge/director_bridge.py`.
- Current gap: `DirectorBridge.intensity` is accepted but not mapped; `PipelineInput` has no narrative/audio contract; output metadata does not describe mix/transition/QA constraints.
- Local references from `/Users/shockang/github`:
  - `moyin-creator`: feature routing, retries, partial success patterns.
  - `ViMax`: config-driven provider presets and artifact reuse.
  - `webnovel-writer`: recovery state discipline.
  - `StateLM`: long-run resume and aggregation.
  - `codex SDK`: retryable failure classification.
  - `openclaw`: boundary/contract test style.
- External references:
  - FFmpeg filters provide production primitives for `amix`, `acrossfade`, `loudnorm`, and `sidechaincompress`: https://ffmpeg.org/ffmpeg-filters.html
  - EBU R 128 defines programme loudness and maximum true peak concepts around LUFS/true peak: https://tech.ebu.ch/publications/r128
  - Music emotion research commonly uses valence/arousal; temporal cues strongly convey arousal and pitch/harmony relate to valence: https://pmc.ncbi.nlm.nih.gov/articles/PMC9837297/
  - Recent video soundtrack work aligns video emotions and temporal boundaries using discrete emotion categories bridged to continuous valence/arousal: https://arxiv.org/abs/2502.10154

## File Structure

- Create: `src/ace_music/schemas/audio_contract.py`
  - Pydantic contract models for scene/narrative cues, segment boundaries, layer policy, transition policy, mix policy, and QA targets.
- Create: `src/ace_music/tools/emotion_mapper.py`
  - Deterministic, dependency-free mapping from `AudioSceneContract` to music/mix/QA hints.
- Modify: `src/ace_music/schemas/pipeline.py`
  - Add optional `audio_contract` to `PipelineInput`.
- Modify: `src/ace_music/schemas/__init__.py`
  - Export contract models.
- Modify: `src/ace_music/agent.py`
  - Apply mapped hints before style planning and pass contract/mapping/mix/QA metadata into persisted output metadata.
- Modify: `src/ace_music/tools/output.py`
  - Accept extra metadata fields so sidecar JSON and in-memory `PipelineOutput.metadata` stay identical.
- Modify: `src/ace_music/bridge/__init__.py`
  - Add minimal cross-system fields needed by `auto-director`: `valence`, `arousal`, `shot_count`, `tts_present`, `dialogue_density`, `target_lufs`, `max_true_peak_db`, `crossfade_seconds`.
- Modify: `src/ace_music/bridge/director_bridge.py`
  - Convert `DirectorBridge.Request` into `AudioSceneContract` and pass it through `PipelineInput`.
- Create: `tests/test_audio_contract.py`
  - Contract defaults, validation, segment boundaries, mapper behavior.
- Modify: `tests/test_pipeline.py`
  - Bridge and pipeline metadata integration tests.
- Create: `docs/audio-engine-architecture.md`
  - Deliver the requested A-E engineering diagnosis, architecture, P0/P1/P2 roadmap, prompt/config templates, and acceptance criteria.
- Modify: `README.md`
  - Add a short pointer to contract-driven usage and architecture doc.

## Implementation Constraints

- Do not add new dependencies.
- Do not invoke real ACE-Step/GPU paths in unit tests; use `GeneratorConfig(mock_mode=True)`.
- Do not commit; the controlling session will decide commit/merge later.
- Keep all new mappings deterministic and explicit so downstream systems can regression-test them.
- Preserve backward compatibility: existing `PipelineInput(description=...)` flows must continue unchanged.

---

### Task 1: Contract Models and Emotion Mapper

**Files:**
- Create: `src/ace_music/schemas/audio_contract.py`
- Create: `src/ace_music/tools/emotion_mapper.py`
- Modify: `src/ace_music/schemas/__init__.py`
- Create: `tests/test_audio_contract.py`

- [ ] **Step 1: Write failing schema tests**

Add `tests/test_audio_contract.py` with tests covering defaults, validation, segment boundaries, serialization, and mapper output.

```python
from ace_music.schemas.audio_contract import AudioSceneContract
from ace_music.tools.emotion_mapper import map_scene_contract


def test_audio_scene_contract_defaults():
    contract = AudioSceneContract(
        scene_id="scene_001",
        duration_seconds=30,
        mood="tense",
    )

    assert contract.scene_id == "scene_001"
    assert contract.intensity == 0.5
    assert contract.layers.tts_present is True
    assert contract.qa_targets.min_composition_success_rate == 0.98


def test_audio_scene_contract_validates_range():
    with pytest.raises(ValueError):
        AudioSceneContract(scene_id="bad", duration_seconds=30, mood="tense", arousal=1.2)


def test_mapper_turns_high_arousal_into_fast_tempo_and_ducking():
    contract = AudioSceneContract(
        scene_id="chase",
        duration_seconds=45,
        mood="urgent",
        intensity=0.9,
        arousal=0.95,
        valence=-0.3,
        shot_count=18,
        dialogue_density=0.8,
    )

    mapped = map_scene_contract(contract)

    assert mapped.tempo_preference == "fast"
    assert mapped.guidance_scale >= 16.0
    assert "tense" in mapped.style_tags
    assert mapped.mix.bgm_gain_db <= -12.0
    assert mapped.mix.ducking_db >= 8.0


def test_audio_scene_contract_serializes_segment_boundaries():
    contract = AudioSceneContract(
        scene_id="multi",
        duration_seconds=30,
        mood="tense",
        segments=[{"segment_id": "intro", "start_seconds": 0, "end_seconds": 8}],
    )

    dumped = contract.model_dump(mode="json")
    loaded = AudioSceneContract.model_validate(dumped)

    assert loaded.segments[0].segment_id == "intro"
    assert loaded.segments[0].end_seconds == 8


def test_audio_segment_cue_requires_positive_range():
    with pytest.raises(ValueError):
        AudioSceneContract(
            scene_id="bad_segment",
            duration_seconds=30,
            mood="tense",
            segments=[{"segment_id": "bad", "start_seconds": 8, "end_seconds": 8}],
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest -q tests/test_audio_contract.py`

Expected: FAIL with missing `ace_music.schemas.audio_contract` / `ace_music.tools.emotion_mapper`.

- [ ] **Step 3: Add contract schema models**

Create `src/ace_music/schemas/audio_contract.py`:

```python
"""Narrative/video audio contract models for ace-music."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class AudioLayerPolicy(BaseModel):
    """Which audio layers coexist in the final video mix."""

    tts_present: bool = True
    bgm_present: bool = True
    ambience_present: bool = False
    effects_present: bool = False


class TransitionPolicy(BaseModel):
    """Constraints for joining generated segments."""

    crossfade_seconds: float = Field(default=1.5, ge=0.0, le=10.0)
    allow_looping: bool = True
    require_seamless_tail: bool = True


class MixPolicy(BaseModel):
    """Mixing targets for downstream TTS/BGM/video composition."""

    target_lufs: float = Field(default=-18.0, ge=-30.0, le=-10.0)
    max_true_peak_db: float = Field(default=-1.5, ge=-6.0, le=0.0)
    bgm_gain_db: float = Field(default=-14.0, ge=-30.0, le=0.0)
    ducking_db: float = Field(default=8.0, ge=0.0, le=24.0)
    sidechain_source: Literal["tts", "none"] = "tts"


class AudioQATargets(BaseModel):
    """Machine-checkable acceptance targets for generated audio assets."""

    duration_tolerance_seconds: float = Field(default=1.0, ge=0.0, le=10.0)
    min_emotion_match_score: float = Field(default=0.75, ge=0.0, le=1.0)
    max_dialogue_conflict_rate: float = Field(default=0.05, ge=0.0, le=1.0)
    min_composition_success_rate: float = Field(default=0.98, ge=0.0, le=1.0)


class AudioSegmentCue(BaseModel):
    """A bounded audio cue inside a longer scene contract."""

    segment_id: str
    start_seconds: float = Field(ge=0.0)
    end_seconds: float = Field(gt=0.0)
    mood: str | None = None
    intensity: float | None = Field(default=None, ge=0.0, le=1.0)
    transition: TransitionPolicy | None = None

    @model_validator(mode="after")
    def validate_time_range(self) -> "AudioSegmentCue":
        if self.end_seconds <= self.start_seconds:
            raise ValueError("end_seconds must be greater than start_seconds")
        return self


class AudioSceneContract(BaseModel):
    """Structured audio request from novel/video orchestration systems."""

    scene_id: str
    duration_seconds: float = Field(ge=5.0, le=240.0)
    mood: str
    scene_description: str | None = None
    narrative_beat: str | None = None
    valence: float | None = Field(default=None, ge=-1.0, le=1.0)
    arousal: float | None = Field(default=None, ge=0.0, le=1.0)
    intensity: float = Field(default=0.5, ge=0.0, le=1.0)
    shot_count: int | None = Field(default=None, ge=0)
    dialogue_density: float = Field(default=0.5, ge=0.0, le=1.0)
    role_theme: str | None = None
    segments: list[AudioSegmentCue] = Field(default_factory=list)
    layers: AudioLayerPolicy = Field(default_factory=AudioLayerPolicy)
    transition: TransitionPolicy = Field(default_factory=TransitionPolicy)
    mix: MixPolicy = Field(default_factory=MixPolicy)
    qa_targets: AudioQATargets = Field(default_factory=AudioQATargets)
```

- [ ] **Step 4: Add deterministic mapper**

Create `src/ace_music/tools/emotion_mapper.py`:

```python
"""Deterministic emotion-to-music mapping for contract-driven generation."""

from pydantic import BaseModel, Field

from ace_music.schemas.audio_contract import AudioSceneContract, MixPolicy, TransitionPolicy


MOOD_STYLE_TAGS = {
    "tense": ["cinematic", "dark", "suspense", "pulsing"],
    "urgent": ["cinematic", "tense", "driving", "percussion"],
    "melancholic": ["emotional", "minor", "slow", "ambient"],
    "calm": ["ambient", "soft", "warm", "minimal"],
    "hopeful": ["uplifting", "warm", "major", "cinematic"],
}


class MappedAudioParameters(BaseModel):
    """Mapped generation and mix hints derived from an audio contract."""

    style_tags: list[str] = Field(default_factory=list)
    tempo_preference: str | None = None
    guidance_scale: float | None = None
    prompt_suffix: str = ""
    mix: MixPolicy
    transition: TransitionPolicy
    qa_targets: dict

    def to_metadata(self) -> dict:
        return self.model_dump(mode="json")


def map_scene_contract(contract: AudioSceneContract) -> MappedAudioParameters:
    mood_key = contract.mood.lower().strip()
    tags = list(MOOD_STYLE_TAGS.get(mood_key, [mood_key]))
    if contract.valence is not None and contract.valence < -0.25:
        tags.extend(["minor", "shadowed"])
    if contract.valence is not None and contract.valence > 0.25:
        tags.extend(["major", "uplifting"])
    if contract.arousal is not None and contract.arousal >= 0.75:
        tags.extend(["high energy", "rhythmic"])
    if contract.role_theme:
        tags.append(f"theme:{contract.role_theme}")

    pace = _estimate_pace(contract)
    guidance_scale = round(12.0 + contract.intensity * 6.0, 2)
    mix = _derive_mix(contract)
    prompt_suffix = _build_prompt_suffix(contract, pace)
    unique_tags = list(dict.fromkeys(tags))

    return MappedAudioParameters(
        style_tags=unique_tags,
        tempo_preference=pace,
        guidance_scale=guidance_scale,
        prompt_suffix=prompt_suffix,
        mix=mix,
        transition=contract.transition,
        qa_targets=contract.qa_targets.model_dump(mode="json"),
    )
```

Implement helper functions `_estimate_pace`, `_derive_mix`, and `_build_prompt_suffix` in the same file. `_estimate_pace` should return `"fast"` when arousal is high or shot density is high, `"slow"` when arousal is low, otherwise `"moderate"`. `_derive_mix` should lower `bgm_gain_db` and increase `ducking_db` as `dialogue_density` rises. `_build_prompt_suffix` should summarize mood, intensity, pace, scene description, and transition requirements in one concise sentence.

- [ ] **Step 5: Export schemas**

Modify `src/ace_music/schemas/__init__.py` to import and export:

```python
from .audio_contract import (
    AudioLayerPolicy,
    AudioQATargets,
    AudioSceneContract,
    AudioSegmentCue,
    MixPolicy,
    TransitionPolicy,
)
```

- [ ] **Step 6: Run tests to verify pass**

Run: `python3 -m pytest -q tests/test_audio_contract.py`

Expected: PASS.

---

### Task 2: Pipeline and DirectorBridge Integration

**Files:**
- Modify: `src/ace_music/schemas/pipeline.py`
- Modify: `src/ace_music/agent.py`
- Modify: `src/ace_music/tools/output.py`
- Modify: `src/ace_music/bridge/__init__.py`
- Modify: `src/ace_music/bridge/director_bridge.py`
- Modify: `tests/test_pipeline.py`

- [ ] **Step 1: Write failing integration tests**

Add tests to `tests/test_pipeline.py`:

```python
from ace_music.schemas.audio_contract import AudioSceneContract


def test_director_bridge_builds_audio_contract():
    req = DirectorBridge.Request(
        scene_id="scene_contract",
        mood="tense",
        duration_seconds=30,
        scene_description="A chase through a narrow alley",
        intensity=0.9,
        arousal=0.95,
        valence=-0.4,
        shot_count=16,
        dialogue_density=0.7,
        tts_present=True,
        crossfade_seconds=2.0,
    )

    pipeline_input = request_to_pipeline_input(req)

    assert pipeline_input.audio_contract is not None
    assert pipeline_input.audio_contract.scene_id == "scene_contract"
    assert pipeline_input.audio_contract.intensity == 0.9
    assert pipeline_input.audio_contract.transition.crossfade_seconds == 2.0


@pytest.mark.asyncio
async def test_pipeline_metadata_includes_audio_contract(agent, tmp_path):
    contract = AudioSceneContract(
        scene_id="scene_meta",
        mood="urgent",
        duration_seconds=5,
        intensity=0.85,
        arousal=0.9,
        dialogue_density=0.8,
    )

    result = await agent.run(
        PipelineInput(
            description="background music",
            duration_seconds=5,
            is_instrumental=True,
            audio_contract=contract,
            output_dir=str(tmp_path),
        )
    )

    assert result.metadata["audio_contract"]["scene_id"] == "scene_meta"
    assert result.metadata["mapped_audio"]["tempo_preference"] == "fast"
    assert result.metadata["mix"]["ducking_db"] >= 8.0
    assert result.metadata["qa_targets"]["min_composition_success_rate"] == 0.98
    metadata_path = next(Path(result.audio_path).parent.glob("*_metadata.json"))
    persisted = json.loads(metadata_path.read_text())
    assert persisted["audio_contract"]["scene_id"] == "scene_meta"
```

Add `import json` if not already present.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest -q tests/test_pipeline.py::TestDirectorBridgeEnhanced tests/test_pipeline.py::TestMusicAgentPipeline`

Expected: FAIL until `audio_contract` is added to pipeline and bridge.

- [ ] **Step 3: Add contract field to `PipelineInput`**

Modify `src/ace_music/schemas/pipeline.py`:

```python
from ace_music.schemas.audio_contract import AudioSceneContract

audio_contract: AudioSceneContract | None = Field(
    default=None,
    description="Structured scene/video audio contract from upstream orchestration",
)
```

- [ ] **Step 4: Apply contract hints in `MusicAgent.run`**

Modify `src/ace_music/agent.py`:

```python
from ace_music.tools.emotion_mapper import map_scene_contract

mapped_audio = None
contract = input_data.audio_contract
effective_style_tags = list(input_data.style_tags)
effective_tempo = input_data.tempo_preference
effective_guidance = input_data.guidance_scale
effective_description = input_data.description

if contract:
    mapped_audio = map_scene_contract(contract)
    effective_style_tags.extend(
        tag for tag in mapped_audio.style_tags if tag not in effective_style_tags
    )
    effective_tempo = effective_tempo or mapped_audio.tempo_preference
    effective_guidance = effective_guidance or mapped_audio.guidance_scale
    if mapped_audio.prompt_suffix:
        effective_description = f"{effective_description}. {mapped_audio.prompt_suffix}"
```

Use these effective values when constructing `StyleInput`, applying overrides, and output metadata. Preserve material enrichment by applying material additions to the effective variables, not directly mutating `PipelineInput`.

Extend `OutputInput` in `src/ace_music/tools/output.py` with:

```python
extra_metadata: dict | None = None
```

When `OutputWorker.execute()` builds the metadata dict, merge `extra_metadata` into the top-level metadata before writing the sidecar JSON:

```python
if input_data.extra_metadata:
    metadata.update(input_data.extra_metadata)
```

When building `OutputInput` in `MusicAgent.run`, compute:

```python
contract_metadata = contract.model_dump(mode="json") if contract else None
mapped_metadata = mapped_audio.to_metadata() if mapped_audio else None
```

Then pass these fields to `OutputInput(extra_metadata=extra_metadata)` before `OutputWorker` runs so persisted sidecar metadata and returned `PipelineOutput.metadata` stay identical:

```python
extra_metadata = {}
if contract_metadata:
    extra_metadata["audio_contract"] = contract_metadata
if mapped_metadata:
    extra_metadata["mapped_audio"] = mapped_metadata
    extra_metadata["mix"] = mapped_metadata["mix"]
    extra_metadata["transition"] = mapped_metadata["transition"]
    extra_metadata["qa_targets"] = mapped_metadata["qa_targets"]
```

- [ ] **Step 5: Extend bridge request fields**

Modify `src/ace_music/bridge/__init__.py`:

```python
valence: float | None = Field(default=None, ge=-1.0, le=1.0)
arousal: float | None = Field(default=None, ge=0.0, le=1.0)
shot_count: int | None = Field(default=None, ge=0)
dialogue_density: float = Field(default=0.5, ge=0.0, le=1.0)
tts_present: bool = True
target_lufs: float | None = Field(default=None, ge=-30.0, le=-10.0)
max_true_peak_db: float | None = Field(default=None, ge=-6.0, le=0.0)
crossfade_seconds: float | None = Field(default=None, ge=0.0, le=10.0)
```

- [ ] **Step 6: Convert bridge request to contract**

Modify `src/ace_music/bridge/director_bridge.py` to instantiate `AudioSceneContract`, `AudioLayerPolicy`, `MixPolicy`, and `TransitionPolicy` from request fields. Pass `audio_contract=contract` into `PipelineInput`.

- [ ] **Step 7: Run focused tests**

Run: `python3 -m pytest -q tests/test_audio_contract.py tests/test_pipeline.py`

Expected: PASS.

---

### Task 3: Architecture Documentation and Templates

**Files:**
- Create: `docs/audio-engine-architecture.md`
- Modify: `README.md`
- Add or modify tests only if a doc-link convention already exists; otherwise no tests.

- [ ] **Step 1: Create architecture document**

Create `docs/audio-engine-architecture.md` with these sections:

```markdown
# ace-music Audio Engine Architecture

## A. Current Diagnosis

## B. Upgraded Audio Engine Architecture

## C. Executable Migration Plan

## D. Prompt and Configuration Templates

## E. Acceptance Criteria

## References
```

The document must explicitly state:

- `ace-music` is not an independent composition app; it is the audio generation and emotional score engine for the creative-engine pipeline.
- Current external chain is `novel-writer -> auto-director -> ace-music -> VideoComposer`, with `auto-director` as the direct consumer.
- The upgraded input contract should include chapter/scene emotion curve, scene mood tags, shot pace, dialogue density/TTS presence, role theme, segment boundaries, and output/mix constraints.
- The intermediate artifacts should include `audio_contract`, `mapped_audio`, raw BGM, post-processed BGM, mix policy, transition policy, and QA report.
- The output contract should contain final audio path, metadata, mix/transition policy, QA targets, and composition readiness.
- The emotion mapping should use valence/arousal/intensity as stable internal coordinates, then map to tags, tempo, guidance, loudness, ducking, and crossfade constraints.

- [ ] **Step 2: Include required templates**

Add concrete templates for:

1. Emotion tags -> BGM generation prompt.
2. Story beat -> scoring plan prompt.
3. TTS + BGM mixing strategy prompt.
4. Multi-segment crossfade/transition rules template.
5. Audio QA/review prompt.

Each template must show placeholders such as `{scene_id}`, `{mood}`, `{valence}`, `{arousal}`, `{dialogue_density}`, `{target_lufs}`, `{crossfade_seconds}`.

- [ ] **Step 3: Include P0/P1/P2 roadmap**

Document:

- P0: contract and responsibility correction.
- P1: emotion matching and output stability.
- P2: advanced mixing and long-video adaptation.

- [ ] **Step 4: Include acceptance criteria**

Document thresholds:

- Emotion match score: `>= 0.75` initially, target `>= 0.85` after calibrated evaluator.
- Stitchable segment rate: `>= 0.95`.
- Mixed TTS intelligibility: no BGM-over-dialogue conflict above `0.05` conflict rate.
- Loudness/peak compliance: default `target_lufs=-18`, `max_true_peak_db=-1.5`, configurable per platform.
- Final composition success rate: `>= 0.98` in mock/contract lane.

- [ ] **Step 5: Update README pointer**

Add a short section:

```markdown
## Contract-Driven Audio Engine

`ace-music` can also consume `AudioSceneContract` for narrative/video workflows.
See `docs/audio-engine-architecture.md` for the structured input contract,
emotion mapping, mix policy, transition rules, and QA acceptance criteria.
```

- [ ] **Step 6: Run doc-adjacent validation**

Run: `test -f docs/audio-engine-architecture.md && rg -n "AudioSceneContract|Emotion tags|Acceptance Criteria" docs/audio-engine-architecture.md README.md`

Expected: command exits `0` and prints matching lines.

---

### Task 4: Final Regression and Static Validation

**Files:**
- No new files unless a previous task requires a fix.

- [ ] **Step 1: Run focused regression suite**

Run: `python3 -m pytest -q tests/test_audio_contract.py tests/test_pipeline.py tests/test_material_pipeline.py tests/test_output.py tests/test_post_processor.py`

Expected: PASS.

- [ ] **Step 2: Run non-integration suite**

Run: `python3 -m pytest -q -m "not integration"`

Expected: PASS.

- [ ] **Step 3: Run lint**

Run: `python3 -m ruff check src tests`

Expected: PASS. If `ruff` is unavailable, report it as a verification gap rather than adding a dependency.

- [ ] **Step 4: Inspect git status**

Run: `git status --short`

Expected: only planned files are modified/created.

- [ ] **Step 5: Final review handoff**

Dispatch a final code-reviewer subagent with:

- Plan path: `docs/superpowers/plans/2026-04-25-audio-engine-contracts.md`
- Changed files from `git status --short`
- Verification output summaries.

Expected: Approved or issues fixed before completion.

---

## Non-Goals

- Do not build a real FFmpeg mixer in this slice.
- Do not add ML-based emotion classification.
- Do not add new providers or model APIs.
- Do not change `auto-director` in this branch.
- Do not replace the existing style planner; the mapper only provides structured hints.
