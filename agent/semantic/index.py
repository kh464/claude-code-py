from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .graph import SemanticGraph
from .lsp_client import LSPClient, NoopLSPClient
from .refactor_fallback import SemanticRefactorFallback


_DEFINITION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("class", re.compile(r"^\s*class\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\b")),
    ("function", re.compile(r"^\s*def\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\b")),
    ("class", re.compile(r"^\s*export\s+class\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\b")),
    ("function", re.compile(r"^\s*(export\s+)?function\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\b")),
)


class SemanticIndex:
    def __init__(
        self,
        *,
        root: str | Path,
        extensions: tuple[str, ...] | None = None,
        lsp_client: LSPClient | None = None,
        strict_lsp: bool = False,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        self.extensions = extensions or (".py", ".ts", ".tsx", ".js", ".jsx")
        self.lsp_client = lsp_client or NoopLSPClient()
        self.strict_lsp = bool(strict_lsp)
        self.refactor_fallback = SemanticRefactorFallback(root=self.root)

    @staticmethod
    def _normalize_refactor_kind(*, kind: str | None, title: str | None) -> str:
        kind_text = str(kind or "").strip().lower()
        title_text = str(title or "").strip().lower()
        merged = f"{kind_text} {title_text}".strip()
        if "rename" in merged:
            return "rename"
        if "extract" in merged:
            return "extract"
        if "move" in merged:
            return "move"
        if "inline" in merged:
            return "inline"
        if "organizeimports" in merged or "organize imports" in merged:
            return "organize_imports"
        return "other"

    def _resolve_fallback_kind(
        self,
        *,
        kinds: list[str] | None,
        action_title: str | None,
        chosen_action: dict[str, Any] | None = None,
    ) -> str | None:
        for item in list(kinds or []):
            normalized = self._normalize_refactor_kind(kind=str(item), title=None)
            if normalized in set(self.refactor_fallback.supported_kinds()):
                return normalized
        if action_title:
            normalized = self._normalize_refactor_kind(kind=None, title=action_title)
            if normalized in set(self.refactor_fallback.supported_kinds()):
                return normalized
        if isinstance(chosen_action, dict):
            normalized = self._normalize_refactor_kind(
                kind=str(chosen_action.get("kind", "")).strip() or None,
                title=str(chosen_action.get("title", "")).strip() or None,
            )
            if normalized in set(self.refactor_fallback.supported_kinds()):
                return normalized
        return None

    def _iter_source_files(self) -> list[Path]:
        if not self.root.exists():
            return []
        files: list[Path] = []
        for path in self.root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in self.extensions:
                continue
            files.append(path)
        files.sort()
        return files

    def _iter_lines(self, path: Path):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line_number, line in enumerate(text.splitlines(), start=1):
            yield line_number, line

    @staticmethod
    def _normalize_definition(target: str, entry: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(entry)
        normalized["symbol"] = str(entry.get("symbol", target))
        normalized["kind"] = str(entry.get("kind", "symbol"))
        normalized["path"] = str(entry.get("path", ""))
        normalized["line_number"] = int(entry.get("line_number", 0))
        normalized["line"] = str(entry.get("line", "")).strip("\n")
        return normalized

    @staticmethod
    def _normalize_reference(target: str, entry: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(entry)
        normalized["symbol"] = str(entry.get("symbol", target))
        normalized["path"] = str(entry.get("path", ""))
        normalized["line_number"] = int(entry.get("line_number", 0))
        normalized["line"] = str(entry.get("line", "")).strip("\n")
        return normalized

    def _scan_definitions(self, target: str) -> list[dict[str, Any]]:
        target = target.strip()
        if not target:
            return []
        results: list[dict] = []
        for path in self._iter_source_files():
            for line_number, line in self._iter_lines(path):
                for kind, pattern in _DEFINITION_PATTERNS:
                    match = pattern.search(line)
                    if not match:
                        continue
                    if match.group("name") != target:
                        continue
                    results.append(
                        {
                            "symbol": target,
                            "kind": kind,
                            "path": str(path),
                            "line_number": line_number,
                            "line": line,
                            "source": "scan",
                        }
                    )
        return [self._normalize_definition(target, entry) for entry in results]

    def _scan_references(self, target: str) -> list[dict[str, Any]]:
        if not target:
            return []
        pattern = re.compile(rf"\b{re.escape(target)}\b")
        results: list[dict] = []
        for path in self._iter_source_files():
            for line_number, line in self._iter_lines(path):
                if not pattern.search(line):
                    continue
                results.append(
                    {
                        "symbol": target,
                        "path": str(path),
                        "line_number": line_number,
                        "line": line,
                        "source": "scan",
                    }
                )
        return [self._normalize_reference(target, entry) for entry in results]

    def _scan_diagnostics(self, *, path: Path | None = None) -> list[dict[str, Any]]:
        targets = [path] if path is not None else self._iter_source_files()
        diagnostics: list[dict[str, Any]] = []
        for file_path in targets:
            if file_path is None or not file_path.exists() or not file_path.is_file():
                continue
            if file_path.suffix != ".py":
                continue
            try:
                source = file_path.read_text(encoding="utf-8", errors="ignore")
                ast.parse(source)
            except SyntaxError as exc:
                line_number = int(exc.lineno or 1)
                line = ""
                lines = source.splitlines()
                if 1 <= line_number <= len(lines):
                    line = lines[line_number - 1]
                diagnostics.append(
                    {
                        "path": str(file_path),
                        "line_number": line_number,
                        "severity": 1,
                        "message": str(exc.msg),
                        "source": "scan",
                        "line": line,
                    }
                )
            except Exception:
                continue
        diagnostics.sort(key=lambda item: (item["path"], item["line_number"], item["message"]))
        return diagnostics

    @staticmethod
    def _uri_to_path(uri: str) -> Path:
        parsed = urlparse(str(uri))
        if parsed.scheme == "file":
            raw_path = parsed.path
            if re.match(r"^/[A-Za-z]:", raw_path):
                raw_path = raw_path[1:]
            return Path(raw_path)
        return Path(str(uri))

    @staticmethod
    def _path_to_uri(path: Path) -> str:
        return path.expanduser().resolve().as_uri()

    @staticmethod
    def _line_starts(text: str) -> list[int]:
        starts = [0]
        for index, char in enumerate(text):
            if char == "\n":
                starts.append(index + 1)
        return starts

    @staticmethod
    def _position_to_offset(text: str, *, line: int, character: int) -> int:
        starts = SemanticIndex._line_starts(text)
        if not starts:
            return 0
        safe_line = max(0, min(int(line), len(starts) - 1))
        line_start = starts[safe_line]
        if safe_line + 1 < len(starts):
            line_end = starts[safe_line + 1] - 1
        else:
            line_end = len(text)
        return max(line_start, min(line_start + max(0, int(character)), line_end))

    @classmethod
    def _apply_text_edits(cls, *, text: str, edits: list[dict[str, Any]]) -> str:
        if not edits:
            return text
        normalized: list[tuple[int, int, str]] = []
        for edit in edits:
            start = dict(edit.get("start", {}))
            end = dict(edit.get("end", {}))
            start_offset = cls._position_to_offset(
                text,
                line=int(start.get("line", 0)),
                character=int(start.get("character", 0)),
            )
            end_offset = cls._position_to_offset(
                text,
                line=int(end.get("line", 0)),
                character=int(end.get("character", 0)),
            )
            if end_offset < start_offset:
                start_offset, end_offset = end_offset, start_offset
            normalized.append((start_offset, end_offset, str(edit.get("new_text", ""))))
        normalized.sort(key=lambda item: item[0], reverse=True)
        updated = text
        for start_offset, end_offset, new_text in normalized:
            updated = f"{updated[:start_offset]}{new_text}{updated[end_offset:]}"
        return updated

    @classmethod
    def _extract_workspace_edits(cls, payload: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not isinstance(payload, dict):
            return []
        grouped: dict[str, list[dict[str, Any]]] = {}
        changes = payload.get("changes", {})
        if isinstance(changes, dict):
            for uri, raw_edits in changes.items():
                path = str(cls._uri_to_path(str(uri)).expanduser().resolve())
                if not isinstance(raw_edits, list):
                    continue
                bucket = grouped.setdefault(path, [])
                for item in raw_edits:
                    if not isinstance(item, dict):
                        continue
                    raw_range = item.get("range", {})
                    if not isinstance(raw_range, dict):
                        continue
                    start = dict(raw_range.get("start", {}))
                    end = dict(raw_range.get("end", {}))
                    bucket.append(
                        {
                            "start": {"line": int(start.get("line", 0)), "character": int(start.get("character", 0))},
                            "end": {"line": int(end.get("line", 0)), "character": int(end.get("character", 0))},
                            "new_text": str(item.get("newText", "")),
                        }
                    )

        document_changes = payload.get("documentChanges", [])
        if isinstance(document_changes, list):
            for change in document_changes:
                if not isinstance(change, dict):
                    continue
                text_document = change.get("textDocument", {})
                if not isinstance(text_document, dict):
                    continue
                uri = str(text_document.get("uri", "")).strip()
                if not uri:
                    continue
                path = str(cls._uri_to_path(uri).expanduser().resolve())
                edits = change.get("edits", [])
                if not isinstance(edits, list):
                    continue
                bucket = grouped.setdefault(path, [])
                for item in edits:
                    if not isinstance(item, dict):
                        continue
                    raw_range = item.get("range", {})
                    if not isinstance(raw_range, dict):
                        continue
                    start = dict(raw_range.get("start", {}))
                    end = dict(raw_range.get("end", {}))
                    bucket.append(
                        {
                            "start": {"line": int(start.get("line", 0)), "character": int(start.get("character", 0))},
                            "end": {"line": int(end.get("line", 0)), "character": int(end.get("character", 0))},
                            "new_text": str(item.get("newText", "")),
                        }
                    )

        output: list[dict[str, Any]] = []
        for path, edits in grouped.items():
            if edits:
                output.append({"path": path, "edits": edits})
        output.sort(key=lambda item: item["path"])
        return output

    @classmethod
    def _apply_workspace_edit_payload(
        cls,
        *,
        payload: dict[str, Any] | None,
        apply: bool,
    ) -> dict[str, Any]:
        edits = cls._extract_workspace_edits(payload)
        applied_count = 0
        changes: list[dict[str, Any]] = []
        for entry in edits:
            path = Path(entry["path"]).expanduser().resolve()
            file_edits = list(entry["edits"])
            if apply and path.exists() and path.is_file():
                original = path.read_text(encoding="utf-8", errors="ignore")
                updated = cls._apply_text_edits(text=original, edits=file_edits)
                if updated != original:
                    path.write_text(updated, encoding="utf-8")
                    applied_count += 1
            changes.append({"path": str(path), "occurrences": len(file_edits), "source": "lsp"})
        return {
            "files_changed": len(changes),
            "occurrences": sum(int(item["occurrences"]) for item in changes),
            "applied_files": applied_count,
            "changes": changes,
        }

    def list_refactor_actions(
        self,
        *,
        path: str | Path,
        start_line: int,
        start_character: int,
        end_line: int,
        end_character: int,
        kinds: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        target = Path(path).expanduser().resolve()
        try:
            raw_actions = self.lsp_client.list_code_actions(
                root=self.root,
                path=target,
                start_line=int(start_line),
                start_character=int(start_character),
                end_line=int(end_line),
                end_character=int(end_character),
                only=kinds,
            )
        except Exception as exc:
            if self.strict_lsp:
                raise RuntimeError(f"lsp code actions failed: {exc}") from exc
            return []

        output: list[dict[str, Any]] = []
        for index, action in enumerate(raw_actions):
            if not isinstance(action, dict):
                continue
            kind = str(action.get("kind", "")).strip()
            title = str(action.get("title", "")).strip()
            if not title:
                continue
            output.append(
                {
                    "index": index,
                    "title": title,
                    "kind": kind or None,
                    "normalized_kind": self._normalize_refactor_kind(kind=kind, title=title),
                    "has_edit": isinstance(action.get("edit"), dict),
                    "has_command": isinstance(action.get("command"), dict),
                }
            )
        return output

    def apply_refactor_action(
        self,
        *,
        path: str | Path,
        target_path: str | Path | None = None,
        start_line: int,
        start_character: int,
        end_line: int,
        end_character: int,
        kinds: list[str] | None = None,
        action_index: int | None = None,
        action_title: str | None = None,
        apply: bool = False,
    ) -> dict[str, Any]:
        target = Path(path).expanduser().resolve()
        fallback_kind = self._resolve_fallback_kind(
            kinds=kinds,
            action_title=action_title,
            chosen_action=None,
        )
        try:
            raw_actions = self.lsp_client.list_code_actions(
                root=self.root,
                path=target,
                start_line=int(start_line),
                start_character=int(start_character),
                end_line=int(end_line),
                end_character=int(end_character),
                only=kinds,
            )
        except Exception as exc:
            if self.strict_lsp:
                raise RuntimeError(f"lsp code actions failed: {exc}") from exc
            return self.refactor_fallback.apply(
                path=target,
                target_path=Path(target_path).expanduser().resolve() if target_path is not None else None,
                start_line=int(start_line),
                start_character=int(start_character),
                end_line=int(end_line),
                end_character=int(end_character),
                normalized_kind=fallback_kind,
                apply=bool(apply),
                reason="lsp_code_actions_error",
            )

        chosen: dict[str, Any] | None = None
        if action_title:
            for item in raw_actions:
                if isinstance(item, dict) and str(item.get("title", "")).strip() == str(action_title).strip():
                    chosen = item
                    break
        if chosen is None:
            index = int(action_index if action_index is not None else 0)
            if 0 <= index < len(raw_actions):
                candidate = raw_actions[index]
                if isinstance(candidate, dict):
                    chosen = candidate

        fallback_kind = self._resolve_fallback_kind(
            kinds=kinds,
            action_title=action_title,
            chosen_action=chosen,
        )
        if not isinstance(chosen, dict):
            return self.refactor_fallback.apply(
                path=target,
                target_path=Path(target_path).expanduser().resolve() if target_path is not None else None,
                start_line=int(start_line),
                start_character=int(start_character),
                end_line=int(end_line),
                end_character=int(end_character),
                normalized_kind=fallback_kind,
                apply=bool(apply),
                reason="lsp_action_missing",
            )

        selected = {
            "title": str(chosen.get("title", "")).strip(),
            "kind": str(chosen.get("kind", "")).strip() or None,
            "normalized_kind": self._normalize_refactor_kind(
                kind=str(chosen.get("kind", "")).strip() or None,
                title=str(chosen.get("title", "")).strip(),
            ),
        }
        edit_payload = chosen.get("edit") if isinstance(chosen.get("edit"), dict) else None
        summary = self._apply_workspace_edit_payload(payload=edit_payload, apply=apply)
        if summary.get("files_changed", 0) == 0 and fallback_kind in set(self.refactor_fallback.supported_kinds()):
            return self.refactor_fallback.apply(
                path=target,
                target_path=Path(target_path).expanduser().resolve() if target_path is not None else None,
                start_line=int(start_line),
                start_character=int(start_character),
                end_line=int(end_line),
                end_character=int(end_character),
                normalized_kind=fallback_kind,
                apply=bool(apply),
                reason="lsp_action_without_edit",
            )
        return {
            "backend": "lsp",
            "applied": bool(apply),
            "selected": selected,
            **summary,
        }

    def describe_lsp_capabilities(
        self,
        *,
        path: str | Path | None = None,
        start_line: int | None = None,
        start_character: int | None = None,
        end_line: int | None = None,
        end_character: int | None = None,
    ) -> dict[str, Any]:
        server_capabilities: dict[str, Any] = {}
        backend = "scan"
        try:
            server_capabilities = dict(self.lsp_client.get_server_capabilities(root=self.root))
            if not isinstance(self.lsp_client, NoopLSPClient):
                backend = "lsp"
        except Exception as exc:
            if self.strict_lsp:
                raise RuntimeError(f"lsp capability discovery failed: {exc}") from exc

        raw_actions: list[dict[str, Any]] = []
        has_range = None not in {path, start_line, start_character, end_line, end_character}
        if has_range:
            target = Path(str(path)).expanduser().resolve()
            try:
                raw_actions = self.lsp_client.list_code_actions(
                    root=self.root,
                    path=target,
                    start_line=int(start_line),
                    start_character=int(start_character),
                    end_line=int(end_line),
                    end_character=int(end_character),
                    only=None,
                )
            except Exception as exc:
                if self.strict_lsp:
                    raise RuntimeError(f"lsp code action discovery failed: {exc}") from exc
                raw_actions = []

        normalized_refactor_kinds = sorted(
            {
                self._normalize_refactor_kind(
                    kind=str(action.get("kind", "")).strip(),
                    title=str(action.get("title", "")).strip(),
                )
                for action in raw_actions
                if isinstance(action, dict)
            }
        )
        supported_operations = [
            "find_symbol",
            "find_references",
            "find_diagnostics",
            "rename_symbol",
            "list_refactors",
            "apply_refactor",
        ]
        return {
            "backend": backend,
            "strict_lsp_effective": self.strict_lsp,
            "supported_operations": supported_operations,
            "supported_refactor_kinds": normalized_refactor_kinds,
            "sampled_refactor_actions": len(raw_actions),
            "server_capabilities": server_capabilities,
        }

    def find_symbol(self, name: str) -> list[dict]:
        target = name.strip()
        if not target:
            return []

        graph = SemanticGraph()
        try:
            lsp_results = self.lsp_client.find_definitions(symbol=target, root=self.root)
        except Exception as exc:
            if self.strict_lsp:
                raise RuntimeError(f"lsp definitions failed: {exc}") from exc
            lsp_results = []

        if lsp_results:
            graph.add_definitions([self._normalize_definition(target, entry) for entry in lsp_results])
            return graph.definitions
        if self.strict_lsp:
            return []

        graph.add_definitions(self._scan_definitions(target))
        return graph.definitions

    def find_references(self, name: str) -> list[dict]:
        target = name.strip()
        if not target:
            return []

        graph = SemanticGraph()
        try:
            lsp_results = self.lsp_client.find_references(symbol=target, root=self.root)
        except Exception as exc:
            if self.strict_lsp:
                raise RuntimeError(f"lsp references failed: {exc}") from exc
            lsp_results = []

        if lsp_results:
            graph.add_references([self._normalize_reference(target, entry) for entry in lsp_results])
            return graph.references
        if self.strict_lsp:
            return []

        graph.add_references(self._scan_references(target))
        return graph.references

    def find_diagnostics(self, *, path: str | Path | None = None) -> list[dict]:
        target_path = Path(path).expanduser().resolve() if path is not None else None
        try:
            lsp_results = self.lsp_client.find_diagnostics(root=self.root, path=target_path)
        except Exception as exc:
            if self.strict_lsp:
                raise RuntimeError(f"lsp diagnostics failed: {exc}") from exc
            lsp_results = []

        normalized: list[dict[str, Any]] = []
        for entry in lsp_results:
            if not isinstance(entry, dict):
                continue
            normalized.append(
                {
                    "path": str(entry.get("path", "")),
                    "line_number": int(entry.get("line_number", 0)),
                    "severity": int(entry.get("severity", 0)),
                    "message": str(entry.get("message", "")),
                    "source": str(entry.get("source", "lsp")),
                    "line": str(entry.get("line", "")).strip("\n"),
                }
            )
        if normalized:
            normalized.sort(key=lambda item: (item["path"], item["line_number"], item["message"]))
            return normalized
        if self.strict_lsp:
            return []
        return self._scan_diagnostics(path=target_path)

    def rename_symbol(self, *, symbol: str, new_name: str, apply: bool = False) -> dict[str, Any]:
        target = symbol.strip()
        replacement = new_name.strip()
        if not target:
            raise ValueError("symbol must not be empty")
        if not replacement:
            raise ValueError("new_name must not be empty")
        if target == replacement:
            return {
                "symbol": target,
                "new_name": replacement,
                "backend": "noop",
                "applied": False,
                "files_changed": 0,
                "occurrences": 0,
                "changes": [],
            }

        lsp_payload: dict[str, Any] | None = None
        try:
            lsp_payload = self.lsp_client.rename_symbol(symbol=target, new_name=replacement, root=self.root)
        except Exception as exc:
            if self.strict_lsp:
                raise RuntimeError(f"lsp rename failed: {exc}") from exc

        lsp_edits = self._extract_workspace_edits(lsp_payload)
        if lsp_edits:
            summary = self._apply_workspace_edit_payload(payload=lsp_payload, apply=apply)
            return {
                "symbol": target,
                "new_name": replacement,
                "backend": "lsp",
                "applied": bool(apply),
                **summary,
            }

        if self.strict_lsp:
            return {
                "symbol": target,
                "new_name": replacement,
                "backend": "lsp",
                "applied": False,
                "files_changed": 0,
                "occurrences": 0,
                "changes": [],
            }

        pattern = re.compile(rf"\b{re.escape(target)}\b")
        changes: list[dict[str, Any]] = []
        for path in self._iter_source_files():
            text = path.read_text(encoding="utf-8", errors="ignore")
            matches = list(pattern.finditer(text))
            if not matches:
                continue
            updated = pattern.sub(replacement, text)
            if apply and updated != text:
                path.write_text(updated, encoding="utf-8")
            changes.append({"path": str(path), "occurrences": len(matches), "source": "scan"})

        return {
            "symbol": target,
            "new_name": replacement,
            "backend": "scan",
            "applied": bool(apply),
            "files_changed": len(changes),
            "occurrences": sum(int(item["occurrences"]) for item in changes),
            "changes": changes,
        }
