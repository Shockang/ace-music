# ace-music

[English](README.md)

[![CI](https://github.com/Shockang/ace-music/actions/workflows/ci.yml/badge.svg)](https://github.com/Shockang/ace-music/actions/workflows/ci.yml)
![License: MIT](https://img.shields.io/badge/license-MIT-0f172a.svg)
![Python 3.12](https://img.shields.io/badge/python-3.12-06b6d4.svg)
![269 tests](https://img.shields.io/badge/tests-269_passed-22c55e.svg)

![ace-music banner](assets/ace-music.png)

契约驱动的 AI 音乐生成，面向 Python 工作流、自动化管线和场景化配乐生产。

`ace-music` 是 [`auto-director`](https://github.com/Shockang/auto-director) 的配套开源工程。`auto-director` 负责故事结构和提示词生产，`ace-music` 负责配乐生成和校验。两者拼在一起，就是一条从文本到画面再到声音的可组合工具链。

## 概述

`ace-music` 是一个契约驱动的音乐生成工具包。

它不是一个直接调用模型端点、然后祈祷输出时长/格式/响度刚好对得上的工具。`ace-music` 运行的是一条结构化管线，每个阶段都内建校验：

```text
PipelineInput
  -> LyricsPlanner（歌词规划）
  -> StylePlanner（风格规划）
  -> Generator（ACE-Step / MiniMax / StableAudio）
  -> PostProcessor（后处理）
  -> OutputWorker（输出）
  -> PipelineOutput（已校验）
```

结果不是"只是一个音频文件"。

结果是一个经过校验、符合契约形态的音频资产，附带元数据、校验记录和机器可读摘要。

## 生态关系

```text
纯文本小说片段
      |
      v
  auto-director
      |
      +--> story / cast / screenplay / scene blueprint / prompt package / review / delivery
      |
      +--> 可选 render handoff assets
      |
      +--> 场景合约、情绪、时长
              |
              v
        ace-music
              |
              +--> 场景化配乐生成
              +--> 带校验的音频输出与元数据
              +--> 混音 / 闪避 / 响度合约
```

分工很清楚：

- `auto-director` 处理故事结构、角色连续性、场景蓝图、提示包、评审工件和交付资产
- `ace-music` 处理配乐生成、音频校验、mock 模式测试和场景化音乐工作流

这不是两个互不相干的项目硬凑在一起。`ace-music` 的 `DirectorBridge` 契约就是专门为 `auto-director` 的场景编排接口设计的。

如果你只想单独用 `ace-music` 做音乐生成，完全可以。它不依赖 `auto-director`，可以独立安装和运行。但如果你在做一个从文本到视频再到配乐的完整工作流，两个项目拼在一起会更省事。

## 为什么值得一看

大多数 AI 音乐生成工具的问题都差不多：

- 输出质量不可预测，每次跑出来的东西差异很大
- 没有结构化接口，集成进工作流很痛苦
- 校验和后处理要么没有，要么需要自己搭
- CI 环境跑不了，因为没有 GPU 就会炸
- 调试靠听，没有元数据可以检查

`ace-music` 试图把这些问题收拾得更干净：

- 契约驱动的管线设计，输入输出都是结构化的
- mock 模式让无 GPU 环境也能跑完整验证
- 内建音频校验和后处理链（响度归一化、格式转换）
- CLI 输出机器可读的 JSON 摘要，适合自动化管线消费
- 多后端支持（本地 ACE-Step、MiniMax 云端、Stable Audio），按场景选择

如果你之前试过用 API 做音乐生成，大概率踩过这些坑：输出时长对不上、格式不统一、没有校验环节、在 CI 里跑不起来。`ace-music` 就是冲着这些问题来的。它不是一个"调用 API 然后保存文件"的薄封装，而是一条完整的从输入到校验到输出的管线。

## 功能一览

| 能力 | 说明 |
| --- | --- |
| 稳定 CLI | `generate` 和 `validate` 命令，退出码语义明确 |
| 多后端 | mock、本地 ACE-Step、MiniMax、Stable Audio |
| 结构化契约 | `PipelineInput`、`AudioSceneContract`、`DirectorBridge` |
| 自动化友好 | JSON 摘要、校验元数据、可预测的输出路径 |
| 可测试发布面 | CPU 安全的 mock 模式，贡献者不需要 GPU 也能验证改动 |
| 场景化编排 | 通过 `DirectorBridge.Request` 接受场景描述、情绪标签、强度、效价等参数 |
| 后处理链 | 响度归一化 (LUFS)、格式转换、混音 profile |
| 可恢复运行 | manifest 追踪每个阶段状态，失败后可以从断点恢复 |
| 9 个 schema 模块 | PipelineInput、PipelineOutput、AudioSceneContract、StyleInput、StyleOutput、LyricsInput、LyricsOutput、MaterialContext、OutputConfig |
| 269 个测试通过 | 完整管线覆盖，包括断点恢复、校验和边界情况 |

## 管线架构

`MusicAgent` 是核心编排器。它走的是一个五阶段管线：

```text
MusicAgent
  -> LyricsPlanner       (歌词解析与结构化)
  -> StylePlanner        (风格映射到 ACE-Step 参数)
  -> Generator           (调用 ACE-Step 模型，或 MiniMax / Stable Audio)
  -> PostProcessor       (响度归一化、格式转换、混音处理)
  -> OutputWorker        (写文件 + 元数据)
```

每个阶段的职责：

1. **LyricsPlanner** — 解析原始歌词文本，切分为定时段落。如果输入是纯器乐，这步直接跳过。
2. **StylePlanner** — 把自然语言描述和风格标签映射成 ACE-Step 模型能理解的参数（BPM、调性、配器等）。
3. **Generator** — 调用模型生成音频。本地走 ACE-Step，云端走 MiniMax 或 Stable Audio。
4. **PostProcessor** — DSP 后处理链：响度归一化（LUFS 目标）、格式转换、混音 profile 应用。
5. **OutputWorker** — 写文件、生成元数据 JSON、跑最终校验。

每一步的输入输出都有明确的类型定义（pydantic schema）。管线是分阶段执行的，不是把所有东西塞进一个大黑盒。

MiniMax 和 Stable Audio 后端走简化管线，跳过歌词规划和后处理（云端 API 返回的音频已经处理过）。云端后端的好处是不需要本地 GPU，坏处是你对生成参数的控制粒度会小一些。

Mock 模式生成的是确定性正弦波 WAV，不是模型输出。它的用途是跑通整个管线、验证契约、检查输出结构。不要用它来评估音质。

## 工具模块一览

`ace-music` 内部有 11 个工具模块，各管一件事：

| 模块 | 职责 |
| --- | --- |
| `audio_validator` | 校验音频文件是否符合时长、采样率、格式要求。CLI `validate` 命令就是调这个 |
| `emotion_mapper` | 把场景契约（情绪、强度、效价）映射成音频参数（节拍、风格标签、混音策略） |
| `generator` | ACE-Step 本地生成器。支持 mock 模式和多种模型变体（2b、xl-base、xl-sft、xl-turbo） |
| `lyrics_planner` | 解析原始歌词文本，切分成定时段落。输入是 `LyricsInput`，输出是 `LyricsOutput` |
| `material_loader` | 加载素材上下文（灵感、风格参考、歌词来源），给管线提供额外参考信息 |
| `minimax_generator` | MiniMax 云端后端。支持器乐、带歌词和翻唱三种模式。需要 `MINIMAX_API_KEY` |
| `stable_audio_generator` | Stable Audio 云端后端。仅支持器乐生成。需要对应 API 配置 |
| `output` | OutputWorker。写最终音频文件、元数据 JSON、跑最终校验 |
| `post_processor` | DSP 链：响度归一化（LUFS 目标）、格式转换、混音 profile 应用 |
| `preset_resolver` | 把命名的风格预设解析成具体参数。预设名对应一组固定的生成参数 |
| `style_planner` | 风格映射。把描述和标签转成 ACE-Step 的生成参数 |

加上 9 个 schema 模块定义数据契约，20 个测试文件覆盖全部功能。当前测试结果：269 passed, 4 skipped, 0 failed。

## 运行模式

| 模式 | 适用场景 | 前置条件 |
| --- | --- | --- |
| Mock | 冒烟测试、CI、首次验证 | 无需 GPU |
| ACE-Step 本地 | 本地高保真生成 | 兼容 GPU，模型已配置 |
| MiniMax | 云端生成 | `MINIMAX_API_KEY` |
| Stable Audio | 云端纯器乐生成 | 对应 API 配置 |

可选依赖组：

| Extra | 安装内容 |
| --- | --- |
| `.[dev]` | 测试运行器、linters、开发工具。贡献代码必须安装 |
| `.[model]` | PyTorch、soundfile 和 GPU/音频依赖。仅用于本地 ACE-Step 生成 |
| `.[audio]` | 额外的音频处理库 |

`.[model]` 从 CI 中排除。只在有 CUDA 工具链的机器上安装。

## auto-director 集成

`DirectorBridge` 是 `ace-music` 为外部编排系统提供的标准请求/响应契约。它的设计直接服务于 `auto-director` 的场景化音乐需求。

`DirectorBridge.Request` 接受的参数包括：

- `scene_id`: 场景标识
- `mood`: 情绪标签（如 'melancholic'、'upbeat'）
- `duration_seconds`: 目标时长（5-240 秒）
- `intensity`: 情绪强度（0.0-1.0）
- `valence`: 效价坐标
- `arousal`: 唤醒度坐标
- `dialogue_density`: 对话密度
- `tts_present`: 是否有 TTS/对话（影响混音策略）
- `preset_name`: 风格预设名称
- `target_lufs`: 目标响度

`DirectorBridge.Response` 返回生成音频路径、实际时长、元数据和对应的 scene_id。

这个契约让 `auto-director` 可以直接按场景请求配乐，不需要了解 `ace-music` 的内部管线细节。

### DirectorBridge.Request 示例

```python
from ace_music.bridge import DirectorBridge

request = DirectorBridge.Request(
    scene_id="scene_042",
    mood="melancholic",
    duration_seconds=30.0,
    style_reference="piano, slow tempo, minor key",
    scene_description="Character walks alone through rain-soaked streets at night",
    intensity=0.7,
    valence=-0.3,
    arousal=0.4,
    dialogue_density=0.2,
    tts_present=False,
    target_lufs=-16.0,
    preset_name="dark_ambient",
)
```

### DirectorBridge.Response 示例

```python
response = DirectorBridge.Response(
    audio_path="/output/scene_042.wav",
    duration_seconds=29.8,
    format="wav",
    scene_id="scene_042",
    success=True,
    metadata={"seed": 42, "bpm": 72, "style": "dark ambient, piano"},
)
```

`auto-director` 生产场景契约，`ace-music` 消费契约并生成满足要求的音频。这就是两个项目之间的全部接口。

## 快速上手

最短的成功路径用的是 mock 模式，不需要 GPU：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
ace-music generate \
  --mock \
  --description "short jazz improvisation" \
  --duration 5 \
  --output-dir ./output \
  --summary-json ./output/last-run.json
```

正常的话，你会得到一个生成的 WAV 文件和一个 JSON 摘要，路径在 `./output/last-run.json`。

## 安装

开发环境 + mock 模式：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

如果你有 GPU，想跑本地生成：

```bash
pip install -e ".[dev,model]"
```

`.[model]` 安装的是项目 Python 侧的 GPU/音频依赖。ACE-Step 运行时本身是外部依赖，需要在目标机器上单独安装和配置。这个 extra 故意从 CI 中排除。

## CLI 参考

生成音频：

```bash
ace-music generate \
  --mock \
  --description "dreamy synthwave with warm pads" \
  --duration 10 \
  --backend acestep \
  --output-dir ./output \
  --summary-json ./output/run.json
```

校验一个已生成的 WAV 文件：

```bash
ace-music validate ./output/generated.wav \
  --expected-sample-rate 48000 \
  --expected-duration 10 \
  --duration-tolerance 5
```

`generate` 命令支持的常用参数（完整列表见 `ace-music generate --help`）：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--description` | 必填 | 自然语言音乐描述 |
| `--backend` | `acestep` | `acestep`、`minimax` 或 `stable_audio` |
| `--mode` | `instrumental` | `instrumental`、`lyrics` 或 `cover`（MiniMax） |
| `--model-variant` | `2b` | `2b`、`xl-base`、`xl-sft`、`xl-turbo`（ACE-Step） |
| `--duration` | `30.0` | 目标时长，5-240 秒 |
| `--mock` | 关闭 | 确定性本地 WAV，不需要 GPU |
| `--preset` | 无 | 命名风格预设 |
| `--seed` | 随机 | 可复现种子 |
| `--format` | `wav` | 输出音频格式 |
| `--output-dir` | `./output` | 输出目录 |
| `--target-lufs` | 无 | 目标输出响度 |
| `--total-timeout` | 自动 | 命令总超时时间 |
| `--summary-json` | 无 | 机器可读 JSON 摘要输出路径 |

`validate` 命令校验采样率、时长和格式。通过返回退出码 0，失败返回 50。始终输出 JSON 摘要。

## Python API

```python
import asyncio

from ace_music.agent import MusicAgent
from ace_music.schemas.pipeline import PipelineInput
from ace_music.tools.generator import GeneratorConfig


async def main() -> None:
    agent = MusicAgent(generator_config=GeneratorConfig(mock_mode=True))
    result = await agent.run(
        PipelineInput(
            description="A dreamy synthwave track about neon cities",
            duration_seconds=20.0,
            output_dir="./output",
        )
    )
    print(result.audio_path)
    print(result.duration_seconds)
    print(result.metadata.get("validation"))


asyncio.run(main())
```

`MusicAgent` 也支持批量生成（`run_sequence`）和断点恢复（`resume`）。具体接口见源码 `src/ace_music/agent.py`。

### 批量生成

```python
results = await agent.run_sequence(
    [
        PipelineInput(description="Opening credits theme", duration_seconds=30.0),
        PipelineInput(description="Tense underscore", duration_seconds=45.0),
        PipelineInput(description="Closing credits", duration_seconds=30.0),
    ]
)
```

### 断点恢复

```python
from ace_music.workspace import WorkspaceManager

workspace = WorkspaceManager(base_dir="./workspace")
result = await agent.resume(run_id="abc123", workspace=workspace)
```

管线追踪每个阶段的完成状态。如果某个阶段失败，`resume` 会跳过已完成的阶段，从断点继续执行。

## 架构

```text
MusicAgent
  |
  +-- LyricsPlanner ........... src/ace_music/tools/lyrics_planner.py
  +-- StylePlanner ............ src/ace_music/tools/style_planner.py
  +-- EmotionMapper ........... src/ace_music/tools/emotion_mapper.py
  +-- PresetResolver .......... src/ace_music/tools/preset_resolver.py
  +-- MaterialLoader .......... src/ace_music/tools/material_loader.py
  |
  +-- ACEStepGenerator ........ src/ace_music/tools/generator.py
  +-- MiniMaxMusicGenerator ... src/ace_music/tools/minimax_generator.py
  +-- StableAudioGenerator .... src/ace_music/tools/stable_audio_generator.py
  |
  +-- PostProcessor ........... src/ace_music/tools/post_processor.py
  +-- AudioValidator .......... src/ace_music/tools/audio_validator.py
  +-- OutputWorker ............ src/ace_music/tools/output.py
  |
  +-- DirectorBridge .......... src/ace_music/bridge/__init__.py
  +-- WorkspaceManager ........ src/ace_music/workspace.py
  +-- FeatureRouter ........... src/ace_music/providers/router.py
```

Schema 层（`src/ace_music/schemas/`）：`pipeline`、`audio_contract`、`audio`、`lyrics`、`material`、`output_config`、`preset`、`repair`、`style`。

默认流程是契约驱动、分阶段执行的。每个阶段的输入输出都有 pydantic schema 定义。详细设计见 [docs/audio-engine-architecture.md](docs/audio-engine-architecture.md)。

核心设计决策：

- **Planning 模式**：`MusicAgent` 先规划执行计划（决定哪些阶段需要运行），再按顺序执行。不是所有请求都需要跑全部五个阶段。
- **多后端路由**：`_build_plan` 根据 `backend` 字段选择不同的管线。ACE-Step 走完整五阶段，MiniMax 和 Stable Audio 走简化管线。
- **超时和 manifest 追踪**：每个阶段可以独立设置超时。配合 `WorkspaceManager`，失败后可以从断点恢复。

## 开发

运行完整测试套件：

```bash
pip install -e ".[dev]"
pytest -q
```

269 个测试通过，4 个跳过（GPU 依赖）。CI 在每次 push 时运行。

常用检查：

```bash
ace-music --help
ace-music generate --help
git diff --check
```

贡献流程和质量要求见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 文档

- [架构概览](docs/audio-engine-architecture.md)
- [校验指南](docs/MUSIC_ENGINE_VALIDATION.md)
- [贡献指南](CONTRIBUTING.md)

## 常见问题

### 安装后出现 `ModuleNotFoundError`

激活虚拟环境后重新安装：

```bash
source .venv/bin/activate
pip install -e ".[dev]"
```

### CUDA 或 GPU 不可用

用 `--mock` 跑冒烟测试。如果你要跑本地 ACE-Step 生成，需要安装 `.[model]`，单独安装/配置 ACE-Step 运行时，并在支持 CUDA 的机器上运行。

### 缺少 `MINIMAX_API_KEY`

使用 MiniMax 后端前需要导出这个环境变量：

```bash
export MINIMAX_API_KEY="your-key"
```

在 macOS 上，CLI 会对云端生成使用 `spawn` worker 上下文，以避免子进程中初始化 Objective-C 库时 `fork()` 崩溃。

### mock 模式音质不行

这是预期行为。mock 模式的用途是 CLI 验证、自动化检查和贡献流程，不是用来评估音质的。它生成的是确定性正弦波 WAV，不是模型输出。

## 当前范围

这个仓库只做契约驱动的音乐生成和校验。

它**不是**：

- 一个托管的音乐服务
- 一个 DAW 插件
- 一个实时音频服务器
- 一个模型训练框架
- 一个通用音频编辑器

这个边界是有意的。保持范围小，代码才好测试、好推理。

## 许可证

MIT。详见 [LICENSE](LICENSE)。
