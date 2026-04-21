from __future__ import annotations

import shutil
import sys
import uuid
from pathlib import Path

from agent.mcp_integration.manager import MCPManager


def _create_temp_dir() -> Path:
    root = Path("tests/.tmp-python-agent") / f"mcp-stdio-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    return root.resolve()


def _write_fake_mcp_server(path: Path) -> None:
    path.write_text(
        """
import json
import sys

UNSTABLE_ATTEMPTS = 0

def read_message():
    headers = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\\r\\n", b"\\n"):
            break
        text = line.decode("ascii", errors="ignore").strip()
        if ":" not in text:
            continue
        key, value = text.split(":", 1)
        headers[key.lower().strip()] = value.strip()
    content_length = int(headers.get("content-length", "0"))
    if content_length <= 0:
        return {}
    body = sys.stdin.buffer.read(content_length)
    return json.loads(body.decode("utf-8", errors="ignore"))

def write_message(payload):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(body)}\\r\\n\\r\\n".encode("ascii"))
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()

while True:
    message = read_message()
    if message is None:
        break
    method = message.get("method")
    msg_id = message.get("id")
    params = message.get("params", {})

    if method == "initialize":
        write_message({"jsonrpc": "2.0", "id": msg_id, "result": {"capabilities": {}}})
        continue

    if method == "tools/list":
        write_message(
            {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": [{"name": "echo"}, {"name": "unstable"}]},
            }
        )
        continue

    if method == "resources/list":
        write_message(
            {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"resources": [{"uri": "doc://guide"}]},
            }
        )
        continue

    if method == "resources/read":
        write_message(
            {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"content": "guide-content"},
            }
        )
        continue

    if method == "tools/call":
        name = str(params.get("name", ""))
        arguments = params.get("arguments", {})
        if name == "unstable":
            if UNSTABLE_ATTEMPTS == 0:
                UNSTABLE_ATTEMPTS += 1
                write_message(
                    {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {"code": -32001, "message": "transient failure"},
                    }
                )
                continue
            write_message(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {"structuredContent": {"unstable": arguments}},
                }
            )
            continue

        write_message(
            {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"structuredContent": {"echo": arguments}},
            }
        )
        continue

    if method == "shutdown":
        write_message({"jsonrpc": "2.0", "id": msg_id, "result": None})
        continue

    write_message(
        {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"unknown method: {method}"},
        }
    )
""".strip(),
        encoding="utf-8",
    )


def test_mcp_stdio_transport_supports_tool_resource_and_retry() -> None:
    temp_root = _create_temp_dir()
    try:
        server_script = temp_root / "fake_mcp_server.py"
        _write_fake_mcp_server(server_script)
        manager = MCPManager()
        manager.register_server(
            "local_stdio",
            transport={"type": "stdio", "command": [sys.executable, str(server_script.resolve())]},
        )

        tools = manager.list_tools("local_stdio")
        assert any(item["name"] == "echo" for item in tools)
        assert any(item["name"] == "unstable" for item in tools)

        echo = manager.invoke_tool("local_stdio", "echo", {"v": 1})
        assert echo["server"] == "local_stdio"
        assert echo["tool"] == "echo"
        assert echo["result"]["echo"]["v"] == 1

        resources = manager.list_resources("local_stdio")
        assert resources == [{"uri": "doc://guide", "server": "local_stdio"}]
        content = manager.read_resource("local_stdio", "doc://guide")
        assert content["content"] == "guide-content"

        unstable = manager.invoke_tool("local_stdio", "unstable", {"x": 2})
        assert unstable["result"]["unstable"]["x"] == 2
        assert unstable["attempts"] == 2
        assert unstable["retry_count"] == 1
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_mcp_stdio_transport_can_reconnect_after_disconnect_toggle() -> None:
    temp_root = _create_temp_dir()
    try:
        server_script = temp_root / "fake_mcp_server.py"
        _write_fake_mcp_server(server_script)
        manager = MCPManager()
        manager.register_server(
            "local_stdio",
            transport={"type": "stdio", "command": [sys.executable, str(server_script.resolve())]},
        )

        _ = manager.invoke_tool("local_stdio", "echo", {"first": True})
        manager.set_connected("local_stdio", False)
        manager.set_connected("local_stdio", True)
        recovered = manager.invoke_tool("local_stdio", "echo", {"second": True})
        assert recovered["result"]["echo"]["second"] is True
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
