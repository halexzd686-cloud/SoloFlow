# SoloFlow

> 把 AI 工作方法保存成工作手册（Playbook），按步骤自动执行。

[![CI](https://github.com/halexzd686-cloud/SoloFlow/actions/workflows/ci.yml/badge.svg)](https://github.com/halexzd686-cloud/SoloFlow/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/soloflow.svg)](https://pypi.org/project/soloflow/)
[![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

当前稳定版本：**v2.0.0**。

## 30 秒跑通

需要 Python 3.12+ 和 [DeepSeek API Key](https://platform.deepseek.com/)。

```powershell
$env:DEEPSEEK_API_KEY = "你的密钥"
```

或者在项目目录创建 `.env`：

```dotenv
DEEPSEEK_API_KEY=你的密钥
```

运行内置工作手册：

```bash
uvx soloflow run content-writer "为我的产品写一篇介绍"
```

临时切换 DeepSeek 模型，不会修改工作手册：

```bash
uvx soloflow run content-writer "为我的产品写一篇介绍" --model deepseek-chat
```

不产生 API 费用时，先预览 Prompt：

```bash
uvx soloflow run content-writer "为我的产品写一篇介绍" --dry-run
```

## 三个概念

- **工作手册（Playbook）**：一份可重复执行的 AI 工作方法，例如 [`content-writer`](skills/writing/content-writer/SKILL.md)。新建工作手册使用 `PLAYBOOK.md`。
- **Flow**：把多个工作手册按依赖顺序串起来，例如 [`blog-pipeline`](flows/blog-pipeline.flow.yml)。
- **Agent（可选）**：给工作手册加上固定角色和行为规则，例如 [`content-editor`](agents/content-editor.agent.yml)。

## 常用命令

| 命令 | 用途 |
| --- | --- |
| `sf run <name> <task>` | 运行一个工作手册，推荐入口 |
| `sf playbook list` | 查看可用工作手册 |
| `sf playbook init <name>` | 创建工作手册 |
| `sf playbook show <name>` | 查看工作手册 |
| `sf playbook validate <path>` | 校验工作手册 |
| `sf flow run <name> -i key=value` | 运行 Flow |
| `sf flow runs` | 查看 Flow 运行记录 |
| `sf flow watch <run-id>` | 实时查看 Flow 进度 |
| `sf flow resume <run-id>` | 从失败处恢复 Flow |
| `sf flow approve <run-id> --step <id>` | 批准人工审批节点并继续 |
| `sf flow reject <run-id> --step <id>` | 拒绝人工审批节点 |
| `sf agent run <name> <task>` | 用 Agent 执行任务 |

从源码开发，把 `sf` 换成 `uv run sf`。项目目录、`~/.soloflow/`、安装包内置资产按优先级查找；工作手册优先查找 `playbooks/<name>/PLAYBOOK.md`，同时兼容旧的 `skills/<name>/SKILL.md`。

已有项目无需迁移：`sf skill`、`SKILL.md`、Flow 中的 `skill:` 和 Agent 中的 `skills:` 仍然有效。

## 文档

- [TrailLight 完整案例](docs/tutorial.md)
- [架构说明](docs/architecture.md)
- [MCP 集成](docs/mcp.md)
- [项目状态](STATUS.md)
- [贡献指南](CONTRIBUTING.md)
- [版本记录](CHANGELOG.md)

## License

[MIT License](LICENSE)
