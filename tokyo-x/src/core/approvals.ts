import { createHmac, randomUUID, timingSafeEqual } from "node:crypto";

import type { Decision } from "./permission-engine.js";

export interface PendingRecord {
  id: string;
  decision: Decision;
  createdAt: string;
  expiresAt: string;
  needsToken: boolean;
  args?: Record<string, unknown>;
  category?: string;
  riskTier?: number;
}

export interface PendingHandle {
  id: string;
  token: string;
  expiresAt: string;
  needsToken: boolean;
}

export interface ResolveOptions {
  via?: "phone" | "local";
  token?: string;
}

type Waiter = (result: { approved: boolean } | null) => void;

export class PendingApprovals {
  private pending = new Map<string, PendingRecord>();
  private waiters = new Map<string, Waiter>();
  private sweeper: ReturnType<typeof setInterval>;

  constructor(
    private readonly secret: string,
    private readonly ttlMs = 5 * 60_000,
    private readonly onCreate?: (handle: PendingHandle, record: PendingRecord) => void
  ) {
    this.sweeper = setInterval(() => this.sweep(), 30_000);
    this.sweeper.unref?.();
  }

  private sign(id: string, expiresAt: string): string {
    return createHmac("sha256", this.secret).update(`${id}.${expiresAt}`).digest("hex");
  }

  create(decision: Decision, args?: Record<string, unknown>, category?: string, riskTier?: number): PendingHandle {
    const id = `apr_${randomUUID().slice(0, 12)}`;
    const expiresAt = new Date(Date.now() + this.ttlMs).toISOString();
    const record: PendingRecord = {
      id,
      decision,
      createdAt: decision.evaluatedAt,
      expiresAt,
      needsToken: decision.requiresApprovalToken,
      args,
      category,
      riskTier,
    };
    this.pending.set(id, record);
    const handle: PendingHandle = {
      id,
      token: this.sign(id, expiresAt),
      expiresAt,
      needsToken: record.needsToken,
    };
    this.onCreate?.(handle, record);
    return handle;
  }

  verifyToken(id: string, expiresAt: string, token: string): boolean {
    const expected = Buffer.from(this.sign(id, expiresAt));
    const given = Buffer.from(token);
    return expected.length === given.length && timingSafeEqual(expected, given);
  }

  resolve(id: string, approved: boolean, opts: ResolveOptions = {}): boolean {
    const rec = this.pending.get(id);
    if (!rec) return false;
    const expired = Date.now() > Date.parse(rec.expiresAt);
    if (expired) {
      this.finish(id, null);
      return false;
    }
    if (rec.needsToken && opts.via !== "phone") {
      if (!opts.token || !this.verifyToken(id, rec.expiresAt, opts.token)) return false;
    }
    this.finish(id, { approved });
    return true;
  }

  async waitResolved(id: string, timeoutMs = 120_000): Promise<{ approved: boolean } | null> {
    const rec = this.pending.get(id);
    if (!rec) return null;
    if (Date.now() > Date.parse(rec.expiresAt)) {
      this.finish(id, null);
      return null;
    }
    return new Promise<{ approved: boolean } | null>((resolve) => {
      const timer = setTimeout(() => {
        if (this.waiters.has(id)) {
          this.waiters.delete(id);
          resolve(null);
        }
      }, timeoutMs);
      timer.unref?.();
      this.waiters.set(id, (result) => {
        clearTimeout(timer);
        resolve(result);
      });
    });
  }

  list(): PendingRecord[] {
    const now = Date.now();
    return [...this.pending.values()].filter((r) => now <= Date.parse(r.expiresAt));
  }

  getHandleForDisplay(id: string): PendingHandle | undefined {
    const rec = this.pending.get(id);
    if (!rec) return undefined;
    return { id: rec.id, token: this.sign(rec.id, rec.expiresAt), expiresAt: rec.expiresAt, needsToken: rec.needsToken };
  }

  private finish(id: string, result: { approved: boolean } | null): void {
    this.pending.delete(id);
    const waiter = this.waiters.get(id);
    this.waiters.delete(id);
    waiter?.(result);
  }

  private sweep(): void {
    const now = Date.now();
    for (const [id, rec] of this.pending) {
      if (now > Date.parse(rec.expiresAt)) this.finish(id, null);
    }
  }

  stop(): void {
    clearInterval(this.sweeper);
  }
}
