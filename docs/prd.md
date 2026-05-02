# PRD v0.3.0: Ace-Music Pipeline

> 文档定位：执行型 PRD。当前活跃真相以 `ace-music` 运行时、Pydantic schema 和可验证恢复协议为核心。
>
> 真源优先级：用户指令 > `AGENTS.md` > 当前代码与测试
>
> 交叉验证依据：
> - `src/ace_music/agent.py`
> - `src/ace_music/tools/`
> - `src/ace_music/schemas/`
> - `src/ace_music/providers/router.py`
> - `src/ace_music/bridge/`

---

## 1. 产品定位

- 将文本描述 + 可选歌词/风格/素材编译为确定性的音频生产资产，而不是直接调用模型端点。
- 支持三条后端管线：`local`（ACEStep）、`minimax`（MiniMax 云 API）、`stable_audio`（Stability API）。
- 所有运行时参数必须由 Pydantic schema 约束；所有 LLM 交互必须经 `FeatureRouter` 路由。
- Bridge 层面向外部导演系统暴露 `DirectorBridge` HTTP 接口。
- Mock 模式生成确定性正弦波 WAV，无需 GPU/API key，用于 CI 与冒烟测试。
- 产物不是"只是一个音频文件"，而是经过验证的、契约形状的音频资产（含元数据、验证记录、机器可读摘要）。

## 2. 核心产物链

当前主产物链路（local 后端完整流程）：

```text
PipelineInput
  -> MaterialContext          (material_loader)
  -> LyricsOutput             (lyrics_planner)
  -> StyleOutput              (style_planner)
  -> AudioOutput              (generator / minimax_generator / stable_audio_generator)
  -> ProcessedAudio           (post_processor, 可选)
  -> PipelineOutput           (output)
```

- `generator_backend` 字段决定后端分支：`local` | `minimax` | `stable_audio`。
- `post_processor` 仅在输出格式非 mp3 时激活（local 管线）。
- 云后端（`minimax`、`stable_audio`）跳过 `post_processor` 阶段。
- 每个阶段接收类型化输入、产生类型化输出；验证在 post-processing 后和 output 后各执行一次。

## 3. 工具目录

| 工具 | 类 | 核心方法 | 职责 |
|------|-----|---------|------|
| `audio_validator.py` | `AudioValidator` | `validate()` | WAV 格式/采样率/时长/可播放性验证 |
| `emotion_mapper.py` | — | `map_scene_contract()` | Russell 环形模型映射 valence/arousal → 音频标签 |
| `generator.py` | `ACEStepGenerator` | `run()` | 本地 ACEStep 模型推理 |
| `lyrics_planner.py` | `LyricsPlanner` | `run()` | 解析 tagged/plain/instrumental 歌词 |
| `material_loader.py` | `MaterialLoader` | `load()` / `load_latest()` | 加载素材到 `MaterialContext` |
| `minimax_generator.py` | `MiniMaxMusicGenerator` | `run()` | MiniMax 云 API 生成 |
| `output.py` | `OutputWorker` | `run()` | 文件输出 + 元数据写入 |
| `post_processor.py` | `PostProcessor` | `run()` | 格式转换/响度归一化/静音裁剪 |
| `preset_resolver.py` | `PresetResolver` | `resolve()` | YAML 预设匹配（exact_id/exact_name/keyword） |
| `stable_audio_generator.py` | `StableAudioGenerator` | `run()` | Stability API 生成（轮询模式） |
| `style_planner.py` | `StylePlanner` | `run()` | 描述→标签提取 + 可选 LLM 增强 |

## 4. Schema 目录

### 4.1 输入契约

