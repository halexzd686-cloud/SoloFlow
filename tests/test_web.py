"""本地网页 P0 入口测试。"""

import json
import threading
from urllib.request import Request, urlopen

from soloflow.web import create_server


def test_web_home_and_health(tmp_path):
    server = create_server(tmp_path, port=0)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        with urlopen(f"http://127.0.0.1:{server.server_port}/") as response:
            body = response.read().decode("utf-8")
            assert response.status == 200
            assert "把重复工作，变成自己的工作助手" in body

        with urlopen(f"http://127.0.0.1:{server.server_port}/api/health") as response:
            assert json.loads(response.read()) == {"status": "ok", "service": "soloflow-web"}
    finally:
        server.shutdown()
        server_thread.join(timeout=2)
        server.server_close()


def test_web_settings_save_key_and_model(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    server = create_server(tmp_path, port=0)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        payload = json.dumps({"api_key": "test-key", "default_model": "deepseek-reasoner"}).encode()
        request = Request(
            f"http://127.0.0.1:{server.server_port}/api/settings",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request) as response:
            result = json.loads(response.read())
            assert response.status == 200
            assert result == {"api_key_configured": True, "default_model": "deepseek-reasoner"}

        assert (tmp_path / ".env").read_text(encoding="utf-8") == "DEEPSEEK_API_KEY=test-key\n"
        settings = json.loads(
            (tmp_path / ".soloflow/config/settings.json").read_text(encoding="utf-8")
        )
        assert settings == {"default_model": "deepseek-reasoner"}
    finally:
        server.shutdown()
        server_thread.join(timeout=2)
        server.server_close()
