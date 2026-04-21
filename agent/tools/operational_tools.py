from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import subprocess
import time
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from agent.contracts import ToolContext, ToolDef, ToolMetadata


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _store_root(context: ToolContext | None) -> Path:
    metadata = context.metadata if context is not None else {}
    explicit = metadata.get("ops_store_root")
    path = Path(str(explicit)).expanduser().resolve() if explicit else (Path.cwd() / ".claude" / "python-agent" / "ops").resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _store_file(context: ToolContext | None, *, key: str, default_name: str) -> Path:
    metadata = context.metadata if context is not None else {}
    explicit = metadata.get(key)
    path = Path(str(explicit)).expanduser().resolve() if explicit else (_store_root(context) / default_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return dict(default)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(default)
    return payload if isinstance(payload, dict) else dict(default)


def _save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class SimpleOpTool(ToolDef):
    output_schema = {"type": "object"}

    def __init__(
        self,
        *,
        name: str,
        input_schema: Mapping[str, Any],
        handler: Callable[[Mapping[str, Any], ToolContext | None], Any],
        read_only: bool = False,
        destructive: bool = False,
    ) -> None:
        self.metadata = ToolMetadata(name=name)
        self.input_schema = input_schema
        self._handler = handler
        self._read_only = read_only
        self._destructive = destructive

    def is_read_only(self) -> bool:
        return self._read_only

    def is_destructive(self) -> bool:
        return self._destructive

    async def call(self, args, context, can_use_tool, parent_message, on_progress):
        _ = can_use_tool, parent_message
        value = self._handler(args, context)
        if asyncio.iscoroutine(value):
            value = await value
        on_progress({"event": "tool_progress", "tool": self.metadata.name, "stage": "done"})
        return value


def _event_append(context: ToolContext | None, *, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    path = _store_file(context, key="event_store_file", default_name="events.json")
    data = _load_json(path, {"events": []})
    events = data.get("events", [])
    if not isinstance(events, list):
        events = []
    event = {"id": f"evt-{uuid.uuid4().hex[:10]}", "kind": kind, "payload": payload, "created_at": _now_iso()}
    events.append(event)
    data["events"] = events[-500:]
    _save_json(path, data)
    return event


def _team_create(args: Mapping[str, Any], context: ToolContext | None) -> dict[str, Any]:
    path = _store_file(context, key="team_store_file", default_name="teams.json")
    data = _load_json(path, {"teams": {}})
    teams = dict(data.get("teams", {}))
    name = str(args["name"]).strip()
    members_raw = args.get("members", [])
    members = [str(m).strip() for m in members_raw if str(m).strip()] if isinstance(members_raw, list) else []
    teams[name] = {"members": sorted(set(members)), "updated_at": _now_iso()}
    data["teams"] = teams
    _save_json(path, data)
    return {"name": name, "members": teams[name]["members"], "count": len(teams)}


def _team_delete(args: Mapping[str, Any], context: ToolContext | None) -> dict[str, Any]:
    path = _store_file(context, key="team_store_file", default_name="teams.json")
    data = _load_json(path, {"teams": {}})
    teams = dict(data.get("teams", {}))
    name = str(args["name"]).strip()
    deleted = name in teams
    teams.pop(name, None)
    data["teams"] = teams
    _save_json(path, data)
    return {"name": name, "deleted": deleted, "count": len(teams)}


def _list_peers(args: Mapping[str, Any], context: ToolContext | None) -> dict[str, Any]:
    path = _store_file(context, key="team_store_file", default_name="teams.json")
    data = _load_json(path, {"teams": {}})
    teams = dict(data.get("teams", {}))
    team = str(args.get("team", "")).strip()
    if team:
        peers = [str(m) for m in teams.get(team, {}).get("members", [])]
    else:
        peers = sorted({str(m) for item in teams.values() if isinstance(item, dict) for m in item.get("members", [])})
    return {"team": team or None, "peers": peers, "count": len(peers)}


def _task_file(context: ToolContext | None) -> Path:
    return _store_file(context, key="task_state_file", default_name="tasks.json")


def _task_create(args: Mapping[str, Any], context: ToolContext | None) -> dict[str, Any]:
    path = _task_file(context)
    data = _load_json(path, {"tasks": {}})
    tasks = dict(data.get("tasks", {}))
    task_id = f"plan-{uuid.uuid4().hex[:8]}"
    tasks[task_id] = {"id": task_id, "title": str(args["title"]).strip(), "description": str(args.get("description", "")), "status": str(args.get("status", "pending")), "updated_at": _now_iso()}
    data["tasks"] = tasks
    _save_json(path, data)
    return tasks[task_id]


def _task_get(args: Mapping[str, Any], context: ToolContext | None) -> dict[str, Any]:
    data = _load_json(_task_file(context), {"tasks": {}})
    return {"task": data.get("tasks", {}).get(str(args["task_id"]).strip())}


def _task_update(args: Mapping[str, Any], context: ToolContext | None) -> dict[str, Any]:
    path = _task_file(context)
    data = _load_json(path, {"tasks": {}})
    tasks = dict(data.get("tasks", {}))
    task_id = str(args["task_id"]).strip()
    task = dict(tasks.get(task_id, {}))
    if not task:
        return {"updated": False, "task": None}
    if "status" in args:
        task["status"] = str(args["status"])
    if "description" in args:
        task["description"] = str(args["description"])
    task["updated_at"] = _now_iso()
    tasks[task_id] = task
    data["tasks"] = tasks
    _save_json(path, data)
    return {"updated": True, "task": task}


def _task_list(args: Mapping[str, Any], context: ToolContext | None) -> dict[str, Any]:
    data = _load_json(_task_file(context), {"tasks": {}})
    wanted = str(args.get("status", "")).strip()
    tasks = [dict(t) for t in data.get("tasks", {}).values() if isinstance(t, dict) and (not wanted or str(t.get("status", "")) == wanted)]
    return {"tasks": tasks, "count": len(tasks)}


def _verify_plan(_args: Mapping[str, Any], context: ToolContext | None) -> dict[str, Any]:
    data = _load_json(_task_file(context), {"tasks": {}})
    tasks = [t for t in data.get("tasks", {}).values() if isinstance(t, dict)]
    completed = [t for t in tasks if str(t.get("status", "")) == "completed"]
    return {"passed": bool(tasks) and len(tasks) == len(completed), "total": len(tasks), "completed": len(completed)}


def _web_browser(args: Mapping[str, Any], _context: ToolContext | None) -> dict[str, Any]:
    url = str(args["url"]).strip()
    timeout_s = int(args.get("timeout_s", 8))
    request = Request(url, headers={"User-Agent": "python-agent-web-browser/0.1"})
    with urlopen(request, timeout=timeout_s) as response:
        text = response.read(50_000).decode("utf-8", errors="ignore")
    low = text.lower()
    s = low.find("<title>")
    e = low.find("</title>")
    title = text[s + 7 : e].strip() if s >= 0 and e > s else ""
    return {"url": url, "title": title, "content_preview": text[:400]}


async def _sleep(args: Mapping[str, Any], _context: ToolContext | None) -> dict[str, Any]:
    seconds = max(0.0, min(5.0, float(args.get("seconds", 0.05))))
    await asyncio.sleep(seconds)
    return {"slept_seconds": seconds}


def _brief(args: Mapping[str, Any], _context: ToolContext | None) -> dict[str, Any]:
    text = str(args.get("text", ""))
    return {"summary": text if len(text) <= 240 else text[:237] + "...", "length": len(text)}


def _snip(args: Mapping[str, Any], _context: ToolContext | None) -> dict[str, Any]:
    path = Path(str(args["path"])).expanduser().resolve()
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    start = max(1, int(args.get("start_line", 1)))
    end = min(len(lines), int(args.get("end_line", min(len(lines), start + 20))))
    return {"path": str(path), "start_line": start, "end_line": end, "snippet": "\n".join(lines[start - 1 : end])}


def _ctx_inspect(_args: Mapping[str, Any], context: ToolContext | None) -> dict[str, Any]:
    return {"session_id": context.session_id if context else None, "task_id": context.task_id if context else None, "metadata": dict(context.metadata) if context else {}}


def _terminal_capture(args: Mapping[str, Any], _context: ToolContext | None) -> dict[str, Any]:
    command = str(args["command"]).strip()
    timeout_s = max(1, int(args.get("timeout_s", 10)))
    cwd = str(Path(str(args["workdir"])).expanduser().resolve()) if args.get("workdir") else None
    proc = subprocess.run(command, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout_s)
    return {"command": command, "returncode": int(proc.returncode), "stdout": proc.stdout, "stderr": proc.stderr}


def _monitor(args: Mapping[str, Any], _context: ToolContext | None) -> dict[str, Any]:
    return {"metric": str(args.get("name", "heartbeat")), "value": args.get("value"), "timestamp": _now_iso()}


def _copy_file(args: Mapping[str, Any], _context: ToolContext | None) -> dict[str, Any]:
    source = Path(str(args["source"])).expanduser().resolve()
    destination = Path(str(args["destination"])).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return {"source": str(source), "destination": str(destination), "bytes": destination.stat().st_size}


def _review_artifact(args: Mapping[str, Any], _context: ToolContext | None) -> dict[str, Any]:
    path = Path(str(args["path"])).expanduser().resolve()
    content = path.read_bytes()
    return {"path": str(path), "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(), "preview": content[:300].decode("utf-8", errors="ignore")}


def _cron_create(args: Mapping[str, Any], context: ToolContext | None) -> dict[str, Any]:
    path = _store_file(context, key="cron_store_file", default_name="cron.json")
    data = _load_json(path, {"jobs": {}})
    jobs = dict(data.get("jobs", {}))
    job_id = f"cron-{uuid.uuid4().hex[:8]}"
    jobs[job_id] = {"id": job_id, "schedule": str(args["schedule"]), "command": str(args["command"]), "updated_at": _now_iso()}
    data["jobs"] = jobs
    _save_json(path, data)
    return jobs[job_id]


def _cron_delete(args: Mapping[str, Any], context: ToolContext | None) -> dict[str, Any]:
    path = _store_file(context, key="cron_store_file", default_name="cron.json")
    data = _load_json(path, {"jobs": {}})
    jobs = dict(data.get("jobs", {}))
    job_id = str(args["job_id"]).strip()
    deleted = job_id in jobs
    jobs.pop(job_id, None)
    data["jobs"] = jobs
    _save_json(path, data)
    return {"job_id": job_id, "deleted": deleted, "count": len(jobs)}


def _cron_list(_args: Mapping[str, Any], context: ToolContext | None) -> dict[str, Any]:
    data = _load_json(_store_file(context, key="cron_store_file", default_name="cron.json"), {"jobs": {}})
    jobs = [dict(item) for item in data.get("jobs", {}).values() if isinstance(item, dict)]
    return {"jobs": jobs, "count": len(jobs)}


def _config(args: Mapping[str, Any], context: ToolContext | None) -> dict[str, Any]:
    path = _store_file(context, key="config_store_file", default_name="config.json")
    data = _load_json(path, {"config": {}})
    config = dict(data.get("config", {}))
    action = str(args["action"]).strip().lower()
    key = str(args.get("key", "")).strip()
    if action == "get":
        return {"key": key, "value": config.get(key)}
    if action == "set":
        config[key] = args.get("value")
        data["config"] = config
        _save_json(path, data)
        return {"updated": True, "key": key, "value": config.get(key)}
    if action == "unset":
        existed = key in config
        config.pop(key, None)
        data["config"] = config
        _save_json(path, data)
        return {"updated": existed, "key": key}
    raise ValueError("action must be one of: get, set, unset")


def _tungsten(args: Mapping[str, Any], _context: ToolContext | None) -> dict[str, Any]:
    text = str(args["input"])
    return {"input_length": len(text), "sha1": hashlib.sha1(text.encode("utf-8")).hexdigest()}


def _repl(args: Mapping[str, Any], _context: ToolContext | None) -> dict[str, Any]:
    expression = str(args["expression"])
    safe_globals = {"__builtins__": {"abs": abs, "min": min, "max": max, "sum": sum, "len": len}}
    return {"expression": expression, "result": eval(expression, safe_globals, {})}


def _overflow(args: Mapping[str, Any], _context: ToolContext | None) -> dict[str, Any]:
    size = max(1, min(20_000, int(args.get("size", 4096))))
    char = (str(args.get("char", "x"))[:1] or "x")
    return {"size": size, "content": char * size}


def _testing_permission(args: Mapping[str, Any], _context: ToolContext | None) -> dict[str, Any]:
    return {"allow": bool(args.get("allow", True)), "reason": str(args.get("reason", ""))}


def _synthetic_output(args: Mapping[str, Any], _context: ToolContext | None) -> dict[str, Any]:
    return {"status": str(args.get("status", "success")).strip() or "success", "content": args.get("content", {})}


def build_operational_tools() -> dict[str, ToolDef]:
    tools: dict[str, ToolDef] = {
        "TeamCreateTool": SimpleOpTool(name="TeamCreateTool", input_schema={"type": "object", "properties": {"name": {"type": "string"}, "members": {"type": "array"}}, "required": ["name"]}, handler=_team_create),
        "TeamDeleteTool": SimpleOpTool(name="TeamDeleteTool", input_schema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}, handler=_team_delete, destructive=True),
        "ListPeersTool": SimpleOpTool(name="ListPeersTool", input_schema={"type": "object", "properties": {"team": {"type": "string"}}, "required": []}, handler=_list_peers, read_only=True),
        "TaskCreateTool": SimpleOpTool(name="TaskCreateTool", input_schema={"type": "object", "properties": {"title": {"type": "string"}, "description": {"type": "string"}, "status": {"type": "string"}}, "required": ["title"]}, handler=_task_create),
        "TaskGetTool": SimpleOpTool(name="TaskGetTool", input_schema={"type": "object", "properties": {"task_id": {"type": "string"}}, "required": ["task_id"]}, handler=_task_get, read_only=True),
        "TaskUpdateTool": SimpleOpTool(name="TaskUpdateTool", input_schema={"type": "object", "properties": {"task_id": {"type": "string"}, "status": {"type": "string"}, "description": {"type": "string"}}, "required": ["task_id"]}, handler=_task_update),
        "TaskListTool": SimpleOpTool(name="TaskListTool", input_schema={"type": "object", "properties": {"status": {"type": "string"}}, "required": []}, handler=_task_list, read_only=True),
        "VerifyPlanExecutionTool": SimpleOpTool(name="VerifyPlanExecutionTool", input_schema={"type": "object", "properties": {}, "required": []}, handler=_verify_plan, read_only=True),
        "WebBrowserTool": SimpleOpTool(name="WebBrowserTool", input_schema={"type": "object", "properties": {"url": {"type": "string"}, "timeout_s": {"type": "integer"}}, "required": ["url"]}, handler=_web_browser, read_only=True),
        "SkillTool": SimpleOpTool(name="SkillTool", input_schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": []}, handler=lambda _a, _c: {"status": "available", "hint": "use Skill docs path"}, read_only=True),
        "WorkflowTool": SimpleOpTool(name="WorkflowTool", input_schema={"type": "object", "properties": {"steps": {"type": "array"}, "name": {"type": "string"}}, "required": []}, handler=lambda a, _c: {"name": str(a.get("name", "workflow")), "steps": [str(s) for s in a.get("steps", [])], "executed": len(a.get("steps", []))}),
        "SleepTool": SimpleOpTool(name="SleepTool", input_schema={"type": "object", "properties": {"seconds": {"type": "number"}}, "required": []}, handler=_sleep, read_only=True),
        "BriefTool": SimpleOpTool(name="BriefTool", input_schema={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}, handler=_brief, read_only=True),
        "SnipTool": SimpleOpTool(name="SnipTool", input_schema={"type": "object", "properties": {"path": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}}, "required": ["path"]}, handler=_snip, read_only=True),
        "CtxInspectTool": SimpleOpTool(name="CtxInspectTool", input_schema={"type": "object", "properties": {}, "required": []}, handler=_ctx_inspect, read_only=True),
        "TerminalCaptureTool": SimpleOpTool(name="TerminalCaptureTool", input_schema={"type": "object", "properties": {"command": {"type": "string"}, "timeout_s": {"type": "integer"}, "workdir": {"type": "string"}}, "required": ["command"]}, handler=_terminal_capture, read_only=True),
        "MonitorTool": SimpleOpTool(name="MonitorTool", input_schema={"type": "object", "properties": {"name": {"type": "string"}, "value": {}}, "required": []}, handler=_monitor, read_only=True),
        "RemoteTriggerTool": SimpleOpTool(name="RemoteTriggerTool", input_schema={"type": "object", "properties": {"target": {"type": "string"}, "payload": {"type": "object"}}, "required": ["target"]}, handler=lambda a, c: {"triggered": True, "event": _event_append(c, kind="remote_trigger", payload={"target": str(a["target"]), "payload": dict(a.get("payload", {}))})}),
        "PushNotificationTool": SimpleOpTool(name="PushNotificationTool", input_schema={"type": "object", "properties": {"title": {"type": "string"}, "body": {"type": "string"}}, "required": ["title"]}, handler=lambda a, c: {"sent": True, "event": _event_append(c, kind="push_notification", payload={"title": str(a["title"]), "body": str(a.get("body", ""))})}),
        "SubscribePRTool": SimpleOpTool(name="SubscribePRTool", input_schema={"type": "object", "properties": {"repo": {"type": "string"}, "pr": {"type": "integer"}}, "required": ["repo", "pr"]}, handler=lambda a, c: {"subscribed": True, "event": _event_append(c, kind="subscribe_pr", payload={"repo": str(a["repo"]), "pr": int(a["pr"])})}),
        "SuggestBackgroundPRTool": SimpleOpTool(name="SuggestBackgroundPRTool", input_schema={"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}, handler=lambda a, c: {"suggested": True, "event": _event_append(c, kind="suggest_background_pr", payload={"summary": str(a["summary"])})}),
        "SendUserFileTool": SimpleOpTool(name="SendUserFileTool", input_schema={"type": "object", "properties": {"source": {"type": "string"}, "destination": {"type": "string"}}, "required": ["source", "destination"]}, handler=_copy_file, destructive=True),
        "ReviewArtifactTool": SimpleOpTool(name="ReviewArtifactTool", input_schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}, handler=_review_artifact, read_only=True),
        "CronCreateTool": SimpleOpTool(name="CronCreateTool", input_schema={"type": "object", "properties": {"schedule": {"type": "string"}, "command": {"type": "string"}}, "required": ["schedule", "command"]}, handler=_cron_create),
        "CronDeleteTool": SimpleOpTool(name="CronDeleteTool", input_schema={"type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"]}, handler=_cron_delete, destructive=True),
        "CronListTool": SimpleOpTool(name="CronListTool", input_schema={"type": "object", "properties": {}, "required": []}, handler=_cron_list, read_only=True),
        "ConfigTool": SimpleOpTool(name="ConfigTool", input_schema={"type": "object", "properties": {"action": {"type": "string"}, "key": {"type": "string"}, "value": {}}, "required": ["action"]}, handler=_config),
        "TungstenTool": SimpleOpTool(name="TungstenTool", input_schema={"type": "object", "properties": {"input": {"type": "string"}}, "required": ["input"]}, handler=_tungsten),
        "REPLTool": SimpleOpTool(name="REPLTool", input_schema={"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]}, handler=_repl),
        "OverflowTestTool": SimpleOpTool(name="OverflowTestTool", input_schema={"type": "object", "properties": {"size": {"type": "integer"}, "char": {"type": "string"}}, "required": []}, handler=_overflow, read_only=True),
        "TestingPermissionTool": SimpleOpTool(name="TestingPermissionTool", input_schema={"type": "object", "properties": {"allow": {"type": "boolean"}, "reason": {"type": "string"}}, "required": []}, handler=_testing_permission),
        "SyntheticOutputTool": SimpleOpTool(name="SyntheticOutputTool", input_schema={"type": "object", "properties": {"status": {"type": "string"}, "content": {}}, "required": []}, handler=_synthetic_output, read_only=True),
    }
    return tools
