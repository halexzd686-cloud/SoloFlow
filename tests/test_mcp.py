"""测试 MCP Server 协议和 Auth。"""

from soloflow.mcp.server import (
    MCP_CONFIG_PATH,
    _check_auth,
    _check_tool_allowed,
    _handle_discover,
    _handle_tools_list,
    _load_mcp_config,
    _process_request,
    _timing_safe_compare,
    save_mcp_config,
    show_mcp_config,
)

# ── 已有测试 ──


def test_discover_response():
    """测试 server/discover 返回协议信息。"""
    resp = _handle_discover(1)
    assert resp["result"]["supportedVersions"] == ["2026-07-28"]
    assert "tools" in resp["result"]["capabilities"]


def test_tools_list_response():
    """测试 tools/list 返回工具列表。"""
    resp = _handle_tools_list(2)
    tools = resp["result"]["tools"]
    assert len(tools) > 0
    names = [t["name"] for t in tools]
    assert "soloflow_list_skills" in names
    assert "soloflow_run_skill" in names


def test_tools_have_schema():
    """测试每个工具都有 inputSchema。"""
    resp = _handle_tools_list(3)
    for tool in resp["result"]["tools"]:
        assert "inputSchema" in tool
        assert "type" in tool["inputSchema"]


def test_process_discover_request():
    """测试完整的 server/discover 流程。"""
    request = {"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {}}
    resp = _process_request(request)
    assert resp is not None
    assert "result" in resp
    assert "supportedVersions" in resp["result"]


def test_process_tools_list_request():
    """测试完整的 tools/list 流程。"""
    request = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    resp = _process_request(request)
    assert resp is not None
    assert "tools" in resp["result"]


def test_process_unknown_method():
    """测试未知方法返回错误。"""
    request = {"jsonrpc": "2.0", "id": 3, "method": "unknown/method", "params": {}}
    resp = _process_request(request)
    assert resp is not None
    assert "error" in resp
    assert resp["error"]["code"] == -32601


def test_process_notification_no_response():
    """测试通知（无 id）不返回响应。"""
    request = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    resp = _process_request(request)
    assert resp is None


def test_tools_call_list_skills():
    """测试 tools/call list_skills。"""
    request = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {"name": "soloflow_list_skills", "arguments": {}},
    }
    resp = _process_request(request)
    assert resp is not None
    assert "result" in resp
    content = resp["result"]["content"]
    assert len(content) == 1
    assert content[0]["type"] == "text"


def test_tools_call_validate_flow():
    """测试 tools/call validate_flow。"""
    request = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {"name": "soloflow_validate_flow", "arguments": {"name": "blog-pipeline"}},
    }
    resp = _process_request(request)
    assert resp is not None
    assert "error" not in resp
    text = resp["result"]["content"][0]["text"]
    assert "blog-pipeline" in text


def test_tools_call_unknown_tool():
    """测试调用不存在的工具返回错误。"""
    request = {
        "jsonrpc": "2.0",
        "id": 6,
        "method": "tools/call",
        "params": {"name": "nonexistent_tool", "arguments": {}},
    }
    resp = _process_request(request)
    assert resp is not None
    assert "error" in resp


# ── 新增测试: MCP Auth / Access Control ──


def test_auth_bypass_when_no_token_configured():
    """未配置 token 时，请求正常通过。"""
    assert _check_auth({"name": "soloflow_list_skills", "arguments": {}}) is None


def test_auth_reject_missing_token(monkeypatch):
    """配置了 token 但请求未提供时拒绝。"""
    monkeypatch.setattr("soloflow.mcp.server._get_auth_token", lambda: "secret-token-123")
    error = _check_auth({"name": "test", "arguments": {}})
    assert error is not None
    assert "Access denied" in error


def test_auth_reject_wrong_token(monkeypatch):
    """提供了错误 token 时拒绝。"""
    monkeypatch.setattr("soloflow.mcp.server._get_auth_token", lambda: "correct-token")
    error = _check_auth({"name": "test", "arguments": {}, "_meta": {"authToken": "wrong-token"}})
    assert error is not None
    assert "invalid" in error.lower()


def test_auth_accept_correct_token(monkeypatch):
    """提供了正确 token 时通过。"""
    monkeypatch.setattr("soloflow.mcp.server._get_auth_token", lambda: "my-secret")
    error = _check_auth({"name": "test", "arguments": {}, "_meta": {"authToken": "my-secret"}})
    assert error is None


def test_tool_allowlist_bypass_when_not_configured(monkeypatch):
    """未配置白名单时所有工具允许。"""
    monkeypatch.setattr("soloflow.mcp.server._get_allowed_tools", lambda: None)
    assert _check_tool_allowed("soloflow_run_skill") is None
    assert _check_tool_allowed("any_random_tool") is None


def test_tool_allowlist_block(monkeypatch):
    """白名单中不存在的工具被拒绝。"""
    monkeypatch.setattr(
        "soloflow.mcp.server._get_allowed_tools",
        lambda: ["soloflow_list_skills", "soloflow_get_skill"],
    )
    assert _check_tool_allowed("soloflow_list_skills") is None
    assert _check_tool_allowed("soloflow_run_skill") is not None


def test_mcp_config_save_and_load():
    """测试保存和加载 MCP 配置。"""
    path = save_mcp_config(auth_token="test-token-abc", allowed_tools=["soloflow_list_skills"])
    assert path == MCP_CONFIG_PATH
    assert MCP_CONFIG_PATH.exists()

    config = _load_mcp_config()
    assert config.get("auth_token") == "test-token-abc"
    assert config.get("allowed_tools") == ["soloflow_list_skills"]

    MCP_CONFIG_PATH.unlink()


def test_mcp_config_show():
    """测试 config show 不崩溃。"""
    config = show_mcp_config()
    assert "auth_enabled" in config
    assert "allowed_tools" in config
    assert "total_tools" in config


def test_timing_safe_compare():
    """测试 timing-safe 字符串比较。"""
    assert _timing_safe_compare("abc", "abc") is True
    assert _timing_safe_compare("abc", "abd") is False
    assert _timing_safe_compare("abc", "ab") is False
    assert _timing_safe_compare("", "") is True
