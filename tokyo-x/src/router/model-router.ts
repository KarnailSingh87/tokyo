import { readFileSync } from "node:fs";
import { join } from "node:path";

import { RouterLogger } from "./logger.js";
import { createDefaultProviders, MockProvider, type Provider } from "./provider.js";
import type { ChatRequest, ChatResponse, ModelSpec, Usage } from "./types.js";

export interface PricingConfig {
  input: Record<string, number>;
  output: Record<string, number>;
  unknownInput: number;
  unknownOutput: number;
}

const DEFAULT_PRICING: PricingConfig = {
  input: { "gpt-4o-mini": 0.15, "gpt-4o": 2.5 },
  output: { "gpt-4o-mini": 0.6, "gpt-4o": 10.0 },
  unknownInput: 1.0,
  unknownOutput: 2.0,
};

interface ModelsFile {
  usdPerMTokens?: { input?: Record<string, number>; output?: Record<string, number> };
  unknownModelFallback?: { input?: number; output?: number };
}

export function loadPricing(configPath?: string): PricingConfig {
  const pricing: PricingConfig = {
    input: { ...DEFAULT_PRICING.input },
    output: { ...DEFAULT_PRICING.output },
    unknownInput: DEFAULT_PRICING.unknownInput,
    unknownOutput: DEFAULT_PRICING.unknownOutput,
  };
  if (!configPath) return pricing;
  try {
    const raw = JSON.parse(readFileSync(configPath, "utf8")) as ModelsFile;
    Object.assign(pricing.input, raw.usdPerMTokens?.input ?? {});
    Object.assign(pricing.output, raw.usdPerMTokens?.output ?? {});
    pricing.unknownInput = raw.unknownModelFallback?.input ?? pricing.unknownInput;
    pricing.unknownOutput = raw.unknownModelFallback?.output ?? pricing.unknownOutput;
  } catch {
    return pricing;
  }
  return pricing;
}

export function parseSpec(spec: string): ModelSpec {
  const i = spec.indexOf(":");
  if (i <= 0 || i === spec.length - 1) {
    throw new Error(`invalid model spec "${spec}" (expected provider:model)`);
  }
  return { provider: spec.slice(0, i), model: spec.slice(i + 1) };
}

export function estimateCost(model: string, usage: Usage, pricing: PricingConfig): number {
  const inRate = pricing.input[model] ?? pricing.unknownInput;
  const outRate = pricing.output[model] ?? pricing.unknownOutput;
  return (usage.promptTokens / 1_000_000) * inRate + (usage.completionTokens / 1_000_000) * outRate;
}

export interface RouterOptions {
  providers?: Provider[];
  logger?: RouterLogger;
  pricing?: PricingConfig;
  mockFallback?: boolean;
}

export class ModelRouter {
  readonly logger: RouterLogger;
  private providers = new Map<string, Provider>();

  constructor(private readonly opts: RouterOptions = {}) {
    this.logger = opts.logger ?? new RouterLogger(join(process.cwd(), "logs"));
    for (const p of opts.providers ?? []) this.register(p);
  }

  register(p: Provider): void {
    this.providers.set(p.name, p);
  }

  has(name: string): boolean {
    return this.providers.has(name);
  }

  providerNames(): string[] {
    return [...this.providers.keys()].sort();
  }

  status(): {
    providers: string[];
    mockFallback: boolean;
    stats: RouterLogger["stats"];
  } {
    return {
      providers: this.providerNames(),
      mockFallback: !!this.opts.mockFallback,
      stats: { ...this.logger.stats },
    };
  }

  async chat(specs: string | string[], req: ChatRequest): Promise<ChatResponse> {
    const chain = (Array.isArray(specs) ? specs : [specs]).map(parseSpec);
    const errors: string[] = [];

    for (const s of chain) {
      const provider = this.providers.get(s.provider);
      if (!provider) {
        errors.push(`${s.provider}: not configured`);
        this.logger.log({
          ts: new Date().toISOString(),
          event: "skip",
          provider: s.provider,
          model: s.model,
          reason: "provider-not-configured",
        });
        continue;
      }
      try {
        const resp = await provider.chat({ ...req, model: s.model });
        resp.costUsd = estimateCost(s.model, resp.usage, this.opts.pricing ?? DEFAULT_PRICING);
        this.logger.log({
          ts: new Date().toISOString(),
          event: "response",
          provider: resp.provider,
          model: resp.model,
          latencyMs: resp.latencyMs,
          promptTokens: resp.usage.promptTokens,
          completionTokens: resp.usage.completionTokens,
          costUsd: resp.costUsd,
        });
        return resp;
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        errors.push(`${s.provider}: ${msg}`);
        this.logger.log({
          ts: new Date().toISOString(),
          event: "error",
          provider: s.provider,
          model: s.model,
          error: msg,
        });
      }
    }

    if (this.opts.mockFallback) {
      const mock = this.providers.get("mock") ?? new MockProvider("mock");
      const model = chain[chain.length - 1]?.model ?? "unknown";
      const resp = await mock.chat({ ...req, model });
      resp.costUsd = 0;
      this.logger.log({
        ts: new Date().toISOString(),
        event: "response",
        provider: "mock",
        model: resp.model,
        reason: "mock-fallback",
        latencyMs: resp.latencyMs,
        promptTokens: resp.usage.promptTokens,
        completionTokens: resp.usage.completionTokens,
        costUsd: 0,
      });
      return resp;
    }

    throw new Error(`all providers failed → ${errors.join(" | ")}`);
  }
}

export function createProductionRouter(logDir: string, configDir: string): ModelRouter {
  const providers = createDefaultProviders();
  const router = new ModelRouter({
    providers,
    logger: new RouterLogger(logDir),
    pricing: loadPricing(join(configDir, "models.json")),
    mockFallback: true,
  });
  if (providers.length === 0) router.register(new MockProvider("mock"));
  return router;
}
