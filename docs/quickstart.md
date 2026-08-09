# Quickstart

## Requirements

- Python 3.12 or 3.13
- Git
- uv（推荐）

## Install from source

运行 PyPI 预发布版：

```bash
uvx --from soloflow==1.0.0rc5 sf version
```

从源码安装开发版本：

```bash
git clone https://github.com/halexzd686-cloud/SoloFlow.git
cd SoloFlow
uv sync --extra dev
uv run sf version
```

## Explore without an API key

```bash
uv run sf skill list
uv run sf agent list
uv run sf flow list
uv run sf skill run content-writer "测试主题" --dry-run
uv run sf flow run blog-pipeline -i topic="测试主题" --dry-run
```

`--dry-run` 只渲染 Prompt 或执行计划，不调用模型。

## Configure a provider

可以使用 Shell 环境变量提供凭据。PowerShell 示例：

```powershell
$env:OPENAI_API_KEY = "<your-key>"
$env:ANTHROPIC_API_KEY = "<your-key>"
$env:DEEPSEEK_API_KEY = "<your-key>"
```

只需要配置实际使用的供应商。Skill 中的 `provider` 和 `model` 决定调用目标。

也可以使用项目本地 `.env`：

```powershell
Copy-Item .env.example .env
# 然后编辑 .env，只填写实际使用的供应商
```

SoloFlow 只加载当前工作目录的 `.env`，不会向父目录搜索，也不会覆盖已有的进程环境变量。`.env` 默认不会进入 Git；不要把任何真实密钥提交到仓库。

## Run and resume a Flow

```bash
uv run sf flow run blog-pipeline -i topic="AI Agent 落地"
uv run sf flow runs
uv run sf flow resume <run-id>
```

运行状态保存在当前项目的 `.soloflow/runs/`，该目录默认不会进入 Git。

## Build and install a wheel

```bash
uv build
uv venv .smoke-venv
uv pip install --python .smoke-venv dist/soloflow-*.whl
```

安装包携带默认 Skill、Agent 和 Flow；当前项目或 `~/.soloflow` 下的同名资产优先。
