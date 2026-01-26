from __future__ import annotations
import json
import os
from dataclasses import dataclass
from typing import Any


@dataclass
class Skill:
    id: str
    name: str
    description: str
    prompt_template: str
    allowed_tools: list[str]
    model_spec: list[str]


class SkillRegistry:
    def __init__(self, path: str | None = None):
        self._skills: dict[str, Skill] = {}
        if path:
            self.load(path)

    def load(self, path: str) -> None:
        with open(path) as f:
            raw = json.load(f)
        for s in raw.get("skills", []):
            self._skills[s["id"]] = Skill(**s)

    def list(self) -> list[Skill]:
        return list(self._skills.values())

    def get(self, id_: str) -> Skill | None:
        return self._skills.get(id_)

    def instantiate(self, id_: str, vars_: dict[str, str]) -> dict[str, Any] | None:
        s = self._skills.get(id_)
        if not s:
            return None
        prompt = s.prompt_template
        for k, v in vars_.items():
            prompt = prompt.replace(f"{{{{{k}}}}}", v)
        return {"prompt": prompt, "skill": s}