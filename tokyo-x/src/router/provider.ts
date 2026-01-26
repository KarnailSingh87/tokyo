import { providerKey, optionalEnv } from "../core/env.js";
import type { ChatResponse, CompletionRequest } from "./types.js";

export interface Provider {
  readonly name: string;
  chat(req: CompletionRequest): Promise<ChatResponse>;
}

export class ProviderError extends Error {
  constructor(
    public readonly provider: string,
    public readonly status: number,
    detail: string
  ) {
    super(`[${provider}] HTTP ${status}: ${detail}`);
    this.name = "ProviderError";
  }
}

export interface OpenAICompatConfig {
  name: string;
  apiKey: string;
  baseUrl: string;
  extraHeaders?: Record<string, string>;
}

interface ChatCompletionsPayload {
  choices?: Array<{ message?: { content?: string }; finish_reason?: string }>;
  usage?: { prompt_tokens?: number; completion_tokens?: number };
  error?: { message?: string };
}

export class OpenAICompatProvider implements Provider {
  constructor(private readonly cfg: OpenAICompatConfig) {}

  get name(): string {
    return this.cfg.name;
  }

  async chat(req: CompletionRequest): Promise<ChatResponse> {
    const started = Date.now();
    let res: Response;
    try {
      res = await fetch(`${this.cfg.baseUrl}/chat/completions`, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          authorization: `Bearer ${this.cfg.apiKey}`,
          ...(this.cfg.extraHeaders ?? {}),
        },
        body: JSON.stringify({
          model: req.model,
          messages: req.messages,
          temperature: req.temperature ?? 0.7,
          max_tokens: req.maxTokens,
        }),
        signal: AbortSignal.timeout(req.timeoutMs ?? 30_000),
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      throw new ProviderError(this.name, 0, `network failure: ${msg}`);
    }

    if (!res.ok) {
      const body = (await res.text().catch(() => "")).slice(0, 300);
      throw new ProviderError(this.name, res.status, body || res.statusText);
    }

    const data = (await res.json().catch(() => null)) as ChatCompletionsPayload | null;
    if (!data || data.error || !data.choices?.[0]?.message) {
      throw new ProviderError(this.name, res.status, data?.error?.message ?? "malformed response payload");
    }

    return {
      provider: this.name,
      model: req.model,
      content: data.choices[0].message.content ?? "",
      usage: {
        promptTokens: data.usage?.prompt_tokens ?? 0,
        completionTokens: data.usage?.completion_tokens ?? 0,
      },
      finishReason: data.choices[0].finish_reason ?? "stop",
      latencyMs: Date.now() - started,
      costUsd: 0,
    };
  }
}

export type MockMode = "ok" | "always-fail";

export class MockProvider implements Provider {
  constructor(
    readonly name: string = "mock",
    private readonly mode: MockMode = "ok"
  ) {}

  async chat(req: CompletionRequest): Promise<ChatResponse> {
    await new Promise((r) => setTimeout(r, 5));
    if (this.mode === "always-fail") throw new ProviderError(this.name, 503, "simulated outage");
    const lastUser = [...req.messages].reverse().find((m) => m.role === "user");
    const echo = lastUser ? lastUser.content.slice(0, 80) : "";
    return {
      provider: this.name,
      model: req.model,
      content: `[mock:${req.model}] ${echo}`.trim(),
      usage: { promptTokens: 32, completionTokens: 48 },
      finishReason: "stop",
      latencyMs: 5,
      costUsd: 0,
    };
  }
}

export function createDefaultProviders(): Provider[] {
  const out: Provider[] = [];
  const oaKey = providerKey("openai");
  if (oaKey) {
    out.push(
      new OpenAICompatProvider({
        name: "openai",
        apiKey: oaKey,
        baseUrl: optionalEnv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
      })
    );
  }
  const orKey = providerKey("openrouter");
  if (orKey) {
    out.push(
      new OpenAICompatProvider({
        name: "openrouter",
        apiKey: orKey,
        baseUrl: optionalEnv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        extraHeaders: { "http-referer": "http://127.0.0.1:8787", "x-title": "TOKYO-X" },
      })
    );
  }
  return out;
}
