from __future__ import annotations

import re


_BASH_DANGEROUS_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(^|\s)rm\s+-rf\s+/(\s|$)"),
    re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;?\s*:", re.IGNORECASE),
    re.compile(r"(^|\s)mkfs(\.\w+)?\s+", re.IGNORECASE),
    re.compile(r"(^|\s)(shutdown|reboot)\b", re.IGNORECASE),
    re.compile(r"\bdd\s+if=.*\bof=/dev/(sd|nvme|hd)", re.IGNORECASE),
)

_POWERSHELL_DANGEROUS_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"remove-item\b.*-recurse\b.*-force\b.*([a-z]:\\|\\\\)", re.IGNORECASE),
    re.compile(r"\b(clear-disk|format-volume)\b", re.IGNORECASE),
    re.compile(r"\b(stop-computer|restart-computer)\b", re.IGNORECASE),
)


def assert_command_safe(command: str, *, shell: str) -> None:
    normalized = command.strip()
    if not normalized:
        return

    patterns: tuple[re.Pattern[str], ...]
    if shell == "bash":
        patterns = _BASH_DANGEROUS_PATTERNS
    elif shell == "powershell":
        patterns = _POWERSHELL_DANGEROUS_PATTERNS
    else:
        patterns = ()

    for pattern in patterns:
        if pattern.search(normalized):
            raise ValueError(f"dangerous command blocked for {shell} shell")
