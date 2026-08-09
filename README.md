# SoloFlow

> Docker Compose for AI Skills —— 文件驱动的 AI 技能管理系统。

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Alpha-orange.svg)]()

将专家经验封装为可复用、可分享、可自我迭代的 SKILL.md 文件，让 AI 按标准干活。

## 为什么需要 SoloFlow

你的提示词散落各处——CLAUDE.md 里塞了几条、聊天记录里藏着几条、Notion 文档里记了一些。每次做类似的事都要重新写、重新调。

**SoloFlow 把它们变成结构化资产：** 一个 Skill 文件 = 一份完整的专家经验包，可以被任何 AI 工具加载和执行。

## 快速开始

> 当前为 Alpha 阶段，尚未发布到 PyPI。请从源码安装。

```bash
# 从源码安装（推荐 uv）
git clone <your-repo-url>/soloflow.git
cd soloflow
uv sync --extra dev

# 运行测试
uv run pytest -q

# 运行 CLI
uv run sf --help
```

## 核心概念

```
Skill（技能文件）     →  封装专家经验，一个文件 = 一个完整技能
Agent（智能体）       →  加载 Skill，扮演特定角色（可绑定多个 Skill）
Flow（工作流）        →  编排多个 Skill/Agent 协同完成复杂任务（DAG）
```

### Skill 文件结构

一个 Skill 文件采用 YAML frontmatter + Markdown body 格式，人机双读：

```markdown
---
name: content-writer
version: 1.0.0
description: 撰写高质量深度长文
context: 你是一位资深商业内容作者...
objective: 撰写一篇 3000-4000 字的深度文章...
rules:
  - "不要有 AI 味儿"
  - "每段不超过 4 行"
---

## Instructions

1. 破题：用一个反直觉的观点开头
2. 展开：用具体案例支撑每个观点
3. 收尾：一句金句 + 行动建议
```

## 快速体验

```bash
# 查看内置 Skill
uv run sf skill list

# 预览 Prompt（不产生 API 费用）
uv run sf skill run content-writer "测试主题" --dry-run

# 查看 Flow 执行计划
uv run sf flow run blog-pipeline -i topic="AI Agent" --dry-run

# TUI 仪表盘（侘寂风）
uv run sf dashboard
```

## CLI 命令

```bash
# Skill 管理
sf skill init <name>              # 创建 Skill
sf skill validate <path>          # 校验格式
sf skill list                     # 列出所有 Skill
sf skill run <name> <task>        # 执行任务（-n 5 抽卡模式，--stream 流式）
sf skill iter <name> -n 30        # 自我迭代

# Agent 管理
sf agent create <name>            # 创建 Agent
sf agent run <name> <task>        # 执行任务
sf agent heartbeat start <name>   # 心跳定时调度

# Flow 编排
sf flow run <name> -i key=value   # 执行 Flow（DAG 并行编排）
sf flow runs                      # 查看运行记录
sf flow resume <run-id>           # 从断点恢复

# Registry 市场
sf registry search <keyword>      # 搜索
sf registry install <name>        # 安装（--version 锁定版本）
sf registry publish <name>        # 发布（--submit 自动 PR）

# 其他
sf dashboard                      # TUI 仪表盘
sf mcp                            # MCP Server（JSON-RPC over stdio）
```

## 内置资产

- **Skills**: `content-writer`（深度写作）、`code-reviewer`（代码审查）、`market-researcher`（市场调研）、`hello-world`（入门示例）
- **Agents**: `content-editor`（主编人格）、`code-guardian`（首席架构师人格）
- **Flows**: `blog-pipeline`、`code-review`、`competitive-analysis`、`content-marketing`、`meeting-notes`、`onboarding-docs`、`release-notes`、`weekly-report`

## 能力边界（重要）

SoloFlow 当前是 **AI Skill/Prompt 编排工具**，不是完整的自主 Agent 平台：

- Runner 只把 Prompt 发给 LLM，不自动提供外部工具（`market-researcher` 不会自己上网）
- Agent 是 Prompt 组合层，无独立记忆、工具调用、规划循环
- Flow 步骤之间只传递字符串输出

## 开发

```bash
uv sync --extra dev
uv run pytest -q          # 233 项测试（本地）
uv run ruff check soloflow tests
uv run ruff format soloflow tests
uv build                  # 构建 wheel/sdist
```

## 路线图

- [x] v0.1 — Skill 核心：创建、校验、执行、迭代
- [x] v0.2 — Agent 管理 + Flow DAG 编排
- [x] v0.3 — 社区 Skill Registry
- [x] v0.4 — 侘寂风 TUI 仪表盘
- [x] v0.5+ — MCP Server、心跳 daemon、版本锁定、流式输出、断点恢复
- [ ] v1.0 — Registry 远程闭环、真实 LLM 端到端验证、发布到 PyPI

## License

MIT
