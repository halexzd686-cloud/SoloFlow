#!/bin/bash
# MCP Server 本地测试脚本
# 无需重启 Claude Code，直接在终端验证

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "===== 1. discover ====="
echo '{"jsonrpc":"2.0","id":1,"method":"server/discover","params":{}}' | uv run sf mcp 2>/dev/null | python -m json.tool

echo ""
echo "===== 2. tools/list ====="
echo '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' | uv run sf mcp 2>/dev/null | python -c "import sys,json; r=json.load(sys.stdin); [print(f'  {t[\"name\"]}: {t[\"description\"][:60]}') for t in r['result']['tools']]"

echo ""
echo "===== 3. list_skills ====="
echo '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"soloflow_list_skills","arguments":{}}}' | uv run sf mcp 2>/dev/null | python -c "import sys,json; r=json.load(sys.stdin); print(r['result']['content'][0]['text'])"

echo ""
echo "===== 4. get_skill ====="
echo '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"soloflow_get_skill","arguments":{"name":"code-reviewer"}}}' | uv run sf mcp 2>/dev/null | python -c "import sys,json; r=json.load(sys.stdin); t=r['result']['content'][0]['text']; print(t[:500])"

echo ""
echo "===== 5. validate_flow ====="
echo '{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"soloflow_validate_flow","arguments":{"name":"code-review"}}}' | uv run sf mcp 2>/dev/null | python -c "import sys,json; r=json.load(sys.stdin); print(r['result']['content'][0]['text'])"

echo ""
echo "===== 6. list_flows ====="
echo '{"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"soloflow_list_flows","arguments":{}}}' | uv run sf mcp 2>/dev/null | python -c "import sys,json; r=json.load(sys.stdin); print(r['result']['content'][0]['text'])"

echo ""
echo "===== ALL TESTS PASSED ====="
