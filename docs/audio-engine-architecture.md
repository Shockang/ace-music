# ace-music Audio Engine Architecture

## A. Current Diagnosis

`ace-music` is not an independent composition app. It is the audio generation and emotional score engine inside the broader creative-engine pipeline. The current direct integration path is `novel-writer -> auto-director -> ace-music -> VideoComposer`, with `auto-director` as the direct consumer and `VideoComposer` as the downstream composition layer.

Today the core pipeline is already stable and readable: `LyricsPlanner -> StylePlanner -> Generator -> PostProcessor -> OutputWorker`. The main weakness is not missing orchestration, but missing contract depth. Before this slice, upstream systems could pass description, mood, tempo, and a few style hints, but they could not express scene-level emotional coordinates, dialogue density, loudness ceilings, transition constraints, or segment boundaries in a structured way.

The practical result was a gap between intent and audio output:

- `DirectorBridge` accepted some useful fields such as `intensity`, but did not turn them into stable generation constraints.
- Output metadata did not persist enough mix and QA structure for downstream validation.
- Multi-segment intent existed conceptually, but not as a minimal first-class contract.

## B. Upgraded Audio Engine Architecture

### Structured Input Contract

The upgraded input contract is `AudioSceneContract`. It is designed to express the information that an orchestration system already knows before audio generation begins:

- Scene identity: `scene_id`
- Duration target: `duration_seconds`
- Emotional intent: `mood`, `valence`, `arousal`, `intensity`
- Narrative context: `scene_description`, `narrative_beat`, `role_theme`
- Video pace proxy: `shot_count`
- Dialogue/TTS pressure: `dialogue_density`, `layers.tts_present`
- Mix constraints: `target_lufs`, `max_true_peak_db`
- Transition constraints: `crossfade_seconds`, looping/tail expectations
- Segment boundaries: `segments[]`, each with `segment_id`, `start_seconds`, `end_seconds`, optional segment mood/intensity, and optional segment transition override

This is intentionally a narrow contract layer beside `PipelineInput`, not a replacement for the existing pipeline. Existing description-driven flows still work. Contract-driven flows add structure when upstream systems have it.

### Emotion Mapping System

The first implemented mapping layer is deterministic. It uses `valence`, `arousal`, `intensity`, mood labels, and dialogue context to derive:

- Style tags
- Tempo preference
- Guidance scale hint
- Mix policy
- Transition policy
- QA targets

The internal rule is:

- `arousal` primarily influences pace and energy
- `valence` influences tonal direction and emotional color
- `intensity` scales generation strength
- `dialogue_density` and `tts_present` influence ducking and BGM gain

This keeps the mapping stable and regression-testable. It does not attempt ML-based emotion inference in this slice.

### Intermediate Artifacts

The engine should treat these as first-class intermediate artifacts:

- `audio_contract`: the normalized structured upstream request
- `mapped_audio`: deterministic generation and mix hints derived from the contract
- Raw BGM output from generation
- Post-processed BGM output
- Mix policy for TTS/BGM coexistence
- Transition policy for segment joins
- QA targets for duration, emotion match, composition success, and dialogue conflict
- A future QA report artifact that records measured results against those targets

### Output Contract

The output contract should include:

- Final audio path
- Audio metadata
- Persisted `audio_contract`
- Persisted `mapped_audio`
- Persisted `mix`
- Persisted `transition`
- Persisted `qa_targets`
- The information required for downstream composition-readiness checks in later phases

This slice already persists the contract-derived metadata into the sidecar JSON so downstream systems do not need to reconstruct it from in-memory state.

### TTS, BGM, Ambience, and Mixing Layers

The layering model is:

- TTS/dialogue is the protected foreground signal
- BGM carries emotion, pacing, and continuity
- Ambience and effects are optional later layers, not required in this slice

The immediate engineering rule is simple:

- If `tts_present=True`, BGM gain can be reduced and ducking can increase with dialogue density
- If `tts_present=False`, ducking stays at the base mix policy and sidechain source remains `none`

This prevents contradictory mixing instructions such as “strong ducking with no sidechain source”.

## C. Executable Migration Plan

### P0: Contract and Responsibility Correction

