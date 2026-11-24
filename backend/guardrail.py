"""Three-layer Cypher Guardrail Validator:
1. Static Read-Only Security & Non-Empty & Statement Type
2. Live Schema Legality Pre-check (Labels, RelTypes, Empty-Label Blocking)
3. Neo4j Native EXPLAIN Syntax & Plan Check
"""
from __future__ import annotations

import re
from typing import Any

from .models import ValidationReport
from .neo4j_client import Neo4jClient, neo4j_client
from .schema_service import SchemaService, schema_service

FORBIDDEN_PATTERNS: list[tuple[str, str]] = [
    (r"\bCREATE\b", "禁止写操作 CREATE"),
    (r"\bMERGE\b", "禁止写操作 MERGE"),
    (r"\bDELETE\b", "禁止写操作 DELETE"),
    (r"\bDETACH\b", "禁止写操作 DETACH"),
    (r"\bSET\b", "禁止写操作 SET"),
    (r"\bREMOVE\b", "禁止写操作 REMOVE"),
    (r"\bDROP\b", "禁止管理操作 DROP"),
    (r"\bFOREACH\b", "禁止写控制语句 FOREACH"),
    (r"\bLOAD\s+CSV\b", "禁止外部文件加载 LOAD CSV"),
    (r"\bALTER\b|\bGRANT\b|\bREVOKE\b|\bDENY\b", "禁止权限/库管理操作"),
    (r"\bCALL\s+apoc\.(export|import|periodic|refactor|create|merge|load)", "禁止危险 APOC 过程"),
    (r"\bCALL\s+dbms\.security", "禁止安全管理过程"),
]

ALLOWED_STARTS = ("MATCH", "OPTIONAL", "WITH", "UNWIND", "CALL", "RETURN")


def _strip_string_literals(cypher: str) -> str:
    """Remove single/double quoted string literals and comments before static keyword inspection."""
    no_line_comments = re.sub(r"//[^\n]*", " ", cypher)
    no_block_comments = re.sub(r"/\*.*?\*/", " ", no_line_comments, flags=re.DOTALL)
    no_single = re.sub(r"'([^'\\]|\\.)*'", "''", no_block_comments)
    no_double = re.sub(r'"([^"\\]|\\.)*"', '""', no_single)
    return no_double


def _extract_node_labels(clean_cypher: str) -> set[str]:
    """Extract node labels from (var:Label) or (:Label) patterns."""
    labels: set[str] = set()
    # Match inside parentheses (...)
    for node_expr in re.findall(r"\(([^()]*)\)", clean_cypher):
        # Drop property maps { ... } inside parentheses
        expr = re.sub(r"\{[^}]*\}", "", node_expr)
        for lbl in re.findall(r":`?([A-Za-z0-9_\u4e00-\u9fff]+)`?", expr):
            labels.add(lbl)
    return labels


def _extract_rel_types(clean_cypher: str) -> set[str]:
    """Extract relationship types from -[r:TYPE|TYPE2*1..3]-> patterns."""
    rels: set[str] = set()
    for rel_expr in re.findall(r"\[([^\[\]]*)\]", clean_cypher):
        expr = re.sub(r"\{[^}]*\}", "", rel_expr)
        expr = re.sub(r"\*[\d.]*", "", expr)
        if ":" in expr:
            after_colon = expr.split(":", 1)[1]
            for part in after_colon.split("|"):
                part = part.strip().strip("`").lstrip(":")
                if re.fullmatch(r"[A-Za-z0-9_\u4e00-\u9fff]+", part):
                    rels.add(part)
    return rels


def _extract_properties(clean_cypher: str) -> set[str]:
    """Extract dot-accessed properties like n.方法名, ignoring procedure namespaces (db/dbms/apoc)."""
    props: set[str] = set()
    ignored_prefixes = {"db", "dbms", "apoc", "gds", "tx"}
    for prefix, prop in re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\.`?([A-Za-z0-9_\u4e00-\u9fff]+)`?", clean_cypher):
        if prefix.lower() in ignored_prefixes:
            continue
        props.add(prop)
    return props


