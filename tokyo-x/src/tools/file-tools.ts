import { mkdirSync, readdirSync, readFileSync, renameSync, rmSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, relative, resolve, sep } from "node:path";

export class SandboxError extends Error {}

export class FileSandbox {
  constructor(readonly root: string) {
    mkdirSync(root, { recursive: true });
  }

  resolveIn(path: string): string {
    if (typeof path !== "string" || path.trim() === "") throw new SandboxError("path required");
    const target = resolve(this.root, path);
    const normRoot = resolve(this.root);
    if (target !== normRoot && !target.startsWith(normRoot + sep)) {
      throw new SandboxError(`path escapes workspace sandbox: ${path}`);
    }
    return target;
  }
}

export function createFileTools(sandbox: FileSandbox) {
  return {
    "fs.read": async (args: Record<string, unknown>) => {
      const p = sandbox.resolveIn(String(args.path));
      const st = statSync(p);
      if (!st.isFile()) throw new Error("not a file");
      if (st.size > 2_000_000) throw new Error("file exceeds 2MB read limit");
      return { path: String(args.path), content: readFileSync(p, "utf8"), size: st.size };
    },
    "fs.write": async (args: Record<string, unknown>) => {
      const p = sandbox.resolveIn(String(args.path));
      const content = String(args.content ?? "");
      mkdirSync(dirname(p), { recursive: true });
      writeFileSync(p, content, "utf8");
      return { path: String(args.path), bytes: Buffer.byteLength(content), written: true };
    },
    "fs.move": async (args: Record<string, unknown>) => {
      const src = sandbox.resolveIn(String(args.from));
      const dst = sandbox.resolveIn(String(args.to));
      mkdirSync(dirname(dst), { recursive: true });
      renameSync(src, dst);
      return { from: String(args.from), to: String(args.to), moved: true };
    },
    "fs.delete": async (args: Record<string, unknown>) => {
      const p = sandbox.resolveIn(String(args.path));
      if (p === resolve(sandbox.root)) throw new SandboxError("cannot delete workspace root");
      rmSync(p, { force: true });
      return { path: String(args.path), deleted: true };
    },
    "fs.search": async (args: Record<string, unknown>) => {
      const pattern = String(args.pattern ?? "").toLowerCase();
      const max = Number(args.max ?? 20);
      const results: Array<{ path: string; size: number }> = [];
      function walk(dir: string, depth = 0) {
        if (depth > 4) return;
        const entries = readdirSync(dir, { withFileTypes: true });
        for (const e of entries) {
          const full = join(dir, e.name);
          if (e.isDirectory()) walk(full, depth + 1);
          else if (!pattern || e.name.toLowerCase().includes(pattern)) {
            const st = statSync(full);
            results.push({ path: relative(sandbox.root, full), size: st.size });
            if (results.length >= max) return;
          }
        }
      }
      walk(sandbox.root);
      return { matches: results };
    },
  };
}