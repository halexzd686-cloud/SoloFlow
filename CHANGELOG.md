# Changelog

本项目遵循 [Semantic Versioning](https://semver.org/)，版本变化按 Added、Changed、Fixed、Security 分类记录。

## Unreleased

### Added

- GitHub 开源协作文件、用户文档和 tag 驱动的 Release 工作流。
- wheel 内置 Skill、Agent、Flow 的发现与安装回归测试。

### Changed

- CI wheel smoke 改为离开源码目录验证内置资产。
- Skill、Agent、Flow 统一采用项目/用户资产优先、包内资产回退的发现顺序。

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
