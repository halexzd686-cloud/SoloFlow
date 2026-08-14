# SoloFlow

<p align="center">
  <strong>把你反复做的工作，变成一个可以重复使用的工作助手。</strong>
</p>

<p align="center">
  SoloFlow 面向不懂 AI、Agent 和 Vibe Coding 的普通公司员工。<br>
  你只需要说清楚要做什么，或者直接上传手上的材料，SoloFlow 会帮你整理成固定的方法。
</p>

<p align="center">
  <a href="#最快开始">最快开始</a> ·
  <a href="#第一次怎么用">第一次怎么用</a> ·
  <a href="#它能帮你做什么">它能帮你做什么</a> ·
  <a href="#数据和隐私">数据和隐私</a>
</p>

[![CI](https://github.com/halexzd686-cloud/SoloFlow/actions/workflows/ci.yml/badge.svg)](https://github.com/halexzd686-cloud/SoloFlow/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/soloflow.svg)](https://pypi.org/project/soloflow/)
[![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## SoloFlow 是什么

很多工作并不是每次都完全不同：周报、会议纪要、销售跟进、数据汇总、内容整理，通常都有相似的步骤和格式。

SoloFlow 的作用是：

1. 你用自己的话描述一项重复工作，或者上传一份现有文件。
2. SoloFlow 把你的说法整理成一套工作方法，交给你检查和修改。
3. 方法保存后，下次只要补充本次材料，就可以再次生成结果。

它不是一个需要你学习复杂概念的聊天机器人，而是一个可以反复使用的本地工作台。

## 它能帮你做什么

| 工作场景 | 你可以让 SoloFlow 做什么 |
| --- | --- |
| 周报和月报 | 按“完成、未完成、问题、下一步”整理成固定格式 |
| 会议纪要 | 提取结论、待办事项、负责人和截止时间 |
| 销售跟进 | 把零散的客户记录整理成跟进汇报 |
| 表格汇总 | 汇总多份 Excel 或 CSV，并标出关键数字和异常 |
| 内容整理 | 把 Word、PDF 或文本材料整理成报告、简报或说明 |
| 其他重复工作 | 根据你自己的流程，定制专属的工作助手 |

你不需要先找到对应的模板。直接告诉它“我平时是怎么做的”，之后再逐步修改就可以。

## 最快开始

### 你需要准备什么

- Python 3.12 或更高版本
- 一个 [DeepSeek API Key](https://platform.deepseek.com/)
- Windows、macOS 或 Linux 电脑

### 启动本地网页

在终端复制运行：

```bash
python -m pip install uv
uvx soloflow web
```

然后打开：

```text
http://127.0.0.1:8765/
```

如果你已经把 SoloFlow 安装到当前 Python 环境，也可以运行：

```bash
sf web
```

如果你是在项目源码目录中开发，可以运行：

```bash
uv run sf web
```

### 配置 DeepSeek

打开网页右上角的“设置 DeepSeek”：

1. 填入你的 DeepSeek API Key。
2. 选择默认模型，首次使用可以保留推荐模型。
3. 点击保存。

API Key 只保存在当前电脑的项目配置中，不会写入工作助手分享文件。

## 第一次怎么用

### 第一步：告诉 SoloFlow 你想重复什么工作

在“我想让 SoloFlow 帮我……”输入框中，用平时说话的方式描述。例如：

```text
我每周都要整理客户跟进记录，按照客户、当前进展、下一步行动和需要协助的问题，输出一份适合给领导看的销售跟进汇报，语气简洁，不要补充原文没有的信息。
```

如果你暂时不知道怎么描述，也可以点击“周报整理”“会议纪要”“表格汇总”或“销售跟进”开始修改示例。

你也可以点击“添加材料”，上传 Word、Excel、PDF 或文本文件，让 SoloFlow 根据材料内容帮你推荐一套工作方法。

### 第二步：检查并修改方法

点击“定制我的Work伙伴”后，SoloFlow 会先生成一份工作助手草稿。请检查：

- 助手名称是否容易理解
- 工作目标和步骤是否符合你的实际做法
- 注意事项是否完整
- 最终输出格式是否符合公司的要求

确认无误后，再保存为自己的工作助手。以后不需要重新解释整套方法。

### 第三步：补充本次材料并生成结果

在“我的工作助手”中选择刚刚保存的助手：

1. 填写这一次要处理的内容。
2. 如有需要，上传本次的 Word、Excel、PDF 或文本文件。
3. 选择本次使用的 DeepSeek 模型。
4. 选择结果格式，例如 Markdown、Word、Excel 或 PDF。
5. 检查隐私提示并确认发送。
6. 生成结果后，单独下载文件，或下载 ZIP 压缩包。

### 一个可以直接试用的例子

第一次可以使用下面这段虚构内容，不需要上传真实业务文件：

```text
本周完成：整理三份客户资料，完成一次产品介绍培训。
未完成：周报排版还没有完成。
问题：暂无。
下周计划：完成周报排版并复盘培训反馈。
```

## 数据和隐私

SoloFlow 默认采用“本地保存、必要内容发送给模型”的方式：

- 工作助手、运行记录和生成文件保存在当前项目本机的 `.soloflow/` 目录。
- 你输入的描述、上传的材料和本次运行内容，会发送给你选择的 DeepSeek 模型。
- 每次定制或运行前，网页都会提示你检查内容是否敏感，由你决定是否发送。
- API Key 只保存在本机，不会随工作助手导出给同事。
- 导出的 `.sfassistant` 文件只包含工作方法和版本信息，不包含 API Key、原始材料、运行记录和生成文件。
- 使用真实客户、财务、人事或内部资料前，请先确认公司的数据合规要求。

真实请求可能产生 DeepSeek API 费用。建议第一次先使用虚构内容测试流程。

## 当前支持范围

当前网页端支持：

- DeepSeek 最新可用的 v4 系列模型
- Word、Excel、CSV、PDF 和文本文件
- Markdown、Word、Excel、PDF 结果
- 多个结果文件的单独下载和 ZIP 打包下载
- 工作助手的本地保存、版本迭代、导出和导入

当前暂不支持：

- 扫描件 OCR
- 图片直接上传（等待支持视觉输入的模型）
- 其他模型供应商
- 自动搜索网页、调用浏览器或自动读取电脑中的其他文件
- 账号、套餐和云端协作

## 常见问题

### Workbuddy 或普通聊天工具也能写周报，为什么还要用 SoloFlow？

Workbuddy 更适合临时提出一个问题并得到一次回答。SoloFlow 更适合把你认可的工作方法保存下来：下周只需要补充新材料，不需要重新解释格式、步骤和注意事项。

### 我不懂 AI，可以使用吗？

可以。你不需要会写 Prompt，也不需要理解 Agent、Skill 或 Flow。直接描述“我平时怎么做”，剩下的步骤由网页引导完成。

### 可以把工作助手发给同事吗？

可以。在“我的工作助手”中导出 `.sfassistant` 文件，同事导入后会得到新的个人副本。双方的 API Key、材料和运行记录不会一起分享。

### 生成的结果可以直接交付吗？

建议人工检查。SoloFlow 会按你确认的方法生成结果，但模型仍可能理解错误或遗漏信息，涉及客户、财务、发布和管理决策的内容尤其需要复核。

## 进阶能力

如果你是开发者，或希望把 SoloFlow 接入自己的自动化流程，可以继续使用命令行、工作手册、Agent、Flow 和 MCP 能力：

```bash
uv sync
uv run sf --help
uv run pytest
uv build
```

相关文档：

- [项目状态](STATUS.md)
- [架构说明](docs/architecture.md)
- [MCP 集成](docs/mcp.md)
- [产品需求说明](docs/product-requirements.md)
- [贡献指南](CONTRIBUTING.md)
- [版本记录](CHANGELOG.md)

## License

[MIT License](LICENSE)
