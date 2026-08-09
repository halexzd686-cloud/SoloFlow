# HANDOFF — SoloFlow 简化重构交接文档

> 受众：接手执行的 AI agent（Codex）或人类开发者
> 目标：把 SoloFlow 从"系统级应用"收敛回"新手 10 分钟能跑通的小工具"
> 当前版本：v1.0.1（main @ 1ab6082），重构后发布为 v2.0.0（允许破坏性变更）

---

## 1. 背景与问题诊断

SoloFlow 的核心价值一句话能说清：**把 AI 工作方法存成文件（Skill），按步骤自动执行（Flow）**。
但当前实现把这个简单内核包进了过重的外壳里。以下事实均来自代码调查，可在括号内的位置复核：

### 1.1 规模与核心不匹配

- 全项目 `soloflow/` 共 36 个文件、约 8 787 行；核心的"加载 Skill → 拼 Prompt → 调 LLM"路径（`core/runner.py` + `core/skill_loader.py` + `models/skill.py`）只有约 800 行。
- 约 44% 的代码服务于边缘功能：Heartbeat（`core/heartbeat.py`，749 行）、Registry（`core/registry.py`，890 行）、auto_iter（`core/auto_iter.py`，498 行）、TUI（`tui/`，1 751 行）。
- Heartbeat 实现了 PID 文件、跨平台进程探测、Unix double-fork、Windows detach——但仓库自带的两个 agent.yml 里 `heartbeat.enabled: false`，**默认没有任何用户使用它**。
- Registry 实现了 git clone 缓存、原子安装、自动建分支 + gh CLI 提 PR——面向一个**尚不存在的社区市场**。
- `storage/`、`utils/` 两个子包是 1 行空壳，纯占位。

### 1.2 新手门槛

- 概念面：README 第一张表就抛出 6 个概念（Skill / Agent / Flow / Registry / Heartbeat / MCP），新用户在跑通第一条命令前要先理解一套"工作室"隐喻。
- 命令面：CLI 共 **32 个命令**、5 个命令组 + 心跳子组 + 5 个顶层命令；`mcp-config` 与 `mcp-config-set` 命名割裂，`skill init` / `flow init` / `agent create` 三种创建方式不统一。
- 入口面：同一批能力有三个入口——CLI（32 命令）、TUI（Textual 仪表盘）、MCP（手写 774 行 JSON-RPC server）。新人需要先判断"我该用哪个入口"。
- 文档面：README 181 行，混合了概念教学、教程、能力清单、能力边界、版本路线、发布验收细节；`docs/` 下还有 quickstart / tutorial / mcp / architecture 四篇，内容互相重叠。

### 1.3 内部结构问题（顺手修，不是本次重点）

- 三种资产发现规则不一致：Skill 有 4 级查找路径（`core/skill_loader.py:295`），Flow 只有 2 级（`core/assets.py:22`），Agent 的逻辑放在 CLI 层（`cli/agent.py:23`）。
- "拼 Prompt + 调 LLM + Rich 展示"逻辑重复三份：`core/runner.py`、`core/agent_runner.py`、`core/flow_engine.py:309 _build_step_prompt`。
- 分层倒挂：`core/flow_engine.py:326` 在 core 里 import CLI 层的私有函数 `_load_agent`。
- `run_flow`（`core/flow_engine.py:585`）单函数约 406 行、9 个参数，其中 4 个下划线开头的私有参数专门用于 resume，属于接口泄漏。
- `llm/client.py` 用 litellm 做"多 provider 统一抽象"，但实际只支持 DeepSeek 一家；`models/skill.py` 为 Skill 依赖实现了 7 种版本约束符的小语言（约 115 行）。

---

## 2. 重构原则（执行全程生效，优先级高于任何具体任务）

