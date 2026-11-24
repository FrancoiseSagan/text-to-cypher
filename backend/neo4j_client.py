"""Safe read-only Neo4j driver wrapper with EXPLAIN pre-check and topology extraction."""
from __future__ import annotations

import time
from typing import Any
from neo4j import GraphDatabase, Driver, unit_of_work
from neo4j.graph import Node, Relationship, Path

from .config import settings
from .models import TopologyData, TopologyEdge, TopologyNode

# High-value display properties to keep compact node metadata for UI inspection
DISPLAY_NODE_PROPS = [
    "服务名称", "caption", "简名", "方法名", "全限定名", "类类型", "moduleId",
    "HTTP方法", "API路径", "目标服务名", "完整URL", "交换机名称", "交换机类型",
    "队列名称", "所属服务名", "key", "maskedValue", "configurationKind",
    "是否入口方法", "返回类型", "serviceContexts", "来源文件", "图谱版本", "nodeId",
]

DISPLAY_REL_PROPS = [
    "消息流类型", "路由键", "关系语义", "调用类型", "目标服务名", "目标路由",
    "解析状态", "匹配类型", "来源文件", "来源行号",
]


def _pick_node_label(node: Node) -> str:
    props = dict(node)
    for key in ("服务名称", "队列名称", "交换机名称", "caption", "简名", "方法名", "全限定名", "key", "nodeId"):
        val = props.get(key)
        if val is not None and str(val).strip():
            return str(val)
    labels = list(node.labels)
    return f"{labels[0] if labels else 'Node'}#{node.element_id}"


