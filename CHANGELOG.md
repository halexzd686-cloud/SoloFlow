# Changelog

本项目遵循 [Semantic Versioning](https://semver.org/)，版本变化按 Added、Changed、Fixed、Security 分类记录。

## Unreleased

## 1.0.0rc5 - 2026-08-09

### Changed

- GitHub Release 工作流现在也通过 PyPI Trusted Publishing 上传 RC 标签，用预发布版本验证正式发布链路。

## 1.0.0rc4 - 2026-08-09

### Added

- Heartbeat 状态新增尝试数、失败数、连续失败数、最后尝试和最后错误，空响应按失败记录。
- CLI 自动加载当前工作目录的 `.env`，不搜索父目录且不覆盖已有环境变量；新增安全占位示例 `.env.example`。
- Python 包元数据新增主页、源码、问题反馈和 Changelog 链接。
- Release 工作流为稳定标签准备 PyPI Trusted Publishing，RC 标签仍只创建 GitHub 预发布。

### Fixed

- Heartbeat 每次持久化运行状态时保留 `started_at`，确保长时验收的经过时间可可靠计算。

### Verification

- Heartbeat 500 周期故障注入完成 445 次成功和 55 次超时、连接、限流或空响应失败，状态与清理断言通过。
- Heartbeat 真实 DeepSeek 加速 soak 持续约 67 分钟，以 2 分钟间隔完成 33/33 次调用；成功率 100%，无连续失败、空响应、截断输出或日志错误，最终停止和 PID 清理通过。
- v1.0 发布审计覆盖全部 Git 历史敏感信息、63 个隔离环境依赖、发行包内容、Twine 元数据和源码目录外安装，未发现已知漏洞或敏感文件泄漏。

## 1.0.0rc3 - 2026-08-09

### Verification

- DeepSeek 真实超时返回可重试错误，假密钥鉴权失败不会重试。
- 两个 Heartbeat Agent 并发完成各 3 次真实 DeepSeek 调用，并通过状态持久化、结果标记与 PID 清理验收。
- Heartbeat PID 复用探针与真实 daemon 身份识别、重复启动保护和安全停止均已通过。

### Fixed

- Heartbeat 探活同时校验 PID 对应的进程命令行和 Agent 名称，避免 PID 复用导致误报或误杀无关进程。

## 1.0.0rc2 - 2026-08-09

### Fixed

- MCP Server 兼容仍使用 `initialize`、`notifications/initialized` 和 `ping` 的客户端生命周期，同时保留新版 `server/discover` 支持。
- Registry 首次克隆改为缓存同盘 staging 和原子替换，避免 Windows 跨盘移动 `.git` pack 失败及半成品缓存被误用。
- Heartbeat daemon 改用换行生成有效的 Python 启动脚本，启动成功前检查子进程，并按 PID 实际探活报告状态。
- Heartbeat CLI 使用 GBK 兼容的 ASCII 状态标记，避免 Windows 旧终端因心形符号崩溃。
- Flow 的 `$steps.<step-id>.output` 引用支持合法的 kebab-case Step ID，避免正式输出映射保留为未解析字面量。

### Verification

- Claude Code 2.1.201 在 Windows 11 上成功连接 stdio Server 并调用 `soloflow_list_skills`。
- 远程 `skills-registry` 已完成损坏缓存恢复、update、search、严格版本校验和隔离 install。
- Heartbeat daemon 已完成真实启动、重复启动保护、中断恢复、状态报告、停止及 PID 清理。
- DeepSeek V4 Flash 已完成真实 Skill、Agent、Flow 调用；Flow 状态、正式输出映射与 token 累计均通过断言。
- 远程 Registry 已完成 `code-reviewer` 打包、PR 创建、合并和重新安装闭环。
- 本地回归基线更新为 240 项测试通过，Ruff check 与 format check 通过。

## 1.0.0rc1 - 2026-08-09

### Added

- GitHub 开源协作文件、用户文档和 tag 驱动的 Release 工作流。
- wheel 内置 Skill、Agent、Flow 的发现与安装回归测试。

### Changed

- CI wheel smoke 改为离开源码目录验证内置资产。
- Skill、Agent、Flow 统一采用项目/用户资产优先、包内资产回退的发现顺序。
- GitHub Actions 升级到当前 Node.js 24 运行时版本。

## 0.9.1 - 2026-08-08

### Added

- MCP stdio Server、TUI 仪表盘、Heartbeat daemon 和 Registry 工作流。
- Flow 并发限制、失败传播、输出映射、token 累计与断点恢复。
- Skill 自动迭代、退化保护和配置无损保存。

### Fixed

- Windows Heartbeat 使用 Win32 进程探活。
- Registry 安装使用 staging、校验、备份和回滚流程。
- TUI Flow 输入传递、类型转换和恢复行为。
- `max_parallel` 非法值和布尔值校验。

### Verification

- 初始本地基线为 230 项测试通过。
- Ruff check 与 format check 通过。
