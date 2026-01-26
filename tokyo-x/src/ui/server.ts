import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { readFile, stat } from "node:fs/promises";
import { dirname, extname, join, normalize, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { randomBytes } from "node:crypto";
import { WebSocketServer, WebSocket, type RawData } from "ws";
import { Duplex } from "node:stream";

import { loadOrgConfig, ManagerRegistry } from "../agents/managers.js";
import { loadDotEnv, optionalEnv } from "../core/env.js";
import { readFileSync } from "node:fs";
import { FileAuditSink } from "../core/audit.js";
import { PendingApprovals } from "../core/approvals.js";
import { ToolDefinition } from "../core/tool-schema.js";
import { createProductionRouter } from "../router/model-router.js";
import { ElevenLabsTTS, loadVoices } from "../voice/tts.js";
import { createTranscriber } from "../voice/stt.js";
import { TwinMemory } from "../modules/memory/twin.js";
import { AgentBus } from "../modules/a2a/bus.js";
import { TaskManager } from "../modules/jobs/task-manager.js";
import { ProactiveWatcher } from "../modules/proactive/watcher.js";
import { SkillRegistry } from "../modules/skills/registry.js";
import { CostDashboard } from "../modules/cost/dashboard.js";
import { AgentLoop } from "../core/agent-loop.js";
import { Orchestrator, type ExecutionOutcome } from "../core/orchestrator.js";
import { createToolExecutors, TOOL_DEFINITIONS } from "../tools/index.js";
import { PermissionEngine, parsePolicy, type Decision } from "../core/permission-engine.js";

const rootDir = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const publicDir = join(rootDir, "src", "ui", "public");

loadDotEnv(rootDir);

const host = optionalEnv("TOKYOX_HOST", "127.0.0.1");
const port = Number(optionalEnv("TOKYOX_PORT", "8787"));

const logsDir = join(rootDir, "logs");
const workspaceRoot = optionalEnv("TOKYOX_WORKSPACE_ROOT", "./workspace");
const screenDir = join(rootDir, "logs", "screens");
const auditDir = optionalEnv("TOKYOX_AUDIT_DIR", "./logs/audit");
const approvalSecret = optionalEnv("TOKYOX_APPROVAL_TOKEN_SECRET", "dev-secret-change-me");

const pairingCode = Array.from(randomBytes(8)).map((b) => b.toString(16).padStart(2, "0")).join("-").toUpperCase();
const pairToken = pairingCode.replace(/-/g, "");

const org = loadOrgConfig(join(rootDir, "config", "managers.json"));
const policy = parsePolicy(JSON.parse(readFileSync(join(rootDir, "config", "permissions.json"), "utf8")));

const voices = loadVoices(join(rootDir, "config", "voices.json"));
const tts = new ElevenLabsTTS(voices);
const stt = createTranscriber();

const twin = new TwinMemory(join(rootDir, "logs", "twin"));
const bus = new AgentBus();
const watcher = new ProactiveWatcher(bus, twin);
const skills = new SkillRegistry(join(rootDir, "config", "skills.json"));
const jobs = new TaskManager(logsDir);
const router = createProductionRouter(logsDir, join(rootDir, "config"));
const costDashboard = new CostDashboard(router.logger);

const auditSink = new FileAuditSink(auditDir);
const engine = new PermissionEngine(policy, [auditSink]);
const approvals = new PendingApprovals(approvalSecret, 5 * 60_000, (handle, rec) => {
  hub.broadcastApproval({ id: handle.id, tool: rec.decision.tool, tier: rec.riskTier ?? 0, args: rec.args ?? {}, expiresAt: handle.expiresAt });
});

const orchestrator = new Orchestrator(
  new ManagerRegistry(org),
  engine,
  router,
  approvals
);

for (const td of TOOL_DEFINITIONS) orchestrator.tools.register(td);
const execs = createToolExecutors({
  workspaceRoot: join(rootDir, workspaceRoot),
  screenDir,
  twin,
});
for (const [name, fn] of Object.entries(execs)) orchestrator.registerExecutor(name, fn);

jobs.register("goal", async (payload: unknown, job, report) => {
  const { goal, actor = "kapil" } = payload as { goal: string; actor?: string };
  const loop = new AgentLoop(router, orchestrator);
  const run = await loop.runGoal(goal, actor);
  report(50);
  return { run, summary: run.summary };
});

const agentLoop = new AgentLoop(router, orchestrator);

class ApprovalHub {
  private wss = new WebSocketServer({ noServer: true });
  private clients = new Map<WebSocket, { id: string; authed: boolean }>();

  constructor(
    private readonly pairToken: string,
    private readonly onDecision: (id: string, approved: boolean) => void
  ) {}

  handleUpgrade(req: IncomingMessage, socket: Duplex, head: Buffer) {
    if (new URL(req.url ?? "/", `http://${req.headers.host}`).pathname !== "/ws/phone") {
      socket.destroy();
      return;
    }
    this.wss.handleUpgrade(req, socket, head, (ws) => this.setup(ws));
  }

  private setup(ws: WebSocket) {
    const state = { id: randomBytes(6).toString("hex"), authed: false };
    this.clients.set(ws, state);
    ws.on("message", (raw: RawData) => {
      let msg;
      try {
        msg = JSON.parse(String(raw));
      } catch {
        ws.close();
        return;
      }
      if (!state.authed) {
        if (msg?.type === "hello" && typeof msg.token === "string" && this.safeEq(msg.token, pairToken)) {
          state.authed = true;
          ws.send(JSON.stringify({ type: "welcome", clientId: state.id }));
          ws.send(JSON.stringify({ type: "pending", approvals: approvals.list().map((r) => this.serialize(r)) }));
        } else {
          ws.close();
        }
        return;
      }
      if (msg?.type === "decision" && typeof msg.id === "string" && typeof msg.approved === "boolean") {
        approvals.resolve(msg.id, msg.approved, { via: "phone" });
      }
    });
    ws.on("close", () => this.clients.delete(ws));
    ws.on("error", () => {});
  }

  private safeEq(a: string, b: string): boolean {
    const ba = Buffer.from(a);
    const bb = Buffer.from(b);
    return ba.length === bb.length && require("node:crypto").timingSafeEqual(ba, bb);
  }

  private serialize(r: { id: string; decision: Decision; createdAt: string; expiresAt: string; needsToken: boolean; args?: Record<string, unknown>; category?: string; riskTier?: number }) {
    return { id: r.id, tool: r.decision.tool, tier: r.riskTier ?? 0, args: r.args ?? {}, expiresAt: r.expiresAt };
  }

  broadcastApproval(payload: { id: string; tool: string; tier: number; args?: Record<string, unknown>; expiresAt: string }) {
    const msg = JSON.stringify({ type: "approval_request", ...payload });
    for (const [ws, st] of this.clients) if (st.authed && ws.readyState === WebSocket.OPEN) ws.send(msg);
  }

  broadcastUpdate(payload: { id: string; approved: boolean }) {
    const msg = JSON.stringify({ type: "approval_update", ...payload });
    for (const [ws, st] of this.clients) if (st.authed && ws.readyState === WebSocket.OPEN) ws.send(msg);
  }
}

const hub = new ApprovalHub(pairToken, (id: string, approved: boolean) => {
  hub.broadcastUpdate({ id, approved });
});

const mime: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
  ".webmanifest": "application/manifest+json",
};

