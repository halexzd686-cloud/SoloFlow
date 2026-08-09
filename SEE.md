# SoloFlow — 项目现状总览

> **版本**: v0.9.1 | **日期**: 2026-08-09 | **测试**: 233/233 通过（本地） | **Ruff**: 0 错误 | **CI**: 配置存在，尚未在远程 CI 实际验证 | **wheel**: 本地干净虚拟环境安装及源码目录外 smoke 通过

---

## 一、这个项目是做什么的？

**SoloFlow = Docker Compose for AI Skills** —— 文件驱动的 AI 技能管理系统。

核心思想：把"怎么用好 AI 干活"这件事，从**散落各处的聊天记录、临时提示词**，升级为**结构化的、可复用、可分享、可自我进化的技能资产**。

一个 `SKILL.md` 文件 = 一份完整的专家经验包：

```markdown
---
name: content-writer          # 技能名
model: claude-sonnet-4-20250514
provider: anthropic
context: 你是一位资深商业内容作者...   # CoSTAR 六要素
objective: 撰写一篇 3000-4000 字深度文章...
rules:
  - "不要有 AI 味儿"
---

## Instructions
1. 破题：用一个反直觉的观点开头
2. 展开：用具体案例支撑每个观点
```

### 三个核心概念

```
Skill（技能文件） → 封装专家经验，一个文件 = 一个完整技能
Agent（智能体）   → 加载 Skill，扮演特定角色（可绑定多个 Skill）
Flow（工作流）    → 编排多个 Skill/Agent 协同完成复杂任务（DAG 有向无环图）
```

### 解决什么问题？

| 痛点 | SoloFlow 的解法 |
|------|----------------|
| 提示词散落各处，每次都要重新写 | Skill 文件化，一处定义、处处复用 |
| 调好的 prompt 换个场景就失效 | Skill 自我迭代引擎，AI 自己评估自己改进 |
| 复杂任务靠单次对话搞不定 | Flow DAG 编排，多 Skill 并行协作 |
| 经验无法传递给别人 | SKILL.md 是纯文本，Git 友好，可发布到社区 Registry |
| 不确定用哪个模型 | LiteLLM 统一调用层，一键切换 OpenAI/Anthropic/国产模型 |

---

## 二、现阶段完成了什么？（v0.1 → v0.9.1）

### ✅ Skill 系统（100%）

- SKILL.md 创建 / 校验 / 列表 / 详情 / 执行（`sf skill *`）
- CoSTAR 六要素模型（Context / Objective / Style / Tone / Audience / Response）
- `sf skill iter` — 自我迭代引擎（评估→改进→再评估循环，含 JSON 健壮解析、退化回退保护、评分锚点）
- 3 个内置示例 Skill：content-writer / code-reviewer / market-researcher

### ✅ Agent 系统（98%）

- Agent 定义（Soul 人格 + Skills 绑定 + Heartbeat 心跳）
- `sf agent run` 执行任务；**Agent 配置覆盖采用 Optional 语义**（None=继承 Skill，非 None=显式覆盖）
- **内置 Agent 示例**：content-editor、code-guardian
- **心跳 daemon**：定时自动执行 Agent（start/stop/list/resume，Windows 安全探活）

### ✅ Flow 编排引擎（99%）

- YAML 定义 DAG，自动拓扑排序生成分层并行执行计划
- 变量引用（`$input.xxx` / `$steps.xxx.output`）、循环依赖检测
- asyncio 并行执行 + 失败恢复（依赖失败的步骤自动跳过）
- 运行状态持久化 + **`sf flow resume` 断点恢复**（复用原 run_id + attempt lineage + 完整上游输出）
- **`flow.output` 正式输出映射** + **输入类型/enum/min-max 校验**
- **真实 token usage 累计** + 步骤级 timeout/retry
- 8 个预置 Flow 模板（见案例）

### ✅ Registry 社区市场（85%）

- 离线内置索引 + Git 远程仓库拉取（网络不可用时自动回退，**pull 失败明确报告**）
- 搜索 / 安装（**严格版本锁定**，版本不存在必须失败或 `--fallback-latest`）/ 发布（`--submit` 自动 PR）/ 条目校验
- **供应链安全检查**（5MB 大小上限）
- **本地 git 裸仓库闭环验证**（clone→索引→版本安装全链路测试）

### ✅ MCP Server（100%）

- JSON-RPC 2.0 over stdio，暴露 **9 个工具**给 Claude/其他 AI 客户端调用
- auth token + 工具白名单（**真实子进程 E2E 测试覆盖**）

### ✅ TUI 仪表盘（99%）

- 侘寂风（和纸白 + 焦茶 + 利休色）四面板仪表盘
- 键盘导航（s/f/g/↑↓/enter/tab/q）+ 详情弹窗 + Registry 搜索
- **自适应布局**：三档终端断点 + Tab 折叠 Registry
- **Flow 动态输入表单**（BUG-TUI-001 修复：必填输入弹窗收集）+ 一键恢复
- **Textual 无头自动化测试**（5 项）

### ✅ LLM 调用层（95%）

