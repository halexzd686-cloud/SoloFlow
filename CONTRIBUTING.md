# Contributing to SoloFlow

感谢你帮助改进 SoloFlow。请先搜索已有 Issue，较大的功能或行为变更建议先开 Issue 讨论。

## 开发环境

要求 Python 3.12 或 3.13，并推荐使用 uv：

```bash
git clone https://github.com/halexzd686-cloud/SoloFlow.git
cd SoloFlow
uv sync --extra dev
uv run pytest -q
```

## 工作方式

1. 从最新 `main` 创建短期分支，例如 `fix/flow-resume` 或 `docs/mcp-setup`。
2. 每个提交只解决一个清晰问题，并使用 `feat:`、`fix:`、`docs:`、`test:`、`refactor:`、`chore:` 等前缀。
3. 行为修改必须增加或更新回归测试。
4. 不要把 API Key、`.env`、运行记录、虚拟环境或构建产物提交到仓库。
5. 提交 Pull Request 前运行全部本地门禁。

## 本地门禁

```bash
uv run ruff check soloflow tests
uv run ruff format --check soloflow tests
uv run pytest -q
uv build
```

如果修改资产发现或打包逻辑，还应在源码目录外的新虚拟环境安装 wheel，并验证：

```bash
sf skill show content-writer --json
sf agent show content-editor --json
sf flow run blog-pipeline --dry-run -i topic=test
```

## Pull Request 要求

- 说明问题、方案和用户可见变化。
- 列出实际运行的测试命令和结果。
- 区分 mock、本地 E2E 和真实外部服务验证。
- 更新 README、CHANGELOG 或相关文档。
- 保持兼容现有 Skill、Agent、Flow 和运行记录，或明确标注 breaking change。

维护者会关注正确性、跨平台行为、安全边界、向后兼容和文档准确性。
