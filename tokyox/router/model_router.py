from __future__ import annotations
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx


@dataclass
class ChatMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass
class ChatRequest:
    messages: list[ChatMessage]
    temperature: float | None = None
    max_tokens: int | None = None
    timeout_ms: int | None = None
    metadata: dict[str, str] | None = None


@dataclass
class Usage:
    prompt_tokens: int
    completion_tokens: int


@dataclass
class ChatResponse:
    provider: str
    model: str
    content: str
    usage: Usage
    finish_reason: str
    latency_ms: int
    cost_usd: float = 0.0


@dataclass
class ModelSpec:
    provider: str
    model: str


class ProviderError(Exception):
    def __init__(self, provider: str, status: int, detail: str):
        self.provider = provider
        self.status = status
        super().__init__(f"[{provider}] HTTP {status}: {detail}")


class Provider:
    name: str

    async def chat(self, req: ChatRequest, model: str) -> ChatResponse:
        raise NotImplementedError


class OpenAICompatProvider(Provider):
    def __init__(self, name: str, api_key: str, base_url: str, extra_headers: dict[str, str] | None = None):
        self.name = name
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._extra_headers = extra_headers or {}

    async def chat(self, req: ChatRequest, model: str) -> ChatResponse:
        started = time.time()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
            **self._extra_headers,
        }
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in req.messages],
            "temperature": req.temperature if req.temperature is not None else 0.7,
        }
        if req.max_tokens is not None:
            payload["max_tokens"] = req.max_tokens

        timeout = req.timeout_ms / 1000.0 if req.timeout_ms else 30.0
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{self._base_url}/chat/completions", headers=headers, json=payload)
            if not resp.is_success:
                body = resp.text[:300]
                raise ProviderError(self.name, resp.status_code, body or resp.reason_phrase)
            data = resp.json()
            choice = data.get("choices", [{}])[0]
            msg = choice.get("message", {})
            usage = data.get("usage", {})
            return ChatResponse(
                provider=self.name,
                model=model,
                content=msg.get("content", ""),
                usage=Usage(
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                ),
                finish_reason=choice.get("finish_reason", "stop"),
                latency_ms=int((time.time() - started) * 1000),
                cost_usd=0.0,
            )


class MockProvider(Provider):
    def __init__(self, name: str = "mock", mode: Literal["ok", "always-fail"] = "ok"):
        self.name = name
        self.mode = mode

    async def chat(self, req: ChatRequest, model: str) -> ChatResponse:
        await asyncio.sleep(0.005)
        if self.mode == "always-fail":
            raise ProviderError(self.name, 503, "simulated outage")
        last_user = next((m for m in reversed(req.messages) if m.role == "user"), None)
        echo = last_user.content[:80] if last_user else ""
        return ChatResponse(
            provider=self.name,
            model=model,
            content=f"[mock:{model}] {echo}".strip(),
            usage=Usage(prompt_tokens=32, completion_tokens=48),
            finish_reason="stop",
            latency_ms=5,
            cost_usd=0.0,
        )


import asyncio


def parse_spec(spec: str) -> ModelSpec:
    i = spec.find(":")
    if i <= 0 or i == len(spec) - 1:
        raise ValueError(f'invalid model spec "{spec}" (expected provider:model)')
    return ModelSpec(provider=spec[:i], model=spec[i + 1 :])


@dataclass
class PricingConfig:
    input: dict[str, float] = field(default_factory=dict)
    output: dict[str, float] = field(default_factory=dict)
    unknown_input: float = 1.0
    unknown_output: float = 2.0


DEFAULT_PRICING = PricingConfig(
    input={"gpt-4o-mini": 0.15, "gpt-4o": 2.5},
    output={"gpt-4o-mini": 0.6, "gpt-4o": 10.0},
)


def load_pricing(config_path: str | None = None) -> PricingConfig:
    pricing = PricingConfig(
        input=dict(DEFAULT_PRICING.input),
        output=dict(DEFAULT_PRICING.output),
        unknown_input=DEFAULT_PRICING.unknown_input,
        unknown_output=DEFAULT_PRICING.unknown_output,
    )
    if not config_path or not os.path.exists(config_path):
        return pricing
    try:
        with open(config_path) as f:
            raw = json.load(f)
        usd = raw.get("usdPerMTokens", {})
        pricing.input.update(usd.get("input", {}))
        pricing.output.update(usd.get("output", {}))
        fallback = raw.get("unknownModelFallback", {})
        pricing.unknown_input = fallback.get("input", pricing.unknown_input)
        pricing.unknown_output = fallback.get("output", pricing.unknown_output)
    except Exception:
        pass
    return pricing


def estimate_cost(model: str, usage: Usage, pricing: PricingConfig) -> float:
    in_rate = pricing.input.get(model, pricing.unknown_input)
    out_rate = pricing.output.get(model, pricing.unknown_output)
    return (usage.prompt_tokens / 1_000_000) * in_rate + (usage.completion_tokens / 1_000_000) * out_rate


@dataclass
class RouterLogEntry:
    ts: str
    event: str
    provider: str | None = None
    model: str | None = None
    latency_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None
    reason: str | None = None
    error: str | None = None


