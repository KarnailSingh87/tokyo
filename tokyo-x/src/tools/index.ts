import type { ToolDefinition, RiskTier, ToolCategory } from "../core/tool-schema.js";
import type { ExecutorFn } from "../core/orchestrator.js";
import { FileSandbox, createFileTools } from "./file-tools.js";
import { createTerminalTool } from "./terminal-tools.js";
import { createBrowserTools } from "./browser-tools.js";
import { createScreenTools } from "./screen-tools.js";
import type { TwinMemory } from "../modules/memory/twin.js";

const memoryStore = new Map<string, { value: string; tags: string[]; ts: string }>();

function now() {
  return new Date().toISOString();
}

export const TOOL_DEFINITIONS: ToolDefinition[] = [
  {
    name: "fs.read",
    version: "0.1.0",
    description: "Read a text file inside the workspace",
    category: "file",
    riskTier: 0,
    enabled: true,
    inputSchema: { type: "object", required: ["path"], properties: { path: { type: "string", description: "workspace-relative path" } } },
  },
  {
    name: "fs.write",
    version: "0.1.0",
    description: "Create or overwrite a file inside the workspace",
    category: "file",
    riskTier: 1,
    enabled: true,
    inputSchema: { type: "object", required: ["path", "content"], properties: { path: { type: "string" }, content: { type: "string" } } },
  },
  {
    name: "fs.move",
    version: "0.1.0",
    description: "Move or rename a file inside the workspace",
    category: "file",
    riskTier: 1,
    enabled: true,
    inputSchema: { type: "object", required: ["from", "to"], properties: { from: { type: "string" }, to: { type: "string" } } },
  },
  {
    name: "fs.delete",
    version: "0.1.0",
    description: "Delete a file inside the workspace",
    category: "file",
    riskTier: 2,
    enabled: true,
    inputSchema: { type: "object", required: ["path"], properties: { path: { type: "string" } } },
  },
  {
    name: "fs.search",
    version: "0.1.0",
    description: "Search files by name pattern inside the workspace",
    category: "file",
    riskTier: 0,
    enabled: true,
    inputSchema: { type: "object", properties: { pattern: { type: "string" }, max: { type: "number" } } },
  },
  {
    name: "terminal.exec",
    version: "0.1.0",
    description: "Run a shell command with timeout and output capture",
    category: "terminal",
    riskTier: 2,
    enabled: true,
    inputSchema: { type: "object", required: ["command"], properties: { command: { type: "string" }, timeoutMs: { type: "number" } } },
  },
  {
    name: "browser.open",
    version: "0.1.0",
    description: "Open a URL and return title/status",
    category: "browser",
    riskTier: 1,
    enabled: true,
    inputSchema: { type: "object", required: ["url"], properties: { url: { type: "string" } } },
  },
  {
    name: "browser.search",
    version: "0.1.0",
    description: "Search the web via DuckDuckGo HTML",
    category: "browser",
    riskTier: 1,
    enabled: true,
    inputSchema: { type: "object", required: ["query"], properties: { query: { type: "string" } } },
  },
  {
    name: "browser.act",
    version: "0.1.0",
    description: "Automated browser actions (planned)",
    category: "browser",
    riskTier: 2,
    enabled: true,
    inputSchema: { type: "object", properties: { script: { type: "string" } } },
  },
  {
    name: "screen.capture",
    version: "0.1.0",
    description: "Capture a screenshot of a display",
    category: "screen",
    riskTier: 2,
    enabled: true,
    inputSchema: { type: "object", required: [], properties: { display: { type: "number" } } },
  },
  {
    name: "screen.read",
    version: "0.1.0",
    description: "Read screen metadata (placeholder)",
    category: "screen",
    riskTier: 1,
    enabled: true,
    inputSchema: { type: "object", required: [], properties: { display: { type: "number" } } },
  },
  {
    name: "memory.get",
    version: "0.1.0",
    description: "Get a value from the digital twin memory",
    category: "memory",
    riskTier: 0,
    enabled: true,
    inputSchema: { type: "object", required: ["key"], properties: { key: { type: "string" } } },
  },
  {
    name: "memory.set",
    version: "0.1.0",
    description: "Set a value in the digital twin memory",
    category: "memory",
    riskTier: 0,
    enabled: true,
    inputSchema: { type: "object", required: ["key", "value"], properties: { key: { type: "string" }, value: { type: "string" }, tags: { type: "array", items: { type: "string" } } } },
  },
  {
    name: "voice.stt",
    version: "0.1.0",
    description: "Speech-to-text via API endpoints",
    category: "voice",
    riskTier: 0,
    enabled: true,
    inputSchema: { type: "object", properties: {} },
  },
  {
    name: "voice.tts",
    version: "0.1.0",
    description: "Text-to-speech via API endpoints",
    category: "voice",
    riskTier: 0,
    enabled: true,
    inputSchema: { type: "object", properties: {} },
  },
  {
    name: "notify.send",
    version: "0.1.0",
    description: "Send a notification (log placeholder)",
    category: "notify",
    riskTier: 1,
    enabled: true,
    inputSchema: { type: "object", required: ["target", "message"], properties: { target: { type: "string" }, message: { type: "string" } } },
  },
];

export function createToolExecutors(opts: {
  workspaceRoot: string;
  screenDir: string;
  twin?: TwinMemory;
  extraExecutors?: Record<string, ExecutorFn>;
}): Record<string, ExecutorFn> {
  const sandbox = new FileSandbox(opts.workspaceRoot);
  const file = createFileTools(sandbox);
  const terminal = createTerminalTool(opts.workspaceRoot);
  const browser = createBrowserTools();
  const screen = createScreenTools(opts.screenDir);

  const execs: Record<string, ExecutorFn> = {
    "fs.read": file["fs.read"],
    "fs.write": file["fs.write"],
    "fs.move": file["fs.move"],
    "fs.delete": file["fs.delete"],
    "fs.search": file["fs.search"],
    "terminal.exec": terminal["terminal.exec"],
    "browser.open": browser["browser.open"],
    "browser.search": browser["browser.search"],
    "browser.act": browser["browser.act"],
    "screen.capture": screen["screen.capture"],
    "screen.read": screen["screen.read"],
    "memory.get": async (args: Record<string, unknown>) => {
      const key = String(args.key ?? "");
      if (!key) throw new Error("key required");
      const twin = opts.twin;
      const entry = twin ? twin.get(key) : memoryStore.get(key);
      return entry ? { key, value: entry.value, tags: entry.tags, ts: entry.ts } : null;
    },
    "memory.set": async (args: Record<string, unknown>) => {
      const key = String(args.key ?? "");
      const value = String(args.value ?? "");
      if (!key) throw new Error("key required");
      const tags = (args.tags as string[] ?? []) || [];
      if (opts.twin) {
        return opts.twin.set(key, value, tags);
      } else {
        memoryStore.set(key, { value, tags, ts: now() });
        return { key, value, tags, ts: now() };
      }
    },
    "voice.stt": async (_args: Record<string, unknown>) => ({ configured: false, note: "use /api/voice/stt endpoint" }),
    "voice.tts": async (_args: Record<string, unknown>) => ({ configured: false, note: "use /api/voice/tts endpoint" }),
    "notify.send": async (args: Record<string, unknown>) => ({
      queued: true,
      target: String(args.target ?? "log"),
      message: String(args.message ?? ""),
      ts: now(),
    }),
    ...(opts.extraExecutors ?? {}),
  };

  return execs;
}