- `LLMResult` 结构化结果（token/model/request_id）
- **重试 + 指数退避 + 超时**（限流/超时/网络错误自动重试）
- 流式 usage 汇总回调（非 chunk 数）

### 质量基线

| 指标 | 数值 |
|------|------|
| 测试 | 233/233 通过（本地） |
| Ruff | 0 错误 |
| CI | Windows+Linux × 3.12/3.13 矩阵 + wheel smoke |
| 可用命令 | skill(6) / agent(4) / flow(6) / registry(6) + dashboard / mcp / version |
| 内置资产 | 4 Skill + 2 Agent + 8 Flow 模板 |

---

## 三、还有什么未完成？

### 🔴 需要真实环境（v1.0 前）

| 任务 | 说明 | 依赖 |
|------|------|------|
| **Registry 真实远程仓库** | 在 GitHub 创建 `soloflow-community/skills-registry`，跑通 publish → PR → install（本地 git 闭环已验证） | GitHub 账号 |
| **真实 LLM 端到端验证** | Skill/Agent/Flow/auto_iter 用真实 API 多轮验证 | API Key |
| **真实 MCP 客户端验证** | 用 Claude Code / Cursor 连一次 `sf mcp` | 外部客户端 |

### 🟡 产品决策 / 后续迭代

| 任务 | 说明 | 优先级 |
|------|------|--------|
| Heartbeat daemon 稳定性 | Windows 重启恢复/并发/重复 start-stop | 中 |
| Skill 依赖自动安装 + lockfile | 目前只校验不安装 | 低 |
| Flow fallback model / 条件执行 / 人工审批 | 步骤级策略扩展 | 低 |
| **发布 PyPI** | `1.0.0rc1` → `1.0.0`（wheel 已验证可安装） | 待定 |
| Web UI / VS Code 扩展 / i18n | 正确性修复完成后考虑 | 暂缓 |

### 已知技术债

- **Windows GBK 终端中文乱码**（TUI 不受影响，UTF-8 管道输出正常）
- LiteLLM 依赖体积大
- 心跳 daemon 在 Windows 上靠 subprocess，稳定性待验证（BUG-HB-002）

---

## 四、案例参考：用 blog-pipeline 一键产出整套内容

### 场景

你是一个独立开发者，想围绕"AI Agent 落地"这个主题做一次完整的内容发布。
以前你需要：查资料 → 写文章 → 写 5 条推文 → 写 2 条 LinkedIn 文案，全程手动、重复调 prompt。
现在你只需要 **一条命令**。

### 1. 定义 Flow（已内置）

`flows/blog-pipeline.flow.yml` 定义了整条流水线：

```
输入: topic="AI Agent 落地"

Level 1:  research (market-researcher)     ← 调研选题角度和竞品内容
Level 2:  write (content-writer)           ← 基于调研写 3000-4000 字长文
Level 3:  social-twitter (content-writer)  ← 从文章生成 5 条推文
          social-linkedin (content-writer) ← 从文章生成 2 条 LinkedIn 文案
```

关键点：
- 步骤间通过 `$input.topic`、`$steps.research.output` 传递数据
- research 和 write 串行（写作依赖调研结果），两个 social 步骤**并行执行**
- 每个步骤可以指定不同的 Skill，甚至不同的模型

### 2. 一键运行

```bash
cd soloflow
sf flow run blog-pipeline -i topic="AI Agent 落地"
```

执行过程：
- 引擎自动拓扑排序 → 生成分层执行计划
- 逐层执行：`research` 完成 → `write` 开始 → 两个 social 步骤并行
- 每步结果实时保存到 `.soloflow/runs/`，TUI 可实时查看进度条

### 3. 中途挂了怎么办？

```bash
# 查看运行记录，找到 run-xxxx
sf flow runs

# 从断点恢复 —— 已完成的步骤自动跳过
sf flow resume run-xxxx
```

### 4. 更高阶的玩法

```bash
# 在 TUI 仪表盘里用 ↑↓ 选中 blog-pipeline，按 R 直接跑
sf dashboard

# 让 AI 客户端通过 MCP 直接调你的技能库
# (在 Claude Code 的配置里指向 mcp-config.example.json)

# 把调好的技能发布到社区，别人一条命令就能装
sf registry publish skills/writing/content-writer --submit
```

### 5. 进阶：技能自我进化

```bash
# 让 content-writer 自己迭代 30 轮，越用越强
sf skill iter content-writer -n 30
```

引擎会循环执行：**用当前技能生成测试输出 → LLM 评估打分 → LLM 提出改进 → 改入 SKILL.md**，并带有退化回退保护（分数下跌时回滚到最佳版本）。

---

## 五、快速拉起

```bash
cd E:/outdoor/soloflow
uv sync --group dev
uv run pytest tests/ -v     # 233 tests, 全部通过
uv run sf skill list        # 查看 3 个 Skill
uv run sf flow list         # 查看 8 个 Flow
uv run sf dashboard         # TUI 仪表盘
uv run sf flow run blog-pipeline -i topic="..." --dry-run  # 先看执行计划
```

---

*本文件由项目现状整理而成，详细技术文档见 `HANDOFF.md`*
