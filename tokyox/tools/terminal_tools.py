from __future__ import annotations
import asyncio
import os
import shlex
import sys
from typing import Any


def make_terminal_tool(cwd: str, defaults: dict[str, Any] | None = None):
    defaults = defaults or {}

    async def terminal_exec(args: dict[str, Any], ctx: dict[str, str]) -> dict[str, Any]:
        command = str(args.get("command", ""))
        timeout_ms = min(int(args.get("timeoutMs", defaults.get("timeoutMs", 15_000))), 60_000)
        shell = "cmd" if sys.platform == "win32" else "/bin/zsh"
        shell_args = ["/c", command] if sys.platform == "win32" else ["-lc", command]
        env = {**os.environ, "PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", ""), "TOKYOX_ACTOR": ctx.get("actor", "")}

        proc = await asyncio.create_subprocess_exec(
            shell,
            *shell_args,
            cwd=cwd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_ms / 1000)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {"code": -1, "signal": "SIGTERM", "stdout": "", "stderr": "", "timedOut": True, "truncated": True}
        cap = defaults.get("maxOutput", 100_000)
        out = stdout.decode(errors="replace")[:cap]
        err = stderr.decode(errors="replace")[:cap]
        return {
            "code": proc.returncode,
            "signal": None,
            "stdout": out,
            "stderr": err,
            "timedOut": False,
            "truncated": len(stdout) > cap or len(stderr) > cap,
        }

    return {"terminal.exec": terminal_exec}


TOOL_DEFINITIONS_TERMINAL: list = [
    # defined in tools/__init__.py
]