def _clean_props(raw: dict[str, Any], allowlist: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k in allowlist:
        if k in raw and raw[k] is not None:
            v = raw[k]
            if isinstance(v, str) and len(v) > 200:
                v = v[:200] + "..."
            elif isinstance(v, list) and len(v) > 10:
                v = v[:10]
            out[k] = v
    if not out:
        for k, v in list(raw.items())[:8]:
            if v is not None:
                out[k] = str(v)[:160] if isinstance(v, str) else v
    return out


def _detect_mechanism(rel_type: str, rel_props: dict[str, Any], src_cat: str, dst_cat: str) -> str:
    if rel_type == "消息流":
        return "MQ"
    if rel_type == "目标服务" or src_cat == "下游API" or dst_cat in ("下游API", "上游API"):
        return "RPC"
    sem = str(rel_props.get("关系语义", ""))
    if "HTTP" in sem or "跨服务" in sem:
        return "RPC"
    return "STRUCTURAL"


def _format_cell_value(val: Any) -> Any:
    if isinstance(val, Node):
        labels = ":".join(val.labels)
        return f"({labels}) {_pick_node_label(val)}"
    if isinstance(val, Relationship):
        stage = val.get("消息流类型")
        return f"[:{val.type}{f'({stage})' if stage else ''}]"
    if isinstance(val, Path):
        parts = []
        nodes = val.nodes
        rels = val.relationships
        for i, n in enumerate(nodes):
            parts.append(_pick_node_label(n))
            if i < len(rels):
                r = rels[i]
                stage = r.get("消息流类型")
                r_lbl = f"{r.type}:{stage}" if stage else r.type
                parts.append(f"-[{r_lbl}]->")
        return " ".join(parts)
    if isinstance(val, list):
        return [_format_cell_value(x) for x in val[:20]]
    if isinstance(val, dict):
        return {k: _format_cell_value(v) for k, v in list(val.items())[:15]}
    return val


class Neo4jClient:
    def __init__(self, uri: str | None = None, user: str | None = None, password: str | None = None):
        self.uri = uri or settings.neo4j_uri
        self.user = user or settings.neo4j_user
        self.password = password or settings.neo4j_password
        self._driver: Driver | None = None

    @property
    def driver(self) -> Driver:
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password),
                max_connection_lifetime=1800,
                connection_timeout=10,
            )
        return self._driver

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def ping(self) -> bool:
        try:
            with self.driver.session() as session:
                res = session.execute_read(lambda tx: tx.run("RETURN 1 AS ok").single())
                return bool(res and res["ok"] == 1)
        except Exception:
            return False

    def explain(self, cypher: str, timeout_s: float | None = None) -> tuple[bool, str | None]:
        t = timeout_s or settings.query_timeout_seconds

        @unit_of_work(timeout=t)
        def _tx(tx):
            tx.run(f"EXPLAIN {cypher}").consume()

        try:
            with self.driver.session() as session:
                session.execute_read(_tx)
            return True, None
        except Exception as exc:
            return False, str(exc)

    def run_raw_read(self, cypher: str, params: dict[str, Any] | None = None, timeout_s: float | None = None) -> list[dict[str, Any]]:
        t = timeout_s or settings.query_timeout_seconds

        @unit_of_work(timeout=t)
        def _tx(tx):
            return tx.run(cypher, params or {}).data()

        with self.driver.session() as session:
            return session.execute_read(_tx)

    def execute_query(
        self,
        cypher: str,
        timeout_s: float | None = None,
        max_rows: int | None = None,
    ) -> dict[str, Any]:
        """Run a read-only Cypher query and extract tabular rows + graph topology."""
        t = timeout_s or settings.query_timeout_seconds
        limit = max_rows or settings.max_result_rows
        start = time.perf_counter()

        @unit_of_work(timeout=t)
        def _tx_run(tx):
            result = tx.run(cypher)
            keys = list(result.keys())
            records = []
            for idx, rec in enumerate(result):
                if idx >= limit:
                    break
                records.append(rec)
            return keys, records

        with self.driver.session() as session:
            keys, records = session.execute_read(_tx_run)

        elapsed_ms = round((time.perf_counter() - start) * 1000, 1)

        nodes_map: dict[str, TopologyNode] = {}
        edges_map: dict[str, TopologyEdge] = {}

        def _register_node(n: Node) -> str:
            nid = str(n.element_id)
            if nid not in nodes_map:
                labels = list(n.labels)
                cat = labels[0] if labels else "未知"
                nodes_map[nid] = TopologyNode(
                    id=nid,
                    label=_pick_node_label(n),
                    category=cat,
                    properties=_clean_props(dict(n), DISPLAY_NODE_PROPS),
                )
            return nid

        def _register_rel(r: Relationship) -> None:
            if r.start_node is None or r.end_node is None:
                return
            src_id = _register_node(r.start_node)
            dst_id = _register_node(r.end_node)
            eid = str(r.element_id)
            if eid not in edges_map:
                rprops = _clean_props(dict(r), DISPLAY_REL_PROPS)
                stage = rprops.get("消息流类型")
                rk = rprops.get("路由键")
                edge_lbl = f"{r.type}:{stage}" if stage else r.type
                if rk:
                    edge_lbl = f"{edge_lbl} ({rk})"
                src_cat = nodes_map[src_id].category
                dst_cat = nodes_map[dst_id].category
                edges_map[eid] = TopologyEdge(
                    id=eid,
                    source=src_id,
                    target=dst_id,
                    type=r.type,
                    label=edge_lbl,
                    mechanism=_detect_mechanism(r.type, rprops, src_cat, dst_cat),
                    properties=rprops,
                )

        def _walk_graph_objects(val: Any) -> None:
            if isinstance(val, Node):
                _register_node(val)
            elif isinstance(val, Relationship):
                _register_rel(val)
            elif isinstance(val, Path):
                for n in val.nodes:
                    _register_node(n)
                for r in val.relationships:
                    _register_rel(r)
            elif isinstance(val, list):
                for item in val:
                    _walk_graph_objects(item)
            elif isinstance(val, dict):
                for item in val.values():
                    _walk_graph_objects(item)

        # Determine which columns are purely graph objects vs readable tabular columns
        graph_only_cols: set[str] = set()
        if records:
            for k in keys:
                if all(isinstance(rec[k], (Node, Relationship, Path)) or rec[k] is None for rec in records):
                    # Keep column in table only if all columns are graph objects
                    graph_only_cols.add(k)
        display_keys = [k for k in keys if k not in graph_only_cols] or keys

        rows: list[dict[str, Any]] = []
        for rec in records:
            for k in keys:
                _walk_graph_objects(rec[k])
            row = {k: _format_cell_value(rec[k]) for k in display_keys}
            rows.append(row)

        # Fallback: if query returned pure tabular dependency rows (e.g., UNION ALL RPC+MQ),
        # synthesize clean service-level topology nodes & edges so visualization still works!
        if not nodes_map and rows:
            self._synthesize_topology_from_rows(rows, nodes_map, edges_map)

        return {
            "columns": display_keys,
            "rows": rows,
            "row_count": len(rows),
            "topology": TopologyData(
                nodes=list(nodes_map.values()),
                edges=list(edges_map.values()),
            ),
            "duration_ms": elapsed_ms,
        }

    @staticmethod
    def _synthesize_topology_from_rows(
        rows: list[dict[str, Any]],
        nodes_map: dict[str, TopologyNode],
        edges_map: dict[str, TopologyEdge],
    ) -> None:
        src_keys = ("源服务", "调用方服务", "发布服务", "上游服务", "上游调用服务", "受影响上游服务", "微服务")
        dst_keys = ("目标服务", "目标微服务", "消费服务", "下游服务")
        kind_keys = ("依赖类型", "通信机制")
        chan_keys = ("通道或接口", "接口或队列", "下游API", "调用接口", "队列名称", "队列")

        for idx, r in enumerate(rows):
            src = next((str(r[k]) for k in src_keys if k in r and r[k]), None)
            dst = next((str(r[k]) for k in dst_keys if k in r and r[k]), None)
            if not src or not dst:
                continue
            kind = next((str(r[k]) for k in kind_keys if k in r and r[k]), "RPC")
            chan = next((str(r[k]) for k in chan_keys if k in r and r[k]), "")
            src_id = f"svc:{src}"
            dst_id = f"svc:{dst}"
            if src_id not in nodes_map:
                nodes_map[src_id] = TopologyNode(id=src_id, label=src, category="微服务", properties={"服务名称": src})
            if dst_id not in nodes_map:
                nodes_map[dst_id] = TopologyNode(id=dst_id, label=dst, category="微服务", properties={"服务名称": dst})
            mech = "MQ" if "MQ" in kind.upper() else "RPC"
            edge_id = f"syn:{src_id}->{dst_id}:{mech}:{chan or idx}"
            if edge_id not in edges_map:
                edges_map[edge_id] = TopologyEdge(
                    id=edge_id,
                    source=src_id,
                    target=dst_id,
                    type="消息流" if mech == "MQ" else "调用",
                    label=f"{kind}: {chan}" if chan else kind,
                    mechanism=mech,
                    properties={"依赖类型": kind, "通道": chan},
                )


neo4j_client = Neo4jClient()
