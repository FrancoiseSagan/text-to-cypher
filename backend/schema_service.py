"""Auto-introspected Enhanced Schema (Ozsoy 2025) + LLM-guided Value-Aware Entity Grounding.

No hardcoded alias dictionaries, regex entity extractors, or keyword switches:
schema expansion flags and candidate entity search terms are produced semantically by the LLM
in the planning stage and verified against live Neo4j data here.
"""
from __future__ import annotations

from difflib import SequenceMatcher
import threading
import time
from typing import Any

from .models import GroundedEntity
from .neo4j_client import Neo4jClient, neo4j_client

PRIORITY_NODE_PROPS: dict[str, list[str]] = {
    "微服务": ["服务名称", "caption", "nodeId"],
    "类": ["简名", "全限定名", "类类型", "moduleId", "包名", "是否接口", "是否抽象类", "serviceContexts"],
    "方法": ["方法名", "全限定名", "所属类名", "moduleId", "是否入口方法", "访问修饰符", "返回类型", "方法签名", "serviceContexts"],
    "上游API": ["HTTP方法", "API路径", "caption", "控制器方法", "serviceContexts", "nodeId"],
    "下游API": ["HTTP方法", "API路径", "caption", "完整URL", "目标服务名", "authority", "protocol", "serviceContexts", "匹配质量"],
    "消息交换机": ["交换机名称", "交换机类型", "所属服务名", "serviceContexts"],
    "消息队列": ["队列名称", "所属服务名", "serviceContexts"],
    "配置": ["key", "maskedValue", "configurationKind", "logicalResourcePath", "moduleId", "sourceType", "serviceContexts"],
}

PRIORITY_REL_PROPS: dict[str, list[str]] = {
    "归属于": ["serviceContexts", "关系语义"],
    "调用": ["关系语义", "调用类型", "目标服务名", "目标路由", "解析状态"],
    "消息流": ["消息流类型", "路由键"],
    "目标服务": ["关系语义"],
    "接口实现": ["关系语义", "继承层级"],
    "继承": ["关系语义", "继承类型"],
    "导入": ["关系语义", "目标全限定名列表"],
    "链中下一节点": ["入口API节点", "位置索引", "关系语义"],
}


