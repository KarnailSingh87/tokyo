import { appendFileSync, existsSync, mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { randomUUID } from "node:crypto";

export interface MemoryEntry {
  key: string;
  value: string;
  tags: string[];
  ts: string;
}

export class TwinMemory {
  private entries = new Map<string, MemoryEntry>();

  constructor(private readonly dir: string) {
    mkdirSync(dir, { recursive: true });
    const file = this.file;
    if (existsSync(file)) {
      for (const line of readFileSync(file, "utf8").split("\n").filter(Boolean)) {
        try {
          const e = JSON.parse(line) as MemoryEntry;
          this.entries.set(e.key, e);
        } catch {
          continue;
        }
      }
    }
  }

  private get file(): string {
    return join(this.dir, "twin.jsonl");
  }

  set(key: string, value: string, tags: string[] = []): MemoryEntry {
    if (!key.trim()) throw new Error("memory key required");
    const entry: MemoryEntry = { key: key.slice(0, 120), value: String(value).slice(0, 8000), tags: tags.slice(0, 8), ts: new Date().toISOString() };
    this.entries.set(entry.key, entry);
    appendFileSync(this.file, JSON.stringify(entry) + "\n");
    return entry;
  }

  get(key: string): MemoryEntry | undefined {
    return this.entries.get(key);
  }

  search(query: string, limit = 5): Array<MemoryEntry & { score: number }> {
    const tokens = query.toLowerCase().split(/\s+/).filter(Boolean);
    const scored: Array<MemoryEntry & { score: number }> = [];
    for (const e of this.entries.values()) {
      let score = 0;
      const hay = `${e.key} ${e.value}`.toLowerCase();
      for (const t of tokens) if (hay.includes(t)) score += 1;
      for (const tag of e.tags) if (tokens.includes(tag.toLowerCase())) score += 2;
      if (score > 0) scored.push({ ...e, score });
    }
    return scored.sort((a, b) => b.score - a.score || b.ts.localeCompare(a.ts)).slice(0, limit);
  }

  recent(n = 10): MemoryEntry[] {
    return [...this.entries.values()].sort((a, b) => b.ts.localeCompare(a.ts)).slice(0, n);
  }

  get size(): number {
    return this.entries.size;
  }

  newId(): string {
    return randomUUID().slice(0, 8);
  }
}
