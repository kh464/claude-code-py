from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path


class VerificationRunner:
    async def run(self, *, workdir: str, commands: list[str]) -> dict:
        results: list[dict] = []
        cwd = str(Path(workdir).expanduser().resolve())
        if not commands:
            return {
                "status": "skipped",
                "workdir": cwd,
                "results": results,
                "reason": "no verification commands configured",
            }
        overall_status = "passed"

        for command in commands:
            process = await asyncio.to_thread(
                subprocess.run,
                command,
                cwd=cwd,
                shell=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
            )
            returncode = int(process.returncode or 0)
            passed = returncode == 0
            if not passed:
                overall_status = "failed"
            results.append(
                {
                    "command": command,
                    "returncode": returncode,
                    "passed": passed,
                    "stdout": str(process.stdout or ""),
                    "stderr": str(process.stderr or ""),
                }
            )

        return {
            "status": overall_status,
            "workdir": cwd,
            "results": results,
        }

    @staticmethod
    def is_passed(result: dict) -> bool:
        return str(result.get("status", "")).lower() in {"passed", "skipped"}
