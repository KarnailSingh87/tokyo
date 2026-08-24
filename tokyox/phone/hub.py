from __future__ import annotations
import asyncio
import json
import os
import hmac
from typing import Any

import websockets
from websockets.server import WebSocketServerProtocol


class ApprovalHub:
    def __init__(self, pair_token: str, on_decision: Callable[[str, bool], Awaitable[None]]):
        self._pair_token = pair_token.encode()
        self._on_decision = on_decision
        self._clients: dict[WebSocketServerProtocol, dict[str, Any]] = {}

    async def handle(self, ws: WebSocketServerProtocol, path: str):
        if path != "/ws/phone":
            await ws.close()
            return
        state = {"id": os.urandom(6).hex(), "authed": False}
        self._clients[ws] = state
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except Exception:
                    await ws.close()
                    return
                if not state["authed"]:
                    if msg.get("type") == "hello" and isinstance(msg.get("token"), str):
                        if hmac.compare_digest(msg["token"], self._pair_token.decode()):
                            state["authed"] = True
                            await ws.send(json.dumps({"type": "welcome", "clientId": state["id"]}))
                            # pending approvals will be sent by caller via broadcast_pending
                        else:
                            await ws.close()
                    else:
                        await ws.close()
                    continue
                if msg.get("type") == "decision" and isinstance(msg.get("id"), str) and isinstance(msg.get("approved"), bool):
                    result = self._on_decision(msg["id"], msg["approved"])
                    if hasattr(result, "__await__"):
                        await result
        finally:
            self._clients.pop(ws, None)

    async def broadcast_approval(self, payload: dict[str, Any]):
        msg = json.dumps({"type": "approval_request", **payload})
        for ws, st in list(self._clients.items()):
            if st["authed"]:
                try:
                    await ws.send(msg)
                except Exception:
                    self._clients.pop(ws, None)

    async def broadcast_update(self, payload: dict[str, Any]):
        msg = json.dumps({"type": "approval_update", **payload})
        for ws, st in list(self._clients.items()):
            if st["authed"]:
                try:
                    await ws.send(msg)
                except Exception:
                    self._clients.pop(ws, None)

    @property
    def client_count(self) -> int:
        return len(self._clients)


from typing import Callable, Awaitable