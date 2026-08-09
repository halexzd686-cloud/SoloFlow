"""MCP stdio 端到端测试（GAP-MCP-001/002）。

通过 subprocess 启动真实的 stdio server（非函数级 mock），
验证完整 JSON-RPC 交互:
- server/discover
- tools/list（含 allowlist 过滤）
- tools/call 只读工具（list_skills / validate_flow）
- auth token 拒绝/放行
"""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

SERVER_ENTRY = "from soloflow.mcp.server import run_stdio_server; run_stdio_server()"


class McpClient:
    """简单的 stdio MCP 测试客户端。"""

    def __init__(self, env: dict | None = None, cwd: str | None = None):
        full_env = os.environ.copy()
        if env:
            full_env.update(env)
        self.proc = subprocess.Popen(
            [sys.executable, "-c", SERVER_ENTRY],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=full_env,
            cwd=cwd,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._next_id = 0

    def request(
        self, method: str, params: dict | None = None, auth_token: str | None = None
    ) -> dict:
        """发送请求并等待响应（带超时保护）。"""
        self._next_id += 1
        payload = {"jsonrpc": "2.0", "id": self._next_id, "method": method}
        if params is not None:
            if auth_token is not None:
                # authToken 放在 _meta 中
                meta = params.get("_meta", {})
                meta["authToken"] = auth_token
                params = {**params, "_meta": meta}
            payload["params"] = params
        self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

        future = self._executor.submit(self.proc.stdout.readline)
        try:
            line = future.result(timeout=10)
        except Exception:
            self.proc.kill()
            raise RuntimeError("MCP server 无响应（超时）")
        if not line:
            self.proc.kill()
            raise RuntimeError("MCP server 提前退出")
        return json.loads(line)

    def close(self):
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()
        self._executor.shutdown(wait=False)


@pytest.fixture
def project_root():
    """项目根目录（含 skills/ 和 flows/）。"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_mcp_stdio_discover(project_root):
    """GAP-MCP-001: server/discover 返回协议版本与服务器信息。"""
    client = McpClient(cwd=project_root)
    try:
        resp = client.request("server/discover")
        assert resp["jsonrpc"] == "2.0"
        assert "error" not in resp
        result = resp["result"]
        assert "2026-07-28" in result["supportedVersions"]
        server_info = result["_meta"]["io.modelcontextprotocol/serverInfo"]
        assert server_info["name"] == "soloflow"
        assert server_info["version"]
    finally:
        client.close()


def test_mcp_stdio_tools_list(project_root):
    """GAP-MCP-001: tools/list 返回全部 9 个工具。"""
    client = McpClient(cwd=project_root)
    try:
        resp = client.request("tools/list")
        assert "error" not in resp
        tools = resp["result"]["tools"]
        names = [t["name"] for t in tools]
        assert len(names) == 9
        assert "soloflow_list_skills" in names
        assert "soloflow_validate_flow" in names
        assert "soloflow_run_flow" in names
    finally:
        client.close()


def test_mcp_stdio_call_readonly_tools(project_root):
    """GAP-MCP-001: 只读工具调用（list_skills / validate_flow）。"""
    client = McpClient(cwd=project_root)
    try:
        # list_skills
        resp = client.request(
            "tools/call",
            {
                "name": "soloflow_list_skills",
                "arguments": {},
            },
        )
        assert "error" not in resp
        text = resp["result"]["content"][0]["text"]
        assert "content-writer" in text

        # validate_flow（blog-pipeline 应校验通过）
        resp = client.request(
            "tools/call",
            {
                "name": "soloflow_validate_flow",
                "arguments": {"name": "blog-pipeline"},
            },
        )
        assert "error" not in resp
        text = resp["result"]["content"][0]["text"]
        assert "校验通过" in text

        # 未知工具 → 错误
        resp = client.request(
            "tools/call",
            {
                "name": "soloflow_unknown_tool",
                "arguments": {},
            },
        )
        assert "error" in resp
    finally:
        client.close()


def test_mcp_stdio_auth_token(project_root):
    """GAP-MCP-001: auth token 拒绝/放行。"""
    client = McpClient(
        cwd=project_root,
        env={"SOLOFLOW_MCP_TOKEN": "secret-token-123"},
    )
    try:
        # 不带 token → 拒绝
        resp = client.request(
            "tools/call",
            {
                "name": "soloflow_list_skills",
                "arguments": {},
            },
        )
        assert resp.get("error", {}).get("code") == -32001

        # 错误 token → 拒绝
        resp = client.request(
            "tools/call",
            {
                "name": "soloflow_list_skills",
                "arguments": {},
            },
            auth_token="wrong-token",
        )
        assert resp.get("error", {}).get("code") == -32001

        # 正确 token → 放行
        resp = client.request(
            "tools/call",
            {
                "name": "soloflow_list_skills",
                "arguments": {},
            },
            auth_token="secret-token-123",
        )
        assert "error" not in resp
    finally:
        client.close()


def test_mcp_stdio_allowlist(project_root):
    """GAP-MCP-001: 工具白名单隐藏与阻止。"""
    client = McpClient(
        cwd=project_root,
        env={"SOLOFLOW_MCP_ALLOWED_TOOLS": "soloflow_list_skills"},
    )
    try:
        # tools/list 只显示白名单工具
        resp = client.request("tools/list")
        tools = resp["result"]["tools"]
        assert len(tools) == 1
        assert tools[0]["name"] == "soloflow_list_skills"

        # 调用白名单外工具 → 拒绝
        resp = client.request(
            "tools/call",
            {
                "name": "soloflow_validate_flow",
                "arguments": {"name": "blog-pipeline"},
            },
        )
        assert resp.get("error", {}).get("code") == -32002

        # 白名单内工具 → 放行
        resp = client.request(
            "tools/call",
            {
                "name": "soloflow_list_skills",
                "arguments": {},
            },
        )
        assert "error" not in resp
    finally:
        client.close()


def test_mcp_stdio_unknown_method(project_root):
    """GAP-MCP-002: 未知方法返回 -32601。"""
    client = McpClient(cwd=project_root)
    try:
        resp = client.request("bogus/method")
        assert resp.get("error", {}).get("code") == -32601
    finally:
        client.close()
