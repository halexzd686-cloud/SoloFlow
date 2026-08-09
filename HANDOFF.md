# SoloFlow 最终收尾交接文档

> 目标读者：DeepSeek v4 Flash 或其他代码 Agent
> 文档用途：最后一轮本地质量收尾与发布前验收
> 最后复核：2026-08-08
> 当前版本：`0.9.1`
> 当前本地测试：`230 passed`
> 当前静态检查：Ruff check 与 format check 均通过
> 当前结论：本地验证充分的 v1.0 RC 候选；正式 v1.0 仍需真实外部环境验证

---

## 0. 最重要的执行规则

这是最终收尾任务，不要重新设计项目，也不要重复修改已经通过行为测试的核心功能。

1. 只处理第 4 节列出的剩余本地问题和文档一致性。
2. 不要增加 Web UI、VS Code 扩展、条件 Flow、工具调用或其他新功能。
3. 每个修改都必须有行为级回归测试；不要只增加测试数量。
4. 不得把 mock、pytest、本地 Git 仓库或本地 wheel 构建写成真实外部服务已验证。
5. 保持 Windows Heartbeat 的 Win32 探活实现：Windows 使用 `OpenProcess + GetExitCodeProcess`，不要改回 `os.kill(pid, 0)`。
6. 不要破坏旧 Skill、Registry 旧版本、Flow resume、token 累计或已有运行记录。
7. 当前目录不是 Git 仓库；没有真实 CI 日志时，不得声称 GitHub Actions 已通过。
8. 如果第 4 节完成且全部验收命令通过，停止继续改代码，只更新准确状态并报告结果。

---

## 1. 项目定位和边界

SoloFlow 是文件驱动的 AI Skill/Prompt 管理与 LLM 工作流编排工具：

```text
SKILL.md → Skill/Agent Runner → LiteLLM → 模型输出

Flow：输入 → DAG Step A → Step B/C → Step D → 输出与运行状态
```

核心对象：

- Skill：可复用的 `SKILL.md` 专家提示词资产。
- Agent：Soul 人格 + 一个或多个 Skill + 可选配置覆盖。
- Flow：YAML DAG，支持变量引用、分层执行、并行、失败跳过和 resume。
- Heartbeat：定时运行 Agent 的 daemon。
- Registry：Git 驱动的 Skill 索引、搜索、安装和发布。
- MCP：通过 stdio 暴露 Skill、Agent、Flow 工具。
- TUI：基于 Textual 的本地终端仪表盘。

明确边界：

- 当前 Runner 不自动提供浏览器、搜索、文件系统或其他工具。
- Agent 不是自主规划、长期记忆或分布式执行平台。
- Flow 没有条件节点、人工审批、fallback model、持久化队列和分布式执行。
- Registry 暂无 checksum、签名和 commit SHA lockfile。

---

## 2. 当前已验证基线

### 2.1 测试和静态检查

在 Windows Python 3.12.13 环境执行：

```text
pytest -q                         → 230 passed in 15.60s
pytest -q tests/test_tui.py -s    → 7 passed in 3.91s
ruff check soloflow tests         → All checks passed!
ruff format --check ...           → 46 files already formatted
```

TUI 专项测试不再输出 `Unexpected error` 或 `Skill not found: content-writer`。

### 2.2 CLI smoke

以下命令已可运行：

```text
sf version       → SoloFlow v0.9.1
sf agent list    → code-guardian、content-editor
sf flow list     → 预置 Flow 列表
```

部分 Windows GBK 终端仍可能把中文描述显示为乱码，这是已知显示问题，不代表资源加载失败。

### 2.3 关键行为

已通过隔离测试确认：

- 非流式同层步骤真实并发，活动计数可观察到重叠。
- `max_parallel` 能限制非流式并发数量。
- A 失败后，B/C 依赖链会分别变为 `skipped`，不会继续调用 LLM。
- 不相关的独立分支可以继续。
- 流式模式 `max_parallel>1` 在引擎层规范化为串行。
- TUI Flow 输入会传递正确的名称、路径和类型转换后的参数。
- Registry staging 校验失败会保护旧安装，成功安装是完整替换。
- Flow resume 会保留历史输出和 token 累计。
- 非法 Step ID 不会写入路径穿越路径。

---

## 3. 已完成的核心修复（不要回退）

### 3.1 Heartbeat

Windows 使用 Win32 进程查询；Unix 才使用 `os.kill(pid, 0)`。当前进程、无效 PID、子进程生命周期测试通过。daemon 长时间运行、重启恢复、PID 复用和多 Agent 并发仍未真实验证。

### 3.2 Skill 保存

examples、tests、iteration changelog 和未知 frontmatter 字段均可无损保存；round-trip 测试通过。

### 3.3 Flow

- 非流式 LLM 调用使用 `asyncio.to_thread(call_llm_full, ...)`。
- `asyncio.Semaphore` 限制同层并发。
- 依赖必须全部 `done` 才执行。
- failed/skipped 状态可跨任意深度传播。
- resume 复用 run ID，并保留历史步骤、输出和 token。
- Step ID 使用 kebab-case 校验。
- 流式模式有明确的串行契约，不要为了“并发”把同步 generator 粗暴塞进线程。

### 3.4 TUI、Agent、Registry

- TUI 使用 closure 传递 Flow 名称和路径；输入测试覆盖 worker 参数。
- TUI Modal 测试已 mock worker，不再吞掉真实运行错误。
- Agent 搜索支持 `agents/`、当前目录和 `.soloflow/agents`。
- CLI/TUI 支持基础 schema 类型转换，schema default/enum/min/max 校验有效。
- Registry 使用 staging → 校验 → backup → 替换 → 回滚流程。

