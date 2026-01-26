import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { ManagerRegistry, loadOrgConfig } from "../agents/managers.js";
import { Orchestrator } from "../core/orchestrator.js";
import {
  PermissionEngine,
  parsePolicy,
  type AuditEvent,
  type AuditSink,
} from "../core/permission-engine.js";
import type { ToolDefinition } from "../core/tool-schema.js";
import { RouterLogger } from "../router/logger.js";
import { loadPricing, ModelRouter, parseSpec } from "../router/model-router.js";
import { MockProvider } from "../router/provider.js";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "..");

const tools: ToolDefinition[] = [
  {
    name: "fs.read",
    version: "0.1.0",
    description: "Read a text file inside the workspace",
    category: "file",
    riskTier: 0,
    enabled: true,
    inputSchema: {
      type: "object",
      required: ["path"],
      properties: { path: { type: "string", description: "workspace-relative path" } },
    },
  },
  {
    name: "fs.write",
    version: "0.1.0",
    description: "Create or overwrite a file inside the workspace",
    category: "file",
    riskTier: 1,
    enabled: true,
    inputSchema: {
      type: "object",
      required: ["path", "content"],
      properties: {
        path: { type: "string" },
        content: { type: "string" },
      },
    },
  },
  {
    name: "terminal.exec",
    version: "0.1.0",
    description: "Run a shell command with timeout and output capture",
    category: "terminal",
    riskTier: 2,
    enabled: true,
    inputSchema: {
      type: "object",
      required: ["command"],
      properties: {
        command: { type: "string" },
        timeoutMs: { type: "number" },
      },
    },
  },
  {
    name: "browser.open",
    version: "0.1.0",
    description: "Open a URL in the managed browser",
    category: "browser",
    riskTier: 1,
    enabled: true,
    inputSchema: {
      type: "object",
      required: ["url"],
      properties: { url: { type: "string" } },
    },
  },
  {
    name: "screen.capture",
    version: "0.1.0",
    description: "Capture a screenshot of a display",
    category: "screen",
    riskTier: 2,
    enabled: true,
    inputSchema: {
      type: "object",
      required: [],
      properties: { display: { type: "number" } },
    },
  },
];

const events: AuditEvent[] = [];
const memorySink: AuditSink = { record: (e) => events.push(e) };

const org = loadOrgConfig(join(root, "config", "managers.json"));
const policy = parsePolicy(JSON.parse(readFileSync(join(root, "config", "permissions.json"), "utf8")));
const engine = new PermissionEngine(policy, [memorySink]);

const routerLogDir = mkdtempSync(join(tmpdir(), "tokyox-router-"));
const routerLogger = new RouterLogger(routerLogDir);
const mainRouter = new ModelRouter({
  providers: [new MockProvider("openai")],
  logger: routerLogger,
  pricing: loadPricing(join(root, "config", "models.json")),
});

const orchestrator = new Orchestrator(new ManagerRegistry(org), engine, mainRouter);
for (const t of tools) orchestrator.tools.register(t);

type Check = { label: string; pass: boolean; detail: string };
const checks: Check[] = [];

function check(label: string, pass: boolean, detail = ""): void {
  checks.push({ label, pass, detail });
}

const vOk = orchestrator.tools.validateInput("terminal.exec", { command: "ls -la", timeoutMs: 5000 });
check("tool input valid for terminal.exec", vOk.ok);

const vBad = orchestrator.tools.validateInput("terminal.exec", {});
check("tool input rejected when command missing", !vBad.ok);

const dRead = orchestrator.authorize("kapil", {
  tool: "fs.read",
  category: "file",
  riskTier: 0,
  args: { path: "notes.md" },
});
check("fs.read -> ALLOW", dRead.verdict === "ALLOW", `${dRead.ruleId}: ${dRead.reason}`);

const dWrite = orchestrator.authorize("kapil", {
  tool: "fs.write",
  category: "file",
  riskTier: 1,
  args: { path: "out.md", content: "hi" },
});
check("fs.write -> CONFIRM (no token)", dWrite.verdict === "CONFIRM" && !dWrite.requiresApprovalToken, dWrite.ruleId);

const dTerm = orchestrator.authorize("w.tester", {
  tool: "terminal.exec",
  category: "terminal",
  riskTier: 2,
  args: { command: "npm test" },
});
check(
  "terminal.exec 'npm test' -> CONFIRM + approval token required",
  dTerm.verdict === "CONFIRM" && dTerm.requiresApprovalToken,
  dTerm.ruleId
);

const dRm = orchestrator.authorize("w.terminal", {
  tool: "terminal.exec",
  category: "terminal",
  riskTier: 2,
  args: { command: "rm -rf /" },
});
check("terminal.exec 'rm -rf /' -> DENY", dRm.verdict === "DENY", `${dRm.ruleId}: ${dRm.reason}`);

const dScreen = orchestrator.authorize("kapil", {
  tool: "screen.capture",
  category: "screen",
  riskTier: 2,
  args: {},
});
check("screen.capture -> CONFIRM + token", dScreen.verdict === "CONFIRM" && dScreen.requiresApprovalToken);

check("audit trail captured all decisions", events.length === 5, `events=${events.length}`);
check("org has 5 managers", new ManagerRegistry(org).all().length === 5);
check("worker lookup works", new ManagerRegistry(org).findWorker("w.tester")?.manager.id === "mgr.code");

check("orchestrator wired to model router", orchestrator.router === mainRouter);

const r1 = await mainRouter.chat("openai:gpt-4o", {
  messages: [{ role: "user", content: "hello tokyo" }],
});
check(
  "router routes named provider",
  r1.provider === "openai" && r1.content.includes("[mock:gpt-4o]"),
  r1.content.slice(0, 40)
);
check("router estimates cost from config pricing", r1.costUsd > 0, `$${r1.costUsd.toFixed(6)}`);

const fallbackRouter = new ModelRouter({
  providers: [new MockProvider("openai", "always-fail"), new MockProvider("openrouter")],
  logger: routerLogger,
});
const r2 = await fallbackRouter.chat(["openai:gpt-4o", "openrouter:anthropic/claude-3.5-sonnet"], {
  messages: [{ role: "user", content: "fallback please" }],
});
check("fallback chain skips failing provider", r2.provider === "openrouter");

const emptyRouter = new ModelRouter({ providers: [], logger: routerLogger, mockFallback: true });
const r3 = await emptyRouter.chat("openai:gpt-4o-mini", {
  messages: [{ role: "user", content: "offline mode" }],
});
check("mock fallback engages with zero providers", r3.provider === "mock");

const logEntries = routerLogger.tailLines(100);
check(
  "router JSONL log captured lifecycle",
  logEntries.some((e) => e.event === "response") &&
    logEntries.some((e) => e.event === "error") &&
    logEntries.some((e) => e.event === "skip"),
  `entries=${logEntries.length}`
);
check(
  "router stats tracked",
  routerLogger.stats.ok >= 3 && routerLogger.stats.failed >= 1 && routerLogger.stats.skipped >= 1
);

let invalidSpecRejected = false;
try {
  parseSpec("nope");
} catch {
  invalidSpecRejected = true;
}
check("invalid model spec rejected", invalidSpecRejected);

let failed = 0;
for (const c of checks) {
  const mark = c.pass ? "PASS" : "FAIL";
  if (!c.pass) failed += 1;
  console.log(`${mark}  ${c.label}${c.detail ? `  (${c.detail})` : ""}`);
}
console.log(`\n${checks.length - failed}/${checks.length} smoke checks passed`);
process.exitCode = failed === 0 ? 0 : 1;
