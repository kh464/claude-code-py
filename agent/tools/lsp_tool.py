from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from agent.contracts import ToolContext, ToolDef, ToolMetadata
from agent.semantic import LSPClient, SemanticIndex
from agent.semantic.lsp_client import StdioLSPClient


class LSPTool(ToolDef):
    metadata = ToolMetadata(name="LSPTool")
    input_schema = {
        "type": "object",
        "properties": {
            "operation": {"type": "string"},
            "symbol": {"type": "string"},
            "path": {"type": "string"},
            "target_path": {"type": "string"},
            "strict": {"type": "boolean"},
            "new_name": {"type": "string"},
            "apply": {"type": "boolean"},
            "start_line": {"type": "integer"},
            "start_character": {"type": "integer"},
            "end_line": {"type": "integer"},
            "end_character": {"type": "integer"},
            "kinds": {"type": "array"},
            "action_index": {"type": "integer"},
            "action_title": {"type": "string"},
        },
        "required": ["operation"],
    }
    output_schema = {"type": "object"}

    def validate_input(self, args: Mapping[str, Any]) -> None:
        operation = str(args.get("operation", ""))
        if operation not in {
            "find_symbol",
            "find_references",
            "find_diagnostics",
            "rename_symbol",
            "list_refactors",
            "apply_refactor",
            "capabilities",
        }:
            raise ValueError(
                "operation must be one of: find_symbol, find_references, find_diagnostics, "
                "rename_symbol, list_refactors, apply_refactor, capabilities"
            )
        if operation in {"find_symbol", "find_references", "rename_symbol"}:
            symbol = str(args.get("symbol", "")).strip()
            if not symbol:
                raise ValueError("symbol must not be empty")
        if operation == "rename_symbol":
            new_name = str(args.get("new_name", "")).strip()
            if not new_name:
                raise ValueError("new_name must not be empty")
        if operation in {"list_refactors", "apply_refactor"}:
            raw_path = str(args.get("path", "")).strip()
            if not raw_path:
                raise ValueError("path must not be empty")
            for key in ("start_line", "start_character", "end_line", "end_character"):
                if key not in args:
                    raise ValueError(f"{key} is required for refactor operations")

    def is_read_only(self) -> bool:
        return True

    def _resolve_root(self, args: Mapping[str, Any], context: ToolContext | None) -> Path:
        if args.get("path"):
            candidate = Path(str(args["path"])).expanduser().resolve()
            return candidate.parent if candidate.is_file() else candidate
        metadata = context.metadata if context is not None else {}
        if metadata.get("current_cwd"):
            return Path(str(metadata["current_cwd"])).expanduser().resolve()
        return Path.cwd().resolve()

    def _resolve_lsp_client(self, context: ToolContext | None) -> LSPClient | None:
        metadata = context.metadata if context is not None else {}
        client = metadata.get("lsp_client")
        if isinstance(client, LSPClient):
            return client
        command_raw = metadata.get("lsp_command")
        command: list[str] = []
        if isinstance(command_raw, str) and command_raw.strip():
            command = [command_raw.strip()]
        elif isinstance(command_raw, list):
            command = [str(part).strip() for part in command_raw if str(part).strip()]
        if command:
            timeout_s = float(metadata.get("lsp_timeout_s", 8.0))
            return StdioLSPClient(command=command, timeout_s=timeout_s)
        return None

    @staticmethod
    def _resolve_strict_mode(
        *,
        args: Mapping[str, Any],
        context: ToolContext | None,
        has_lsp_client: bool,
    ) -> bool:
        if "strict" in args:
            return bool(args.get("strict"))
        metadata = context.metadata if context is not None else {}
        if "lsp_strict" in metadata:
            return bool(metadata.get("lsp_strict"))
        # When an LSP client/command is configured, default to strict mode so
        # caller immediately sees transport/setup failures instead of scan fallback.
        return has_lsp_client

    async def call(
        self,
        args: Mapping[str, Any],
        context: ToolContext | None,
        can_use_tool: Callable[[str], bool] | None,
        parent_message: Mapping[str, Any] | None,
        on_progress,
    ) -> Any:
        _ = can_use_tool, parent_message
        on_progress({"event": "tool_progress", "tool": self.metadata.name, "stage": "indexing"})
        symbol = str(args.get("symbol", "")).strip()
        operation = str(args["operation"])
        lsp_client = self._resolve_lsp_client(context)
        strict_lsp = self._resolve_strict_mode(args=args, context=context, has_lsp_client=lsp_client is not None)
        if strict_lsp and lsp_client is None:
            raise ValueError("strict LSP mode requires lsp_client or lsp_command configuration")
        index = SemanticIndex(
            root=self._resolve_root(args, context),
            lsp_client=lsp_client,
            strict_lsp=strict_lsp,
        )
        if operation == "find_symbol":
            return {
                "operation": operation,
                "symbol": symbol,
                "backend": "lsp_or_scan",
                "definitions": index.find_symbol(symbol),
            }
        if operation == "find_references":
            return {
                "operation": operation,
                "symbol": symbol,
                "backend": "lsp_or_scan",
                "references": index.find_references(symbol),
            }
        if operation == "rename_symbol":
            new_name = str(args.get("new_name", "")).strip()
            rename_result = index.rename_symbol(
                symbol=symbol,
                new_name=new_name,
                apply=bool(args.get("apply", False)),
            )
            return {
                "operation": operation,
                "symbol": symbol,
                "new_name": new_name,
                **rename_result,
            }
        if operation == "list_refactors":
            kinds_raw = args.get("kinds", [])
            kinds = [str(item).strip() for item in kinds_raw if str(item).strip()] if isinstance(kinds_raw, list) else []
            actions = index.list_refactor_actions(
                path=str(args["path"]),
                start_line=int(args["start_line"]),
                start_character=int(args["start_character"]),
                end_line=int(args["end_line"]),
                end_character=int(args["end_character"]),
                kinds=kinds or None,
            )
            return {
                "operation": operation,
                "path": str(Path(str(args["path"])).expanduser().resolve()),
                "actions": actions,
                "count": len(actions),
            }
        if operation == "apply_refactor":
            kinds_raw = args.get("kinds", [])
            kinds = [str(item).strip() for item in kinds_raw if str(item).strip()] if isinstance(kinds_raw, list) else []
            raw_target_path = str(args.get("target_path", "")).strip()
            outcome = index.apply_refactor_action(
                path=str(args["path"]),
                target_path=raw_target_path or None,
                start_line=int(args["start_line"]),
                start_character=int(args["start_character"]),
                end_line=int(args["end_line"]),
                end_character=int(args["end_character"]),
                kinds=kinds or None,
                action_index=int(args["action_index"]) if args.get("action_index") is not None else None,
                action_title=str(args["action_title"]).strip() if args.get("action_title") is not None else None,
                apply=bool(args.get("apply", False)),
            )
            return {
                "operation": operation,
                "path": str(Path(str(args["path"])).expanduser().resolve()),
                **outcome,
            }
        if operation == "capabilities":
            outcome = index.describe_lsp_capabilities(
                path=args.get("path"),
                start_line=int(args["start_line"]) if args.get("start_line") is not None else None,
                start_character=int(args["start_character"]) if args.get("start_character") is not None else None,
                end_line=int(args["end_line"]) if args.get("end_line") is not None else None,
                end_character=int(args["end_character"]) if args.get("end_character") is not None else None,
            )
            return {
                "operation": operation,
                **outcome,
            }
        diagnostics = index.find_diagnostics(path=args.get("path"))
        return {
            "operation": operation,
            "backend": "lsp_or_scan",
            "diagnostics": diagnostics,
            "count": len(diagnostics),
        }
