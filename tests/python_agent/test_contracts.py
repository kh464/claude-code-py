from __future__ import annotations

from dataclasses import dataclass

from agent.contracts import ToolDef, ToolMetadata


@dataclass
class DummyTool(ToolDef):
    metadata: ToolMetadata = ToolMetadata(name="DummyTool")

    input_schema = {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]}
    output_schema = {"type": "object"}

    def call(self, args, context, can_use_tool, parent_message, on_progress):
        return {"echo": args["value"]}


def test_tool_metadata_defaults_are_present() -> None:
    tool = DummyTool()
    assert tool.metadata.name == "DummyTool"
    assert tool.metadata.strict is True
    assert isinstance(tool.metadata.aliases, list)


def test_tool_contract_default_renderers() -> None:
    tool = DummyTool()
    assert tool.user_facing_name() == "DummyTool"
    assert "DummyTool" in tool.get_tool_use_summary({"value": "x"})
    mapped = tool.map_tool_result_to_tool_result_block_param({"echo": "ok"})
    assert mapped["status"] == "success"
