import { appendFileSync, mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

export interface RouterLogEntry {
  ts: string;
  event: "request" | "response" | "error" | "skip";
  provider?: string;
  model?: string;
  latencyMs?: number;
  promptTokens?: number;
  completionTokens?: number;
  costUsd?: number;
  reason?: string;
  error?: string;
}

export interface RouterStats {
  requests: number;
  ok: number;
  failed: number;
  skipped: number;
  tokensIn: number;
  tokensOut: number;
  costUsd: number;
}

export class RouterLogger {
  private file: string;
  readonly stats: RouterStats = {
    requests: 0,
    ok: 0,
    failed: 0,
    skipped: 0,
    tokensIn: 0,
    tokensOut: 0,
    costUsd: 0,
  };

  constructor(logDir: string, private readonly consoleMirror = false) {
    mkdirSync(logDir, { recursive: true });
    this.file = join(logDir, `router-${new Date().toISOString().slice(0, 10)}.jsonl`);
  }

  log(entry: RouterLogEntry): void {
    try {
      appendFileSync(this.file, JSON.stringify(entry) + "\n");
    } catch {
      if (this.consoleMirror) console.error("[router] log write failed");
    }
    if (this.consoleMirror) console.log(`[router] ${JSON.stringify(entry)}`);
    switch (entry.event) {
      case "response":
        this.stats.requests += 1;
        this.stats.ok += 1;
        this.stats.tokensIn += entry.promptTokens ?? 0;
        this.stats.tokensOut += entry.completionTokens ?? 0;
        this.stats.costUsd += entry.costUsd ?? 0;
        break;
      case "error":
        this.stats.requests += 1;
        this.stats.failed += 1;
        break;
      case "skip":
        this.stats.skipped += 1;
        break;
    }
  }

  tailLines(n: number): RouterLogEntry[] {
    let raw: string;
    try {
      raw = readFileSync(this.file, "utf8");
    } catch {
      return [];
    }
    return raw
      .split("\n")
      .filter(Boolean)
      .slice(-n)
      .map((line) => JSON.parse(line) as RouterLogEntry);
  }
}
