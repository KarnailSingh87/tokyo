from __future__ import annotations
import json
import re
from typing import Any

from .types import ToolDefinition, JsonSchemaField, ToolCategory, RiskTier, ValidationResult


TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")


def validate_field(field: JsonSchemaField, value: Any, path: str, errors: list[str]) -> None:
    if field.enum and value not in field.enum:
        errors.append(f"{path}: must be one of {field.enum}")
        return
    if field.type == "string":
        if not isinstance(value, str):
            errors.append(f"{path}: expected string")
    elif field.type == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            errors.append(f"{path}: expected number")
    elif field.type == "boolean":
        if not isinstance(value, bool):
            errors.append(f"{path}: expected boolean")
    elif field.type == "array":
        if not isinstance(value, list):
            errors.append(f"{path}: expected array")
        elif field.items:
            for i, item in enumerate(value):
                validate_field(field.items, item, f"{path}[{i}]", errors)
    elif field.type == "object":
        if not isinstance(value, dict):
            errors.append(f"{path}: expected object")
        else:
            validate_object(field, value, path, errors)


def validate_object(field: JsonSchemaField, value: dict[str, Any], path: str, errors: list[str]) -> None:
    for key in field.required or []:
        if key not in value:
            errors.append(f"{path}.{key}: missing required property")
    for key, child in (field.properties or {}).items():
        if key in value and value[key] is not None:
            validate_field(child, value[key], f"{path}.{key}" if path else key, errors)


def validate_against_schema(schema: JsonSchemaField, input_data: Any) -> ValidationResult:
    if not isinstance(input_data, dict):
        return ValidationResult(ok=False, errors=["input: expected object"])
    errors: list[str] = []
    validate_object(schema, input_data, "", errors)
    return ValidationResult(ok=len(errors) == 0, errors=errors)


def tool_prompt_description(tool: ToolDefinition) -> str:
    if not tool.input_schema or not tool.input_schema.properties:
        params = "none"
    else:
        params = ", ".join(
            f"{k}:{v.type}{'' if tool.input_schema.required and k in tool.input_schema.required else '?'}"
            for k, v in tool.input_schema.properties.items()
        )
    return f"- {tool.name} [{tool.category.value}, tier {tool.risk_tier.value}] {tool.description}. Args: {params}"


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> "ToolRegistry":
        if not TOOL_NAME_RE.match(tool.name):
            raise ValueError(f"invalid tool name: {tool.name}")
        if not tool.input_schema or tool.input_schema.type != "object":
            raise ValueError(f"tool {tool.name} needs an object input_schema")
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool
        return self

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        return name in self._tools

    def list(self) -> list[ToolDefinition]:
        return sorted(self._tools.values(), key=lambda t: t.name)

    def list_by_category(self, category: ToolCategory) -> list[ToolDefinition]:
        return [t for t in self.list() if t.category == category]

    def validate_input(self, name: str, input_data: Any) -> ValidationResult:
        tool = self._tools.get(name)
        if not tool:
            return ValidationResult(ok=False, errors=[f"unknown tool: {name}"])
        if not tool.enabled:
            return ValidationResult(ok=False, errors=[f"tool disabled: {name}"])
        return validate_against_schema(tool.input_schema, input_data)

    def describe_for_llm(self) -> str:
        return "\n".join(tool_prompt_description(t) for t in self.list())