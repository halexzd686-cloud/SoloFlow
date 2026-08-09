# SoloFlow

> 把 AI 工作方法存成文件（Skill），按步骤自动执行（Flow）。

[![CI](https://github.com/halexzd686-cloud/SoloFlow/actions/workflows/ci.yml/badge.svg)](https://github.com/halexzd686-cloud/SoloFlow/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/soloflow.svg)](https://pypi.org/project/soloflow/)
[![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## 30 秒跑通

需要 Python 3.12+ 和 [DeepSeek API Key](https://platform.deepseek.com/)。先配置密钥：

```powershell
$env:DEEPSEEK_API_KEY = "你的密钥"
```

或者在当前目录创建 `.env`：

```dotenv
DEEPSEEK_API_KEY=你的密钥
```

然后运行内置写作 Skill：

```bash
uvx soloflow run content-writer "为我的产品写一篇介绍"
```

不想产生 API 费用时，先预览最终 Prompt：

```bash
uvx soloflow run content-writer "为我的产品写一篇介绍" --dry-run
```

## 只需理解三个概念

- **Skill**：一份可以重复执行的 AI 工作手册，例如 [`content-writer`](skills/writing/content-writer/SKILL.md)。
- **Flow**：把多个 Skill 按依赖顺序串起来，例如 [`blog-pipeline`](flows/blog-pipeline.flow.yml)。
- **Agent（可选）**：给 Skill 加上固定角色和行为规则，例如 [`content-editor`](agents/content-editor.agent.yml)。

## 常用命令

| 命令 | 用途 |
| --- | --- |
| `sf run <skill> <task>` | 运行一个 Skill，推荐入口 |
| `sf skill list` | 查看可用 Skill |
| `sf skill show <name>` | 查看 Skill 内容 |
| `sf skill init <name>` | 创建 Skill |
| `sf flow run <name> -i key=value` | 运行 Flow |
| `sf flow runs` | 查看 Flow 运行记录 |
| `sf flow resume <run-id>` | 从失败处恢复 Flow |
| `sf agent run <name> <task>` | 用 Agent 执行任务 |

如果从源码开发，把 `sf` 换成 `uv run sf`。项目目录、`~/.soloflow/`、安装包内置资产按此顺序查找，同名文件以前者为准。

## 下一步

- [TrailLight 完整案例](docs/tutorial.md)
- [架构说明](docs/architecture.md)
- [项目状态](STATUS.md)
- [贡献指南](CONTRIBUTING.md)
- [版本记录](CHANGELOG.md)

## License

[MIT License](LICENSE)
