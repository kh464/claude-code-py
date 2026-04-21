from __future__ import annotations

import shutil
import sys
import uuid
from pathlib import Path

import pytest

from agent.contracts import ToolContext
from agent.semantic.lsp_client import StdioLSPClient
from agent.semantic import SemanticIndex
from agent.tools.lsp_tool import LSPTool


def _create_temp_dir() -> Path:
    root = Path("tests/.tmp-python-agent") / f"semantic-lsp-stdio-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    return root.resolve()


def _create_sample_project(root: Path) -> None:
    (root / "service.py").write_text(
        "class UserService:\n"
        "    def run(self):\n"
        "        return 'ok'\n",
        encoding="utf-8",
    )
    (root / "handler.py").write_text(
        "from service import UserService\n"
        "def invoke():\n"
        "    return UserService().run(\n",
        encoding="utf-8",
    )


def _write_fake_lsp_server(path: Path) -> None:
    path.write_text(
        """
import json
import sys
from pathlib import Path

ROOT = Path.cwd()

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
    length = int(headers.get("content-length", "0"))
    if length <= 0:
        return {}
    payload = sys.stdin.buffer.read(length)
    return json.loads(payload.decode("utf-8", errors="ignore"))

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

    if method == "initialized":
        continue

    if method == "textDocument/definition":
        location = {
            "uri": (ROOT / "service.py").resolve().as_uri(),
            "range": {"start": {"line": 0, "character": 6}, "end": {"line": 0, "character": 17}},
        }
        write_message({"jsonrpc": "2.0", "id": msg_id, "result": [location]})
        continue

    if method == "textDocument/references":
        locations = [
            {
                "uri": (ROOT / "service.py").resolve().as_uri(),
                "range": {"start": {"line": 0, "character": 6}, "end": {"line": 0, "character": 17}},
            },
            {
                "uri": (ROOT / "handler.py").resolve().as_uri(),
                "range": {"start": {"line": 0, "character": 19}, "end": {"line": 0, "character": 30}},
            },
        ]
        write_message({"jsonrpc": "2.0", "id": msg_id, "result": locations})
        continue

    if method == "textDocument/diagnostic":
        text_document = params.get("textDocument", {})
        target_uri = str(text_document.get("uri", ""))
        result = {
            "kind": "full",
            "items": [
                {
                    "range": {"start": {"line": 1, "character": 4}, "end": {"line": 1, "character": 14}},
                    "severity": 1,
                    "message": "fake diagnostic",
                    "source": "fake-lsp",
                    "uri": target_uri,
                }
            ],
        }
        write_message({"jsonrpc": "2.0", "id": msg_id, "result": result})
        continue

    if method == "shutdown":
        write_message({"jsonrpc": "2.0", "id": msg_id, "result": None})
        continue
""".strip(),
        encoding="utf-8",
    )


def test_stdio_lsp_client_resolves_definitions_references_and_diagnostics() -> None:
    temp_root = _create_temp_dir()
    client: StdioLSPClient | None = None
    try:
        _create_sample_project(temp_root)
        server_path = temp_root / "fake_lsp_server.py"
        _write_fake_lsp_server(server_path)
        client = StdioLSPClient(command=[sys.executable, str(server_path.resolve())])
        index = SemanticIndex(root=temp_root, lsp_client=client)

        definitions = index.find_symbol("UserService")
        references = index.find_references("UserService")
        diagnostics = index.find_diagnostics(path=temp_root / "handler.py")

        assert definitions
        assert definitions[0]["source"] == "lsp"
        assert any(item["path"].endswith("service.py") for item in definitions)
        assert len(references) >= 2
        assert any(item["path"].endswith("handler.py") for item in references)
        assert diagnostics
        assert diagnostics[0]["source"] == "fake-lsp"
    finally:
        if client is not None:
            client.close()
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_lsp_tool_supports_find_diagnostics_operation() -> None:
    temp_root = _create_temp_dir()
    client: StdioLSPClient | None = None
    try:
        _create_sample_project(temp_root)
        server_path = temp_root / "fake_lsp_server.py"
        _write_fake_lsp_server(server_path)
        client = StdioLSPClient(command=[sys.executable, str(server_path.resolve())])
        tool = LSPTool()
        result = await tool.call(
            {"operation": "find_diagnostics", "path": str(temp_root / "handler.py")},
            ToolContext(metadata={"lsp_client": client}),
            None,
            None,
            lambda _event: None,
        )
        assert result["operation"] == "find_diagnostics"
        assert result["count"] >= 1
        assert result["diagnostics"][0]["source"] == "fake-lsp"
    finally:
        if client is not None:
            client.close()
        shutil.rmtree(temp_root, ignore_errors=True)
