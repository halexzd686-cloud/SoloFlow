# SoloFlow

<p align="center">
  <strong>让 AI 按照你认可的方法，完成写作、会议纪要、周报和代码审查等重复工作。</strong>
</p>

<p align="center">
  SoloFlow 是一个在本地运行的 AI 工作工具。你描述任务，它按预先定义好的工作方法执行，<br>
  返回可以继续修改、审核或交付的结果。
</p>

<p align="center">
  <a href="#快速开始">快速开始</a> ·
  <a href="#实际工作例子">实际工作例子</a> ·
  <a href="#它是怎么工作的">它是怎么工作的</a> ·
  <a href="#开发与文档">开发与文档</a>
</p>

[![CI](https://github.com/halexzd686-cloud/SoloFlow/actions/workflows/ci.yml/badge.svg)](https://github.com/halexzd686-cloud/SoloFlow/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/soloflow.svg)](https://pypi.org/project/soloflow/)
[![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

SoloFlow 不是一个让 AI 自由发挥的聊天窗口，而是把一套工作方法保存下来，之后反复使用。
工具本身在本地运行，模型请求发送到 DeepSeek；重要结果仍然需要人工检查。

## 它能帮你做什么

| 你想完成的工作 | SoloFlow 可以做什么 |
| --- | --- |
| 写产品介绍 | 按固定风格生成结构清晰的产品文案 |
| 整理会议记录 | 提取结论、待办事项、负责人和截止时间 |
| 写周报 | 根据工作记录生成结构化的团队周报 |
| 审查代码 | 从规范、逻辑、安全和可维护性等方面检查代码 |
| 生成发布说明 | 根据变更记录整理 Release Notes 和升级提示 |
| 执行多步工作 | 依次完成分析、写作、审核和分发等步骤 |

## 快速开始

### 本地网页入口（当前开发中）

如果你不想理解工作手册、Flow 或命令参数，可以先启动本地网页：

```bash
uvx soloflow web
```

或在已经安装 SoloFlow 的环境中运行：

```bash
sf web
```

浏览器打开后，可以查看示例工作助手、配置 DeepSeek API Key，并用自然语言创建工作助手。当前支持上传 Word、Excel、CSV、PDF、文本和普通图片，生成 Markdown、Word、Excel 或 PDF 结果并下载。

### 1. 准备 DeepSeek API Key

需要 Python 3.12+ 和 [DeepSeek API Key](https://platform.deepseek.com/)。

PowerShell：

```powershell
$env:DEEPSEEK_API_KEY = "你的密钥"
```

也可以在当前项目目录创建 `.env`：

```dotenv
DEEPSEEK_API_KEY=你的密钥
```

### 2. 运行第一个任务

如果已经安装 SoloFlow：

```bash
pip install soloflow
sf run content-writer "为一款面向露营新手的便携灯写一篇产品介绍"
```

不想安装到当前环境，也可以使用 `uvx`：

```bash
uvx soloflow run content-writer "为一款面向露营新手的便携灯写一篇产品介绍"
```

### 3. 先预览，不产生模型费用

```bash
sf run content-writer "写一篇产品介绍" --dry-run
```

`--dry-run` 只显示 SoloFlow 准备交给模型的任务内容，不会请求 DeepSeek。

### 4. 临时切换模型

只影响本次运行，不会修改工作手册：

```bash
sf run content-writer "写一篇产品介绍" --model deepseek-chat
```

当前支持 DeepSeek 官方接口下的 `deepseek-*` 模型；暂不接入其他模型供应商。

## 实际工作例子

### 写一篇产品介绍

```bash
sf run content-writer "为 TrailLight Mini 写一篇面向周末露营新手的产品介绍。已知：180 克、三档亮度、USB-C 充电。不得编造其他参数。"
```

### 审查一个代码变更

把代码差异保存为 `diff.txt`，然后运行：

```bash
sf run code-reviewer --file diff.txt
```

SoloFlow 会按代码规范、逻辑正确性、安全性和可维护性整理审查意见。

### 生成会议纪要

把多个工作步骤连接起来，生成结论、待办和格式化纪要：

```bash
sf flow run meeting-notes -i meeting_title="产品周会" -i transcript="这里粘贴会议记录"
```

Flow 运行期间会显示每个步骤的进度，并在当前目录的 `.soloflow/runs/` 保存运行记录。

## 它是怎么工作的

你可以先把 SoloFlow 理解成三部分：

- **工作手册**：告诉 AI 应该用什么方法完成一类任务，例如写作或代码审查。
- **Flow**：把多个步骤连接起来，例如“分析 → 写作 → 审核”。
- **人工确认**：在发布、发信或提交之前暂停，等待人确认后再继续。

一个典型的工作流程是：

```text
你提供任务
    ↓
SoloFlow 按工作手册执行
    ↓
得到结果或进入下一步
    ↓
必要时等待人工确认
    ↓
完成最终交付
```

### 结构化结果和条件步骤

需要让后续步骤根据结果做判断时，可以让某个步骤返回 JSON，再使用条件表达式：

```yaml
- id: review
  playbook: code-reviewer
  output_format: json
  output_schema:
    type: object
    required: [approved]
    properties:
      approved: {type: boolean}

- id: approval
  type: approval
  depends_on: [review]

- id: publish
  playbook: content-writer
  depends_on: [approval]
  when: $steps.approval.data.approved == true
```

Flow 遇到人工确认节点会暂停。查看运行记录后，可以批准或拒绝：

```bash
sf flow runs
sf flow approve <run-id> --step approval --note "已确认，可以发布"
sf flow reject <run-id> --step approval --note "需要修改后再审"
```

## 使用前知道

- 真实请求需要 DeepSeek API Key，可能产生 API 费用。
- 可以先使用 `--dry-run` 检查任务内容。
- SoloFlow 不会自动联网搜索，也不会自动操作浏览器或修改本地文件。
- 模型输出可能有错误，涉及事实、客户、发布和决策的内容需要人工复核。
- Flow 的运行记录保存在当前目录的 `.soloflow/runs/`，不应将包含敏感信息的运行记录提交到 Git。

Flow 还支持面向实际工作的控制：用 `output_format: json` 产出可判断的结果，用 `when` 控制后续步骤，用 `type: approval` 在发布、发信或提交前暂停等待人工确认。

## 常用命令

| 命令 | 用途 |
| --- | --- |
| `sf run <name> <task>` | 运行一个工作手册 |
| `sf playbook list` | 查看可用工作手册 |
| `sf playbook init <name>` | 创建工作手册 |
| `sf playbook show <name>` | 查看工作手册 |
| `sf playbook validate <path>` | 校验工作手册 |
| `sf flow run <name> -i key=value` | 运行 Flow |
| `sf flow runs` | 查看 Flow 运行记录 |
| `sf flow watch <run-id>` | 重新查看 Flow 进度 |
| `sf flow resume <run-id>` | 从失败处恢复 Flow |
| `sf flow approve <run-id> --step <id>` | 批准人工审批节点并继续 |
| `sf flow reject <run-id> --step <id>` | 拒绝人工审批节点 |
| `sf agent run <name> <task>` | 用 Agent 执行任务 |

如果从源码运行，把 `sf` 换成 `uv run sf`。

已有项目无需迁移：旧的 `sf skill` 命令、`SKILL.md` 文件以及 Flow/Agent 中的旧字段仍然兼容。

## 开发与文档

从源码运行：

```bash
uv sync
uv run sf --help
uv run pytest
uv build
```

- [TrailLight 完整案例](docs/tutorial.md)
- [产品需求说明](docs/product-requirements.md)
- [MVP 重构清单](docs/mvp-refactor-plan.md)
- [架构说明](docs/architecture.md)
- [MCP 集成](docs/mcp.md)
- [项目状态](STATUS.md)
- [贡献指南](CONTRIBUTING.md)
- [版本记录](CHANGELOG.md)

## License

[MIT License](LICENSE)
