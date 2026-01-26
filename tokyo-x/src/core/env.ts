import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

const loaded = new Set<string>();

export function loadDotEnv(dir: string = process.cwd()): void {
  const file = join(dir, ".env");
  if (!existsSync(file)) return;
  for (const line of readFileSync(file, "utf8").split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$/);
    if (!m) continue;
    const key = m[1];
    let value = m[2] ?? "";
    if (value.length >= 2 && (value.startsWith('"') || value.startsWith("'"))) {
      value = value.slice(1, -1);
    }
    loaded.add(key);
    if (!(key in process.env)) process.env[key] = value;
  }
}

export function requireEnv(key: string): string {
  const v = process.env[key];
  if (!v) throw new Error(`missing required env var: ${key} (see .env.example)`);
  return v;
}

export function optionalEnv(key: string, fallback = ""): string {
  return process.env[key] ?? fallback;
}

export function providerKey(provider: "openai" | "openrouter" | "elevenlabs"): string {
  const map = {
    openai: "OPENAI_API_KEY",
    openrouter: "OPENROUTER_API_KEY",
    elevenlabs: "ELEVENLABS_API_KEY",
  } as const;
  return optionalEnv(map[provider]);
}
