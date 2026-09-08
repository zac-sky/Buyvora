"""Verify the real HTTP stack against a protocol fixture or a configured live model.

Default mode uses a local scripted server. It does not test model intelligence.
Use --live only after configuring the user's intended model in .env/environment.
"""

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class ProtocolFixture(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        messages = body["messages"]
        if messages[-1]["role"] == "tool":
            result = json.loads(messages[-1]["content"])
            assert result["ok"] and result["source"] == "demo"
            names = "、".join(item["name"] for item in result["items"])
            message = {"role": "assistant", "content": f"演示商品：{names}。"}
            reason = "stop"
        else:
            users = [m for m in messages if m["role"] == "user"]
            if len(users) > 1:
                assert any(m["role"] == "tool" for m in messages[:-1])
            budget = 200 if len(users) > 1 else 300
            message = {"role": "assistant", "content": None, "tool_calls": [{
                "id": f"search-{len(users)}", "type": "function", "function": {
                    "name": "search_products", "arguments": json.dumps({"q": "耳机", "max_price": budget})}}]}
            reason = "tool_calls"
        payload = json.dumps({"choices": [{"finish_reason": reason, "message": message}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def http_json(base, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(base + path, data=data, headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=180) as response:
            return json.load(response)
    except HTTPError as error:
        # Only emit the application's sanitized code, never provider bodies or credentials.
        try:
            code = json.load(error).get("detail", {}).get("code", "http_error")
        except (ValueError, AttributeError):
            code = "http_error"
        raise RuntimeError(f"HTTP {error.code}: {code}") from None


def verify_turn(body, budget):
    assert body["reply"].strip(), "Missing final reply"
    assert body["catalog_source"] == "demo"
    assert body["products"], "Expected matching headphone cards"
    assert any(t["name"] == "search_products" and t["ok"] for t in body["tool_calls"]), "No successful search"
    for product in body["products"]:
        assert product["category"] == "headphones"
        for sku in product["skus"]:
            assert sku["stock"] > 0
            assert sku["price"]["currency"] == "CNY"
            assert sku["price"]["amount_minor"] <= budget * 100


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Call the configured real model; consumes provider quota")
    args = parser.parse_args()
    env = os.environ.copy()
    fixture = None
    process = None
    try:
        if args.live:
            from app.settings import load_settings
            if not load_settings(ROOT / ".env").configured:
                raise RuntimeError("Live model is not configured. Fill .env locally; do not share the API key.")
        else:
            fixture = ThreadingHTTPServer(("127.0.0.1", 0), ProtocolFixture)
            threading.Thread(target=fixture.serve_forever, daemon=True).start()
            env.update(LLM_BASE_URL=f"http://127.0.0.1:{fixture.server_port}/v1",
                       LLM_MODEL="scripted-protocol-fixture", LLM_API_KEY="",
                       LLM_TIMEOUT_SECONDS="10", AGENT_MAX_MODEL_CALLS="5", AGENT_MAX_TOOL_CALLS="8",
                       SESSION_TTL_SECONDS="1800", SESSION_CAPACITY="128",
                       EMBEDDING_BASE_URL="", EMBEDDING_MODEL="", EMBEDDING_API_KEY="",
                       RERANKER_BASE_URL="", RERANKER_MODEL="", RERANKER_API_KEY="")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        base = f"http://127.0.0.1:{port}"
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError("Application exited before startup")
            try:
                with urlopen(base + "/health", timeout=1) as response:
                    assert json.load(response)["status"] == "ok"
                break
            except URLError:
                time.sleep(0.1)
        else:
            raise RuntimeError("Application startup timed out")
        assert http_json(base, "/ready")["model_configured"]
        first = http_json(base, "/commerce/chat", {"message": "请搜索300元以内有现货的耳机，给出推荐。"})
        verify_turn(first, 300)
        second = http_json(base, "/commerce/chat", {"session_id": first["session_id"],
                           "message": "把预算改成200元以内，仍然只要有现货的耳机，请重新搜索。"})
        verify_turn(second, 200)
        assert first["session_id"] == second["session_id"]
        if not args.live:
            assert len(first["products"]) == 2 and len(second["products"]) == 1
            search = http_json(base, "/commerce/products?" + urlencode({
                "q":"日常使用的蓝牙耳机", "search_mode":"semantic", "sku_name":"白色", "max_price":"200"}))
            assert search["retrieval"]["strategy"] == "keyword_2gram"
            assert search["retrieval"]["fallback_reason"] == "embedding_not_configured"
            assert [p["id"] for p in search["items"]] == ["demo-headphones-02"]
            guidance = http_json(base, "/commerce/knowledge?" + urlencode({"q":"扩展坞 USB-C 接口", "limit":1}))
            assert guidance["items"][0]["source"] == "knowledge/hubs.md"
        print(json.dumps({"mode": "live-model" if args.live else "scripted-protocol-fixture",
                          "status": "passed", "turns": 2,
                          "product_counts": [len(first["products"]), len(second["products"])],
                          "retrieval_http_verified": not args.live}))
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if fixture is not None:
            fixture.shutdown()
            fixture.server_close()


if __name__ == "__main__":
    main()
