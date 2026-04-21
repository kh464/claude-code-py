from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from collections.abc import Mapping
from typing import Any


class StdioMCPClient:
    def __init__(
        self,
        *,
        command: list[str],
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
        timeout_s: float = 8.0,
    ) -> None:
        if not command:
            raise ValueError("command must not be empty")
        self.command = [str(part) for part in command]
        self.cwd = cwd
        self.env = dict(env or {})
        self.timeout_s = max(0.5, float(timeout_s))

        self._process: subprocess.Popen[bytes] | None = None
        self._reader_thread: threading.Thread | None = None
        self._incoming: queue.Queue[dict[str, Any]] = queue.Queue()
        self._request_lock = threading.Lock()
        self._sequence = 0
        self._initialized = False

    def _is_alive(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @staticmethod
    def _read_message(stream) -> dict[str, Any]:
        headers: dict[str, str] = {}
        while True:
            line = stream.readline()
            if line == b"":
                raise EOFError("MCP stream closed")
            if line in {b"\r\n", b"\n"}:
                break
            text = line.decode("ascii", errors="ignore").strip()
            if ":" not in text:
                continue
            key, value = text.split(":", 1)
            headers[key.lower().strip()] = value.strip()
        content_length = int(headers.get("content-length", "0"))
        if content_length <= 0:
            return {}
        payload = stream.read(content_length)
        data = json.loads(payload.decode("utf-8", errors="ignore"))
        if isinstance(data, dict):
            return data
        return {}

    @staticmethod
    def _write_message(stream, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        stream.write(header)
        stream.write(body)
        stream.flush()

    def _reader_loop(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        try:
            while self._is_alive():
                message = self._read_message(process.stdout)
                if not message:
                    continue
                self._incoming.put(message)
        except Exception as exc:
            self._incoming.put({"_error": str(exc)})

    def close(self) -> None:
        process = self._process
        self._process = None
        self._initialized = False
        if process is None:
            return
        try:
            if process.stdin is not None:
                self._write_message(process.stdin, {"jsonrpc": "2.0", "method": "shutdown", "params": {}})
        except Exception:
            pass
        try:
            process.terminate()
            process.wait(timeout=1.0)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    def _ensure_started(self) -> None:
        if self._is_alive():
            return
        self.close()
        self._incoming = queue.Queue()
        self._process = subprocess.Popen(
            self.command,
            cwd=self.cwd,
            env=self.env if self.env else None,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()
        self._initialized = False

    def _request_once(self, method: str, params: dict[str, Any]) -> Any:
        self._ensure_started()
        process = self._process
        if process is None or process.stdin is None:
            raise RuntimeError("MCP process is not running")
        with self._request_lock:
            self._sequence += 1
            request_id = self._sequence
            self._write_message(
                process.stdin,
                {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
            )
            deadline = time.monotonic() + self.timeout_s
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"MCP request timeout for {method}")
                message = self._incoming.get(timeout=remaining)
                if "_error" in message:
                    raise RuntimeError(str(message["_error"]))
                if message.get("id") != request_id:
                    continue
                if "error" in message:
                    raise RuntimeError(str(message["error"]))
                return message.get("result")

    def request(self, method: str, params: dict[str, Any]) -> Any:
        try:
            if not self._initialized and method != "initialize":
                _ = self._request_once("initialize", {"clientInfo": {"name": "python-agent", "version": "0.1"}})
                self._initialized = True
            return self._request_once(method, params)
        except Exception:
            self.close()
            self._ensure_started()
            if method != "initialize":
                _ = self._request_once("initialize", {"clientInfo": {"name": "python-agent", "version": "0.1"}})
                self._initialized = True
            return self._request_once(method, params)

    def list_tools(self) -> list[dict[str, Any]]:
        result = self.request("tools/list", {})
        if isinstance(result, dict):
            tools = result.get("tools", [])
            if isinstance(tools, list):
                return [item for item in tools if isinstance(item, dict)]
        if isinstance(result, list):
            return [item for item in result if isinstance(item, dict)]
        return []

    def list_resources(self) -> list[dict[str, Any]]:
        result = self.request("resources/list", {})
        if isinstance(result, dict):
            resources = result.get("resources", [])
            if isinstance(resources, list):
                return [item for item in resources if isinstance(item, dict)]
        if isinstance(result, list):
            return [item for item in result if isinstance(item, dict)]
        return []

    def read_resource(self, uri: str) -> dict[str, Any]:
        result = self.request("resources/read", {"uri": uri})
        if isinstance(result, dict):
            return result
        return {"content": result}

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        result = self.request("tools/call", {"name": name, "arguments": dict(arguments)})
        if isinstance(result, dict):
            return result
        return {"result": result}