@dataclass
class RouterStats:
    requests: int = 0
    ok: int = 0
    failed: int = 0
    skipped: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


class RouterLogger:
    def __init__(self, log_dir: str):
        os.makedirs(log_dir, exist_ok=True)
        self._file = os.path.join(log_dir, f"router-{time.strftime('%Y-%m-%d')}.jsonl")
        self.stats = RouterStats()

    def log(self, entry: RouterLogEntry) -> None:
        try:
            with open(self._file, "a") as f:
                f.write(json.dumps(entry.__dict__) + "\n")
        except Exception:
            pass
        if entry.event == "response":
            self.stats.requests += 1
            self.stats.ok += 1
            self.stats.tokens_in += entry.prompt_tokens or 0
            self.stats.tokens_out += entry.completion_tokens or 0
            self.stats.cost_usd += entry.cost_usd or 0.0
        elif entry.event == "error":
            self.stats.requests += 1
            self.stats.failed += 1
        elif entry.event == "skip":
            self.stats.skipped += 1

    def tail_lines(self, n: int) -> list[RouterLogEntry]:
        try:
            with open(self._file) as f:
                lines = f.read().splitlines()
        except Exception:
            return []
        return [RouterLogEntry(**json.loads(l)) for l in lines[-n:] if l.strip()]


class ModelRouter:
    def __init__(
        self,
        providers: list[Provider] | None = None,
        logger: RouterLogger | None = None,
        pricing: PricingConfig | None = None,
        mock_fallback: bool = False,
    ):
        self._providers: dict[str, Provider] = {}
        self.logger = logger or RouterLogger(os.getcwd())
        self.pricing = pricing or load_pricing()
        self.mock_fallback = mock_fallback
        for p in providers or []:
            self.register(p)

    def register(self, p: Provider) -> None:
        self._providers[p.name] = p

    def has(self, name: str) -> bool:
        return name in self._providers

    def provider_names(self) -> list[str]:
        return sorted(self._providers.keys())

    def status(self) -> dict[str, Any]:
        return {
            "providers": self.provider_names(),
            "mock_fallback": self.mock_fallback,
            "stats": self.logger.stats.__dict__,
        }

    async def chat(self, specs: str | list[str], req: ChatRequest) -> ChatResponse:
        chain = [parse_spec(s) for s in (specs if isinstance(specs, list) else [specs])]
        errors: list[str] = []
        for s in chain:
            provider = self._providers.get(s.provider)
            if not provider:
                errors.append(f"{s.provider}: not configured")
                self.logger.log(
                    RouterLogEntry(
                        ts=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        event="skip",
                        provider=s.provider,
                        model=s.model,
                        reason="provider-not-configured",
                    )
                )
                continue
            try:
                resp = await provider.chat(req, s.model)
                resp.cost_usd = estimate_cost(s.model, resp.usage, self.pricing)
                self.logger.log(
                    RouterLogEntry(
                        ts=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        event="response",
                        provider=resp.provider,
                        model=resp.model,
                        latency_ms=resp.latency_ms,
                        prompt_tokens=resp.usage.prompt_tokens,
                        completion_tokens=resp.usage.completion_tokens,
                        cost_usd=resp.cost_usd,
                    )
                )
                return resp
            except Exception as err:
                msg = str(err)
                errors.append(f"{s.provider}: {msg}")
                self.logger.log(
                    RouterLogEntry(
                        ts=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        event="error",
                        provider=s.provider,
                        model=s.model,
                        error=msg,
                    )
                )
        if self.mock_fallback and not any(s.provider == "mock" for s in chain):
            mock = self._providers.get("mock") or MockProvider("mock")
            model = chain[-1].model if chain else "unknown"
            resp = await mock.chat(req, model)
            resp.cost_usd = 0.0
            self.logger.log(
                RouterLogEntry(
                    ts=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    event="response",
                    provider="mock",
                    model=resp.model,
                    reason="mock-fallback",
                    latency_ms=resp.latency_ms,
                    prompt_tokens=resp.usage.prompt_tokens,
                    completion_tokens=resp.usage.completion_tokens,
                    cost_usd=0.0,
                )
            )
            return resp
        raise Exception(f"all providers failed -> {' | '.join(errors)}")


def create_default_providers() -> list[Provider]:
    out: list[Provider] = []
    oa_key = os.environ.get("OPENAI_API_KEY")
    if oa_key:
        out.append(
            OpenAICompatProvider(
                "openai",
                oa_key,
                os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            )
        )
    or_key = os.environ.get("OPENROUTER_API_KEY")
    if or_key:
        out.append(
            OpenAICompatProvider(
                "openrouter",
                or_key,
                os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
                {"HTTP-Referer": "http://127.0.0.1:8787", "X-Title": "TOKYO-X"},
            )
        )
    return out


def create_production_router(log_dir: str, config_dir: str) -> ModelRouter:
    providers = create_default_providers()
    router = ModelRouter(
        providers=providers,
        logger=RouterLogger(log_dir),
        pricing=load_pricing(os.path.join(config_dir, "models.json")),
        mock_fallback=True,
    )
    if not providers:
        router.register(MockProvider("mock"))
    return router