from __future__ import annotations
import hmac
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from .types import Decision


@dataclass
class PendingRecord:
    id: str
    decision: Decision
    created_at: str
    expires_at: str
    needs_token: bool
    args: dict[str, Any] | None = None
    category: str | None = None
    risk_tier: int | None = None


@dataclass
class PendingHandle:
    id: str
    token: str
    expires_at: str
    needs_token: bool


ResolveVia = Literal["phone", "local"]


@dataclass
class ResolveOptions:
    via: ResolveVia = "local"
    token: str | None = None


class PendingApprovals:
    def __init__(
        self,
        secret: str,
        ttl_ms: int = 5 * 60_000,
        on_create: callable | None = None,
    ):
        self._secret = secret.encode()
        self._ttl_ms = ttl_ms
        self._on_create = on_create
        self._pending: dict[str, PendingRecord] = {}
        self._waiters: dict[str, asyncio.Future] = {}

    def _sign(self, id_: str, expires_at: str) -> str:
        return hmac.new(self._secret, f"{id_}.{expires_at}".encode(), "sha256").hexdigest()

    def _verify_token(self, id_: str, expires_at: str, token: str) -> bool:
        expected = self._sign(id_, expires_at)
        return hmac.compare_digest(expected, token)

    def create(self, decision: Decision, args: dict[str, Any] | None = None, category: str | None = None, risk_tier: int | None = None) -> PendingHandle:
        id_ = f"apr_{uuid.uuid4().hex[:12]}"
        expires_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + self._ttl_ms / 1000))
        record = PendingRecord(
            id=id_,
            decision=decision,
            created_at=decision.evaluated_at,
            expires_at=expires_at,
            needs_token=decision.requires_approval_token,
            args=args,
            category=category,
            risk_tier=risk_tier,
        )
        self._pending[id_] = record
        handle = PendingHandle(
            id=id_,
            token=self._sign(id_, expires_at),
            expires_at=expires_at,
            needs_token=record.needs_token,
        )
        if self._on_create:
            self._on_create(handle, record)
        return handle

    def verify_token(self, id_: str, expires_at: str, token: str) -> bool:
        return self._verify_token(id_, expires_at, token)

    def resolve(self, id_: str, approved: bool, opts: ResolveOptions = ResolveOptions()) -> bool:
        rec = self._pending.get(id_)
        if not rec:
            return False
        if time.time() > time.mktime(time.strptime(rec.expires_at, "%Y-%m-%dT%H:%M:%SZ")):
            self._finish(id_, None)
            return False
        if rec.needs_token and opts.via != "phone":
            if not opts.token or not self._verify_token(id_, rec.expires_at, opts.token):
                return False
        self._finish(id_, {"approved": approved})
        return True

    def _finish(self, id_: str, result: dict[str, bool] | None) -> None:
        self._pending.pop(id_, None)
        fut = self._waiters.pop(id_, None)
        if fut and not fut.done():
            fut.set_result(result)

    async def wait_resolved(self, id_: str, timeout_ms: int = 120_000) -> dict[str, bool] | None:
        rec = self._pending.get(id_)
        if not rec:
            return None
        if time.time() > time.mktime(time.strptime(rec.expires_at, "%Y-%m-%dT%H:%M:%SZ")):
            self._finish(id_, None)
            return None
        if id_ not in self._waiters:
            self._waiters[id_] = asyncio.get_event_loop().create_future()
        try:
            return await asyncio.wait_for(self._waiters[id_], timeout=timeout_ms / 1000)
        except asyncio.TimeoutError:
            self._finish(id_, None)
            return None

    def list(self) -> list[PendingRecord]:
        now = time.time()
        return [r for r in self._pending.values() if now <= time.mktime(time.strptime(r.expires_at, "%Y-%m-%dT%H:%M:%SZ"))]

    def get_handle_for_display(self, id_: str) -> PendingHandle | None:
        rec = self._pending.get(id_)
        if not rec:
            return None
        return PendingHandle(
            id=rec.id,
            token=self._sign(rec.id, rec.expires_at),
            expires_at=rec.expires_at,
            needs_token=rec.needs_token,
        )


import asyncio