from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping


@dataclass(slots=True, frozen=True)
class ToolMetadata:
    name: str
    aliases: list[str] = field(default_factory=list)
    search_hint: str | None = None
    strict: bool = True
    max_result_size_chars: int | None = None


@dataclass(slots=True)
class ToolContext:
    session_id: str | None = None
    task_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


ProgressCallback = Callable[[dict[str, Any]], None]


class ToolDef(ABC):
    metadata: ToolMetadata
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any]

    def validate_input(self, args: Mapping[str, Any]) -> None:
        return None

    def check_permissions(self, _args: Mapping[str, Any], _context: ToolContext | None = None) -> None:
        return None

    def is_concurrency_safe(self) -> bool:
        return True

    def is_read_only(self) -> bool:
        return False

    def is_destructive(self) -> bool:
        return False

    def user_facing_name(self) -> str:
        return self.metadata.name

    def get_tool_use_summary(self, args: Mapping[str, Any]) -> str:
        return f"{self.metadata.name} args={dict(args)}"

    def get_activity_description(self, args: Mapping[str, Any]) -> str:
        return self.get_tool_use_summary(args)

    def map_tool_result_to_tool_result_block_param(self, result: Any) -> dict[str, Any]:
        return {"status": "success", "content": result}

    def render_tool_use_message(self, args: Mapping[str, Any]) -> str:
        return self.get_tool_use_summary(args)

    def render_tool_result_message(self, result: Any) -> str:
        return f"{self.metadata.name} -> {result}"

    @abstractmethod
    def call(
        self,
        args: Mapping[str, Any],
        context: ToolContext | None,
        can_use_tool: Callable[[str], bool] | None,
        parent_message: Mapping[str, Any] | None,
        on_progress: ProgressCallback,
    ) -> Any:
        raise NotImplementedError
