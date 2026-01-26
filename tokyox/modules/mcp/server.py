from __future__ import annotations
import json
import sys
from typing import Any

from ...core.orchestrator import Orchestrator


class McpServer:
    def __init__(self, orchestrator: Orchestrator):
        self._orch = orchestrator

    async def handle_request(self, req: dict[str, Any]) -> dict[str, Any]:
        id_ = req.get("id")
        method = req.get("method")
        params = req.get("params") or {}

        try:
            if method == "initialize":
                return {
                    "jsonrpc": "2.0",
                    "id": id_,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "tokyo-x", "version": "0.1.0"},
                    },
                }
            elif method == "tools/list":
                tools = [
                    {
                        "name": t.name,
                        "description": t.description,
                        "inputSchema": t.input_schema.__dict__ if t.input_schema else {},
                    }
                    for t in self._orch.tools.list()
                ]
                return {"jsonrpc": "2.0", "id": id_, "result": {"tools": tools}}
            elif method == "tools/call":
                name = params.get("name")
                args = params.get("arguments") or {}
                if not name:
                    raise ValueError("tools/call requires params.name")
                outcome = await self._orch.execute_tool("mcp-client", name, args)
                return {
                    "jsonrpc": "2.0",
                    "id": id_,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(outcome.__dict__, default=str)}],
                        "isError": outcome.status != "executed",
                    },
                }
            else:
                return {"jsonrpc": "2.0", "id": id_, "error": {"code": -32601, "message": f"method not found: {method}"}}
        except Exception as err:
            return {"jsonrpc": "2.0", "id": id_, "error": {"code": -32603, "message": str(err)}}

    def serve_stdio(self) -> None:
        loop = __import__("asyncio").get_event_loop()
        for line in sys.stdin:
            try:
                req = json.loads(line)
                resp = loop.run_until_complete(self.handle_request(req))
                print(json.dumps(resp), flush=True)
            except Exception:
                print(json.dumps({"jsonrpc": "2.0", "error": {"code": -32700, "message": "parse error"}}), flush=True)


from dataclasses import field