1. **KISS，能删就不改。** 默认动作是删除/降级，不是"加个配置项让它可选"。可配置性是过度设计的温床。
2. **核心路径只有一个。** 重构后，新用户的心智模型只需三个概念：Skill、Flow、（可选的）Agent。其余一切要么删除，要么从默认视野中消失。
3. **文档先行。** 先重写 README 和 quickstart，让"目标体验"被文字定义下来，再动代码去匹配它。不要改完代码再补文档。
4. **不新增抽象。** 本项目的病就是抽象过多。重构期间禁止引入新的基类、注册表、插件机制、provider 抽象层。合并不需要的新模块时，直接内联。
5. **每个阶段独立提交、独立可验收。** 不要一个巨型 commit。删除的代码靠 git history 保留，不留注释掉的尸体。
6. **测试必须保持绿。** 删除功能时同步删除其测试；保留功能的现有测试不允许为了通过而削弱断言。

---

## 3. 目标体验（北极星）

一个从没见过 SoloFlow 的用户，在装好 Python 3.12+ 和 DeepSeek API Key 的前提下：

```bash
uvx soloflow run content-writer "为我的产品写一篇介绍"
```

- 全程只需理解"Skill = 一份工作手册"一个概念就能跑通。
- README 首屏（约 60 行以内）看完即可执行上述命令；不配 key 时错误信息直接告诉用户怎么配。
- `sf --help` 展示的常用命令不超过 10 个，高级功能折叠或移除。

---

## 4. 改造方案（按阶段执行）

### 阶段 0：决策确认（动手前）

以下裁剪项影响面大，先与项目所有者确认去留，再进入后续阶段。**推荐方案已标注**，若无人确认，按推荐执行。

| 功能 | 代码量 | 推荐处理 | 理由 |
| --- | --- | --- | --- |
| Heartbeat（`core/heartbeat.py` + `agent heartbeat` 命令组） | ~750 行 + 26 测试 | **删除** | 默认关闭、无真实用户；定时任务用系统 cron/Task Scheduler 调 `sf skill run` 即可替代 |
| Registry（`core/registry.py` + `registry` 命令组） | ~890 行 + 31 测试 | **删除**，README 留一段"用 git 分享 Skill 文件"的说明 | 社区市场超前建设；分享文本文件不需要专用协议 |
| Textual TUI（`tui/` + `dashboard` 命令） | ~1 750 行 + 7 测试 | **替换为 Rich 实时进度视图**（项目所有者已确认保留演示能力，见阶段 2 第 3 条） | 演示价值保留，但 Textual 实现维护成本过高；Rich 已是现有依赖，预计 200–300 行替代 1 750 行 |
| auto_iter（`core/auto_iter.py` + `skill iter` 命令） | ~500 行 + 8 测试 | **删除** | "LLM 当评委自动改 Skill"属于研究性功能，可日后以独立脚本回归 |
| MCP server（`mcp/` + `mcp`/`mcp-config` 命令） | ~775 行 + 28 测试 | **保留但降级**：移出 README 主流程，归入 `docs/mcp.md` | 已有真实 Claude Code 用户验证，是差异化能力；但不应出现在新手路径上 |
| LLM 调用层（`llm/client.py`，litellm 封装） | ~300 行 | **用 httpx 直连 OpenAI 兼容协议替代 litellm**，保持 DeepSeek-only 白名单锁定（项目所有者已确认现阶段只用 `deepseek-v4-flash`，未来可能接 OpenAI/Claude，见阶段 3 第 6 条） | litellm 是为不存在的多供应商需求付的"持有税"；OpenAI 兼容协议天然覆盖 DeepSeek/OpenAI/Kimi 等，未来扩展只需改配置 |

裁剪后预计代码量从 ~8 800 行降到 ~4 000–4 500 行，命令从 32 个降到 12 个左右。

### 阶段 1：文档与上手体验（先于代码改动）

1. **重写 README.md，目标 ≤ 100 行**，结构固定为：
   - 一句话定位（沿用现有 tagline）。
   - 30 秒安装 + 跑通（一条 `uvx` 命令 + 配 key + 一条 run 命令）。
   - 三个概念：Skill / Flow / Agent，各一句话 + 一个文件示例链接。
   - 常用命令速查表（≤ 10 行表格）。
   - 链接区：文档、贡献、License。
   - 删除：工作室隐喻大表、能力边界清单、发布验收细节、版本路线（移入 CHANGELOG/STATUS）、MCP/Registry/Heartbeat 的所有提及。
