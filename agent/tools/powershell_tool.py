from __future__ import annotations

import asyncio
import os
import subprocess
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from agent.contracts import ToolContext, ToolDef, ToolMetadata
from agent.errors import ToolInterruptedError

from .shell_safety import assert_command_safe


class PowerShellTool(ToolDef):
    metadata = ToolMetadata(name="PowerShellTool")
    input_schema = {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "timeout_ms": {"type": "integer"},
            "workdir": {"type": "string"},
            "env": {"type": "object"},
        },
        "required": ["command"],
    }
    output_schema = {"type": "object"}

    def validate_input(self, args: Mapping[str, Any]) -> None:
        timeout_ms = int(args.get("timeout_ms", 30_000))
        if timeout_ms <= 0:
            raise ValueError("timeout_ms must be > 0")
        command = str(args.get("command", "")).strip()
        if not command:
            raise ValueError("command must not be empty")
        assert_command_safe(command, shell="powershell")

    async def call(
        self,
        args: Mapping[str, Any],
        context: ToolContext | None,
        can_use_tool: Callable[[str], bool] | None,
        parent_message: Mapping[str, Any] | None,
        on_progress,
    ) -> Any:
        _ = context, can_use_tool, parent_message
        command = str(args["command"])
        timeout_ms = int(args.get("timeout_ms", 30_000))
        timeout_s = timeout_ms / 1000.0
        workdir_input = args.get("workdir")
        cwd = str(Path(str(workdir_input)).expanduser().resolve()) if workdir_input is not None else None

        raw_env = args.get("env")
        env = os.environ.copy()
        if isinstance(raw_env, Mapping):
            for key, value in raw_env.items():
                env[str(key)] = str(value)

        started_at = time.perf_counter()
        process = subprocess.Popen(
            [
                "powershell",
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command,
            ],
            shell=False,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        on_progress(
            {
                "event": "tool_progress",
                "tool": self.metadata.name,
                "stage": "spawned",
                "pid": process.pid,
            }
        )

        timed_out = False
        interrupted = False
        try:
            deadline = time.perf_counter() + timeout_s
            while process.poll() is None:
                if time.perf_counter() >= deadline:
                    timed_out = True
                    interrupted = True
                    process.kill()
                    break
                await asyncio.sleep(0.05)
            stdout, stderr = await asyncio.to_thread(process.communicate)
        except subprocess.TimeoutExpired:
            timed_out = True
            interrupted = True
            if process.poll() is None:
                process.kill()
            stdout, stderr = await asyncio.to_thread(process.communicate)
        except asyncio.CancelledError as exc:
            interrupted = True
            if process.poll() is None:
                process.kill()
            try:
                await asyncio.wait_for(asyncio.to_thread(process.communicate), timeout=1.0)
            except Exception:
                pass
            on_progress(
                {
                    "event": "tool_progress",
                    "tool": self.metadata.name,
                    "stage": "interrupted",
                    "pid": process.pid,
                }
            )
            raise ToolInterruptedError("PowerShell tool execution interrupted") from exc

        if not isinstance(stdout, str):
            stdout = str(stdout or "")
        if not isinstance(stderr, str):
            stderr = str(stderr or "")

        for line in stdout.splitlines(keepends=True):
            on_progress(
                {
                    "event": "tool_progress",
                    "tool": self.metadata.name,
                    "stream": "stdout",
                    "chunk": line,
                }
            )
        for line in stderr.splitlines(keepends=True):
            on_progress(
                {
                    "event": "tool_progress",
                    "tool": self.metadata.name,
                    "stream": "stderr",
                    "chunk": line,
                }
            )

        duration_ms = int((time.perf_counter() - started_at) * 1000)
        exit_code = int(process.returncode) if process.returncode is not None else -1
        on_progress(
            {
                "event": "tool_progress",
                "tool": self.metadata.name,
                "stage": "completed",
                "pid": process.pid,
                "exit_code": exit_code,
                "timed_out": timed_out,
            }
        )
        return {
            "command": command,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "timed_out": timed_out,
            "interrupted": interrupted,
            "duration_ms": duration_ms,
        }
