import { appendFileSync, mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

import type { AuditEvent, AuditSink } from "./permission-engine.js";

function todayStamp(): string {
  return new Date().toISOString().slice(0, 10);
}

export class FileAuditSink implements AuditSink {
  constructor(private readonly dir: string, private readonly consoleEcho = false) {
    mkdirSync(dir, { recursive: true });
  }

  get file(): string {
    return join(this.dir, `audit-${todayStamp()}.jsonl`);
  }

  record(event: AuditEvent): void {
    try {
      appendFileSync(this.file, JSON.stringify(event) + "\n");
    } catch {
      if (this.consoleEcho) console.error("[audit] write failed");
    }
    if (this.consoleEcho) console.log(`[audit] ${JSON.stringify(event.decision)}`);
  }

  tail(n: number): AuditEvent[] {
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
      .map((line) => JSON.parse(line) as AuditEvent);
  }
}

export function appendSystemEvent(dir: string, type: string, payload: unknown): void {
  mkdirSync(dir, { recursive: true });
  const line = JSON.stringify({ ts: new Date().toISOString(), type, payload }) + "\n";
  appendFileSync(join(dir, `events-${todayStamp()}.jsonl`), line);
}