function send(res: ServerResponse, code: number, body: string | Buffer, type = "application/json"): void {
  res.writeHead(code, { "content-type": type, "cache-control": "no-store" });
  res.end(body);
}

async function readJsonBody(req: IncomingMessage, limit = 1_000_000): Promise<Record<string, unknown>> {
  const chunks: Buffer[] = [];
  for await (const c of req) {
    chunks.push(c);
    if (Buffer.concat(chunks).length > limit) throw new Error("body too large");
  }
  return JSON.parse(Buffer.concat(chunks).toString()) as Record<string, unknown>;
}

async function readRawBody(req: IncomingMessage, limit = 5_000_000): Promise<Buffer> {
  const chunks: Buffer[] = [];
  for await (const c of req) {
    chunks.push(c);
    if (Buffer.concat(chunks).length > limit) throw new Error("body too large");
  }
  return Buffer.concat(chunks);
}

async function serveStatic(pathname: string, res: ServerResponse): Promise<void> {
  let rel = pathname === "/" ? "index.html" : pathname.replace(/^\/+/, "");
  if (rel.endsWith("/")) rel += "index.html";
  if (rel.startsWith("phone") && rel === "phone") rel = "phone/index.html";
  const filePath = normalize(join(publicDir, rel));
  if (!filePath.startsWith(publicDir + sep)) return send(res, 403, JSON.stringify({ error: "forbidden" }));
  try {
    await stat(filePath);
  } catch {
    return send(res, 404, JSON.stringify({ error: "not found" }));
  }
  const data = await readFile(filePath);
  send(res, 200, data, mime[extname(filePath).toLowerCase()] ?? "application/octet-stream");
}