class CypherGuardrail:
    def __init__(self, client: Neo4jClient = neo4j_client, schema_svc: SchemaService = schema_service):
        self.client = client
        self.schema_svc = schema_svc

    def validate(self, cypher: str, run_explain: bool = True) -> ValidationReport:
        checks: list[dict[str, Any]] = []
        errors: list[str] = []
        warnings: list[str] = []

        # 1. Non-empty check
        if not cypher or not cypher.strip():
            errors.append("Cypher 语句为空")
            checks.append({"name": "非空检查", "passed": False, "detail": "语句为空"})
            return ValidationReport(valid=False, checks=checks, errors=errors, warnings=warnings)
        checks.append({"name": "非空检查", "passed": True, "detail": f"长度 {len(cypher)} 字符"})

        clean = _strip_string_literals(cypher).strip()

        # 2. Statement type check
        first_word = (re.split(r"\s+", clean)[0] if clean else "").upper()
        if first_word not in ALLOWED_STARTS:
            errors.append(f"不允许的语句起始关键字: {first_word}（仅允许只读查询）")
            checks.append({"name": "语句类型检查", "passed": False, "detail": f"起始词 {first_word}"})
        else:
            checks.append({"name": "语句类型检查", "passed": True, "detail": f"只读起始词 {first_word}"})

        # 3. Forbidden write/admin operation check
        forbidden_hits: list[str] = []
        for pat, msg in FORBIDDEN_PATTERNS:
            if re.search(pat, clean, flags=re.IGNORECASE):
                forbidden_hits.append(msg)
        if forbidden_hits:
            errors.extend(forbidden_hits)
            checks.append({"name": "禁用操作检测", "passed": False, "detail": "; ".join(forbidden_hits)})
        else:
            checks.append({"name": "禁用操作检测", "passed": True, "detail": "无写操作或危险指令"})

        # Check unbounded variable-length path [*]
        if re.search(r"\[\s*[A-Za-z0-9_]*\s*(?::[^\]]*)?\*\s*\]", clean):
            warnings.append("检测到无界变长路径 [*]，可能导致环路或超时，建议限制跳数如 *1..5")

        # 4. Schema legality pre-check
        schema = self.schema_svc.get_schema()
        valid_labels = set(schema["active_labels"])
        empty_labels = set(schema["empty_labels"])
        valid_rels = set(schema["rel_types"])
        all_valid_props: set[str] = set()
        for plist in schema["node_properties"].values():
            all_valid_props.update(plist)
        for plist in schema["rel_properties"].values():
            all_valid_props.update(plist)

        used_labels = _extract_node_labels(clean)
        used_rels = _extract_rel_types(clean)
        used_props = _extract_properties(clean)

        schema_errs: list[str] = []
        for lbl in used_labels:
            if lbl in empty_labels:
                schema_errs.append(f"节点标签 `:{lbl}` 在当前图谱中节点数为 0（请改用有效标签如 `上游API`/`下游API`/`配置`）")
            elif lbl not in valid_labels:
                schema_errs.append(f"图谱中不存在节点标签 `:{lbl}`（有效标签: {', '.join(sorted(valid_labels))}）")

        for rel in used_rels:
            if rel not in valid_rels:
                schema_errs.append(f"图谱中不存在关系类型 `[:{rel}]`（有效关系: {', '.join(sorted(valid_rels))}）")

        unknown_props = [p for p in used_props if p not in all_valid_props]
        if unknown_props:
            schema_errs.append(f"图谱中不存在属性: {', '.join(unknown_props)}")

        if schema_errs:
            errors.extend(schema_errs)
            checks.append({"name": "Schema 合法性预检", "passed": False, "detail": "; ".join(schema_errs)})
        else:
            checks.append(
                {
                    "name": "Schema 合法性预检",
                    "passed": True,
                    "detail": f"标签 {sorted(used_labels)} / 关系 {sorted(used_rels)} 均合法",
                }
            )

        # 5. Neo4j native EXPLAIN syntax check (only if no forbidden writes)
        if run_explain and not forbidden_hits:
            ok, err = self.client.explain(cypher)
            if ok:
                checks.append({"name": "Neo4j EXPLAIN 语法校验", "passed": True, "detail": "执行计划解析通过"})
            else:
                errors.append(f"Neo4j 语法/计划校验失败: {err}")
                checks.append({"name": "Neo4j EXPLAIN 语法校验", "passed": False, "detail": str(err)[:240]})

        return ValidationReport(
            valid=len(errors) == 0,
            checks=checks,
            errors=errors,
            warnings=warnings,
        )


guardrail = CypherGuardrail()
