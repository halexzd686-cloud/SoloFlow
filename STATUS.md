# SoloFlow Project Status

> Version: 2.0.0 | Stage: Stable | Branch: `main` | Released: 2026-08-10

## Current scope

- 核心概念只有 Skill、Flow 和可选 Agent。
- 新手推荐入口是 `sf run <skill> <task>`。
- 模型调用使用 `httpx` 直连 DeepSeek OpenAI 兼容接口；白名单只允许 `deepseek/deepseek-v4-flash`。
- MCP 作为高级入口保留，不进入 README 主流程；它复用同一 Core 与 Runner。

## Verified locally

- Windows 11、Python 3.12.13。
- `164 passed`。
- Ruff check 通过，34 个 Python 文件 format check 通过。
- wheel 与 sdist 构建通过。
- GitHub Actions 的 Windows/Linux × Python 3.12/3.13 测试矩阵与 Ubuntu build/clean-wheel smoke 通过。
- wheel 在新建隔离环境安装成功，共安装 24 个包；离开源码目录后可发现内置资产并执行 `sf run content-writer "测试主题" --dry-run`。
- README 70 行；`sf --help` 顶层命令 7 个。
- `soloflow/` Python 代码 3,476 行，无空包、无 `core → cli` 反向导入。
- Skill、Flow、Agent 共用项目 → 用户 → 内置的资产发现顺序。
- Prompt 与模型调用统一进入 Runner；生产代码只有 Runner 调用 `chat()`。
- 非白名单的 `base_url`、`api_key_env` 或 `model` 会在读取密钥和创建 HTTP 客户端前被拒绝。
- `litellm` 与 `textual` 已从项目依赖和 `uv.lock` 移除。
- v2.0.0 GitHub Release 与 PyPI OIDC Trusted Publishing 成功；wheel、sdist 在两端的 SHA256 一致。
- 从 PyPI 官方索引隔离安装 `soloflow==2.0.0` 成功；源码目录外的版本、内置资产发现与 DeepSeek dry-run 验收通过。

## Removed in v2

- Heartbeat daemon 与相关 CLI。
- 远程 Registry 与 publish/install/update 工作流。
- Textual dashboard。
- `skill iter` / auto_iter。
- Skill 依赖版本小语言、Skill `depends_on` 与迭代元数据。
- 空的 `storage/`、`utils/` 包。

## Not part of release verification

- 重构后的 `httpx` 客户端尚未执行付费的真实 DeepSeek 请求；协议、流式 SSE、usage、重试、认证失败和提前拒绝均由无网络 mock 测试覆盖。

## Known limitations

- Runner 不自动提供浏览器、搜索、文件系统或其他外部工具。
- Flow 暂无条件节点、人工审批、fallback model、持久化队列或分布式执行。
- 当前只允许 DeepSeek V4 Flash；其他模型不在 v2.0.0 范围内。
- Windows GBK 终端可能出现中文显示问题。

## Release gate

v2.0.0 已完成 `main` CI、GitHub Release、PyPI 发布和官方索引安装验收。后续版本继续使用同一 tag 驱动门禁。
