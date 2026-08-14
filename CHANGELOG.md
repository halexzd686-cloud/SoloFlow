# Changelog

本项目遵循 [Semantic Versioning](https://semver.org/)，版本变化按 Added、Changed、Fixed、Security 分类记录。

## Unreleased

### Changed

- 暂时关闭普通用户网页中的图片上传入口，避免将 DeepSeek 纯文本模型误认为视觉模型。

## 2.1.0 - 2026-08-14

### Added

- 新增面向普通用户的本地网页入口 `sf web`，支持用自然语言或上传材料定制工作助手。
- 新增工作助手草稿确认、版本保存、重复运行、本地运行记录和助手导入导出。
- 新增 Word、Excel、CSV、PDF、文本和普通图片输入，以及 Markdown、Word、Excel、PDF 结果和 ZIP 打包下载。
- 新增每次运行前的隐私确认、DeepSeek API Key 设置和本次模型选择。

### Changed

- 面向普通用户的名称改为 **Playbook（工作手册）**，新增 `sf playbook` 命令组。
- 新建工作手册默认写入 `playbooks/<name>/PLAYBOOK.md`。
- Flow 支持 `playbook:` 字段，Agent 支持 `playbooks:` 字段。
- 保留 `sf skill`、`SKILL.md`、`skill:` 和 `skills:` 作为兼容格式；MCP 的旧 `*_skill` 工具名也继续保留。
- DeepSeek 模型配置放宽为任意 `deepseek-*` 模型名，同时继续锁定官方接口和 `DEEPSEEK_API_KEY`。
- Runner 支持 `sf run ... --model <deepseek-model>` 临时覆盖模型配置。
- Flow 支持 JSON 输出契约、`when` 条件节点和可暂停恢复的 `approval` 人工审批节点。

### Fixed

- Windows CLI 输出统一尝试使用 UTF-8，降低 GBK 终端下中文乱码概率。
- 清理安全策略中关于已删除 Registry 的历史表述。
- 修复不同操作系统下 Typer/Rich 帮助文本排版差异导致的 `--no-open` CI 误报。

### Verification

- 本地 192 项测试通过；Ruff check、format check 和 `uv build` 通过。
- GitHub Actions 的 Windows/Linux × Python 3.12/3.13 测试矩阵和 Ubuntu build smoke 通过。
- 真实 DeepSeek 请求验收通过；当前支持所有 `deepseek-*` 模型名，并继续锁定 DeepSeek 官方接口。

## 2.0.0 - 2026-08-10

### Added

- 新增顶层快捷入口 `sf run <skill> <task>`，首次使用只需理解 Skill 一个概念。
- 新增基于 Rich 的 Skill/Flow 实时视图和 `sf flow watch <run-id>`，替代 Textual 仪表盘。
- Skill 模型配置新增 `base_url` 与 `api_key_env`；与 `model` 一起构成未来兼容接口的唯一配置缝隙。

### Changed

- README 收敛为 48 行的新手入口，教程保留一个完整 TrailLight 案例。
- Skill、Flow、Agent 统一使用“项目目录 → `~/.soloflow/` → 安装包内置”资产发现顺序。
- Skill、Agent、Flow 的 Prompt 拼装、模型调用与输出展示统一进入 `core/runner.py`。
- Agent 加载与保存下沉到 Core，消除 `core → cli` 反向依赖。
- `run_flow()` 只保留 5 个公开参数并缩短到 24 行；恢复状态仅由 `resume_flow()` 处理。
- LLM 客户端改为 `httpx` 直连 DeepSeek 的 OpenAI 兼容 Chat Completions 接口。全项目只通过 `chat()` 调用模型，当前白名单只允许 `deepseek/deepseek-v4-flash`，并在读取 API Key 前拒绝其他目标。

### Removed

- 删除 Heartbeat daemon 与 `agent heartbeat`。迁移方式：用 Task Scheduler、cron 等系统定时器调用 `sf run`。
- 删除远程 Registry 及 publish/install/update 命令。迁移方式：直接用 Git 分享和版本管理 Skill 文件。
- 删除 Textual TUI 与 `dashboard`。运行时进度改由 Rich 视图展示，需要重新挂载时使用 `sf flow watch`。
- 删除 `skill iter` 与 auto_iter。迁移方式：直接编辑 Skill，并通过 Git 评审和回滚。
- 删除 Skill `depends_on`、版本约束小语言和迭代元数据；Flow 步骤的 `depends_on` 保持不变。
- 删除空的 `storage/`、`utils/` 包，以及 `litellm`、`textual` 依赖。

### Breaking Changes

- Skill frontmatter 不再使用 `provider`；改用 `base_url`、`api_key_env`、`model`。当前可用值仍固定为 DeepSeek 默认组合。
- Agent 的模型覆盖字段同步移除 `provider`，可按需覆盖 `base_url`、`api_key_env`、`model`、`temperature`、`max_tokens`。
- 依赖 Heartbeat、Registry、dashboard、`skill iter` 或 Skill 依赖元数据的脚本需要按上面的迁移说明调整。
- 调用 `run_flow()` 私有恢复参数的代码应改用 `resume_flow(run_id, ...)`。

### Verification

- 本地 164 项测试通过；Ruff check 与 34 个 Python 文件 format check 通过。
- GitHub Actions 的 Windows/Linux × Python 3.12/3.13 测试矩阵和 Ubuntu clean-wheel build smoke 通过。
- wheel 和 sdist 构建通过；wheel 在隔离环境安装后，从源码目录外执行 `sf run content-writer "测试主题" --dry-run` 成功。
- 隔离安装包含 24 个包；`litellm` 已从项目依赖和锁文件移除。
- `soloflow/` Python 代码 3,476 行，README 70 行，顶层命令 7 个。
- v2.0.0 已通过 GitHub Release 与 PyPI OIDC Trusted Publishing 发布；两端 wheel、sdist 的 SHA256 一致，官方索引隔离安装与源码目录外 dry-run 通过。

## 1.0.1 - 2026-08-09

### Changed

- 内置 4 个 Skill、`code-guardian` Agent 及未显式配置时的 LLM 默认值统一改为已验证的 `deepseek/deepseek-v4-flash`。
- README 改为面向首次使用者的渐进式结构，增加概念类比、五分钟入门和 TrailLight Mini 虚拟案例。
- 快速开始文档明确 DeepSeek-only 配置路径，并链接新的完整案例教程。

### Added

- 新增 `docs/tutorial.md`，覆盖 Skill、Agent、Flow dry-run、真实调用、运行记录、断点恢复、安全配置和常见问题。
- 新增内置 Skill 默认供应商回归测试，防止教程与发行包配置再次偏离。

### Fixed

- 缺少 API Key 时的错误提示现在明确要求 `DEEPSEEK_API_KEY`。
- 非 `deepseek/deepseek-v4-flash` 的调用目标会在读取密钥和网络请求前被拒绝。

### Verification

- 本地 251 项测试通过，Ruff check 与 50 个 Python 文件 format check 通过。
- `content-writer` Skill、`content-editor` Agent 与 `blog-pipeline` Flow 的 DeepSeek dry-run 均通过。
- v1.0.1 已通过 GitHub OIDC 发布到 PyPI；官方索引干净安装、DeepSeek-only 配置、非指定目标提前拒绝、wheel/sdist 数字证明与 GitHub/PyPI SHA256 一致性均验证通过。

## 1.0.0 - 2026-08-09

### Added

- 文件驱动的 Skill、Agent 与 Flow 编排，支持 DAG 并发、状态持久化、失败传播和恢复。
- TUI 仪表盘、MCP stdio Server、Heartbeat daemon 与远程 Skill Registry 工作流。
- wheel 内置 4 个 Skill、2 个 Agent 和 8 个 Flow，并支持项目及用户级资产覆盖。
- GitHub Release、SHA256 校验文件与 PyPI OIDC Trusted Publishing 自动发布链路。

### Changed

- v1.0 明确以 DeepSeek 为官方验证和推荐供应商，其他供应商不在正式验收范围内。

### Verification

- 本地 248 项测试、Ruff 检查、Windows/Linux × Python 3.12/3.13 CI 和 clean-wheel smoke 均通过。
- DeepSeek Skill、Agent、Flow、错误处理、双 Agent Heartbeat、500 周期故障注入与 67 分钟真实 soak 均通过。
- Claude Code MCP 实连、远程 Registry publish/PR/install，以及 PyPI RC5 发布、官方索引安装和数字发布证明均通过。
- v1.0.0 已通过 GitHub OIDC 发布到 PyPI；GitHub/PyPI wheel 与 sdist 哈希一致，正式 wheel 的仓库绑定数字证明和官方索引全新安装均通过。

## 1.0.0rc5 - 2026-08-09

### Changed

- GitHub Release 工作流现在也通过 PyPI Trusted Publishing 上传 RC 标签，用预发布版本验证正式发布链路。

### Verification

- RC5 已通过 GitHub OIDC 发布到 PyPI；官方索引 wheel/sdist、项目链接、全新环境安装和仓库绑定的数字发布证明均验证通过。

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
