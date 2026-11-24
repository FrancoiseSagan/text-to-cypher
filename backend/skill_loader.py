"""Dynamic loader & CRUD manager for modular, versioned Skill units (SKILL.md format)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
from typing import Any
import yaml

from .config import settings

VALID_SKILL_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")


@dataclass
class SkillUnit:
    name: str
    version: str
    description: str
    triggers: list[str]
    body: str
    raw_content: str
    path: str


def _serialize_skill_md(name: str, version: str, description: str, triggers: list[str], body: str) -> str:
    frontmatter = yaml.safe_dump(
        {
            "name": name,
            "version": version,
            "description": description,
            "triggers": triggers,
        },
        allow_unicode=True,
        sort_keys=False,
    ).strip()
    return f"---\n{frontmatter}\n---\n\n{body.strip()}\n"


class SkillLoader:
    def __init__(self, skills_dir: Path | None = None):
        self.skills_dir = skills_dir or settings.skills_dir
        self._skills: list[SkillUnit] = []
        self.reload()

    def reload(self) -> None:
        units: list[SkillUnit] = []
        if not self.skills_dir.exists():
            self._skills = []
            return
        for skill_file in sorted(self.skills_dir.glob("*/SKILL.md")):
            raw = skill_file.read_text(encoding="utf-8")
            meta: dict[str, Any] = {}
            body = raw
            if raw.startswith("---"):
                parts = raw.split("---", 2)
                if len(parts) == 3:
                    meta = yaml.safe_load(parts[1]) or {}
                    body = parts[2].strip()
            units.append(
                SkillUnit(
                    name=str(meta.get("name", skill_file.parent.name)),
                    version=str(meta.get("version", "1.0.0")),
                    description=str(meta.get("description", "")),
                    triggers=[str(t) for t in meta.get("triggers", [])],
                    body=body,
                    raw_content=raw,
                    path=str(skill_file),
                )
            )
        self._skills = units

    @staticmethod
    def _to_dict(s: SkillUnit) -> dict[str, Any]:
        return {
            "name": s.name,
            "version": s.version,
            "description": s.description,
            "triggers": s.triggers,
            "body": s.body,
            "raw_content": s.raw_content,
            "is_base": s.name == "base-code-graph",
        }

    def list_skills(self) -> list[dict[str, Any]]:
        return [self._to_dict(s) for s in self._skills]

    def get_skill(self, name: str) -> dict[str, Any] | None:
        for s in self._skills:
            if s.name == name:
                return self._to_dict(s)
        return None

    def create_skill(
        self,
        name: str,
        version: str,
        description: str,
        triggers: list[str],
        body: str,
    ) -> dict[str, Any]:
        clean_name = name.strip()
        if not VALID_SKILL_NAME.match(clean_name):
            raise ValueError("技能名称仅支持字母、数字、连字符(-)和下划线(_)")
        target_dir = self.skills_dir / clean_name
        target_file = target_dir / "SKILL.md"
        if target_file.exists():
            raise ValueError(f"技能 '{clean_name}' 已存在")
        target_dir.mkdir(parents=True, exist_ok=True)
        content = _serialize_skill_md(clean_name, version.strip() or "1.0.0", description.strip(), triggers, body)
        target_file.write_text(content, encoding="utf-8")
        self.reload()
        return self.get_skill(clean_name)  # type: ignore[return-value]

    def update_skill(
        self,
        name: str,
        version: str | None = None,
        description: str | None = None,
        triggers: list[str] | None = None,
        body: str | None = None,
        raw_content: str | None = None,
    ) -> dict[str, Any] | None:
        existing = next((s for s in self._skills if s.name == name), None)
        if not existing:
            return None
        target_file = Path(existing.path)
        if raw_content is not None:
            target_file.write_text(raw_content, encoding="utf-8")
        else:
            new_ver = version.strip() if version is not None else existing.version
            new_desc = description.strip() if description is not None else existing.description
            new_trigs = triggers if triggers is not None else existing.triggers
            new_body = body if body is not None else existing.body
            content = _serialize_skill_md(existing.name, new_ver, new_desc, new_trigs, new_body)
            target_file.write_text(content, encoding="utf-8")
        self.reload()
        return self.get_skill(name)

    def delete_skill(self, name: str) -> bool:
        if name == "base-code-graph":
            raise ValueError("基础规范技能 base-code-graph 不可删除（可编辑）")
        existing = next((s for s in self._skills if s.name == name), None)
        if not existing:
            return False
        skill_dir = Path(existing.path).parent
        if skill_dir.exists() and skill_dir.parent == self.skills_dir:
            shutil.rmtree(skill_dir)
        self.reload()
        return True

    def select_by_names(self, names: list[str]) -> list[SkillUnit]:
        """Load base skill plus semantically chosen skill units by name."""
        name_set = set(names)
        selected: list[SkillUnit] = []
        for s in self._skills:
            if s.name == "base-code-graph" or s.name in name_set:
                selected.append(s)
        return selected

    def format_catalog_for_router(self) -> str:
        """Compact catalog of available Skills for LLM semantic selection."""
        lines = []
        for s in self._skills:
            if s.name == "base-code-graph":
                continue
            lines.append(f"- `{s.name}`: {s.description}")
        return "\n".join(lines)

    def select_skills(self, question: str, intent_category: str = "") -> list[SkillUnit]:
        """Fallback selector when explicit skill names are not provided."""
        selected: list[SkillUnit] = []
        q_lower = question.lower()
        for s in self._skills:
            if s.name == "base-code-graph":
                selected.append(s)
                continue
            if any(trig == intent_category or (trig and trig.lower() in q_lower) for trig in s.triggers):
                selected.append(s)
        return selected

    def format_for_prompt(self, skills: list[SkillUnit]) -> str:
        if not skills:
            return ""
        blocks = [f"### Skill: {s.name} (v{s.version})\n{s.body}" for s in skills]
        return "## 加载的领域查询技能 (Skills)\n" + "\n\n".join(blocks)


skill_loader = SkillLoader()