- **`PipelineInput`**：`description`, `lyrics`, `style_tags`, `duration_seconds`, `language`, `is_instrumental`, `seed`, `output_format`, `output_dir`, `tempo_preference`, `mood`, `preset_name`, `guidance_scale`, `infer_step`, `output_config`, `audio_contract`, `passthrough_audio_contract`, `material`, `generator_backend`
- **`LyricsInput`**：`raw_text`, `language`, `is_instrumental`
- **`StyleInput`**：`description`, `reference_tags`, `reference_audio_path`, `tempo_preference`, `mood`
- **`GenerationInput`**（ACEStep）：`lyrics`, `style`, `audio_duration`, `seed`, `batch_size`, `output_dir`, `format`
- **`MiniMaxMusicInput`**：`description`, `mode`（`instrumental` | `lyrics` | `cover`）, `lyrics`, `ref_audio`, `output_dir`
- **`StableAudioInput`**：`description`, `duration_seconds`, `mode`, `output_dir`
- **`PostProcessInput`**：`audio`, `target_format`, `normalize_loudness`, `target_lufs`, `trim_silence`, `silence_threshold_db`, `output_dir`, `audio_contract`
- **`OutputInput`**：`audio`, `style`, `seed`, `lyrics_text`, `description`, `output_dir`, `output_config`, `extra_metadata`, `material_provenance`

### 4.2 场景契约

- **`AudioSceneContract`**：`scene_id`, `mood`, `duration_seconds`, `style_reference`, `genre`, `tempo_bpm`, `key_signature`, `time_signature`, `vocal_required`, `language`, `lyrics`, `audio_layer_policy`, `transition_policy`, `mix_policy`, `qa_targets`, `segment_cues`, `description`
  - 这是跨系统契约，不是可选提示词。`auto-director` 产出此契约，`ace-music` 消费它。

### 4.3 中间产物

- **`LyricsOutput`**：`segments`, `formatted_lyrics`, `language`, `is_instrumental`, `total_estimated_duration`
- **`StyleOutput`**：`tags`, `prompt`, `guidance_scale`, `omega_scale`, `infer_step`, `scheduler_type`, `cfg_type`, `guidance_interval`, `guidance_interval_decay`, `min_guidance_scale`, `use_erg_tag`, `use_erg_lyric`, `use_erg_diffusion`, `tempo_bpm`, `key_signature`
- **`MaterialContext`**：`entries`（list[`MaterialEntry`]）
  - `MaterialEntry`：`source_file`, `content`, `category`, `tags`, `mood`, `style`
- **`PresetMatch`**：`preset`, `confidence`, `match_method`（`exact_id` | `exact_name` | `keyword`）

### 4.4 输出契约

- **`AudioOutput`**：`file_path`, `duration_seconds`, `sample_rate`, `format`, `channels`
- **`ProcessedAudio`**：`file_path`, `duration_seconds`, `sample_rate`, `format`, `channels`, `loudness_lufs`, `peak_db`
- **`PipelineOutput`**：`audio_path`, `metadata_path`, `duration_seconds`, `format`, `sample_rate`, `seed`, `description`, `style_tags`, `lyrics_text`, `artifacts`, `run_id`

### 4.5 预设与验证

- **`StylePreset`**：`id`, `name`, `description`, `prompt`, `guidance_scale`, `omega_scale`, `infer_step`, `scheduler_type`, `cfg_type`, `guidance_interval`, `guidance_interval_decay`, `min_guidance_scale`, `use_erg_tag`, `use_erg_lyric`, `use_erg_diffusion`, `tempo_range`
- **`PresetStyleOverrides`**：与 `StylePreset` 相同字段（不含 `id`/`name`/`description`/`prompt`/`tempo_range`），用于预设叠加覆盖
- **`ValidationResult`**：`file_path`, `is_valid`, `format`, `sample_rate`, `channels`, `duration_seconds`, `file_size_bytes`, `errors`
- **`OutputConfig`**：`base_dir`, `naming`（`nested` | `flat`）, `filename_template`, `create_metadata`

### 4.6 配置与运行时

- **`GeneratorConfig`**（ACEStep）：`checkpoint_dir`, `device_id`, `dtype`, `torch_compile`, `cpu_offload`
- **`MiniMaxMusicConfig`**：`api_key`, `base_url`, `timeout`, `rate_limit_per_minute`, `sample_rate`, `audio_format`, `output_format`
- **`StableAudioConfig`**：`api_key`, `base_url`, `timeout`, `rate_limit_per_minute`, `audio_format`, `poll_interval_seconds`, `poll_timeout_seconds`
- **`RunManifest`**：`run_id`, `description`, `seed`, `preset_name`, `artifacts`（dict[str, `ArtifactRecord`]）
- **`ArtifactStatus`**：`PENDING` | `IN_PROGRESS` | `COMPLETED` | `FAILED` | `SKIPPED`

