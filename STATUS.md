# SoloFlow Project Status

> Version: 1.0.0rc1 | Stage: v1.0 Release Candidate | Updated: 2026-08-09

## Verified locally

- Windows 11, Python 3.12.13。
- `237 passed`。
- Ruff check 通过，63 个 Python 文件格式检查通过。
- wheel 和 sdist 可构建。
- wheel 在全新虚拟环境安装成功。
- 离开源码目录后可发现 4 个 Skill、2 个 Agent、8 个 Flow，并可 dry-run `blog-pipeline`。
- MCP stdio、Registry 本地 Git 闭环和 TUI 无头测试由自动化测试覆盖。
- Claude Code 2.1.201 已完成真实 MCP 连接，并成功调用 `soloflow_list_skills`。
- GitHub `skills-registry` 已完成真实 update、search、严格版本校验和隔离安装。
- GitHub Actions Windows/Linux × Python 3.12/3.13 矩阵通过。
- GitHub Actions Ubuntu clean-wheel 安装及源码目录外 smoke 通过。

## Not yet externally verified

- 真实 OpenAI、Anthropic、DeepSeek 调用及限流、超时和 token usage。
- Cursor 和 Codex 的真实 MCP 客户端连接（Claude Code 已验证）。
- 真实远程 Registry 的 publish 和 PR 闭环（update、search、install 已验证）。
- Heartbeat 长时间运行、重启恢复、PID 复用和多 Agent 并发。
- PyPI 发布和第三方用户的干净安装反馈。

## Known limitations

- Runner 不自动提供浏览器、搜索、文件系统和其他外部工具。
- Flow 暂无条件节点、人工审批、fallback model、持久化队列和分布式执行。
- Registry 暂无签名、checksum 和 commit SHA lockfile。
- Windows GBK 终端可能出现中文显示问题。
- LiteLLM 及其依赖体积较大。

未经真实验证的事项不会在 README 或 Release 中标记为完成。