class SchemaService:
    def __init__(self, client: Neo4jClient = neo4j_client):
        self.client = client
        self._lock = threading.Lock()
        self._schema: dict[str, Any] | None = None
        self._last_loaded: float = 0.0

    def get_schema(self, force_refresh: bool = False) -> dict[str, Any]:
        with self._lock:
            if self._schema is not None and not force_refresh:
                return self._schema
            self._schema = self._introspect()
            self._last_loaded = time.time()
            return self._schema

    def _introspect(self) -> dict[str, Any]:
        all_labels = [
            r["label"]
            for r in self.client.run_raw_read("CALL db.labels() YIELD label RETURN label ORDER BY label")
        ]
        all_rels = [
            r["relationshipType"]
            for r in self.client.run_raw_read(
                "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType ORDER BY relationshipType"
            )
        ]

        label_counts: dict[str, int] = {}
        node_properties: dict[str, list[str]] = {}
        active_labels: list[str] = []
        empty_labels: list[str] = []

        for lbl in all_labels:
            cnt_row = self.client.run_raw_read(f"MATCH (n:`{lbl}`) RETURN count(n) AS c")
            cnt = int(cnt_row[0]["c"]) if cnt_row else 0
            label_counts[lbl] = cnt
            if cnt == 0:
                empty_labels.append(lbl)
                node_properties[lbl] = []
                continue
            active_labels.append(lbl)
            prop_rows = self.client.run_raw_read(
                f"MATCH (n:`{lbl}`) WITH n LIMIT 250 UNWIND keys(n) AS k RETURN DISTINCT k ORDER BY k"
            )
            node_properties[lbl] = [r["k"] for r in prop_rows]

        rel_counts: dict[str, int] = {}
        rel_properties: dict[str, list[str]] = {}
        for rel in all_rels:
            cnt_row = self.client.run_raw_read(f"MATCH ()-[r:`{rel}`]->() RETURN count(r) AS c")
            cnt = int(cnt_row[0]["c"]) if cnt_row else 0
            rel_counts[rel] = cnt
            if cnt == 0:
                rel_properties[rel] = []
                continue
            prop_rows = self.client.run_raw_read(
                f"MATCH ()-[r:`{rel}`]->() WITH r LIMIT 400 UNWIND keys(r) AS k RETURN DISTINCT k ORDER BY k"
            )
            rel_properties[rel] = [r["k"] for r in prop_rows]

        triplets = self.client.run_raw_read(
            """
            MATCH (a)-[r]->(b)
            RETURN head(labels(a)) AS src, type(r) AS rel, head(labels(b)) AS dst, count(*) AS count
            ORDER BY count DESC
            """
        )

        services = [
            r["name"]
            for r in self.client.run_raw_read(
                "MATCH (s:微服务) WHERE s.服务名称 IS NOT NULL RETURN DISTINCT s.服务名称 AS name ORDER BY name"
            )
        ]
        class_types = [
            r["v"]
            for r in self.client.run_raw_read(
                "MATCH (c:类) WHERE c.类类型 IS NOT NULL RETURN DISTINCT c.类类型 AS v ORDER BY v"
            )
        ]
        mq_stages = [
            r["v"]
            for r in self.client.run_raw_read(
                "MATCH ()-[r:消息流]->() WHERE r.消息流类型 IS NOT NULL RETURN DISTINCT r.消息流类型 AS v ORDER BY v"
            )
        ]
        queues = [
            r["v"]
            for r in self.client.run_raw_read(
                "MATCH (q:消息队列) WHERE q.队列名称 IS NOT NULL RETURN DISTINCT q.队列名称 AS v ORDER BY v"
            )
        ]
        exchanges = [
            r["v"]
            for r in self.client.run_raw_read(
                "MATCH (e:消息交换机) WHERE e.交换机名称 IS NOT NULL RETURN DISTINCT e.交换机名称 AS v ORDER BY v"
            )
        ]
        http_methods = [
            r["v"]
            for r in self.client.run_raw_read(
                "MATCH (u:上游API) WHERE u.HTTP方法 IS NOT NULL RETURN DISTINCT u.HTTP方法 AS v ORDER BY v"
            )
        ]

        # Lightweight live name vocabularies for fast typo-tolerant fuzzy grounding (difflib / edit similarity)
        method_names = [
            r["v"]
            for r in self.client.run_raw_read(
                "MATCH (m:方法) WHERE m.方法名 IS NOT NULL RETURN DISTINCT m.方法名 AS v"
            )
        ]
        class_names = [
            r["v"]
            for r in self.client.run_raw_read(
                "MATCH (c:类) WHERE c.简名 IS NOT NULL RETURN DISTINCT c.简名 AS v"
            )
        ]
        uapi_paths = [
            r["v"]
            for r in self.client.run_raw_read(
                "MATCH (u:上游API) WHERE u.API路径 IS NOT NULL RETURN DISTINCT u.API路径 AS v"
            )
        ]
        config_keys = [
            r["v"]
            for r in self.client.run_raw_read(
                "MATCH (cfg:配置) WHERE cfg.key IS NOT NULL RETURN DISTINCT cfg.key AS v"
            )
        ]

        return {
            "active_labels": active_labels,
            "empty_labels": empty_labels,
            "all_labels": all_labels,
            "label_counts": label_counts,
            "rel_types": all_rels,
            "rel_counts": rel_counts,
            "triplets": triplets,
            "node_properties": node_properties,
            "rel_properties": rel_properties,
            "enums": {
                "微服务.服务名称": services,
                "类.类类型": class_types,
                "消息流.消息流类型": mq_stages,
                "消息队列.队列名称": queues,
                "消息交换机.交换机名称": exchanges,
                "上游API.HTTP方法": http_methods,
            },
            "vocab": {
                "微服务": services,
                "方法": method_names,
                "类": class_names,
                "上游API": uapi_paths,
                "消息队列": queues,
                "消息交换机": exchanges,
                "配置": config_keys,
            },
            "refreshed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

    def format_compact_overview_for_planner(self) -> str:
        """Ultra-compact live schema skeleton for the LLM Semantic Analyzer & Entity Extractor."""
        s = self.get_schema()
        lines = [
            "有效节点标签: " + ", ".join(f":{l}({s['label_counts'].get(l, 0)})" for l in s["active_labels"]),
            "核心有向关系: " + "; ".join(f"(:{t['src']})-[:{t['rel']}]->(:{t['dst']})" for t in s["triplets"][:18]),
            f"全部微服务名({len(s['enums'].get('微服务.服务名称', []))}): " + ", ".join(s["enums"].get("微服务.服务名称", [])),
            f"全部消息队列: {s['enums'].get('消息队列.队列名称', [])} | 交换机: {s['enums'].get('消息交换机.交换机名称', [])}",
        ]
        return "\n".join(lines)

    def format_enhanced_schema_for_prompt(
        self,
        include_config_details: bool = False,
        include_version_details: bool = False,
    ) -> str:
        """Build Enhanced Schema controlled strictly by semantic planner flags (no keyword matching)."""
        s = self.get_schema()

        lines: list[str] = ["## Neo4j 代码图谱真实 Schema（自动获取）"]
        lines.append("### 1. 有效节点标签及核心属性")
        for lbl in s["active_labels"]:
            cnt = s["label_counts"].get(lbl, 0)
            if lbl == "配置" and not include_config_details:
                lines.append(f"- `:{lbl}` ({cnt}个) 核心属性: `key`, `maskedValue`, `moduleId`, `configurationKind`")
                continue
            avail = set(s["node_properties"].get(lbl, []))
            prio = [p for p in PRIORITY_NODE_PROPS.get(lbl, []) if p in avail]
            if include_version_details:
                for vp in ("来源文件", "来源行号", "图谱版本", "nodeId"):
                    if vp in avail and vp not in prio:
                        prio.append(vp)
            prop_str = ", ".join(f"`{p}`" for p in prio)
            lines.append(f"- `:{lbl}` ({cnt}个) 核心属性: {prop_str}")

        if s["empty_labels"]:
            lines.append(f"- 注意：以下标签当前节点数为 0，禁止在查询中使用: {', '.join(s['empty_labels'])}")

        lines.append("\n### 2. 有向关系拓扑 (Start)-[Rel]->(End)")
        for t in s["triplets"]:
            if t["src"] == "配置" and not include_config_details:
                continue
            lines.append(f"- `(:{t['src']})-[:{t['rel']}]->(:{t['dst']})` ({t['count']}条)")

        lines.append("\n### 3. 关系核心属性")
        for rel in s["rel_types"]:
            avail = set(s["rel_properties"].get(rel, []))
            prio = [p for p in PRIORITY_REL_PROPS.get(rel, []) if p in avail]
            if prio:
                lines.append(f"- `[:{rel}]`: " + ", ".join(f"`{p}`" for p in prio))

        lines.append("\n### 4. 关键属性枚举值与样例")
        enums = s["enums"]
        lines.append(f"- `类.类类型`: {enums.get('类.类类型', [])}")
        lines.append(f"- `消息流.消息流类型`: {enums.get('消息流.消息流类型', [])}")
        lines.append(f"- `消息队列.队列名称`: {enums.get('消息队列.队列名称', [])}")
        lines.append(f"- `消息交换机.交换机名称`: {enums.get('消息交换机.交换机名称', [])}")
        lines.append(f"- `上游API.HTTP方法`: {enums.get('上游API.HTTP方法', [])}")
        svcs = enums.get("微服务.服务名称", [])
        lines.append(f"- `微服务.服务名称` (共{len(svcs)}个): {', '.join(svcs)}")

        return "\n".join(lines)

    @staticmethod
    def _fuzzy_candidates(term: str, vocab: list[str], cutoff: float = 0.68, limit: int = 3) -> list[tuple[str, float]]:
        """Case-insensitive edit-similarity fuzzy match against live Neo4j entity vocabulary."""
        tl = term.lower().strip()
        if len(tl) < 3 or not vocab:
            return []
        scored: list[tuple[float, str]] = []
        for item in vocab:
            il = item.lower()
            ratio = SequenceMatcher(None, tl, il).ratio()
            if ratio >= cutoff:
                scored.append((round(ratio, 3), item))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [(name, score) for score, name in scored[:limit]]

    def ground_entities_from_candidates(self, candidates: list[dict[str, Any]]) -> list[GroundedEntity]:
        """Verify LLM-extracted semantic entity candidates against live Neo4j values with typo-tolerant fuzzy fallback."""
        s = self.get_schema()
        grounded: list[GroundedEntity] = []
        seen: set[tuple[str, str]] = set()

        def _add(mention: str, label: str, matched_name: str, prop_key: str, extra: dict[str, Any] | None = None) -> None:
            key = (label, matched_name)
            if key not in seen:
                seen.add(key)
                grounded.append(
                    GroundedEntity(
                        mention=mention,
                        label=label,
                        matched_name=matched_name,
                        property_key=prop_key,
                        extra=extra or {},
                    )
                )

        vocab: dict[str, list[str]] = s.get("vocab", {})
        cached_services: list[str] = vocab.get("微服务", s["enums"].get("微服务.服务名称", []))
        cached_queues: list[str] = vocab.get("消息队列", s["enums"].get("消息队列.队列名称", []))
        cached_exchanges: list[str] = vocab.get("消息交换机", s["enums"].get("消息交换机.交换机名称", []))

        for cand in candidates[:10]:
            mention = str(cand.get("mention", "")).strip()
            target_label = str(cand.get("target_label", "")).strip()
            raw_terms = cand.get("search_terms", [])
            terms = [str(t).strip() for t in raw_terms if str(t).strip()] if isinstance(raw_terms, list) else []
            if not terms and mention:
                terms = [mention]
            if not terms:
                continue

            labels_to_check = [target_label] if target_label in s["active_labels"] else ["微服务", "方法", "类", "上游API", "消息队列", "配置"]

            for lbl in labels_to_check:
                for term in terms[:3]:
                    tl = term.lower()
                    if lbl == "微服务":
                        exact = [sv for sv in cached_services if sv.lower() == tl]
                        matches = exact or [sv for sv in cached_services if tl in sv.lower()]
                        if matches:
                            for sv in matches[:5]:
                                _add(mention or term, "微服务", sv, "服务名称")
                        else:
                            for sv, score in self._fuzzy_candidates(term, cached_services, cutoff=0.68):
                                _add(mention or term, "微服务", sv, "服务名称", {"容错匹配": True, "相似度": score})
                    elif lbl == "消息队列":
                        hits = [qn for qn in cached_queues if tl in qn.lower()]
                        if hits:
                            for qn in hits:
                                _add(mention or term, "消息队列", qn, "队列名称")
                        else:
                            for qn, score in self._fuzzy_candidates(term, cached_queues, cutoff=0.65):
                                _add(mention or term, "消息队列", qn, "队列名称", {"容错匹配": True, "相似度": score})
                    elif lbl == "消息交换机":
                        hits = [ex for ex in cached_exchanges if tl in ex.lower()]
                        for ex in hits:
                            _add(mention or term, "消息交换机", ex, "交换机名称")
                    elif lbl == "方法":
                        rows = self.client.run_raw_read(
                            """
                            MATCH (m:方法)
                            WHERE toLower(m.方法名) = toLower($t) OR toLower(m.全限定名) ENDS WITH toLower('.' + $t)
                            RETURN m.方法名 AS name, m.全限定名 AS fqn, m.moduleId AS mod LIMIT 6
                            """,
                            {"t": term},
                        )
                        if not rows and len(term) >= 3:
                            rows = self.client.run_raw_read(
                                """
                                MATCH (m:方法)
                                WHERE toLower(m.方法名) CONTAINS toLower($t)
                                RETURN m.方法名 AS name, m.全限定名 AS fqn, m.moduleId AS mod LIMIT 6
                                """,
                                {"t": term},
                            )
                        if rows:
                            for r in rows:
                                _add(mention or term, "方法", r["name"], "方法名", {"全限定名": r["fqn"], "moduleId": r["mod"]})
                        else:
                            for mname, score in self._fuzzy_candidates(term, vocab.get("方法", []), cutoff=0.72):
                                frows = self.client.run_raw_read(
                                    "MATCH (m:方法 {方法名: $t}) RETURN m.方法名 AS name, m.全限定名 AS fqn, m.moduleId AS mod LIMIT 3",
                                    {"t": mname},
                                )
                                for r in frows:
                                    _add(
                                        mention or term,
                                        "方法",
                                        r["name"],
                                        "方法名",
                                        {"全限定名": r["fqn"], "moduleId": r["mod"], "容错匹配": True, "相似度": score},
                                    )
                    elif lbl == "类":
                        rows = self.client.run_raw_read(
                            """
                            MATCH (c:类)
                            WHERE toLower(c.简名) = toLower($t) OR toLower(c.全限定名) = toLower($t)
                            RETURN c.简名 AS name, c.全限定名 AS fqn, c.类类型 AS kind, c.moduleId AS mod LIMIT 5
                            """,
                            {"t": term},
                        )
                        if not rows and len(term) >= 3:
                            rows = self.client.run_raw_read(
                                """
                                MATCH (c:类)
                                WHERE toLower(c.简名) CONTAINS toLower($t)
                                RETURN c.简名 AS name, c.全限定名 AS fqn, c.类类型 AS kind, c.moduleId AS mod LIMIT 5
                                """,
                                {"t": term},
                            )
                        if rows:
                            for r in rows:
                                _add(mention or term, "类", r["name"], "简名", {"全限定名": r["fqn"], "类类型": r["kind"], "moduleId": r["mod"]})
                        else:
                            for cname, score in self._fuzzy_candidates(term, vocab.get("类", []), cutoff=0.72):
                                frows = self.client.run_raw_read(
                                    "MATCH (c:类 {简名: $t}) RETURN c.简名 AS name, c.全限定名 AS fqn, c.类类型 AS kind, c.moduleId AS mod LIMIT 3",
                                    {"t": cname},
                                )
                                for r in frows:
                                    _add(
                                        mention or term,
                                        "类",
                                        r["name"],
                                        "简名",
                                        {"全限定名": r["fqn"], "类类型": r["kind"], "moduleId": r["mod"], "容错匹配": True, "相似度": score},
                                    )
                    elif lbl in ("上游API", "下游API"):
                        rows = self.client.run_raw_read(
                            f"""
                            MATCH (a:`{lbl}`)
                            WHERE toLower(a.API路径) CONTAINS toLower($t) OR toLower(a.caption) CONTAINS toLower($t)
                            RETURN a.API路径 AS p, a.HTTP方法 AS m, a.serviceContexts AS s LIMIT 5
                            """,
                            {"t": term},
                        )
                        if rows:
                            for r in rows:
                                _add(mention or term, lbl, r["p"], "API路径", {"HTTP方法": r["m"], "serviceContexts": r["s"]})
                        elif lbl == "上游API":
                            for apath, score in self._fuzzy_candidates(term, vocab.get("上游API", []), cutoff=0.68):
                                _add(mention or term, lbl, apath, "API路径", {"容错匹配": True, "相似度": score})
                    elif lbl == "配置":
                        rows = self.client.run_raw_read(
                            "MATCH (cfg:配置) WHERE toLower(cfg.key) CONTAINS toLower($t) RETURN DISTINCT cfg.key AS k LIMIT 5",
                            {"t": term},
                        )
                        if rows:
                            for r in rows:
                                _add(mention or term, "配置", r["k"], "key")
                        else:
                            for ckey, score in self._fuzzy_candidates(term, vocab.get("配置", []), cutoff=0.72):
                                _add(mention or term, "配置", ckey, "key", {"容错匹配": True, "相似度": score})

        return grounded[:18]


schema_service = SchemaService()
