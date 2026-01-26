from __future__ import annotations
import time
from typing import Any, Awaitable, Callable

from ..core.types import ToolDefinition, ToolCategory, RiskTier, JsonSchemaField
from .file_tools import make_sandbox, TOOL_DEFINITIONS_FILE
from .terminal_tools import make_terminal_tool
from .browser_tools import make_browser_tools
from .screen_tools import make_screen_tools


_memory_store: dict[str, dict[str, Any]] = {}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


TOOL_DEFINITIONS: list[ToolDefinition] = [
    *TOOL_DEFINITIONS_FILE,
    ToolDefinition(
        name="terminal.exec",
        version="0.1.0",
        description="Run a shell command with timeout and output capture",
        category=ToolCategory.TERMINAL,
        risk_tier=RiskTier.SYSTEM_AFFECTING,
        input_schema=JsonSchemaField(type="object", required=["command"], properties={"command": JsonSchemaField(type="string"), "timeoutMs": JsonSchemaField(type="number")}),
    ),
    ToolDefinition(
        name="browser.open",
        version="0.1.0",
        description="Open a URL and return title/status",
        category=ToolCategory.BROWSER,
        risk_tier=RiskTier.REVERSIBLE_WRITE,
        input_schema=JsonSchemaField(type="object", required=["url"], properties={"url": JsonSchemaField(type="string")}),
    ),
    ToolDefinition(
        name="browser.search",
        version="0.1.0",
        description="Search the web via DuckDuckGo HTML",
        category=ToolCategory.BROWSER,
        risk_tier=RiskTier.REVERSIBLE_WRITE,
        input_schema=JsonSchemaField(type="object", required=["query"], properties={"query": JsonSchemaField(type="string")}),
    ),
    ToolDefinition(
        name="browser.act",
        version="0.1.0",
        description="Automated browser actions (planned)",
        category=ToolCategory.BROWSER,
        risk_tier=RiskTier.SYSTEM_AFFECTING,
        input_schema=JsonSchemaField(type="object", properties={"script": JsonSchemaField(type="string")}),
    ),
    ToolDefinition(
        name="screen.capture",
        version="0.1.0",
        description="Capture a screenshot of a display",
        category=ToolCategory.SCREEN,
        risk_tier=RiskTier.SYSTEM_AFFECTING,
        input_schema=JsonSchemaField(type="object", required=[], properties={"display": JsonSchemaField(type="number")}),
    ),
    ToolDefinition(
        name="screen.read",
        version="0.1.0",
        description="Read screen metadata (placeholder)",
        category=ToolCategory.SCREEN,
        risk_tier=RiskTier.REVERSIBLE_WRITE,
        input_schema=JsonSchemaField(type="object", required=[], properties={"display": JsonSchemaField(type="number")}),
    ),
    ToolDefinition(
        name="memory.get",
        version="0.1.0",
        description="Get a value from the digital twin memory",
        category=ToolCategory.MEMORY,
        risk_tier=RiskTier.READ_ONLY,
        input_schema=JsonSchemaField(type="object", required=["key"], properties={"key": JsonSchemaField(type="string")}),
    ),
    ToolDefinition(
        name="memory.set",
        version="0.1.0",
        description="Set a value in the digital twin memory",
        category=ToolCategory.MEMORY,
        risk_tier=RiskTier.READ_ONLY,
        input_schema=JsonSchemaField(type="object", required=["key", "value"], properties={"key": JsonSchemaField(type="string"), "value": JsonSchemaField(type="string"), "tags": JsonSchemaField(type="array", items=JsonSchemaField(type="string"))}),
    ),
    ToolDefinition(
        name="voice.stt",
        version="0.1.0",
        description="Speech-to-text via API endpoints",
        category=ToolCategory.VOICE,
        risk_tier=RiskTier.READ_ONLY,
        input_schema=JsonSchemaField(type="object", properties={}),
    ),
    ToolDefinition(
        name="voice.tts",
        version="0.1.0",
        description="Text-to-speech via API endpoints",
        category=ToolCategory.VOICE,
        risk_tier=RiskTier.READ_ONLY,
        input_schema=JsonSchemaField(type="object", properties={}),
    ),
    ToolDefinition(
        name="notify.send",
        version="0.1.0",
        description="Send a notification (log placeholder)",
        category=ToolCategory.NOTIFY,
        risk_tier=RiskTier.REVERSIBLE_WRITE,
        input_schema=JsonSchemaField(type="object", required=["target", "message"], properties={"target": JsonSchemaField(type="string"), "message": JsonSchemaField(type="string")}),
    ),
]


ExecutorFn = Callable[[dict[str, Any], dict[str, str]], Awaitable[Any]]


def create_tool_executors(
    workspace_root: str,
    screen_dir: str,
    twin: Any | None = None,
    extra: dict[str, Callable] | None = None,
) -> dict[str, Callable]:
    sandbox = make_sandbox(workspace_root)
    file = make_sandbox(workspace_root)
    terminal = make_terminal_tool(workspace_root)
    browser = make_browser_tools()
    screen = make_screen_tools(screen_dir)

    execs: dict[str, Callable] = {
        "fs.read": file["fs.read"],
        "fs.write": file["fs.write"],
        "fs.move": file["fs.move"],
        "fs.delete": file["fs.delete"],
        "fs.search": file["fs.search"],
        "terminal.exec": terminal["terminal.exec"],
        "browser.open": browser["browser.open"],
        "browser.search": browser["browser.search"],
        "browser.act": browser["browser.act"],
        "screen.capture": screen["screen.capture"],
        "screen.read": screen["screen.read"],
        "memory.get": lambda args, ctx: (
            twin.get(args["key"])
            if twin and twin.get(args["key"])
            else _memory_store.get(args["key"])
        ),
        "memory.set": lambda args, ctx: (
            twin.set(args["key"], args["value"], args.get("tags") or [])
            if twin
            else _memory_store.update({args["key"]: {"value": args["value"], "tags": args.get("tags") or [], "ts": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime())}})
            or _memory_store[args["key"]]
        ),
        "voice.stt": lambda a, c: {"configured": False, "note": "use /api/voice/stt endpoint"},
        "voice.tts": lambda a, c: {"configured": False, "note": "use /api/voice/tts endpoint"},
        "notify.send": lambda a, c: {"queued": True, "target": a.get("target", "log"), "message": a.get("message", ""), "ts": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime())},
    }
    if extra:
        execs.update(extra)
    return execs