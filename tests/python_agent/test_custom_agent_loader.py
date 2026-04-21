from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from agent.subagents.loader import (
    get_active_agents,
    load_agent_markdown_file,
    resolve_agent_tools,
)
from agent.subagents.models import AgentDescriptor


def _create_temp_dir() -> Path:
    root = Path("tests/.tmp-python-agent") / f"agent-loader-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=False)
    return root


def test_load_agent_markdown_parses_frontmatter_and_prompt() -> None:
    temp_root = _create_temp_dir()
    try:
        md_path = temp_root / "reviewer.md"
        md_path.write_text(
            """---
name: reviewer
description: Code review specialist
tools: Read, Glob, Grep, Bash
disallowedTools:
  - Bash
permissionMode: plan
model: inherit
mcpServers:
  - slack
hooks:
  PreToolUse:
    - command: audit-log.sh
---
You are a strict reviewer.
""",
            encoding="utf-8",
        )

        descriptor = load_agent_markdown_file(md_path, source="project")
        assert descriptor is not None
        assert descriptor.name == "reviewer"
        assert descriptor.description == "Code review specialist"
        assert descriptor.tools_allowlist == ["Read", "Glob", "Grep", "Bash"]
        assert descriptor.tools_disallowlist == ["Bash"]
        assert descriptor.permission_mode == "plan"
        assert descriptor.model == "inherit"
        assert descriptor.mcp_servers == ["slack"]
        assert "PreToolUse" in descriptor.hooks
        assert descriptor.system_prompt == "You are a strict reviewer."
        assert descriptor.source == "project"
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_load_agent_markdown_returns_none_without_frontmatter() -> None:
    temp_root = _create_temp_dir()
    try:
        md_path = temp_root / "notes.md"
        md_path.write_text("This is not an agent definition.\n", encoding="utf-8")
        descriptor = load_agent_markdown_file(md_path, source="project")
        assert descriptor is None
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_get_active_agents_applies_project_over_user_override() -> None:
    temp_root = _create_temp_dir()
    try:
        user_dir = temp_root / "user-agents"
        project_dir = temp_root / "project-agents"
        user_dir.mkdir(parents=True, exist_ok=True)
        project_dir.mkdir(parents=True, exist_ok=True)

        (user_dir / "Explore.md").write_text(
            """---
name: Explore
description: User override explore
---
User explore prompt
""",
            encoding="utf-8",
        )
        (project_dir / "Explore.md").write_text(
            """---
name: Explore
description: Project override explore
---
Project explore prompt
""",
            encoding="utf-8",
        )

        agents = get_active_agents(
            include_conditionals=True,
            user_agents_dir=user_dir,
            project_agents_dir=project_dir,
        )
        by_name = {agent.name: agent for agent in agents}
        assert "general-purpose" in by_name
        assert "Explore" in by_name
        assert by_name["Explore"].description == "Project override explore"
        assert by_name["Explore"].source == "project"
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_resolve_agent_tools_supports_short_names_and_deny_list() -> None:
    available = ["BashTool", "FileReadTool", "FileEditTool", "FileWriteTool", "GlobTool", "GrepTool"]
    descriptor = AgentDescriptor(
        name="reviewer",
        tools_allowlist=["Read", "Glob", "Grep", "Bash"],
        tools_disallowlist=["Bash"],
    )

    resolved = resolve_agent_tools(descriptor, available)
    assert resolved == ["FileReadTool", "GlobTool", "GrepTool"]


def test_resolve_agent_tools_with_star_allowlist_keeps_all_minus_disallowed() -> None:
    available = ["BashTool", "FileReadTool", "FileWriteTool", "GlobTool"]
    descriptor = AgentDescriptor(
        name="gp",
        tools_allowlist=["*"],
        tools_disallowlist=["Write"],
    )

    resolved = resolve_agent_tools(descriptor, available)
    assert resolved == ["BashTool", "FileReadTool", "GlobTool"]
