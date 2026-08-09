# SoloFlow

> 把一套反复使用的 AI 工作方法，保存成文件，并按步骤自动执行。

[![CI](https://github.com/halexzd686-cloud/SoloFlow/actions/workflows/ci.yml/badge.svg)](https://github.com/halexzd686-cloud/SoloFlow/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/)
[![PyPI](https://img.shields.io/pypi/v/soloflow.svg)](https://pypi.org/project/soloflow/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

SoloFlow 是一个文件驱动的 AI 工作流工具。你可以把“怎么写文章”“怎么审查代码”这类经验写进 `SKILL.md`，把一个角色需要的能力组合成 Agent，再用 YAML Flow 串起调研、写作、分发等多个步骤。所有配置都是普通文本，能在本地运行，也能用 Git 审查、回滚和分享。

当前代码为 `1.0.1` 候选版，仅接入已真实验收的 `deepseek/deepseek-v4-flash`；PyPI 最新正式版为 `1.0.0`。

## 一分钟理解 SoloFlow

可以把 SoloFlow 想成一间由文件管理的工作室：

| 名称 | 通俗理解 | 例子 |
| --- | --- | --- |
| Skill | 一份可重复执行的工作手册 | “如何写一篇不空泛的深度文章” |
| Agent | 带有人格和多项能力的岗位角色 | “严格但诚实的内容主编” |
| Flow | 把多个岗位按依赖关系排成流水线 | 调研 → 写作 → 生成社交文案 |
| Registry | 存放和分享 Skill 的技能仓库 | 从 Git 仓库安装团队 Skill |
| Heartbeat | 定时唤醒 Agent 的本地调度器 | 每两小时生成一次监控摘要 |
| MCP | 让其他 AI 客户端调用 SoloFlow 的接口 | 在 Claude Code 中列出或运行 Skill |

如果你只想完成一个明确任务，用 **Skill**；希望固定角色风格，用 **Agent**；需要多个步骤自动衔接和失败恢复，用 **Flow**。

## 五分钟跑通第一个任务

以下示例使用虚构产品“TrailLight Mini 露营灯”。完整案例见[从零完成一次内容发布](docs/tutorial.md)。

### 1. 安装

需要 Python 3.12 或 3.13，推荐使用 [uv](https://docs.astral.sh/uv/)：

```bash
uv tool install soloflow
sf version
```

如果你正在使用源码仓库，则把后续命令中的 `sf` 换成 `uv run sf`。

### 2. 不花 API 费用，先预览会发生什么

```bash
sf skill list
sf skill run content-writer "为 TrailLight Mini 露营灯写一篇新品介绍" --dry-run
sf flow run blog-pipeline -i topic="TrailLight Mini 露营灯" --dry-run
```

`--dry-run` 不调用模型。第一条运行命令会展示最终 Prompt；第二条会展示 Flow 的四个步骤和三层执行顺序。

### 3. 配置 DeepSeek API Key

在准备运行 SoloFlow 的目录中新建 `.env`：

```dotenv
DEEPSEEK_API_KEY=你的实际密钥
```

也可以只在当前 PowerShell 会话设置：

```powershell
$env:DEEPSEEK_API_KEY = "你的实际密钥"
```

SoloFlow 只读取当前工作目录的 `.env`，不会搜索父目录，也不会覆盖已经存在的环境变量。不要把真实密钥写进 Skill、Flow 或提交到 Git；项目的 `.gitignore` 应包含 `.env`。

### 4. 运行一个真实 Skill

```bash
sf skill run content-writer "为 TrailLight Mini 露营灯写一篇新品介绍。产品为虚构案例，不得补充未经提供的参数。已知信息：重量 180 克、三档亮度、USB-C 充电、面向周末露营新手。"
```

SoloFlow 会读取 `content-writer` 的写作规范，组合你的任务，然后调用 DeepSeek。终端会显示模型输出与 token usage。

### 5. 扩展成完整流水线

```bash
sf flow run blog-pipeline -i topic="TrailLight Mini 露营灯：180 克、三档亮度、USB-C 充电，面向周末露营新手；这是虚构案例，不得编造市场数据"
sf flow runs
```

这个 Flow 会依次完成调研框架、长文写作，再并行生成 X 和 LinkedIn 文案。运行记录保存在当前目录的 `.soloflow/runs/`；若中途失败，可执行：

```bash
sf flow resume <run-id>
```

> `market-researcher` 本身没有联网搜索能力。没有外部工具或可靠资料时，它只能基于输入做结构化分析，不能把生成内容当作已核实的市场事实。

## 虚拟案例：一条命令背后发生了什么

假设小团队要发布 TrailLight Mini：

```text
输入产品资料
    ↓
market-researcher：整理用户、卖点、风险和内容角度
    ↓
content-writer：把调研结果写成长文
    ↓
content-writer：并行生成 X 文案和 LinkedIn 文案
    ↓
保存每一步状态与最终输出
```

这里最重要的不是某一次生成结果，而是这套流程已经写进文件：团队可以修改 Prompt、审查变更、重新运行，并在失败后从断点继续。完整教学包含预期输出、目录说明、故障恢复与定制方法，见 [`docs/tutorial.md`](docs/tutorial.md)。

## 内置示例

安装包自带：

- 4 个 Skill：`content-writer`、`code-reviewer`、`market-researcher`、`hello-world`
- 2 个 Agent：`content-editor`、`code-guardian`
- 8 个 Flow：博客、代码审查、竞品分析、内容营销、会议纪要、入职文档、发布说明和周报

这些示例默认使用 `deepseek/deepseek-v4-flash`。项目目录或 `~/.soloflow` 中的同名资产会覆盖安装包资产，因此可以先复制示例，再改成自己的工作方法。

## 主要能力

- Skill：创建、校验、列表、执行、多版本生成和自动迭代。
- Agent：Soul 人格、多个 Skill、配置继承与 Heartbeat 调度。
- Flow：DAG 校验、变量引用、分层并发、失败跳过、超时重试、输出映射和断点恢复。
- Registry：离线索引、Git 拉取、版本安装、打包发布和可选 PR 提交。
- MCP：JSON-RPC 2.0 over stdio，提供 9 个 Skill、Agent、Flow 工具。
- TUI：终端仪表盘、详情弹窗、动态输入和运行恢复。

## 从源码开发

```bash
git clone https://github.com/halexzd686-cloud/SoloFlow.git
cd SoloFlow
uv sync --extra dev
uv run sf version
```

常用验证命令：

```bash
uv run pytest -q
uv run ruff check soloflow tests
uv run ruff format --check soloflow tests
uv build
```

详细安装说明见[快速开始](docs/quickstart.md)，MCP 配置见[MCP 文档](docs/mcp.md)，当前验收范围见[项目状态](STATUS.md)。

## 模型配置

| 调用目标 | 状态 | 说明 |
| --- | --- | --- |
| `deepseek/deepseek-v4-flash` | 唯一支持、默认 | Skill、Agent、Flow、重试与 Heartbeat 均完成真实调用验收 |

为避免误用其他付费 API，`v1.0.1` 会在读取密钥和发起请求前拒绝其他 provider 或 model。

## 能力边界

SoloFlow 是 Prompt 与 LLM 工作流编排工具，不是完整的自主 Agent 平台：

- Runner 不会自动获得浏览器、搜索、文件系统或其他外部工具。
- Agent 没有自主规划循环、长期记忆和分布式执行能力。
- Flow 主要传递字符串输出，暂不支持条件节点、人工审批和 fallback model。
- Registry 暂无签名、checksum 和 commit SHA lockfile。
- Heartbeat 已通过单机加速稳定性验收，跨机器长期运行仍需更多反馈。

## 项目状态与路线

`v1.0.0` 已发布到 [PyPI](https://pypi.org/project/soloflow/) 和 [GitHub Releases](https://github.com/halexzd686-cloud/SoloFlow/releases/tag/v1.0.0)，并完成跨平台 CI、发行包哈希、数字证明、干净安装、DeepSeek 真实调用、MCP、Registry 与 Heartbeat 验收。

下一阶段计划包括：

- 发布 `v1.0.1`：默认配置统一为 DeepSeek，并补充可复现的入门教程。
- `v1.1`：增强 Flow 条件控制和外部工具能力；是否扩展模型供应商另行评估。

提交问题或代码前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。安全问题请按 [SECURITY.md](SECURITY.md) 私下报告，版本变化见 [CHANGELOG.md](CHANGELOG.md)。

## License

[MIT License](LICENSE)
