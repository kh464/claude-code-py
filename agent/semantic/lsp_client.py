from __future__ import annotations

from abc import ABC, abstractmethod
import json
import queue
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def _path_to_uri(path: Path) -> str:
    return path.expanduser().resolve().as_uri()


def _uri_to_path(uri: str) -> Path:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return Path(uri)
    raw_path = parsed.path
    if re.match(r"^/[A-Za-z]:", raw_path):
        raw_path = raw_path[1:]
    return Path(raw_path)


def _line_text(path: Path, line_number: int) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    lines = text.splitlines()
    if line_number < 1 or line_number > len(lines):
        return ""
    return lines[line_number - 1]


class LSPClient(ABC):
    @abstractmethod
    def find_definitions(self, *, symbol: str, root: Path) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def find_references(self, *, symbol: str, root: Path) -> list[dict]:
        raise NotImplementedError

    def find_diagnostics(self, *, root: Path, path: Path | None = None) -> list[dict]:
        _ = root, path
        return []

    def rename_symbol(self, *, symbol: str, new_name: str, root: Path) -> dict[str, Any] | None:
        _ = symbol, new_name, root
        return None

    def list_code_actions(
        self,
        *,
        root: Path,
        path: Path,
        start_line: int,
        start_character: int,
        end_line: int,
        end_character: int,
        only: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        _ = root, path, start_line, start_character, end_line, end_character, only
        return []

    def execute_command(self, *, root: Path, command: str, arguments: list[Any] | None = None) -> dict[str, Any] | None:
        _ = root, command, arguments
        return None

    def get_server_capabilities(self, *, root: Path) -> dict[str, Any]:
        _ = root
        return {}


class NoopLSPClient(LSPClient):
    def find_definitions(self, *, symbol: str, root: Path) -> list[dict]:
        _ = symbol, root
        return []

    def find_references(self, *, symbol: str, root: Path) -> list[dict]:
        _ = symbol, root
        return []


class StdioLSPClient(LSPClient):
    def __init__(
        self,
        *,
        command: list[str],
        timeout_s: float = 8.0,
        source_extensions: tuple[str, ...] | None = None,
    ) -> None:
        if not command:
            raise ValueError("command must not be empty")
        self.command = [str(part) for part in command]
        self.timeout_s = max(0.5, float(timeout_s))
        self.source_extensions = source_extensions or (".py", ".ts", ".tsx", ".js", ".jsx")

        self._process: subprocess.Popen[bytes] | None = None
        self._reader_thread: threading.Thread | None = None
        self._incoming: queue.Queue[dict[str, Any]] = queue.Queue()
        self._request_lock = threading.Lock()
        self._sequence = 0
        self._initialized_root: Path | None = None
        self._publish_diagnostics: dict[str, list[dict[str, Any]]] = {}
        self._server_capabilities: dict[str, Any] = {}

    def close(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        try:
            self._notify("exit", {})
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

    def _is_alive(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @staticmethod
    def _read_message(stream) -> dict[str, Any]:
        headers: dict[str, str] = {}
        while True:
            line = stream.readline()
            if line == b"":
                raise EOFError("LSP stream closed")
            if line in {b"\r\n", b"\n"}:
                break
            decoded = line.decode("ascii", errors="ignore").strip()
            if ":" not in decoded:
                continue
            key, value = decoded.split(":", 1)
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
                method = str(message.get("method", ""))
                if method == "textDocument/publishDiagnostics":
                    params = message.get("params", {})
                    if isinstance(params, dict):
                        uri = str(params.get("uri", "")).strip()
                        diagnostics = params.get("diagnostics", [])
                        if uri and isinstance(diagnostics, list):
                            self._publish_diagnostics[uri] = list(diagnostics)
                    continue
                self._incoming.put(message)
        except Exception as exc:
            self._incoming.put({"_error": str(exc)})

    def _ensure_started(self, *, root: Path) -> None:
        root = root.expanduser().resolve()
        if self._is_alive() and self._initialized_root == root:
            return

        self.close()
        self._publish_diagnostics.clear()
        self._server_capabilities = {}
        self._incoming = queue.Queue()
        self._process = subprocess.Popen(
            self.command,
            cwd=str(root),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()
        self._initialized_root = root
        initialized = self._request(
            "initialize",
            {
                "processId": None,
                "rootUri": _path_to_uri(root),
                "capabilities": {},
                "clientInfo": {"name": "python-agent", "version": "0.1"},
            },
        )
        if isinstance(initialized, dict):
            capabilities = initialized.get("capabilities", {})
            if isinstance(capabilities, dict):
                self._server_capabilities = dict(capabilities)
        self._notify("initialized", {})

    def _request(self, method: str, params: dict[str, Any]) -> Any:
        process = self._process
        if process is None or process.stdin is None:
            raise RuntimeError("LSP process is not running")
        with self._request_lock:
            self._sequence += 1
            request_id = self._sequence
            self._write_message(
                process.stdin,
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": method,
                    "params": params,
                },
            )
            deadline = time.monotonic() + self.timeout_s
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"LSP request timeout for {method}")
                message = self._incoming.get(timeout=remaining)
                if "_error" in message:
                    raise RuntimeError(str(message["_error"]))
                if message.get("id") != request_id:
                    continue
                if "error" in message:
                    raise RuntimeError(f"LSP error for {method}: {message['error']}")
                return message.get("result")

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None:
            return
        self._write_message(
            process.stdin,
            {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
            },
        )

    def _iter_source_files(self, root: Path) -> list[Path]:
        files: list[Path] = []
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in self.source_extensions:
                continue
            files.append(path)
        files.sort()
        return files

    def _find_symbol_position(self, *, symbol: str, root: Path) -> tuple[Path, int, int] | None:
        pattern = re.compile(rf"\b{re.escape(symbol)}\b")
        for path in self._iter_source_files(root):
            try:
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            for line_index, line in enumerate(lines):
                match = pattern.search(line)
                if not match:
                    continue
                return path, line_index, int(match.start())
        return None

    @staticmethod
    def _normalize_locations(*, symbol: str, payload: Any) -> list[dict[str, Any]]:
        if payload is None:
            return []
        if isinstance(payload, dict):
            raw_locations = [payload]
        elif isinstance(payload, list):
            raw_locations = [item for item in payload if isinstance(item, dict)]
        else:
            raw_locations = []
        normalized: list[dict[str, Any]] = []
        for entry in raw_locations:
            uri = str(entry.get("uri", ""))
            location_range = entry.get("range", {})
            if not isinstance(location_range, dict):
                continue
            start = location_range.get("start", {})
            if not isinstance(start, dict):
                continue
            line_zero = int(start.get("line", 0))
            path = _uri_to_path(uri)
            normalized.append(
                {
                    "symbol": symbol,
                    "path": str(path),
                    "line_number": line_zero + 1,
                    "line": _line_text(path, line_zero + 1),
                    "source": "lsp",
                }
            )
        return normalized

    def _request_locations(self, *, method: str, symbol: str, root: Path, include_declaration: bool = True) -> list[dict]:
        position = self._find_symbol_position(symbol=symbol, root=root)
        if position is None:
            return []
        path, line, character = position
        params = {
            "textDocument": {"uri": _path_to_uri(path)},
            "position": {"line": line, "character": character},
        }
        if method == "textDocument/references":
            params["context"] = {"includeDeclaration": include_declaration}
        result = self._request(method, params)
        return self._normalize_locations(symbol=symbol, payload=result)

    def find_definitions(self, *, symbol: str, root: Path) -> list[dict]:
        root_path = root.expanduser().resolve()
        self._ensure_started(root=root_path)
        return self._request_locations(method="textDocument/definition", symbol=symbol, root=root_path)

    def find_references(self, *, symbol: str, root: Path) -> list[dict]:
        root_path = root.expanduser().resolve()
        self._ensure_started(root=root_path)
        return self._request_locations(
            method="textDocument/references",
            symbol=symbol,
            root=root_path,
            include_declaration=True,
        )

    def rename_symbol(self, *, symbol: str, new_name: str, root: Path) -> dict[str, Any] | None:
        root_path = root.expanduser().resolve()
        self._ensure_started(root=root_path)
        position = self._find_symbol_position(symbol=symbol, root=root_path)
        if position is None:
            return None
        path, line, character = position
        payload = self._request(
            "textDocument/rename",
            {
                "textDocument": {"uri": _path_to_uri(path)},
                "position": {"line": line, "character": character},
                "newName": str(new_name),
            },
        )
        if isinstance(payload, dict):
            return payload
        return None

    def list_code_actions(
        self,
        *,
        root: Path,
        path: Path,
        start_line: int,
        start_character: int,
        end_line: int,
        end_character: int,
        only: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        root_path = root.expanduser().resolve()
        target = path.expanduser().resolve()
        self._ensure_started(root=root_path)
        context: dict[str, Any] = {"diagnostics": []}
        if only:
            context["only"] = [str(item).strip() for item in only if str(item).strip()]
        payload = self._request(
            "textDocument/codeAction",
            {
                "textDocument": {"uri": _path_to_uri(target)},
                "range": {
                    "start": {"line": max(0, int(start_line)), "character": max(0, int(start_character))},
                    "end": {"line": max(0, int(end_line)), "character": max(0, int(end_character))},
                },
                "context": context,
            },
        )
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    def execute_command(self, *, root: Path, command: str, arguments: list[Any] | None = None) -> dict[str, Any] | None:
        root_path = root.expanduser().resolve()
        self._ensure_started(root=root_path)
        payload = self._request(
            "workspace/executeCommand",
            {
                "command": str(command),
                "arguments": list(arguments or []),
            },
        )
        if isinstance(payload, dict):
            return payload
        if payload is None:
            return None
        return {"result": payload}

    def get_server_capabilities(self, *, root: Path) -> dict[str, Any]:
        root_path = root.expanduser().resolve()
        self._ensure_started(root=root_path)
        return dict(self._server_capabilities)

    def find_diagnostics(self, *, root: Path, path: Path | None = None) -> list[dict]:
        root_path = root.expanduser().resolve()
        self._ensure_started(root=root_path)

        targets: list[Path]
        if path is not None:
            targets = [path.expanduser().resolve()]
        else:
            targets = self._iter_source_files(root_path)

        diagnostics: list[dict[str, Any]] = []
        for target in targets:
            uri = _path_to_uri(target)
            try:
                result = self._request("textDocument/diagnostic", {"textDocument": {"uri": uri}})
                items = []
                if isinstance(result, dict):
                    raw_items = result.get("items", [])
                    if isinstance(raw_items, list):
                        items = raw_items
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    location_range = item.get("range", {})
                    start = location_range.get("start", {}) if isinstance(location_range, dict) else {}
                    line_number = int(start.get("line", 0)) + 1 if isinstance(start, dict) else 1
                    diagnostics.append(
                        {
                            "path": str(target),
                            "line_number": line_number,
                            "severity": int(item.get("severity", 0)),
                            "message": str(item.get("message", "")),
                            "source": str(item.get("source", "lsp")),
                            "line": _line_text(target, line_number),
                        }
                    )
            except Exception:
                published = self._publish_diagnostics.get(uri, [])
                for item in published:
                    if not isinstance(item, dict):
                        continue
                    location_range = item.get("range", {})
                    start = location_range.get("start", {}) if isinstance(location_range, dict) else {}
                    line_number = int(start.get("line", 0)) + 1 if isinstance(start, dict) else 1
                    diagnostics.append(
                        {
                            "path": str(target),
                            "line_number": line_number,
                            "severity": int(item.get("severity", 0)),
                            "message": str(item.get("message", "")),
                            "source": str(item.get("source", "lsp")),
                            "line": _line_text(target, line_number),
                        }
                    )
        diagnostics.sort(key=lambda item: (item["path"], item["line_number"], item["message"]))
        return diagnostics
