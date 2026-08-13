# MCP Integration

SoloFlow 通过 JSON-RPC 2.0 over stdio 暴露 MCP 工具。MCP 中的工作手册仍沿用 `skill` 工具名，以兼容已经连接的客户端；返回内容和文档统一按 Playbook（工作手册）理解。

## Start the server

```bash
uv run sf mcp
```

客户端配置可以参考仓库根目录的 `mcp-config.example.json`。其中的路径和命令需要按客户端环境调整。

Claude Code 可在项目根目录注册本地连接：

```bash
claude mcp add --scope local soloflow -- uv run sf mcp
claude mcp get soloflow
```

这里的 Claude Code 仅作为 MCP 客户端连接本地 SoloFlow Server；SoloFlow 的模型调用仍固定为 `deepseek/deepseek-v4-flash`，不会因此调用其他模型供应商 API。

SoloFlow 同时支持 `initialize` / `notifications/initialized` 生命周期和新版 `server/discover`，便于不同协议代际的客户端接入。

## Tools

- `soloflow_list_skills`
- `soloflow_get_skill`
- `soloflow_run_skill`
- `soloflow_list_flows`
- `soloflow_run_flow`
- `soloflow_list_agents`
- `soloflow_run_agent`
- `soloflow_validate_skill`
- `soloflow_validate_flow`

## Security

通过以下环境变量或 `.soloflow/mcp.json` 配置安全策略：

- `SOLOFLOW_MCP_TOKEN`
- `SOLOFLOW_MCP_ALLOWED_TOOLS`

推荐为每个客户端设置非空 token，并只允许实际需要的工具。配置文件和 token 不应提交到 Git。

自动化测试覆盖 stdio 子进程、协议握手、鉴权和工具白名单。Claude Code 2.1.201 已在 Windows 11 上完成真实连接，并成功调用 `soloflow_list_skills`；Cursor 和 Codex 仍列为后续兼容性验证项。
