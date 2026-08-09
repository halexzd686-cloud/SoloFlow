"""SoloFlow MCP Server — JSON-RPC 2.0 over stdio。

让 Claude Code、Cursor、VS Code 等支持 MCP 的 AI 工具直接调用 SoloFlow。

协议版本: 2026-07-28
传输层: stdio (标准输入输出)

Auth/安全:
- 配置文件 .soloflow/mcp.json (auth_token + allowed_tools)
- 环境变量 SOLOFLOW_MCP_TOKEN / SOLOFLOW_MCP_ALLOWED_TOOLS
- allowed_tools: 工具白名单，未配置则允许所有工具
- auth_token: 若配置，客户端必须在 tools/call 的 _meta.authToken 中提供
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = "2026-07-28"
SERVER_NAME = "soloflow"
SERVER_VERSION = __import__("soloflow").__version__

MCP_CONFIG_PATH = Path(".soloflow/mcp.json")


# ── Auth / Access Control ──


def _load_mcp_config() -> dict:
    """加载 MCP 配置文件。"""
    if MCP_CONFIG_PATH.exists():
        try:
            return json.loads(MCP_CONFIG_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def _get_auth_token() -> str | None:
    """获取配置的 auth token（文件 > 环境变量）。"""
    token = os.environ.get("SOLOFLOW_MCP_TOKEN", "")
    if token:
        return token
    config = _load_mcp_config()
    return config.get("auth_token", "") or None


def _get_allowed_tools() -> list[str] | None:
    """获取允许的工具列表（文件 > 环境变量）。None 表示全部允许。"""
    env_val = os.environ.get("SOLOFLOW_MCP_ALLOWED_TOOLS", "")
    if env_val:
        return [t.strip() for t in env_val.split(",") if t.strip()]

    config = _load_mcp_config()
    tools = config.get("allowed_tools", [])
    if tools:
        return tools
    return None  # None = 全部允许


def _check_auth(params: dict) -> str | None:
    """检查请求的认证信息。

    Returns:
        None 表示通过，否则返回错误消息字符串。
    """
    token = _get_auth_token()
    if not token:
        return None  # 未配置 token，放行

    # MCP 协议中 auth 通常在 _meta.authToken
    meta = params.get("_meta", {})
    provided = meta.get("authToken", "")

    if not provided:
        return "Access denied: auth_token required. Set _meta.authToken in tools/call params."

    # 简单 timing-safe 比较
    if not _timing_safe_compare(provided, token):
        return "Access denied: invalid auth_token."

    return None


def _check_tool_allowed(tool_name: str) -> str | None:
    """检查工具是否在白名单中。

    Returns:
        None 表示通过，否则返回错误消息字符串。
    """
    allowed = _get_allowed_tools()
    if allowed is None:
        return None  # 无白名单，全部允许

    if tool_name in allowed:
        return None

    return f"Access denied: tool '{tool_name}' is not in allowed_tools."


def _timing_safe_compare(a: str, b: str) -> bool:
    """简单 timing-safe 字符串比较。"""
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b):
        result |= ord(x) ^ ord(y)
    return result == 0


def save_mcp_config(auth_token: str = "", allowed_tools: list[str] = None) -> Path:
    """保存 MCP 配置到 .soloflow/mcp.json。

    Args:
        auth_token: 认证 token（空字符串表示不设置）。
        allowed_tools: 工具白名单列表（None 表示不限制）。

    Returns:
        配置文件路径。
    """
    MCP_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    config = {}

    if auth_token:
        config["auth_token"] = auth_token
    if allowed_tools:
        config["allowed_tools"] = allowed_tools

    MCP_CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return MCP_CONFIG_PATH


def show_mcp_config() -> dict:
    """返回当前 MCP 配置摘要（不含完整 token）。"""
    token = _get_auth_token()
    tools = _get_allowed_tools()

    return {
        "config_file": str(MCP_CONFIG_PATH),
        "config_exists": MCP_CONFIG_PATH.exists(),
        "auth_enabled": bool(token),
        "auth_token_masked": (token[:8] + "..." if token and len(token) > 8 else "***")
        if token
        else None,
        "allowed_tools": tools,  # None = 全部允许
        "total_tools": len(TOOLS),
    }


# ── Tool 定义 ──

TOOLS = [
    {
        "name": "soloflow_list_skills",
        "title": "List Skills",
        "description": "列出所有可用的 SoloFlow Skill。返回 Skill 名称、版本、描述。",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "soloflow_get_skill",
        "title": "Get Skill",
        "description": "获取一个 Skill 的完整定义——包括 CoSTAR 背景、目标、风格、语气、受众、规则、示例和 Instructions 正文。当你需要了解某个 Skill 的详细内容时使用。",  # noqa: E501
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Skill 名称，如 content-writer、code-reviewer、market-researcher",  # noqa: E501
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "soloflow_run_skill",
        "title": "Run Skill",
        "description": "使用指定的 Skill 执行一个任务。Skill 会按照其定义的 CoSTAR 框架和规则来指导 AI 输出。支持抽卡模式（一次生成多个版本）。",  # noqa: E501
        "inputSchema": {
            "type": "object",
            "properties": {
                "skill": {
                    "type": "string",
                    "description": "Skill 名称，如 content-writer",
                },
                "task": {
                    "type": "string",
                    "description": "要执行的任务描述",
                },
                "count": {
                    "type": "integer",
                    "description": "生成几个版本（抽卡模式），默认 1",
                    "default": 1,
                },
            },
            "required": ["skill", "task"],
        },
    },
    {
        "name": "soloflow_list_flows",
        "title": "List Flows",
        "description": "列出所有可用的 SoloFlow Flow 工作流。返回 Flow 名称、版本、步骤数、描述。",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "soloflow_run_flow",
        "title": "Run Flow",
        "description": "执行一个 Flow 工作流。Flow 会按照 DAG 编排自动执行多个步骤——并行步骤同时运行，串行步骤按序运行。支持 dry_run 预览。",  # noqa: E501
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Flow 名称，如 blog-pipeline、code-review",
                },
                "inputs": {
                    "type": "object",
                    "description": '输入参数，key-value 形式，如 {"topic": "AI Agent"}',
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "仅预览执行计划，不实际调用 LLM",
                    "default": False,
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "soloflow_list_agents",
        "title": "List Agents",
        "description": "列出所有可用的 SoloFlow Agent 智能体。返回 Agent 名称、描述、绑定的 Skill、性格设定。",  # noqa: E501
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "soloflow_run_agent",
        "title": "Run Agent",
        "description": "让一个 Agent 执行任务。Agent 会加载其绑定的所有 Skill，注入角色设定，然后执行任务。",  # noqa: E501
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent": {
                    "type": "string",
                    "description": "Agent 名称",
                },
                "task": {
                    "type": "string",
                    "description": "要执行的任务描述",
                },
            },
            "required": ["agent", "task"],
        },
    },
    {
        "name": "soloflow_validate_skill",
        "title": "Validate Skill",
        "description": "校验一个 Skill 文件的格式完整性。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Skill 名称",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "soloflow_validate_flow",
        "title": "Validate Flow",
        "description": "校验一个 Flow 文件——检查 DAG 结构、循环依赖、步骤引用。返回校验结果和拓扑层级。",  # noqa: E501
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Flow 名称",
                },
            },
            "required": ["name"],
        },
    },
]


# ── JSON-RPC 消息处理 ──


def _build_response(request_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _build_error(request_id: Any, code: int, message: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _handle_discover(request_id: Any) -> dict:
    """server/discover —— 返回服务器能力和协议版本。"""
    return _build_response(
        request_id,
        {
            "resultType": "complete",
            "supportedVersions": [PROTOCOL_VERSION],
            "capabilities": {
                "tools": {},
            },
            "_meta": {
                "io.modelcontextprotocol/serverInfo": {
                    "name": SERVER_NAME,
                    "version": SERVER_VERSION,
                },
            },
            "ttlMs": 3600000,
            "cacheScope": "public",
        },
    )


def _handle_initialize(request_id: Any, params: dict) -> dict:
    """兼容仍使用 initialize 生命周期的 MCP 客户端。

    MCP 2026-07-28 已改用无状态发现，但 Claude Code 等客户端仍可能
    使用旧版 initialize/initialized 握手。基础 tools 能力在这些协议版本
    间兼容，因此回显客户端请求的协议版本并声明 tools 能力。
    """
    requested_version = params.get("protocolVersion")
    negotiated_version = (
        requested_version
        if isinstance(requested_version, str) and requested_version
        else PROTOCOL_VERSION
    )
    return _build_response(
        request_id,
        {
            "protocolVersion": negotiated_version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {
                "name": SERVER_NAME,
                "title": "SoloFlow",
                "version": SERVER_VERSION,
            },
            "instructions": (
                "Use SoloFlow tools to inspect, validate, and run Skills, Agents, and Flows."
            ),
        },
    )


def _handle_tools_list(request_id: Any) -> dict:
    """tools/list —— 返回可用工具列表（受 allowed_tools 限制）。"""
    allowed = _get_allowed_tools()
    if allowed is not None:
        visible_tools = [t for t in TOOLS if t["name"] in allowed]
    else:
        visible_tools = TOOLS

    return _build_response(
        request_id,
        {
            "resultType": "complete",
            "tools": visible_tools,
            "ttlMs": 300000,
            "cacheScope": "public",
        },
    )


def _handle_tools_call(request_id: Any, params: dict) -> dict:
    """tools/call —— 执行指定工具（含 auth 检查）。"""
    tool_name = params.get("name", "")
    arguments = params.get("arguments", {})

    # ── Auth 检查 ──
    auth_error = _check_auth(params)
    if auth_error:
        return _build_error(request_id, -32001, auth_error)

    # ── 工具白名单检查 ──
    allow_error = _check_tool_allowed(tool_name)
    if allow_error:
        return _build_error(request_id, -32002, allow_error)

    try:
        result = _execute_tool(tool_name, arguments)
        return _build_response(
            request_id,
            {
                "resultType": "complete",
                "content": [{"type": "text", "text": result}],
            },
        )
    except ValueError as e:
        return _build_error(request_id, -32602, str(e))
    except Exception as e:
        return _build_error(request_id, -32603, f"Tool execution failed: {e}")


# ── Tool 执行分发 ──


def _execute_tool(name: str, args: dict) -> str:
    """根据 tool name 分发到对应的处理函数。"""
    tool_map = {
        "soloflow_list_skills": _tool_list_skills,
        "soloflow_get_skill": _tool_get_skill,
        "soloflow_run_skill": _tool_run_skill,
        "soloflow_list_flows": _tool_list_flows,
        "soloflow_run_flow": _tool_run_flow,
        "soloflow_list_agents": _tool_list_agents,
        "soloflow_run_agent": _tool_run_agent,
        "soloflow_validate_skill": _tool_validate_skill,
        "soloflow_validate_flow": _tool_validate_flow,
    }

    handler = tool_map.get(name)
    if handler is None:
        raise ValueError(f"Unknown tool: {name}")
    return handler(args)


# ── 各 Tool 实现 ──


def _tool_list_skills(args: dict) -> str:
    """列出所有 Skill。"""
    from soloflow.core.skill_loader import list_available_skills

    skills = list_available_skills()
    if not skills:
        return "没有找到任何 Skill。用 sf skill init <name> 创建一个。"

    lines = [f"共 {len(skills)} 个 Skill:\n"]
    for s in skills:
        lines.append(
            f"- **{s['name']}** v{s.get('version', '?')}: {s.get('description', '无描述')[:80]}"
        )
    return "\n".join(lines)


def _tool_get_skill(args: dict) -> str:
    """获取 Skill 完整详情。"""
    name = args["name"]
    from soloflow.core.skill_loader import find_skill, load_skill

    skill_path = find_skill(name)
    skill = load_skill(skill_path)

    lines = [
        f"# {skill.meta.name} v{skill.meta.version}",
        "",
        f"**描述**: {skill.meta.description}",
        f"**作者**: {skill.meta.author}",
        f"**标签**: {', '.join(skill.meta.tags) if skill.meta.tags else '无'}",
        "",
    ]

    # CoSTAR
    if skill.costar.context:
        lines.append(f"## Context（背景）\n{skill.costar.context}\n")
    if skill.costar.objective:
        lines.append(f"## Objective（目标）\n{skill.costar.objective}\n")
    if skill.costar.style:
        lines.append(f"## Style（风格）\n{skill.costar.style}\n")
    if skill.costar.tone:
        lines.append(f"## Tone（语气）\n{skill.costar.tone}\n")
    if skill.costar.audience:
        lines.append(f"## Audience（受众）\n{skill.costar.audience}\n")

    # Rules
    if skill.rules:
        lines.append("## Rules（规则）")
        for r in skill.rules:
            lines.append(f"- {r}")
        lines.append("")

    # Body
    lines.append(f"## Instructions\n{skill.body}")

    # Config
    lines.append(
        f"\n---\n**LLM 配置**: model={skill.config.model}, "
        f"provider={skill.config.provider}, "
        f"temperature={skill.config.temperature}, "
        f"max_tokens={skill.config.max_tokens}"
    )

    return "\n".join(lines)


def _tool_run_skill(args: dict) -> str:
    """执行 Skill。"""
    skill_name = args["skill"]
    task = args["task"]

    from soloflow.core.skill_loader import find_skill, load_skill

    skill_path = find_skill(skill_name)
    skill = load_skill(skill_path)

    # 通过 runner 执行（它处理 prompt 拼接和 LLM 调用）
    # 但是 runner.run_skill 的接口不同，直接使用 call_llm
    from soloflow.llm.client import call_llm

    full_prompt = f"{skill.full_prompt}\n\n---\n\n# Task\n\n{task}"
    try:
        result = call_llm(
            prompt=full_prompt,
            model=skill.config.model,
            provider=skill.config.provider,
            temperature=skill.config.temperature,
            max_tokens=skill.config.max_tokens,
        )
        return result
    except RuntimeError as e:
        return f"执行失败: {e}\n请设置当前 Skill 供应商对应的 API Key 环境变量。"


def _tool_list_flows(args: dict) -> str:
    """列出所有 Flow。"""
    flows_dir = Path("flows")
    if not flows_dir.is_dir():
        return "没有找到任何 Flow。用 sf flow init <name> 创建一个。"

    from soloflow.core.flow_engine import load_flow

    lines = []
    flow_files = sorted(flows_dir.glob("*.flow.y*ml"))
    lines.append(f"共 {len(flow_files)} 个 Flow:\n")

    for f in flow_files:
        try:
            flow = load_flow(f)
            lines.append(
                f"- **{flow.name}** v{flow.version}: "
                f"{flow.description[:80] if flow.description else '无描述'} "
                f"({len(flow.steps)} 步)"
            )
        except Exception:
            lines.append(f"- {f.stem}: 解析失败")

    return "\n".join(lines)


def _tool_run_flow(args: dict) -> str:
    """执行 Flow。"""
    name = args["name"]
    inputs = args.get("inputs", {})
    dry_run = args.get("dry_run", False)

    from soloflow.core.flow_engine import load_flow, run_flow

    flow_path = Path("flows") / f"{name}.flow.yml"
    if not flow_path.exists():
        return f"Flow 不存在: {name}"

    flow = load_flow(flow_path)
    result = run_flow(flow, inputs=inputs, dry_run=dry_run)

    if dry_run:
        return f"Dry run 完成。Flow '{name}' 共 {len(flow.steps)} 步。"

    # 汇总结果
    done = sum(1 for sr in result.steps.values() if sr.status == "done")
    failed = sum(1 for sr in result.steps.values() if sr.status == "failed")
    skipped = sum(1 for sr in result.steps.values() if sr.status == "skipped")

    lines = [
        f"Flow '{name}' 执行完成:",
        f"- 状态: {result.status}",
        f"- 完成: {done}, 失败: {failed}, 跳过: {skipped}",
        f"- 总耗时: {result.total_duration:.1f}s",
        "",
    ]

    for sid, sr in result.steps.items():
        status_icon = "✓" if sr.status == "done" else "✗" if sr.status == "failed" else "○"
        lines.append(f"{status_icon} **{sid}**: {sr.status} ({sr.duration:.1f}s)")
        if sr.output:
            # 截取前 500 字符
            preview = sr.output[:500]
            lines.append(f"  {preview}{'...' if len(sr.output) > 500 else ''}")
        if sr.error:
            lines.append(f"  Error: {sr.error}")

    return "\n".join(lines)


def _tool_list_agents(args: dict) -> str:
    """列出所有 Agent。"""
    agents_dir = Path(".soloflow/agents")
    if not agents_dir.is_dir():
        return "没有找到任何 Agent。用 sf agent create <name> 创建一个。"

    import yaml

    lines = []
    agent_files = sorted(agents_dir.glob("*.agent.y*ml"))
    lines.append(f"共 {len(agent_files)} 个 Agent:\n")

    for f in agent_files:
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
            name = data.get("name", f.stem.replace(".agent", ""))
            desc = data.get("description", "无描述")
            skills = ", ".join(data.get("skills", [])) or "无"
            personality = data.get("soul", {}).get("personality", "")[:60]
            lines.append(f"- **{name}**: {desc[:60]}")
            lines.append(f"  Skills: {skills}")
            if personality:
                lines.append(f"  性格: {personality}")
        except Exception:
            lines.append(f"- {f.stem}: 解析失败")

    return "\n".join(lines)


def _tool_run_agent(args: dict) -> str:
    """执行 Agent。"""
    agent_name = args["agent"]
    task = args["task"]

    import yaml

    from soloflow.core.agent_runner import run_agent
    from soloflow.models.agent import AgentDefinition

    # 加载 Agent 定义
    search_paths = [
        Path(f"{agent_name}.agent.yml"),
        Path(f"{agent_name}.agent.yaml"),
        Path(".soloflow/agents") / f"{agent_name}.agent.yml",
        Path(".soloflow/agents") / f"{agent_name}.agent.yaml",
    ]
    agent = None
    for p in search_paths:
        if p.exists():
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
            agent = AgentDefinition(**data)
            break

    if agent is None:
        return f"Agent 不存在: {agent_name}"

    results = run_agent(agent, task)
    if not results:
        return "Agent 执行失败——可能缺少绑定的 Skill 或 API Key。"

    return results[0]


def _tool_validate_skill(args: dict) -> str:
    """校验 Skill。"""
    name = args["name"]
    from soloflow.core.skill_loader import find_skill, load_skill, validate_skill

    skill_path = find_skill(name)
    skill = load_skill(skill_path)
    issues = validate_skill(skill)

    if not issues:
        return f"✓ Skill '{skill.meta.name}' v{skill.meta.version} 校验通过。"
    return f"Skill '{skill.meta.name}' 校验发现 {len(issues)} 个问题:\n" + "\n".join(
        f"- {i}" for i in issues
    )


def _tool_validate_flow(args: dict) -> str:
    """校验 Flow。"""
    name = args["name"]
    from soloflow.core.flow_engine import _topological_sort, load_flow, validate_flow

    flow_path = Path("flows") / f"{name}.flow.yml"
    if not flow_path.exists():
        return f"Flow 文件不存在: {flow_path}"

    flow = load_flow(flow_path)
    issues = validate_flow(flow)

    if issues:
        return f"Flow '{flow.name}' 校验失败:\n" + "\n".join(f"- {i}" for i in issues)

    levels = _topological_sort(flow.steps)
    level_desc = "\n".join(f"  Level {i}: {' | '.join(level)}" for i, level in enumerate(levels, 1))
    return f"✓ Flow '{flow.name}' v{flow.version} 校验通过。\n{len(flow.steps)} 步, {len(levels)} 层:\n{level_desc}"  # noqa: E501


# ── 主循环 ──


def run_stdio_server():
    """通过 stdio 运行 MCP 服务器（同步、跨平台）。

    从 stdin 逐行读取 JSON-RPC 请求，处理后写入 stdout。
    MCP 客户端发送每行一个 JSON 消息，这是最可靠的跨平台 stdio 传输方式。
    """
    # 确保 stdout 使用 UTF-8
    sys.stdout.reconfigure(encoding="utf-8")

    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break  # EOF

            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                continue

            response = _process_request(request)
            if response is not None:
                resp_str = json.dumps(response, ensure_ascii=False)
                sys.stdout.write(resp_str + "\n")
                sys.stdout.flush()

        except KeyboardInterrupt:
            break
        except Exception as e:
            error_resp = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32603, "message": str(e)},
                },
                ensure_ascii=False,
            )
            sys.stdout.write(error_resp + "\n")
            sys.stdout.flush()


def _process_request(request: dict) -> dict | None:
    """处理单个 JSON-RPC 请求，返回响应或 None（通知不响应）。"""
    req_id = request.get("id")
    method = request.get("method", "")
    params = request.get("params", {})

    # 通知（无 id）不响应
    if req_id is None:
        return None

    if method == "initialize":
        return _handle_initialize(req_id, params)
    elif method == "server/discover":
        return _handle_discover(req_id)
    elif method == "ping":
        return _build_response(req_id, {})
    elif method == "tools/list":
        return _handle_tools_list(req_id)
    elif method == "tools/call":
        return _handle_tools_call(req_id, params)
    else:
        return _build_error(req_id, -32601, f"Method not found: {method}")
