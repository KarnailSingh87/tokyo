import { readFileSync } from "node:fs";
import { join } from "node:path";

export interface Skill {
  id: string;
  name: string;
  description: string;
  promptTemplate: string;
  allowedTools: string[];
  modelSpec: string[];
}

export class SkillRegistry {
  private skills = new Map<string, Skill>();

  constructor(path?: string) {
    if (path) this.load(path);
  }

  load(path: string): void {
    const raw = JSON.parse(readFileSync(path, "utf8")) as { skills: Skill[] };
    for (const s of raw.skills ?? []) this.skills.set(s.id, s);
  }

  list(): Skill[] {
    return [...this.skills.values()];
  }

  get(id: string): Skill | undefined {
    return this.skills.get(id);
  }

  instantiate(id: string, vars: Record<string, string>): { prompt: string; skill: Skill } | null {
    const s = this.skills.get(id);
    if (!s) return null;
    let prompt = s.promptTemplate;
    for (const [k, v] of Object.entries(vars)) prompt = prompt.replaceAll(`{{${k}}}`, v);
    return { prompt, skill: s };
  }
}