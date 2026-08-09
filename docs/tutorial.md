# 从零完成一次 SoloFlow 内容发布

这份教程通过一个完整的虚拟案例，展示 Skill、Agent、Flow 和断点恢复分别解决什么问题。你不需要先理解 DAG 或 Agent 框架；按顺序执行命令即可。

## 案例目标

“TrailLight Mini”是一款虚构的露营灯。已知资料只有：

- 重量 180 克；
- 三档亮度；
- USB-C 充电；
- 目标用户是周末露营新手。

我们希望得到一篇新品介绍，以及适合 X 和 LinkedIn 的分发文案。案例中的产品与数据均为教学用途，不代表真实商品。

## 先理解四个角色

| 组件 | 在本案例中的职责 | 文件形式 |
| --- | --- | --- |
| Skill | 定义“怎样调研”“怎样写文章” | `SKILL.md` |
| Agent | 给 Skill 加上固定人格和行为规则 | `*.agent.yml` |
| Flow | 规定先调研、再写作、最后并行分发 | `*.flow.yml` |
| Run | 记录每一步状态，供查看与恢复 | `.soloflow/runs/*.json` |

可以先把 Skill 理解为工作手册，把 Agent 理解为使用工作手册的员工，把 Flow 理解为项目排期。

## 第一步：准备环境

需要 Python 3.12 或 3.13，并已安装 `uv`。

安装 PyPI 正式版：

```bash
uv tool install soloflow
sf version
```

从源码体验当前开发版：

```bash
git clone https://github.com/halexzd686-cloud/SoloFlow.git
cd SoloFlow
uv sync --extra dev
uv run sf version
```

如果使用源码，把下文的 `sf` 替换为 `uv run sf`。

建议新建一个单独的练习目录，并始终在该目录执行命令。SoloFlow 会把 `.env` 和运行记录关联到当前工作目录。

## 第二步：查看已有资产

```bash
sf skill list
sf agent list
sf flow list
```

你应该能看到 `content-writer`、`content-editor` 和 `blog-pipeline`。它们分别代表写作 Skill、主编 Agent 和内容生产 Flow。

如果列表为空，先运行 `sf version` 确认安装成功；源码模式下确认当前目录是 SoloFlow 仓库根目录。

## 第三步：先 dry-run，不调用模型

### 预览一个 Skill

```bash
sf skill run content-writer "为 TrailLight Mini 露营灯写一篇新品介绍" --dry-run
```

预期会看到两类内容：

1. `content-writer` 中定义的身份、目标、语气和质量规则；
2. 你刚输入的 TrailLight Mini 写作任务。

最后显示 `[DRY RUN]`，表示没有请求 DeepSeek，也不会产生 API 费用。

### 预览一个 Agent

```bash
sf agent run content-editor "检查并优化 TrailLight Mini 新品介绍" --dry-run
```

Agent 会在 Skill 规则之外加入“资深内容主编”的人格、价值观和行为约束。需要固定角色时使用 Agent；只需要一次明确能力时，直接使用 Skill 更简单。

### 预览完整 Flow

```bash
sf flow run blog-pipeline -i topic="TrailLight Mini 露营灯" --dry-run
```

预期执行计划为：

```text
第 1 层：research
第 2 层：write
第 3 层：social-twitter + social-linkedin（并行）
```

这就是 Flow 的价值：后一步可以引用前一步输出，互不依赖的步骤可以并行运行。

## 第四步：安全配置 DeepSeek

在运行命令的当前目录创建 `.env`：

```dotenv
DEEPSEEK_API_KEY=你的实际密钥
```

如果你从源码运行，可以复制安全模板：

```powershell
Copy-Item .env.example .env
```

然后只填写 `DEEPSEEK_API_KEY`。也可以使用当前终端的临时环境变量：

```powershell
$env:DEEPSEEK_API_KEY = "你的实际密钥"
```

安全规则：

- 不要把密钥写进 `SKILL.md`、Agent 或 Flow 文件；
- 不要截图、粘贴或提交真实密钥；
- 确认 `.gitignore` 包含 `.env`；
- 如果密钥曾经公开，立即在供应商后台撤销并创建新密钥。

SoloFlow 只加载当前目录的 `.env`，不会向父目录查找，也不会覆盖 Shell 已设置的同名变量。

## 第五步：执行真实写作任务

