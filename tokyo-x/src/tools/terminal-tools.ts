import { spawn } from "node:child_process";

export function createTerminalTool(cwd: string, defaults: { timeoutMs?: number; maxOutput?: number } = {}) {
  return {
    "terminal.exec": async (args: Record<string, unknown>, ctx: { actor: string }) => {
      const command = String(args.command ?? "");
      const timeoutMs = Math.min(Number(args.timeoutMs ?? defaults.timeoutMs ?? 15_000), 60_000);
      const shell = process.platform === "win32" ? "cmd" : "/bin/zsh";
      const shellArgs = process.platform === "win32" ? ["/c", command] : ["-lc", command];
      return await new Promise((resolve, reject) => {
        const child = spawn(shell, shellArgs, {
          cwd,
          env: { PATH: process.env.PATH, HOME: process.env.HOME, TOKYOX_ACTOR: ctx.actor },
          signal: AbortSignal.timeout(timeoutMs),
        });
        let out = "";
        let err = "";
        const cap = defaults.maxOutput ?? 100_000;
        child.stdout.on("data", (d) => {
          if (out.length < cap) out += d;
        });
        child.stderr.on("data", (d) => {
          if (err.length < cap) err += d;
        });
        child.on("error", reject);
        child.on("close", (code, sig) => {
          resolve({
            code,
            signal: sig,
            stdout: out.slice(0, cap),
            stderr: err.slice(0, cap),
            timedOut: sig === "SIGTERM",
            truncated: out.length >= cap || err.length >= cap,
          });
        });
      });
    },
  };
}