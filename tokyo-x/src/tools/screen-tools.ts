import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { mkdirSync, statSync } from "node:fs";
import { join } from "node:path";

const run = promisify(execFile);

export function createScreenTools(outputDir: string) {
  mkdirSync(outputDir, { recursive: true });
  return {
    "screen.capture": async (args: Record<string, unknown>) => {
      if (process.platform !== "darwin") throw new Error("screen.capture currently supports macOS only");
      const display = Number(args.display ?? 1);
      const file = join(outputDir, `screen-${Date.now()}.png`);
      await run("screencapture", ["-x", `-D${display}`, file], { timeout: 10_000 });
      const size = statSync(file).size;
      return { display, file, bytes: size };
    },
    "screen.read": async (args: Record<string, unknown>) => ({
      display: Number(args.display ?? 1),
      note: "ocr pipeline planned; metadata only in phase 5 scaffold",
    }),
  };
}