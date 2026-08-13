# SoloFlow Project Status

> Version: 2.0.0 | Stage: local web P3 sharing and history management implemented | Branch: `dev` | Released: 2026-08-10

## Current scope

- 核心概念只有工作手册（Playbook）、Flow 和可选 Agent。
- 新手推荐入口是 `sf run <name> <task>`；`sf skill` 作为旧命令兼容保留。
- 模型调用使用 `httpx` 直连 DeepSeek OpenAI 兼容接口；固定官方地址和 `DEEPSEEK_API_KEY`，支持任意 `deepseek-*` 模型名。
- Runner 支持通过 `sf run ... --model <deepseek-model>` 临时覆盖模型，不修改工作手册。
- Flow 支持 JSON 输出契约、条件节点和人工审批节点；审批结果通过运行记录恢复。
- MCP 作为高级入口保留，不进入 README 主流程；它复用同一 Core 与 Runner。
- 本地网页 P0 已接入：`sf web` 可启动本地网页，提供示例助手首页、DeepSeek API Key 配置和默认模型保存。
- 本地网页 P1 已接入文字版核心闭环：自然语言生成助手草稿、表单确认、试运行、保存版本、手动运行和本地运行记录。
- 本地网页 P2 已接入文件输入、敏感信息检查、建议脱敏、结果格式选择、单独下载和 ZIP 打包下载。
- 本地网页 P3 已接入工作助手 `.sfassistant` 导出、导入个人副本、单次运行删除和按助手清空历史。

## Verified locally

- Windows 11、Python 3.12.13。
- `189 passed`（核心测试 182 项，MCP stdio 端到端测试 7 项）。
- Ruff check 通过，34 个 Python 文件 format check 通过。
- wheel 与 sdist 构建通过。
- GitHub Actions 的 Windows/Linux × Python 3.12/3.13 测试矩阵与 Ubuntu build/clean-wheel smoke 通过。
- wheel 在新建隔离环境安装成功，共安装 24 个包；离开源码目录后可发现内置资产并执行 `sf run content-writer "测试主题" --dry-run`。
- README 70 行；`sf --help` 顶层命令 7 个。
- `soloflow/` Python 代码 3,476 行，无空包、无 `core → cli` 反向导入。
- 工作手册、Flow、Agent 共用项目 → 用户 → 内置的资产发现顺序；工作手册优先查找 `playbooks/PLAYBOOK.md`，同时兼容 `skills/SKILL.md`。
- Prompt 与模型调用统一进入 Runner；生产代码只有 Runner 调用 `chat()`。
- 非 DeepSeek 的 `base_url`、`api_key_env` 或 `model` 会在读取密钥和创建 HTTP 客户端前被拒绝。
- `litellm` 与 `textual` 已从项目依赖和 `uv.lock` 移除。
- v2.0.0 GitHub Release 与 PyPI OIDC Trusted Publishing 成功；wheel、sdist 在两端的 SHA256 一致。
- 从 PyPI 官方索引隔离安装 `soloflow==2.0.0` 成功；源码目录外的版本、内置资产发现与 DeepSeek dry-run 验收通过。
- 真实 DeepSeek 请求验收通过：短任务返回预期文本；CLI `--model deepseek-chat` 端到端调用成功。

## Removed in v2

- Heartbeat daemon 与相关 CLI。
- 远程 Registry 与 publish/install/update 工作流。
- Textual dashboard。
- `skill iter` / auto_iter。
- Skill 依赖版本小语言、Skill `depends_on` 与迭代元数据。
- 空的 `storage/`、`utils/` 包。

## Not part of v2.0.0 release verification

- v2.0.0 发布门禁使用无网络 mock 测试；本 dev 分支已额外完成一次真实 DeepSeek 请求验收。

## Known limitations

- PDF 只支持可提取文本；扫描件和 OCR 暂不支持。
- 图片输入需要用户选择带 `vl`、`vision` 或 `image` 标识的 DeepSeek 模型。
- 尚未提供运行历史列表、按日期筛选和“清空全部项目数据”等更完整的历史管理功能。
- Runner 不自动提供浏览器、搜索、文件系统或其他外部工具。
- Flow 暂无 fallback model、持久化队列或分布式执行。

## Release gate

v2.0.0 已完成 `main` CI、GitHub Release、PyPI 发布和官方索引安装验收。后续版本继续使用同一 tag 驱动门禁。
