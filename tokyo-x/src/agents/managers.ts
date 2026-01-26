import { readFileSync } from "node:fs";

export interface WorkerSpec {
  id: string;
  name: string;
  tools: string[];
  maxRiskTier: 0 | 1 | 2 | 3;
}

export interface ManagerSpec {
  id: string;
  name: string;
  domain: string;
  defaultModel: string;
  maxRiskTier: 0 | 1 | 2 | 3;
  workers: WorkerSpec[];
}

export interface OrgConfig {
  version: string;
  ceo: { name: string; role: string; approvalRights: string[] };
  orchestrator: {
    id: string;
    role: string;
    modelDefault: string;
    fallbackModels: string[];
    escalatesTo: string;
    responsibilities: string[];
  };
  managers: ManagerSpec[];
}

export function loadOrgConfig(path: string): OrgConfig {
  return JSON.parse(readFileSync(path, "utf8")) as OrgConfig;
}

export class ManagerRegistry {
  private byId = new Map<string, ManagerSpec>();

  constructor(org: OrgConfig) {
    for (const m of org.managers) this.byId.set(m.id, m);
  }

  get(id: string): ManagerSpec | undefined {
    return this.byId.get(id);
  }

  all(): ManagerSpec[] {
    return [...this.byId.values()];
  }

  findWorker(workerId: string): { manager: ManagerSpec; worker: WorkerSpec } | undefined {
    for (const manager of this.all()) {
      const worker = manager.workers.find((w) => w.id === workerId);
      if (worker) return { manager, worker };
    }
    return undefined;
  }
}
