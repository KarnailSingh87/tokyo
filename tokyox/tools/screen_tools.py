from __future__ import annotations
import asyncio
import os
import shutil
from pathlib import Path
from typing import Any


def make_screen_tools(output_dir: str):
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    async def screen_capture(args: dict[str, Any], ctx: dict[str, str]) -> dict[str, Any]:
        if sys.platform != "darwin":
            raise NotImplementedError("screen.capture currently supports macOS only")
        display = int(args.get("display", 1))
        out_dir = Path(output_dir)
        file = out_dir / f"screen-{int(asyncio.get_event_loop().time() * 1000)}.png"
        proc = await asyncio.create_subprocess_exec(
            "screencapture", "-x", f"-D{display}", str(file),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await asyncio.wait_for(proc.wait(), timeout=10)
        size = file.stat().st_size
        return {"display": display, "file": str(file), "bytes": size}

    async def screen_read(args: dict[str, Any], ctx: dict[str, str]) -> dict[str, Any]:
        return {"display": int(args.get("display", 1)), "note": "ocr pipeline planned; metadata only"}

    return {"screen.capture": screen_capture, "screen.read": screen_read}


import sys

TOOL_DEFINITIONS_SCREEN = []  # defined in tools/__init__.py