---

## 4. 最后剩余的本地任务

### P1：拒绝布尔值作为 `max_parallel`

当前校验已经拒绝 `0`、负数、浮点数和字符串，并且 CLI `--parallel 0` 会友好报错、非零退出。但 Python 中：

```python
isinstance(True, int)  # True
```

因此直接调用：

```python
run_flow(flow, max_parallel=True)
```

可能被当作并发数 1 接受，违背“正整数”契约。

要求：

1. 在 `soloflow/core/flow_engine.py` 公共入口拒绝 `bool`。
2. 错误信息继续保持清晰，例如 `max_parallel must be a positive integer`。
3. 增加 API 回归测试：`True` 和 `False` 都立即抛 `ValueError`。
4. 保持已有 0、负数、浮点数、字符串、正常 1/2/5 和流式串行测试不变。

建议校验语义：

```python
if isinstance(max_parallel, bool) or not isinstance(max_parallel, int) or max_parallel < 1:
    raise ValueError(...)
```

验收：布尔值不会创建 semaphore、不会启动任何步骤，也不会挂起。

---

### P1：文档最终一致性

确认并保持以下状态：

- `README.md` 测试基线为 `230`。
- `SEE.md` 测试基线为 `230/230 通过（本地）`。
- `HANDOFF.md` 测试基线为 `230 passed`。
- CI 写成“配置存在，尚未在远程 CI 实际验证”。
- wheel 写成“本地构建成功，未在干净机器验证”。
- 不再出现旧测试数量、虚假的 CI 通过声明或重复的“问题未修复”章节。

检查命令：

```powershell
rg -n '196|222|224|CI.*✅|GitHub Actions.*通过' README.md SEE.md HANDOFF.md
```

允许命令本身在 HANDOFF 的说明中出现；三个文档的当前状态不得出现旧数字或虚假完成声明。

---

## 5. 仍需真实外部验证的事项

以下不能靠 mock 标记完成：

1. 真实 OpenAI、Anthropic 或 DeepSeek API 的 Skill → Agent → Flow 链路。
2. 真实 token usage、timeout、retry、限流和网络异常。
3. 真实远程 Registry 的 pull、publish、PR、update、install 闭环。
4. Claude Code、Cursor、Codex 等真实 MCP 客户端连接 `sf mcp`。
5. GitHub Actions Windows/Linux 矩阵和 wheel smoke。
6. 干净 Python 环境安装 wheel 后运行 CLI smoke。
7. Heartbeat daemon 长时间运行、重启恢复、PID 复用和多 Agent 并发。
8. auto_iter 多轮真实效果、评分退化保护和失败恢复。

回报时必须区分：单元测试、本地子进程 E2E、模拟 Git 仓库闭环、真实外部服务。

---

## 6. 最终执行顺序

1. 修复并测试 `max_parallel=True/False`。
2. 运行文档检查，确认三个文档都使用最新基线 230。
3. 运行第 7 节全部本地验收命令。
4. 如果全部通过，不再增加功能或重构已通过模块。
5. 只在具备凭据和外部环境时进行第 5 节验证；没有条件就明确报告“未验证”。

---

## 7. 最终验收命令

在 `E:\outdoor\soloflow` 执行：

```powershell
Set-Location E:\outdoor\soloflow
$env:PYTHONIOENCODING = 'utf-8'

& .\.venv\Scripts\python.exe -m pytest -q
& .\.venv\Scripts\python.exe -m pytest -q tests/test_tui.py -s
& .\.venv\Scripts\ruff.exe check soloflow tests
& .\.venv\Scripts\ruff.exe format --check soloflow tests

& .\.venv\Scripts\sf.exe version
& .\.venv\Scripts\sf.exe skill list
& .\.venv\Scripts\sf.exe agent list
& .\.venv\Scripts\sf.exe flow list
```

预期：

- 完整 pytest 为 `230 passed` 或更高；若数量变化，立即同步三个文档。
- TUI 专项无未断言错误输出。
- Ruff 和格式检查通过。
- CLI smoke 正常退出。

---

## 8. 最终完成标准

- [x] `max_parallel=True/False` 立即抛出清晰的 `ValueError`。
- [x] `max_parallel=0`、负数、浮点数、字符串仍立即失败。
- [x] 正常并发限制和流式串行契约未回退。
- [x] README、SEE、HANDOFF 当前测试基线一致为 230。
- [x] HANDOFF 只有当前状态，不含已修复问题的旧未修复正文。
- [x] 完整 pytest、TUI 专项、Ruff、format、CLI smoke 全部通过。
- [x] 真实外部验证项目仍明确标记为已验证或未验证。

最终准确表述：

> 核心本地行为已通过自动化测试，项目可作为 v1.0 RC 候选；正式 v1.0 仍等待真实 LLM、Registry、MCP、CI、wheel 和 Heartbeat 验证。

---

## 9. 完成后的回报格式

请报告：

1. 修改了哪些文件以及每个文件解决什么问题。
2. 新增或修改的测试验证了哪些最终行为。
3. 完整 pytest、TUI 专项、Ruff、format、CLI smoke 的实际输出。
4. 真实外部服务是否运行；没有就明确写“未验证”。
5. 尚存风险和下一步建议。

不要只报告“测试通过”或“优化完成”。
