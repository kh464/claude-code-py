from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any
from urllib.request import Request, urlopen

from agent.contracts import ToolContext, ToolDef, ToolMetadata


class WebFetchTool(ToolDef):
    metadata = ToolMetadata(name="WebFetchTool")
    input_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "timeout_s": {"type": "integer"},
            "max_bytes": {"type": "integer"},
        },
        "required": ["url"],
    }
    output_schema = {"type": "object"}

    def is_read_only(self) -> bool:
        return True

    async def call(
        self,
        args: Mapping[str, Any],
        context: ToolContext | None,
        can_use_tool: Callable[[str], bool] | None,
        parent_message: Mapping[str, Any] | None,
        on_progress,
    ) -> Any:
        _ = context, can_use_tool, parent_message
        url = str(args["url"]).strip()
        timeout_s = int(args.get("timeout_s", 10))
        max_bytes = int(args.get("max_bytes", 200_000))

        on_progress({"event": "tool_progress", "tool": self.metadata.name, "stage": "fetching", "url": url})
        request = Request(url, headers={"User-Agent": "python-full-tooling-agent/0.1"})
        with urlopen(request, timeout=timeout_s) as response:
            raw = response.read(max_bytes + 1)
            truncated = len(raw) > max_bytes
            body = raw[:max_bytes]
            content = body.decode("utf-8", errors="ignore")
            return {
                "url": url,
                "status_code": int(response.getcode() or 0),
                "content_type": str(response.headers.get("content-type", "")),
                "content": content,
                "truncated": truncated,
                "bytes": len(body),
            }