2. **合并 docs/**：`quickstart.md` 并入 README；`tutorial.md` 保留但精简为一份完整的 TrailLight 案例；`architecture.md` 重写以反映裁剪后的结构；`mcp.md` 保留。
3. **改善错误信息**：缺少 `DEEPSEEK_API_KEY` 时，报错文案直接给出两种配置方式（`.env` 和环境变量）和获取 key 的链接，而不是 generic 异常。

**验收**：让一个不了解项目的人只看 README，能在 10 分钟内跑通第一条真实命令。

### 阶段 2：命令面收敛

1. 删除阶段 0 确认裁剪的命令组及其 CLI 文件（`cli/registry.py`、heartbeat 子组、`skill iter`）。
2. 顶层增加快捷命令 `sf run <skill-name> <task>` 作为 `sf skill run` 的别名，作为 README 主推入口。
3. **用 Rich 实时进度视图替换 Textual TUI**（项目所有者要求保留演示时的视觉直观性）：
   - 删除整个 `tui/` 包（9 个文件、1 751 行）和 `dashboard` 命令，移除 textual 依赖。
   - 在 `core/runner.py` / `core/flow_engine.py` 执行期间，用 `rich.Live` 渲染实时刷新面板：Flow 步骤 DAG 进度、当前步骤 spinner、token 用量、最终输出。这是 `run` 命令的默认行为，终端滚动展示，演示时观众能看到完整过程。
   - 新增 `sf flow watch <run-id>`，可随时重新挂载到正在运行的 Flow 上查看实时进度，覆盖原 dashboard 的核心用途。
   - 全部展示代码集中在一个新模块（如 `cli/live_view.py`），目标 200–300 行，只读运行状态文件，不写任何逻辑。
4. 统一创建命令：保留 `skill init` / `flow init` / `agent create`，但三者输出格式、生成的模板字段保持一致风格。
5. `mcp` 命令保留；`mcp-config` 与 `mcp-config-set` 合并为一个命令（保留 `mcp-config`，带 `--set` 之类子参数或直接交互式生成）。
6. 最终命令面（目标）：
   - 顶层：`run`、`version`、`mcp`
   - `skill`：`init`、`list`、`show`、`run`、`validate`
   - `flow`：`init`、`list`、`show`、`run`、`runs`、`resume`、`watch`、`validate`
   - `agent`：`create`、`list`、`show`、`run`

**验收**：`sf --help` 与 README 速查表完全一致；`uv run pytest -q` 全绿。

### 阶段 3：代码结构简化

按依赖顺序执行，每步独立提交：

1. **统一资产发现**：在 `core/assets.py` 中实现单一 `find_asset(kind, name)`，对 Skill/Flow/Agent 使用同一套查找顺序：项目目录 → `~/.soloflow/` → 内置。删除 `cli/agent.py` 中的查找逻辑和 `skill_loader.py` 中的特化路径。同步更新 README 中关于覆盖规则的说明（一段话能说清）。
2. **消除三份 prompt 拼装重复**：把"加载资产 + 渲染 prompt + 调用 LLM + 展示结果"收敛到 `core/runner.py` 一个函数族；`agent_runner.py` 和 `flow_engine.py` 改为调用它。
3. **解除 core→cli 反向依赖**：`_load_agent` 从 `cli/agent.py` 下沉到 core，`flow_engine.py:326` 改为正向 import。
4. **拆 `run_flow`**：把 resume 逻辑抽成独立的 `resume_flow()` 入口，删除 4 个下划线私有参数；`run_flow` 只保留公开参数。单函数控制在 150 行以内，超出部分按职责拆为私有辅助函数。
5. **删除空壳**：移除 `storage/`、`utils/` 空包及所有引用。
6. **重写 LLM 调用层**：去掉 litellm 依赖，用 `httpx` 直连 OpenAI 兼容接口（`llm/client.py` 从 304 行降到约 100 行，并显著减小安装体积——`STATUS.md` 自己也承认"LiteLLM 及其依赖体积较大"）。设计要求：
   - `base_url`、`api_key_env`、`model` 做成配置项，DeepSeek 只是默认的一组取值。OpenAI、Kimi、通义等同样讲 OpenAI 兼容协议，未来接入只需改配置，无需架构变更。
   - **保留并强化白名单护栏**：现阶段只允许 `deepseek/deepseek-v4-flash`，非白名单模型在读取 API key 之前就报错拒绝（防止朋友使用时手滑把账单打到其他付费 API）。白名单本身是一个常量列表，未来放开时改一处即可。
   - 全项目调用 LLM 只经过一个函数（如 `chat(messages, model_config)`），这是为未来 provider（包括协议不同的 Claude）留的唯一一条"缝"。禁止提前抽象出 provider 基类或注册机制。
   - 同时删除 `models/skill.py` 中的版本约束小语言，Skill 依赖只保留精确版本号或删除该字段。
7. **依赖清理**：`pyproject.toml` 移除 litellm、textual 及裁剪功能涉及的依赖。

**验收**：`uv run pytest -q` 全绿；`uv build` 通过；wheel 在干净环境安装后 `sf run content-writer --dry-run` 可用；`ruff check` 与 `ruff format --check` 通过。

### 阶段 4：发布

1. 版本号升为 `2.0.0`，`CHANGELOG.md` 用一节明确列出所有破坏性变更和被删功能的迁移建议（如"Heartbeat 用户请改用系统定时任务 + `sf run`"）。
2. 更新 `STATUS.md`：删除已裁剪功能的验收记录，补充重构后的验证结果。
3. 按现有 OIDC Trusted Publishing 流程发布 PyPI 与 GitHub Release。

---

## 5. 明确不做的事（Non-goals）

- 不增加新的模型 provider（保持 DeepSeek-only 白名单；OpenAI 兼容配置项属于阶段 3 第 6 条的既定设计，不算新增 provider；接 Claude 等独立协议留待真实需求出现）。
- 不为 Flow 增加条件节点、人工审批、fallback model。
- 不引入插件系统、扩展点、hook 机制、provider 基类或注册机制。
- 不重写测试框架或迁移测试目录结构。
- 不改动 LICENSE、SECURITY.md、CODE_OF_CONDUCT.md。

## 6. 给执行者（Codex）的特别提醒

你有把任务做成"系统级应用"的倾向，本次任务的要求恰好相反。执行时遵守：

- **先列删除清单再动手**：阶段 2/3 开始前，先输出"将删除的文件与命令"清单，确认后再改。
- **禁止补偿性建设**：删除一个功能后，不要为它设计"轻量替代框架"。删了就是删了，README 里一段文字说明足够。唯一的例外是阶段 2 第 3 条的 Rich 实时视图，那是项目所有者明确要求保留的演示能力，且行数预算已限定在 200–300 行。
- **"留缝不留架"**：为未来可能性（如其他模型 provider）只保留配置项和单一函数边界，不提前建抽象层。
- **每个阶段结束时汇报**：改动文件数、删除/新增行数、测试数变化。如果某阶段代码行数不降反升，停下来重新评估。
- **遇到"也许以后有用"的代码，默认删除**——git history 就是它的存档，不需要留在工作区。

## 7. 总体验收标准

- [ ] README ≤ 100 行，新用户按 README 10 分钟内跑通真实命令。
- [ ] `sf --help` 常用命令 ≤ 10 个，无 Registry/Heartbeat/iter/dashboard 相关命令。
- [ ] `sf flow run` 执行时有 Rich 实时进度面板，`sf flow watch <run-id>` 可重新挂载查看；textual 依赖已移除。
- [ ] `soloflow/` 代码 ≤ 4 500 行，无空包子模块，无 core→cli 反向 import。
- [ ] LLM 调用不经过 litellm；非 `deepseek/deepseek-v4-flash` 的模型在读 key 前被拒绝；`base_url`/`api_key_env`/`model` 可配置。
- [ ] 三种资产共用一套发现逻辑，文档中一段话可描述。
- [ ] `uv run pytest -q` 全绿，`ruff check` / `ruff format --check` 通过，`uv build` 通过，干净环境 wheel smoke 通过。
- [ ] CHANGELOG v2.0.0 列出全部破坏性变更与迁移建议。