const server = createServer(async (req: IncomingMessage, res: ServerResponse) => {
  const url = new URL(req.url ?? "/", `http://${req.headers.host ?? "localhost"}`);
  try {
    if (url.pathname === "/api/health") return send(res, 200, JSON.stringify({ status: "ok", service: "tokyo-x", phase: 8 }));
    if (url.pathname === "/api/status")
      return send(
        res,
        200,
        JSON.stringify({
          status: "ok",
          service: "tokyo-x",
          phase: 8,
          uptimeSec: Math.round(process.uptime()),
          router: router.status(),
          pairingCode,
          pendingApprovals: approvals.list().length,
          jobs: jobs.stats,
        })
      );
    if (url.pathname === "/api/org") return send(res, 200, JSON.stringify(org));
    if (url.pathname === "/api/audit/tail") return send(res, 200, JSON.stringify(auditSink.tail(Number(url.searchParams.get("n") ?? 50))));
    if (url.pathname === "/api/voice/presets")
      return send(res, 200, JSON.stringify({ presets: tts.presets(), default: tts.defaultPreset().id, ttsAvailable: tts.isConfigured() }));
    if (url.pathname === "/api/voice/tts" && req.method === "POST") {
      const body = await readJsonBody(req);
      const result = await tts.synthesize(String(body.text ?? ""), body.preset as string | undefined);
      if (!result.ok || !result.audio) return send(res, 503, JSON.stringify({ fallback: true, reason: result.reason }));
      return send(res, 200, result.audio, "audio/mpeg");
    }
    if (url.pathname === "/api/voice/stt" && req.method === "POST") {
      const audio = await readRawBody(req);
      const mimeType = req.headers["content-type"] ?? "audio/webm";
      const result = await stt.transcribe(audio, mimeType);
      return send(res, 200, JSON.stringify(result));
    }
    if (url.pathname === "/api/approvals" && req.method === "GET") {
      const list = approvals.list().map((r) => {
        const h = approvals.getHandleForDisplay(r.id);
        return { ...r, token: h?.token, needsToken: h?.needsToken };
      });
      return send(res, 200, JSON.stringify(list));
    }
    if (url.pathname === "/api/approvals/resolve" && req.method === "POST") {
      const body = await readJsonBody(req);
      const ok = approvals.resolve(String(body.id), Boolean(body.approved), { token: body.token as string | undefined });
      return send(res, ok ? 200 : 400, JSON.stringify({ ok }));
    }
    if (url.pathname === "/api/goal" && req.method === "POST") {
      const body = await readJsonBody(req);
      const run = await agentLoop.runGoal(String(body.goal ?? ""), "kapil");
      return send(res, 200, JSON.stringify(run));
    }
    if (url.pathname === "/api/jobs" && req.method === "POST") {
      const body = await readJsonBody(req);
      const job = jobs.submit(String(body.kind), body.payload);
      return send(res, 201, JSON.stringify(job));
    }
    if (url.pathname === "/api/jobs" && req.method === "GET") return send(res, 200, JSON.stringify(jobs.list()));
    if (url.pathname === "/api/jobs/cancel" && req.method === "POST") {
      const body = await readJsonBody(req);
      return send(res, jobs.cancel(String(body.id)) ? 200 : 404, JSON.stringify({ ok: jobs.cancel(String(body.id)) }));
    }
    if (url.pathname === "/api/costs") return send(res, 200, JSON.stringify(costDashboard.summary()));
    if (url.pathname === "/api/memory" && req.method === "GET") {
      const q = url.searchParams.get("q") ?? "";
      return send(res, 200, JSON.stringify(q ? twin.search(q) : twin.recent(20)));
    }
    if (url.pathname === "/api/memory" && req.method === "POST") {
      const body = await readJsonBody(req);
      return send(res, 200, JSON.stringify(twin.set(String(body.key), String(body.value), body.tags as string[] ?? [])));
    }
    if (url.pathname === "/api/simulation" && req.method === "POST") {
      const body = await readJsonBody(req);
      const { simulation } = await import("../modules/simulation.js");
      simulation.enabled = Boolean(body.enabled);
      return send(res, 200, JSON.stringify({ simulation: simulation.enabled }));
    }
    await serveStatic(url.pathname, res);
  } catch (err) {
    send(res, 500, JSON.stringify({ error: err instanceof Error ? err.message : "internal error" }));
  }
});

server.on("upgrade", (req, socket, head) => hub.handleUpgrade(req, socket, head));

server.listen(port, host, () => {
  console.log(`[tokyo-x] UI online at http://${host}:${port}`);
  console.log(`[tokyo-x] pairing code: ${pairingCode}  (enter on phone at /phone)`);
});