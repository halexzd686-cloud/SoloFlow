# Security Policy

## 支持范围

安全修复优先应用于最新稳定版和 `main`。旧的 Release Candidate 与开发标签不保证持续维护。

## 私下报告漏洞

请不要为尚未修复的漏洞创建公开 Issue。优先使用 GitHub 仓库的 **Security → Report a vulnerability** 私下提交报告。

报告中请包括：

- 受影响版本或 commit；
- 复现步骤或最小示例；
- 潜在影响；
- 已知缓解方法；
- 是否涉及工作手册内容、MCP 鉴权、路径处理或凭据泄露。

维护者确认问题后会协调修复和披露时间。

## 凭据与不受信任内容

- API Key 只能通过环境变量或本机秘密管理提供。
- 不要把 `.env`、MCP token、真实运行记录或第三方凭据提交到仓库。
- 从第三方来源获取工作手册前应审查其内容；当前版本尚未提供签名和 checksum 验证。
- MCP 客户端应启用 auth token 和最小工具白名单。
