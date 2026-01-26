from __future__ import annotations
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..core.types import ToolDefinition, ToolCategory, RiskTier, JsonSchemaField


def make_sandbox(root: str | Path):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)

    class SandboxError(Exception):
        pass

    class FileSandbox:
        def __init__(self):
            pass

        def resolve(self, path: str) -> Path:
            if not path or not path.strip():
                raise SandboxError("path required")
            target = (root / path).resolve()
            if target != root and not str(target).startswith(str(root) + os.sep):
                raise SandboxError(f"path escapes workspace sandbox: {path}")
            return target

    sandbox = FileSandbox()

    async def fs_read(args: dict[str, Any], ctx: dict[str, str]) -> dict[str, Any]:
        p = sandbox.resolve(args["path"])
        st = p.stat()
        if not st.st_mode & 0o100000:  # not a regular file
            raise ValueError("not a file")
        if st.st_size > 2_000_000:
            raise ValueError("file exceeds 2MB read limit")
        return {"path": args["path"], "content": p.read_text(encoding="utf-8"), "size": st.st_size}

    async def fs_write(args: dict[str, Any], ctx: dict[str, str]) -> dict[str, Any]:
        p = sandbox.resolve(args["path"])
        content = str(args.get("content", ""))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"path": args["path"], "bytes": len(content.encode()), "written": True}

    async def fs_move(args: dict[str, Any], ctx: dict[str, str]) -> dict[str, Any]:
        src = sandbox.resolve(args["from"])
        dst = sandbox.resolve(args["to"])
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return {"from": args["from"], "to": args["to"], "moved": True}

    async def fs_delete(args: dict[str, Any], ctx: dict[str, str]) -> dict[str, Any]:
        p = sandbox.resolve(args["path"])
        if p == root:
            raise SandboxError("cannot delete workspace root")
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
        return {"path": args["path"], "deleted": True}

    async def fs_search(args: dict[str, Any], ctx: dict[str, str]) -> dict[str, Any]:
        pattern = str(args.get("pattern", "")).lower()
        max_results = int(args.get("max", 20))
        results: list[dict[str, Any]] = []

        def walk(dir_: Path, depth: int = 0):
            if depth > 4:
                return
            for e in dir_.iterdir():
                if e.is_dir():
                    walk(e, depth + 1)
                elif not pattern or pattern in e.name.lower():
                    st = e.stat()
                    results.append({"path": str(e.relative_to(root)), "size": st.st_size})
                    if len(results) >= max_results:
                        return

        walk(root)
        return {"matches": results}

    return {
        "fs.read": fs_read,
        "fs.write": fs_write,
        "fs.move": fs_move,
        "fs.delete": fs_delete,
        "fs.search": fs_search,
        "_sandbox": sandbox,
    }


TOOL_DEFINITIONS_FILE: list[ToolDefinition] = [
    ToolDefinition(
        name="fs.read",
        version="0.1.0",
        description="Read a text file inside the workspace",
        category=ToolCategory.FILE,
        risk_tier=RiskTier.READ_ONLY,
        input_schema=JsonSchemaField(type="object", required=["path"], properties={"path": JsonSchemaField(type="string")}),
    ),
    ToolDefinition(
        name="fs.write",
        version="0.1.0",
        description="Create or overwrite a file inside the workspace",
        category=ToolCategory.FILE,
        risk_tier=RiskTier.REVERSIBLE_WRITE,
        input_schema=JsonSchemaField(type="object", required=["path", "content"], properties={"path": JsonSchemaField(type="string"), "content": JsonSchemaField(type="string")}),
    ),
    ToolDefinition(
        name="fs.move",
        version="0.1.0",
        description="Move or rename a file inside the workspace",
        category=ToolCategory.FILE,
        risk_tier=RiskTier.REVERSIBLE_WRITE,
        input_schema=JsonSchemaField(type="object", required=["from", "to"], properties={"from": JsonSchemaField(type="string"), "to": JsonSchemaField(type="string")}),
    ),
    ToolDefinition(
        name="fs.delete",
        version="0.1.0",
        description="Delete a file inside the workspace",
        category=ToolCategory.FILE,
        risk_tier=RiskTier.SYSTEM_AFFECTING,
        input_schema=JsonSchemaField(type="object", required=["path"], properties={"path": JsonSchemaField(type="string")}),
    ),
    ToolDefinition(
        name="fs.search",
        version="0.1.0",
        description="Search files by name pattern inside the workspace",
        category=ToolCategory.FILE,
        risk_tier=RiskTier.READ_ONLY,
        input_schema=JsonSchemaField(type="object", properties={"pattern": JsonSchemaField(type="string"), "max": JsonSchemaField(type="number")}),
    ),
]