```bash
sf skill run content-writer "为 TrailLight Mini 露营灯写一篇新品介绍。产品为虚构案例，不得补充未经提供的参数。已知信息：重量 180 克、三档亮度、USB-C 充电、面向周末露营新手。"
```

运行过程会显示 `deepseek/deepseek-v4-flash`、生成内容和 token usage。实际文字每次可能不同，但应该遵守 Skill 中的结构、语气和“不编造数据”规则。

如果提示缺少 `DEEPSEEK_API_KEY`，请确认：

1. `.env` 与执行命令时的当前目录一致；
2. 文件名确实是 `.env`，不是 `.env.txt`；
3. 等号两侧没有多余引号或空格；
4. 修改 `.env` 后重新执行命令。

## 第六步：执行完整内容流水线

```bash
sf flow run blog-pipeline -i topic="TrailLight Mini 露营灯：180 克、三档亮度、USB-C 充电，面向周末露营新手；这是虚构案例，不得编造市场数据"
```

Flow 会完成四个步骤：

1. `research`：根据已提供资料整理受众、卖点、风险和内容角度；
2. `write`：引用调研结果生成长文；
3. `social-twitter`：根据文章生成 5 条 X 文案；
4. `social-linkedin`：根据文章生成 2 条 LinkedIn 文案。

后两个步骤没有相互依赖，因此会并行执行。最终输出包含 `research`、`article`、`twitter_posts` 和 `linkedin_posts`。

`market-researcher` 没有浏览器或搜索工具。它可以组织你提供的信息，但不能自行核实市场规模、竞品销量或用户调查。生产使用时，应把可信资料一并放进输入，或后续接入外部工具。

## 第七步：查看记录与恢复失败任务

列出历史运行：

```bash
sf flow runs
```

每次运行都有类似 `run-a1b2c3d4e5f6` 的 ID，详细状态保存在：

```text
.soloflow/runs/<run-id>.json
```

若网络波动或模型暂时失败，先确认 API Key 和网络已经恢复，再执行：

```bash
sf flow resume <run-id>
```

恢复命令会读取之前的成功步骤，继续处理尚未完成的部分，而不是强制从头开始。你也可以先加 `--dry-run` 查看待恢复计划：

```bash
sf flow resume <run-id> --dry-run
```

## 第八步：把示例改成自己的流程

最直接的做法是复制内置源码资产：

```text
skills/writing/content-writer/SKILL.md
agents/content-editor.agent.yml
flows/blog-pipeline.flow.yml
```

然后修改：

- Skill 的 `context`、`objective`、`style`、`rules`；
- Agent 的 `personality`、`values`、`behavior_rules`；
- Flow 的 `steps`、`depends_on` 和 `$steps.<id>.output` 引用。

项目目录中的同名资产优先于安装包资产，因此可以定制本项目行为而不修改 Python 包。修改后先运行列表和 `--dry-run`，确认 SoloFlow 找到的是预期资产，再执行真实任务。

## 常见问题

### 为什么有 Skill 还需要 Agent？

Skill 负责“怎么做”，Agent 负责“以什么身份和原则做”。例如 `content-writer` 能写文章，`content-editor` 会额外用主编视角检查开头、结尾和 AI 味。简单任务优先用 Skill。

### 为什么 Flow 不是普通脚本？

Flow 理解步骤依赖、并行关系、输出引用和运行状态。脚本失败通常需要自行设计恢复逻辑；SoloFlow 会保存 Run，允许从断点继续。

### dry-run 为什么很重要？

它能在零 API 费用下检查资产发现、变量传递和最终 Prompt。修改 Skill 或 Flow 后，应先 dry-run，再进行真实调用。

### 能否只使用 DeepSeek？

可以。`v1.0.1` 和内置示例只支持 `deepseek/deepseek-v4-flash`，只需配置 `DEEPSEEK_API_KEY`；其他调用目标会在网络请求前被拒绝。

### 输出是否一定正确？

不一定。SoloFlow 能让流程可复用、可观察、可恢复，但不能消除模型幻觉。涉及事实、代码安全或外部决策时，仍需提供可靠上下文并进行人工复核。

## 接下来阅读什么

- [README](../README.md)：项目概览与能力边界
- [快速开始](quickstart.md)：安装、配置与常用命令速查
- [架构说明](architecture.md)：资产优先级、Flow 执行机制与信任边界
- [MCP](mcp.md)：连接外部 AI 客户端
- [项目状态](../STATUS.md)：已经验收和仍待验证的范围
