import type { RouterLogger, RouterStats } from "../../router/logger.js";

export class CostDashboard {
  constructor(private readonly logger: RouterLogger) {}

  summary(): {
    totals: RouterStats;
    byModel: Record<string, { calls: number; in: number; out: number; costUsd: number }>;
    recent: Array<{ ts: string; provider: string; model: string; costUsd: number }>;
  } {
    const totals: RouterStats = { ...this.logger.stats };
    const byModel: Record<string, { calls: number; in: number; out: number; costUsd: number }> = {};
    const recent: Array<{ ts: string; provider: string; model: string; costUsd: number }> = [];

    const entries = this.logger.tailLines(500);
    for (const e of entries) {
      if (e.event !== "response") continue;
      const model = e.model ?? "unknown";
      const prov = e.provider ?? "unknown";
      const cost = e.costUsd ?? 0;
      const key = `${prov}:${model}`;
      if (!byModel[key]) byModel[key] = { calls: 0, in: 0, out: 0, costUsd: 0 };
      byModel[key].calls += 1;
      byModel[key].in += e.promptTokens ?? 0;
      byModel[key].out += e.completionTokens ?? 0;
      byModel[key].costUsd += cost;
      recent.push({ ts: e.ts, provider: prov, model, costUsd: cost });
    }

    return { totals, byModel, recent: recent.slice(-20) };
  }
}