## 5. Provider 路由

- **`FeatureRouter`**：按 feature name 路由 LLM 请求到 `ChatProvider` 实例。
  - `complete(feature, messages)` → `ChatResponse`
  - `default_provider` + `feature_providers` dict 覆盖
- `FeatureRouter` 仅管理 LLM 文本补全，不负责生成器后端选择。
- 生成器后端选择由 `PipelineInput.generator_backend` 字段在 `agent.py` 中分发。
- 两个路由系统互不耦合：`FeatureRouter` 管 LLM 调用，`agent.py` 管生成器分发。

## 6. Pipeline 模式

### 6.1 Local Pipeline (`_run_local_pipeline`)

```text
lyrics_planner → style_planner → ACEStepGenerator → post_processor → output
```

- 完整 5 阶段。`post_processor` 在输出格式非 mp3 时激活。

### 6.2 MiniMax Pipeline (`_run_minimax_pipeline`)

```text
lyrics_planner → style_planner → MiniMaxMusicGenerator → output
```

- `MiniMaxMusicInput.mode`：`instrumental` | `lyrics` | `cover`
- 跳过 `post_processor`。

### 6.3 Stable Audio Pipeline (`_run_stable_audio_pipeline`)

```text
lyrics_planner → style_planner → StableAudioGenerator → output
```

- `StableAudioInput.mode`，轮询模式等待生成完成。
- 跳过 `post_processor`。

## 7. 恢复机制

- `resume(run_id)` 从 `RunManifest` 加载已运行状态。
- `stages_to_run()` 检查 `completed_stages`，返回未完成阶段列表。
- Pipeline 从首个未完成阶段重新进入，已完成的阶段产出直接复用。
- `ArtifactStatus` 跟踪每个工件生命周期：`PENDING` → `IN_PROGRESS` → `COMPLETED` / `FAILED` / `SKIPPED`。
- 恢复必须验证 `RunManifest` 存在且 `completed_stages` 与实际工件一致，不得跳过阶段验证。

## 8. 验证门

- **`AudioValidator`** 检查项：
  - WAV 格式校验
  - `sample_rate` 默认 48000 Hz
  - 最小时长 1.0 秒
  - 时长偏差容限 5.0 秒（`expected_duration`）
  - 文件存在性
  - 可播放性
- 验证失败必须返回 `ValidationResult.errors`，不得静默通过。
- **`PostProcessor`** 混音 profile（`MIX_PROFILES`）：
  - `streaming`：流媒体响度标准
  - `radio`：广播响度标准
  - `cinematic`：影院响度标准
- 验证在 post-processing 后和 output 后各执行一次。

## 9. Bridge API

- **`DirectorBridge`**（version `"1.0"`）面向外部导演系统。

### 9.1 Request 字段

`scene_id`, `mood`, `duration_seconds`, `style_reference`, `lyrics_hint`, `tempo_preference`, `output_format`, `seed`, `scene_description`, `intensity`, `valence`

### 9.2 Response 字段

`audio_path`, `metadata_path`, `duration_seconds`, `format`, `sample_rate`, `seed_used`, `style_tags`, `run_id`, `status`（`success` | `failed` | `partial`）, `error_message`

## 10. MUST 约束

- 保持 Python-first、Pydantic-first、deterministic
- 所有 schema 字段名必须与 Pydantic 模型定义一致
- 生成器后端选择必须通过 `PipelineInput.generator_backend` 字段
- `FeatureRouter` 与生成器路由是两个独立系统，不得混淆
- 恢复必须基于 `RunManifest`，不得跳过阶段验证
- 验证失败必须返回 `ValidationResult.errors`，不得静默通过
- Bridge response 的 `status` 必须是 `success` / `failed` / `partial` 三值之一

## 11. DO NOT 约束

- 不要把 LLM prompt 规则散落到工具、schema 或 glue 代码
- 不要静默 clamp、auto-heal、fallback 到默认参数
- 不要在 `FeatureRouter` 中硬编码生成器后端逻辑
- 不要将 `AudioSceneContract` 字段作为可选提示词使用——它是契约
- 不要跳过 `post_processor` 的响度归一化（当 pipeline 包含该阶段时）
- 不要在没有 `RunManifest` 的情况下声称恢复完成
