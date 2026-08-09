# SoloFlow Project Status

> Version: 1.0.0rc4 | Stage: v1.0 Release Candidate | Updated: 2026-08-09

## Verified locally

- Windows 11, Python 3.12.13。
- `248 passed`。
- Ruff check 通过，65 个 Python 文件格式检查通过。
- wheel 和 sdist 可构建。
- wheel 在全新虚拟环境安装成功。
- 离开源码目录后可发现 4 个 Skill、2 个 Agent、8 个 Flow，并可 dry-run `blog-pipeline`。
- MCP stdio、Registry 本地 Git 闭环和 TUI 无头测试由自动化测试覆盖。
- Claude Code 2.1.201 已完成真实 MCP 连接，并成功调用 `soloflow_list_skills`。
- GitHub `skills-registry` 已完成真实 update、search、严格版本校验和隔离安装。
- `code-reviewer` 已通过 SoloFlow publish 命令创建 PR、合并并从远程 Registry 重新安装。
- Heartbeat daemon 已完成真实启动、探活、重复启动保护、中断恢复、停止和 PID 清理。
- 两个 Heartbeat Agent 已并发完成各 3 次真实 DeepSeek 调用，结果持久化和停止清理均通过。
- Heartbeat 使用 PID 与进程命令行联合校验，PID 复用探针和真实 daemon 身份链路均已通过。
- Heartbeat 500 周期加速测试完成 445 次成功和 55 次注入失败，daemon 持续运行且指标一致。
- Heartbeat 真实 DeepSeek 加速 soak 持续约 67 分钟，2 分钟间隔共完成 33/33 次调用；成功率 100%，无连续失败、空响应、截断输出或日志错误，停止状态与 PID 清理通过。
- DeepSeek V4 Flash 已完成真实 Skill、Agent、Flow 调用，输出、状态和 token usage 均已验证。
- GitHub Actions Windows/Linux × Python 3.12/3.13 矩阵通过。
- GitHub Actions Ubuntu clean-wheel 安装及源码目录外 smoke 通过。
- CLI 可安全加载当前工作目录 `.env`，已有进程环境变量优先且不会搜索父目录。
- PyPI 项目链接元数据已补齐；稳定标签的 Trusted Publishing 工作流已准备，RC 标签不会上传 PyPI。

## Not yet externally verified

- 真实 OpenAI、Anthropic 调用和 DeepSeek 限流场景（DeepSeek 正常调用、超时与鉴权失败已验证）。
- Cursor 和 Codex 的真实 MCP 客户端连接（Claude Code 已验证）。
- PyPI 发布和第三方用户的干净安装反馈。

## Known limitations

- Runner 不自动提供浏览器、搜索、文件系统和其他外部工具。
- Flow 暂无条件节点、人工审批、fallback model、持久化队列和分布式执行。
- Registry 暂无签名、checksum 和 commit SHA lockfile。
- Windows GBK 终端可能出现中文显示问题。
- LiteLLM 及其依赖体积较大。

未经真实验证的事项不会在 README 或 Release 中标记为完成。
