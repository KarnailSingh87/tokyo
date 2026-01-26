import { appendFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { randomUUID } from "node:crypto";

export type JobStatus = "queued" | "running" | "done" | "failed" | "cancelled";

export interface Job {
  id: string;
  kind: string;
  payload: unknown;
  status: JobStatus;
  progress: number;
  result?: unknown;
  error?: string;
  createdAt: string;
  startedAt?: string;
  finishedAt?: string;
}

export type Runner = (payload: unknown, job: Job, report: (progress: number) => void) => Promise<unknown>;

export class TaskManager {
  private jobs = new Map<string, Job>();
  private queue: string[] = [];
  private runners = new Map<string, Runner>();
  private active = 0;
  private pumpTimer: ReturnType<typeof setInterval>;

  constructor(private readonly eventDir: string, private readonly concurrency = 2) {
    mkdirSync(eventDir, { recursive: true });
    this.pumpTimer = setInterval(() => this.pump(), 250);
    this.pumpTimer.unref?.();
  }

  register(kind: string, runner: Runner): void {
    this.runners.set(kind, runner);
  }

  submit(kind: string, payload: unknown): Job {
    if (!this.runners.has(kind)) throw new Error(`no runner registered for kind "${kind}"`);
    const job: Job = {
      id: `job_${randomUUID().slice(0, 10)}`,
      kind,
      payload,
      status: "queued",
      progress: 0,
      createdAt: new Date().toISOString(),
    };
    this.jobs.set(job.id, job);
    this.queue.push(job.id);
    this.event(job, "queued");
    setImmediate(() => this.pump());
    return { ...job };
  }

  cancel(id: string): boolean {
    const job = this.jobs.get(id);
    if (!job) return false;
    if (job.status === "queued") {
      this.queue = this.queue.filter((x) => x !== id);
      job.status = "cancelled";
      job.finishedAt = new Date().toISOString();
      this.event(job, "cancelled");
      return true;
    }
    return false;
  }

  get(id: string): Job | undefined {
    const j = this.jobs.get(id);
    return j ? { ...j } : undefined;
  }

  list(): Job[] {
    return [...this.jobs.values()].map((j) => ({ ...j })).sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  }

  get stats(): { total: number; active: number; queued: number } {
    const all = [...this.jobs.values()];
    return {
      total: all.length,
      active: all.filter((j) => j.status === "running").length,
      queued: all.filter((j) => j.status === "queued").length,
    };
  }

  private pump(): void {
    while (this.active < this.concurrency && this.queue.length > 0) {
      const id = this.queue.shift();
      if (!id) break;
      const job = this.jobs.get(id);
      if (!job || job.status !== "queued") continue;
      void this.run(job);
    }
  }

  private async run(job: Job): Promise<void> {
    const runner = this.runners.get(job.kind);
    if (!runner) {
      job.status = "failed";
      job.error = "runner vanished";
      this.event(job, "failed");
      return;
    }
    this.active += 1;
    job.status = "running";
    job.startedAt = new Date().toISOString();
    this.event(job, "started");
    try {
      job.result = await runner(job.payload, job, (p) => {
        job.progress = Math.max(0, Math.min(100, p));
      });
      job.progress = 100;
      job.status = "done";
    } catch (err) {
      job.status = "failed";
      job.error = err instanceof Error ? err.message : String(err);
    } finally {
      job.finishedAt = new Date().toISOString();
      this.active -= 1;
      this.event(job, job.status);
      this.pump();
    }
  }

  private event(job: Job, phase: string): void {
    const line =
      JSON.stringify({ ts: new Date().toISOString(), phase, id: job.id, kind: job.kind, status: job.status, progress: job.progress }) +
      "\n";
    try {
      appendFileSync(join(this.eventDir, "jobs.jsonl"), line);
    } catch {
      return;
    }
  }
}
