# TrailLight：从一个工作手册到完整 Flow

这份教程用虚构产品 TrailLight Mini 演示 SoloFlow 的完整主路径。产品资料均为教学数据。

## 目标

已知资料：

- 重量 180 克；
- 三档亮度；
- USB-C 充电；
- 面向周末露营新手。

我们先生成一篇产品介绍，再让 Flow 自动完成调研、长文和社交文案。

## 1. 配置 DeepSeek

PowerShell：

```powershell
$env:DEEPSEEK_API_KEY = "你的密钥"
```

也可以在运行目录创建 `.env`：

```dotenv
DEEPSEEK_API_KEY=你的密钥
```

SoloFlow 只读取当前目录的 `.env`。不要把真实密钥写进工作手册或提交到 Git。

## 2. 先做零费用预览

```bash
uvx soloflow run content-writer "为 TrailLight Mini 写一篇产品介绍" --dry-run
```

输出会包含工作手册的身份、写作目标、风格、规则和你的任务。`--dry-run` 不请求模型。

## 3. 运行真实工作手册

```bash
uvx soloflow run content-writer "为 TrailLight Mini 写一篇产品介绍。已知：180 克、三档亮度、USB-C 充电、面向周末露营新手。不得编造其他参数。"
```

SoloFlow 使用配置的 DeepSeek 模型生成内容，并显示 token 用量。默认模型是 `deepseek-v4-flash`，也可以在工作手册中改成其他 `deepseek-*` 模型。事实仍需人工复核。

如果只想本次运行换一个模型，不修改工作手册：

```bash
uvx soloflow run content-writer "为 TrailLight Mini 写一篇产品介绍" --model deepseek-chat
```

## 4. 看懂工作手册文件

内置兼容示例位于 [`skills/writing/content-writer/SKILL.md`](../skills/writing/content-writer/SKILL.md)。新建工作手册会使用 `playbooks/<name>/PLAYBOOK.md`：

```yaml
---
name: content-writer
base_url: https://api.deepseek.com
api_key_env: DEEPSEEK_API_KEY
model: deepseek-v4-flash
objective: 根据主题撰写一篇结构清晰的文章
rules:
  - 不编造数据
---
```

frontmatter 保存模型配置和规则，下面的 Markdown 是具体工作方法。复制并修改这个文件，就能得到自己的工作手册。

## 5. 执行完整 Flow

先预览四个步骤：

```bash
uvx soloflow flow run blog-pipeline --dry-run -i topic="TrailLight Mini"
```

执行顺序是：

```text
research → write → social-twitter
                 ↘ social-linkedin
```

后两个步骤可以并行。确认后执行真实 Flow：

```bash
uvx soloflow flow run blog-pipeline -i topic="TrailLight Mini：180 克、三档亮度、USB-C 充电；不得编造市场数据"
```

Flow 本身没有联网搜索能力；`research` 只能整理输入信息，不能核实外部市场事实。

### 加入结构化审核和人工确认

工作中常见的做法是让审核节点返回机器可判断的 JSON，再决定是否进入发布步骤：

```yaml
- id: review
  playbook: code-reviewer
  output_format: json
  output_schema:
    type: object
    required: [approved, issues]
    properties:
      approved: {type: boolean}
      issues: {type: array}

- id: approval
  type: approval
  depends_on: [review]

- id: publish
  playbook: content-writer
  depends_on: [approval]
  when: $steps.approval.data.approved == true
```

Flow 遇到 `approval` 会保存运行记录并暂停。查看 `sf flow runs` 得到 run ID 后，人工确认：

```bash
uvx soloflow flow approve <run-id> --step approval --note "已复核，可发布"
# 或
uvx soloflow flow reject <run-id> --step approval --note "需要修改后再审"
```

## 6. 查看与恢复

```bash
uvx soloflow flow runs
uvx soloflow flow resume <run-id>
```

运行记录保存在当前目录的 `.soloflow/runs/`。恢复时会复用已经完成的步骤，从失败处继续；人工审批也使用同一套恢复机制。

## 7. 可选：使用 Agent

Agent 给工作手册增加固定角色。下面的命令会让“内容主编”执行写作任务：

```bash
uvx soloflow agent run content-editor "为 TrailLight Mini 写一篇产品介绍"
```

首次使用只需掌握工作手册；需要稳定的人格和行为规则时再使用 Agent。

## 常见问题

### 提示缺少 API Key

确认 `.env` 位于执行命令的当前目录，文件名不是 `.env.txt`；也可以重新设置终端环境变量。

### 想先确认任务内容

加 `--dry-run`。它会渲染 Prompt 和 Flow 计划，但不会产生模型费用。

### Flow 中途网络失败

运行 `flow runs` 找到 run ID，网络恢复后执行 `flow resume <run-id>`。

### 输出能否直接发布

不能保证。SoloFlow 让工作方法和执行过程可重复，但模型输出仍需要人工检查。
