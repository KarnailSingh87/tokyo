import { createInterface, type Interface } from "node:readline/promises";

import type { Orchestrator, ExecutionOutcome, Decision } from "../../core/orchestrator.js";

export class McpServer {
  private rl?: Interface;

  constructor(private readonly orchestrator: Orchestrator) {}

  async handleRequest(req: { id?: string | number; method: string; params?: unknown }): Promise<{
    jsonrpc: "2.0";
    id?: string | number;
    result?: unknown;
    error?: { code: number; message: string; data?: unknown };
  }> {
    const id = req.id;
    try {
      switch (req.method) {
        case "initialize":
          return { jsonrpc: "2.0", id, result: { protocolVersion: "2024-11-05", capabilities: { tools: {} }, serverInfo: { name: "tokyo-x", version: "0.1.0" } } };
        case "tools/list": {
          const tools = this.orchestrator.tools.list().map((t) => ({
            name: t.name,
            description: t.description,
            inputSchema: t.inputSchema,
          }));
          return { jsonrpc: "2.0", id, result: { tools } };
        }
        case "tools/call": {
          const params = req.params as { name?: string; arguments?: Record<string, unknown> };
          if (!params?.name) throw new Error("tools/call requires params.name");
          const actor = "mcp-client";
          const outcome: ExecutionOutcome = await this.orchestrator.executeTool(actor, params.name, params.arguments ?? {});
          const payload = JSON.stringify(outcome, null, 2);
          return {
            jsonrpc: "2.0",
            id,
            result: {
              content: [{ type: "text", text: payload }],
              isError: outcome.status !== "executed",
            },
          };
        }
        default:
          return { jsonrpc: "2.0", id, error: { code: -32601, message: `method not found: ${req.method}` } };
      }
    } catch (err) {
      return { jsonrpc: "2.0", id, error: { code: -32603, message: err instanceof Error ? err.message : String(err) } };
    }
  }

  async serveStdio(): Promise<void> {
    this.rl = createInterface({ input: process.stdin, output: process.stdout, terminal: false });
    for await (const line of this.rl) {
      try {
        const req = JSON.parse(line);
        const resp = await this.handleRequest(req);
        console.log(JSON.stringify(resp));
      } catch {
        console.log(JSON.stringify({ jsonrpc: "2.0", error: { code: -32700, message: "parse error" } }));
      }
    }
  }
}

if (process.env.TOKYOX_MCP_STDIO === "1") {
  console.error("[mcp] stdio mode requires pre-built orchestrator; run via server instead");
}