- Add `AudioSceneContract` and `AudioSegmentCue`
- Validate segment ordering, overlap, and bounds
- Map `DirectorBridge.Request` into `AudioSceneContract`
- Pass contract-derived metadata into persisted output sidecars
- Keep backward compatibility for legacy `PipelineInput(description=...)` flows

### P1: Emotion Matching and Output Stability

- Expand deterministic mood-to-tag coverage
- Refine valence/arousal to tempo/guidance heuristics
- Add automated scoring for emotion-match drift
- Add contract-aware resume and manifest persistence so interrupted runs preserve the original structured request
- Expose contract/material inputs cleanly in CLI or config-driven entrypoints

### P2: Advanced Mixing and Long-Video Adaptation

- Add per-segment generation and stitching workflows
- Introduce explicit ambience/effects layer contracts
- Add long-form asset management for multiple scenes and segment reuse
- Add FFmpeg or equivalent mixing/composition lane for crossfade, loudness normalization, and sidechain automation
- Add composition QA against real TTS/video assembly outputs

## D. Prompt and Configuration Templates

### Emotion Tags -> BGM Prompt

```text
Generate background music for scene {scene_id}.
Mood: {mood}
Valence: {valence}
Arousal: {arousal}
Intensity: {intensity}
Role theme: {role_theme}
Scene description: {scene_description}
Required pacing: {tempo_preference}
Transition requirement: {crossfade_seconds}s crossfade
Keep the output stitchable, mix-safe under dialogue, and emotionally stable.
```

### Story Beat -> Scoring Plan Prompt

```text
Create a scoring plan for scene {scene_id}.
Narrative beat: {narrative_beat}
Mood: {mood}
Valence/arousal: {valence}/{arousal}
Shot pace proxy: {shot_count}
Dialogue density: {dialogue_density}
Segment boundaries: {segments}
Return segment-level BGM intent, pacing shifts, and transition notes only.
```

### TTS + BGM Mixing Strategy Prompt

```text
Define a TTS-safe mixing strategy for scene {scene_id}.
TTS present: {tts_present}
Dialogue density: {dialogue_density}
Target loudness: {target_lufs} LUFS
Max true peak: {max_true_peak_db} dBTP
Base BGM gain: {bgm_gain_db} dB
Ducking target: {ducking_db} dB
Crossfade target: {crossfade_seconds}s
Output a stable foreground/background balance plan with no dialogue masking.
```

### Multi-Segment Crossfade / Transition Rules Template

```text
Scene {scene_id} transition rules
- Segment list: {segments}
- Default crossfade: {crossfade_seconds}s
- Allow looping: {allow_looping}
- Require seamless tail: {require_seamless_tail}
- If adjacent segment moods diverge, smooth with a ramp instead of a hard cut.
- Do not allow overlapping musical peaks during crossfade.
- Preserve stitchable tempo and tonal continuity unless the segment metadata explicitly requests a break.
```

### Audio QA / Review Prompt

```text
Review generated audio for scene {scene_id}.
Mood target: {mood}
Valence/arousal target: {valence}/{arousal}
Dialogue density: {dialogue_density}
Target loudness: {target_lufs}
Max true peak: {max_true_peak_db}
Crossfade target: {crossfade_seconds}
Acceptance checks:
- duration within tolerance
- emotion match score
- stitchable transition quality
- dialogue conflict rate
- composition readiness
Return pass/fail plus the failed metric names.
```

## E. Acceptance Criteria

Initial engineering acceptance targets:

- Emotion match score: `>= 0.75`
- Calibrated future target: `>= 0.85`
- Stitchable segment rate: `>= 0.95`
- Mixed TTS intelligibility: dialogue conflict rate `<= 0.05`
- Loudness compliance default: `target_lufs=-18`
- True peak ceiling default: `max_true_peak_db=-1.5`
- Final composition success rate: `>= 0.98`

These are contract targets first. Later phases should add actual evaluators and composition-lane measurements to confirm them against real rendered outputs.

## References

- FFmpeg filters: `amix`, `acrossfade`, `loudnorm`, `sidechaincompress` via https://ffmpeg.org/ffmpeg-filters.html
- EBU R 128 loudness recommendation via https://tech.ebu.ch/publications/r128
- Music emotion recognition survey on valence/arousal via https://pmc.ncbi.nlm.nih.gov/articles/PMC9837297/
- Video soundtrack generation alignment work via https://arxiv.org/abs/2502.10154
