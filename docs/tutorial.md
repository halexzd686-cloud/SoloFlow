# TrailLight：从一个 Skill 到完整 Flow

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

SoloFlow 只读取当前目录的 `.env`。不要把真实密钥写进 Skill 或提交到 Git。

## 2. 先做零费用预览

```bash
uvx soloflow run content-writer "为 TrailLight Mini 写一篇产品介绍" --dry-run
```

输出会包含 Skill 的身份、写作目标、风格、规则和你的任务。`--dry-run` 不请求模型。

## 3. 运行真实 Skill

```bash
uvx soloflow run content-writer "为 TrailLight Mini 写一篇产品介绍。已知：180 克、三档亮度、USB-C 充电、面向周末露营新手。不得编造其他参数。"
```

SoloFlow 使用 `deepseek/deepseek-v4-flash` 生成内容，并显示 token 用量。事实仍需人工复核。

## 4. 看懂 Skill 文件

内置示例位于 [`skills/writing/content-writer/SKILL.md`](../skills/writing/content-writer/SKILL.md)：

```yaml
---
name: content-writer
model: deepseek-v4-flash
provider: deepseek
objective: 根据主题撰写一篇结构清晰的文章
rules:
  - 不编造数据
---
```

frontmatter 保存模型配置和规则，下面的 Markdown 是具体工作方法。复制并修改这个文件，就能得到自己的 Skill。

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

## 6. 查看与恢复

```bash
uvx soloflow flow runs
uvx soloflow flow resume <run-id>
```

运行记录保存在当前目录的 `.soloflow/runs/`。恢复时会复用已经完成的步骤，从失败处继续。

## 7. 可选：使用 Agent

Agent 给 Skill 增加固定角色。下面的命令会让“内容主编”执行写作任务：

```bash
uvx soloflow agent run content-editor "为 TrailLight Mini 写一篇产品介绍"
```

首次使用只需掌握 Skill；需要稳定的人格和行为规则时再使用 Agent。

## 常见问题

### 提示缺少 API Key

确认 `.env` 位于执行命令的当前目录，文件名不是 `.env.txt`；也可以重新设置终端环境变量。

### 想先确认任务内容

加 `--dry-run`。它会渲染 Prompt 和 Flow 计划，但不会产生模型费用。

### Flow 中途网络失败

运行 `flow runs` 找到 run ID，网络恢复后执行 `flow resume <run-id>`。

### 输出能否直接发布

不能保证。SoloFlow 让工作方法和执行过程可重复，但模型输出仍需要人工检查。
