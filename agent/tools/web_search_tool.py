from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from agent.contracts import ToolContext, ToolDef, ToolMetadata


def _flatten_related_topics(items: list[dict]) -> list[dict]:
    flattened: list[dict] = []
    for item in items:
        if "Topics" in item and isinstance(item["Topics"], list):
            flattened.extend(_flatten_related_topics(item["Topics"]))
            continue
        flattened.append(item)
    return flattened


def perform_search_request(*, query: str, timeout_s: int) -> dict:
    encoded_query = quote_plus(query)
    url = f"https://api.duckduckgo.com/?q={encoded_query}&format=json&no_html=1&skip_disambig=1"
    request = Request(url, headers={"User-Agent": "python-full-tooling-agent/0.1"})
    with urlopen(request, timeout=timeout_s) as response:
        payload = json.loads(response.read().decode("utf-8", errors="ignore"))

    results: list[dict] = []
    abstract = str(payload.get("AbstractText") or "").strip()
    abstract_url = str(payload.get("AbstractURL") or "").strip()
    if abstract and abstract_url:
        results.append(
            {
                "title": str(payload.get("Heading") or query),
                "url": abstract_url,
                "snippet": abstract,
            }
        )

    topics = _flatten_related_topics(payload.get("RelatedTopics", []))
    for topic in topics:
        text = str(topic.get("Text") or "").strip()
        first_url = str(topic.get("FirstURL") or "").strip()
        if not text or not first_url:
            continue
        title = text.split(" - ", 1)[0]
        results.append({"title": title, "url": first_url, "snippet": text})

    return {"query": query, "results": results}


class WebSearchTool(ToolDef):
    metadata = ToolMetadata(name="WebSearchTool")
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "timeout_s": {"type": "integer"},
            "max_results": {"type": "integer"},
        },
        "required": ["query"],
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
        query = str(args["query"]).strip()
        timeout_s = int(args.get("timeout_s", 10))
        max_results = int(args.get("max_results", 5))

        on_progress({"event": "tool_progress", "tool": self.metadata.name, "stage": "searching", "query": query})
        payload = perform_search_request(query=query, timeout_s=timeout_s)
        return {
            "query": payload["query"],
            "results": list(payload["results"])[:max_results],
        }
