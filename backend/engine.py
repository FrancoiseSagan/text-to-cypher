"""Closed-loop Text2Cypher Query Engine:
1. Enhanced Schema + Value-Aware Entity Grounding
2. Adaptive Difficulty Router + Modular Skills + Dynamic KB Few-Shot RAG
3. CodexGraph-style Complex Query Planner & Multi-Subgraph Merger
4. Three-Layer Guardrail + Execution-Guided Self-Correction Loop
5. Fact-Grounded Natural Language Summarizer + Markdown Report Exporter
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Callable

from .config import AllowedProvider, settings
from .guardrail import CypherGuardrail, guardrail
from .kb_store import KBStore, kb_store
from .llm_client import LLMClient, extract_cypher, extract_json_block, llm_client
from .models import (
    GroundedEntity,
    QueryRequest,
    QueryResponse,
    SubQueryExecution,
    TopologyData,
    TopologyEdge,
    TopologyNode,
    TraceStep,
    ValidationReport,
)
from .neo4j_client import Neo4jClient, neo4j_client
from .schema_service import SchemaService, schema_service
from .skill_loader import SkillLoader, skill_loader


INTENT_CATEGORIES = [
    "单节点查询",
    "属性过滤",
    "入口 API 发现",
    "下游服务发现",
    "反向影响分析",
    "MQ 发布者与完整链路",
    "REST 与 MQ 综合依赖",
]


def _format_grounded_entities(entities: list[GroundedEntity]) -> str:
    if not entities:
        return "（未探测到特定代码实体，可按通用 Schema 编写查询）"
    lines = ["以下实体已在目标 Neo4j 图谱中实库验证存在，请优先精确使用其标签与属性值："]
    for e in entities:
        extra_str = f" | 补充: {json.dumps(e.extra, ensure_ascii=False)}" if e.extra else ""
        lines.append(f"- 问题词「{e.mention}」→ `(:{e.label} {{{e.property_key}: '{e.matched_name}'}})`{extra_str}")
    return "\n".join(lines)


def _format_examples(examples: list[dict[str, Any]]) -> str:
    if not examples:
        return ""
    blocks = ["## 相似已验证 NL-Cypher 参考示例（来自知识库）"]
    for idx, ex in enumerate(examples, 1):
        blocks.append(
            f"### 示例 {idx} [{ex['category']} / {ex['complexity']}]\n"
            f"问题: {ex['question']}\n"
            f"```cypher\n{ex['cypher']}\n```"
        )
    return "\n\n".join(blocks)


def _merge_topologies(topos: list[TopologyData]) -> TopologyData:
    nodes: dict[str, TopologyNode] = {}
    edges: dict[str, TopologyEdge] = {}
    for t in topos:
        for n in t.nodes:
            if n.id not in nodes:
                nodes[n.id] = n
        for e in t.edges:
            if e.id not in edges:
                edges[e.id] = e
    return TopologyData(nodes=list(nodes.values()), edges=list(edges.values()))


class Text2CypherEngine:
    def __init__(
        self,
        neo4j: Neo4jClient = neo4j_client,
        schema_svc: SchemaService = schema_service,
        kb: KBStore = kb_store,
        skills: SkillLoader = skill_loader,
        llm: LLMClient = llm_client,
        validator: CypherGuardrail = guardrail,
    ):
        self.neo4j = neo4j
        self.schema_svc = schema_svc
        self.kb = kb
        self.skills = skills
        self.llm = llm
        self.validator = validator

    def run_query(
        self,
        req: QueryRequest,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> QueryResponse:
        t0 = time.perf_counter()
        query_id = f"q-{uuid.uuid4().hex[:10]}"
        created_at = time.strftime("%Y-%m-%d %H:%M:%S")
        trace: list[TraceStep] = []

        def _emit(event_type: str, **payload: Any) -> None:
            if progress_callback:
                progress_callback(
                    {
                        "event": event_type,
                        "elapsed_s": round(time.perf_counter() - t0, 2),
                        **payload,
                    }
                )

        provider: AllowedProvider = req.provider or settings.get_default_provider()
        resolved_provider: str = provider
        resolved_model: str = req.model or ""
        reasoning_effort: str = req.reasoning_effort or "low"
        max_retries = req.max_retries if req.max_retries is not None else settings.max_self_correction_retries

        sub_executions: list[SubQueryExecution] = []
        sub_topologies: list[TopologyData] = []
        final_cypher = ""
        final_validation: ValidationReport | None = None
        final_columns: list[str] = []
        final_rows: list[dict[str, Any]] = []
        top_error: str | None = None
        intent_category = "单节点查询"
        resolved_difficulty = req.difficulty if req.difficulty != "自动" else "简单"
        examples: list[dict[str, Any]] = []
        loaded_skill_names: list[str] = []
        grounded_entities: list[GroundedEntity] = []

        try:
            # --- Stage 1: Unified LLM Semantic Analysis, Difficulty Assessment, Skill Selection & Entity Extraction ---
            _emit("stage_start", stage_key="plan", stage="语义评估与查询规划", message="正在通过大模型语义评估难度、意图、实体候选、所需技能与拆解方案...")
            st_plan = time.perf_counter()
            compact_overview = self.schema_svc.format_compact_overview_for_planner()
            plan_info, resolved_provider, resolved_model = self._semantic_analyze_and_plan(
                question=req.question,
                requested_difficulty=req.difficulty,
                compact_overview=compact_overview,
                provider=provider,
                model=req.model,
                api_key=req.api_key,
                reasoning_effort=reasoning_effort,
            )
            intent_category = plan_info["intent_category"]
            assessed_difficulty = plan_info["difficulty"]
            difficulty_reason = plan_info["difficulty_reason"]
            resolved_difficulty = assessed_difficulty if req.difficulty == "自动" else req.difficulty
            selected_skills = self.skills.select_by_names(plan_info["selected_skills"])
            loaded_skill_names = [f"{s.name}@v{s.version}" for s in selected_skills]
            plan_tasks = plan_info["sub_queries"]

            dur_plan_ms = round((time.perf_counter() - st_plan) * 1000, 1)
            plan_sum = (
                f"语义判定「{intent_category}」/ 难度「{resolved_difficulty}」（{difficulty_reason}）；"
                f"抽取 {len(plan_info['entity_mentions'])} 个实体候选，加载 {len(loaded_skill_names)} 个 Skill"
                + (f"，拆分为 {len(plan_tasks)} 个子查询" if len(plan_tasks) > 1 else "，单查询执行")
            )
            trace.append(
                TraceStep(
                    stage="语义评估与查询规划",
                    status="ok",
                    duration_ms=dur_plan_ms,
                    summary=plan_sum,
                    detail={
                        "intent_category": intent_category,
                        "assessed_difficulty": assessed_difficulty,
                        "resolved_difficulty": resolved_difficulty,
                        "difficulty_reason": difficulty_reason,
                        "need_config_schema": plan_info["need_config_schema"],
                        "need_source_meta": plan_info["need_source_meta"],
                        "entity_mentions": plan_info["entity_mentions"],
                        "skills": loaded_skill_names,
                        "decompose": len(plan_tasks) > 1,
                        "sub_queries": plan_tasks,
                    },
                )
            )
            _emit(
                "stage_done",
                stage_key="plan",
                stage="语义评估与查询规划",
                status="ok",
                duration_s=round(dur_plan_ms / 1000, 2),
                summary=plan_sum,
            )

            # --- Stage 2: Semantic-Driven Schema Assembly, Live Entity Grounding & KB Retrieval ---
            _emit("stage_start", stage_key="schema", stage="Schema装配与实库对齐", message="正在按语义结果装配 Enhanced Schema、实库验证实体候选并召回知识库示例...")
            st_ground = time.perf_counter()
            enhanced_schema = self.schema_svc.format_enhanced_schema_for_prompt(
                include_config_details=plan_info["need_config_schema"],
                include_version_details=plan_info["need_source_meta"],
            )
            grounded_entities = self.schema_svc.ground_entities_from_candidates(plan_info["entity_mentions"])
            examples = self.kb.retrieve_similar(req.question, top_k=4, intent_category=intent_category)
            dur_ground_ms = round((time.perf_counter() - st_ground) * 1000, 1)
            sum_ground = f"装配实时 Schema（配置详情={plan_info['need_config_schema']}），实库对齐 {len(grounded_entities)} 个实体，召回 {len(examples)} 条示例"
            trace.append(
                TraceStep(
                    stage="Schema装配与实库对齐",
                    status="ok",
                    duration_ms=dur_ground_ms,
                    summary=sum_ground,
                    detail={
                        "grounded_count": len(grounded_entities),
                        "entities": [e.model_dump() for e in grounded_entities[:10]],
                        "examples": [{"id": e["id"], "question": e["question"], "score": e["score"]} for e in examples],
                    },
                )
            )
            _emit(
                "stage_done",
                stage_key="schema",
                stage="Schema装配与实库对齐",
                status="ok",
                duration_s=round(dur_ground_ms / 1000, 2),
                summary=sum_ground,
            )

            _emit("stage_start", stage_key="execute", stage="Cypher 生成·校验·执行闭环", message="正在生成 Cypher 并执行三层安全校验与只读查询...")
            st_exec_stage = time.perf_counter()

            if len(plan_tasks) > 1:
                # Complex decomposed multi-subquery path (CodexGraph / T3)
                for idx, task in enumerate(plan_tasks, 1):
                    sub_id = f"sub-{idx}"
                    sub_q = task["sub_question"]
                    sub_title = task.get("title", f"子查询 {idx}")
                    mech = task.get("mechanism", "GENERAL")
                    sub_examples = self.kb.retrieve_similar(sub_q, top_k=3, intent_category=intent_category)
                    sub_skills = self.skills.select_by_names(plan_info["selected_skills"])

                    exec_res, topo, resolved_provider, resolved_model = self._run_single_closed_loop(
                        question=sub_q,
                        title=sub_title,
                        sub_id=sub_id,
                        mechanism=mech,
                        enhanced_schema=enhanced_schema,
                        grounded_entities=grounded_entities,
                        examples=sub_examples,
                        skills_text=self.skills.format_for_prompt(sub_skills),
                        provider=provider,
                        model=req.model,
                        api_key=req.api_key,
                        reasoning_effort=reasoning_effort,
                        max_retries=max_retries,
                        allow_empty_as_valid=True,
                        trace=trace,
                        emit=_emit,
                    )
                    sub_executions.append(exec_res)
                    sub_topologies.append(topo)

                _emit(
                    "stage_done",
                    stage_key="execute",
                    stage="Cypher 生成·校验·执行闭环",
                    status="ok",
                    duration_s=round(time.perf_counter() - st_exec_stage, 2),
                    summary=f"完成 {len(sub_executions)} 个子查询闭环执行",
                )

                # Merge sub-query results & topologies
                _emit("stage_start", stage_key="merge", stage="多子图归并去重", message="正在按节点 ID 合并多子图并去重...")
                st_merge = time.perf_counter()
                merged_topology = _merge_topologies(sub_topologies)
                combined_cypher_parts = [
                    f"// [{sq.title} | {sq.mechanism}]\n{sq.cypher}" for sq in sub_executions if sq.cypher
                ]
                final_cypher = "\n\n".join(combined_cypher_parts)
                final_columns, final_rows = self._merge_subquery_rows(sub_executions)

                all_checks = []
                all_errs = []
                all_warns = []
                for sq in sub_executions:
                    if sq.validation:
                        for c in sq.validation.checks:
                            all_checks.append({**c, "name": f"[{sq.title}] {c['name']}"})
                        all_errs.extend(sq.validation.errors)
                        all_warns.extend(sq.validation.warnings)
                final_validation = ValidationReport(
                    valid=any(sq.error is None for sq in sub_executions),
                    checks=all_checks,
                    errors=all_errs,
                    warnings=all_warns,
                )
                dur_merge = round((time.perf_counter() - st_merge) * 1000, 1)
                sum_merge = f"合并 {len(sub_executions)} 个子查询，共 {len(final_rows)} 行、{len(merged_topology.nodes)} 节点、{len(merged_topology.edges)} 关系"
                trace.append(
                    TraceStep(
                        stage="多子图归并去重",
                        status="ok",
                        duration_ms=dur_merge,
                        summary=sum_merge,
                        detail={
                            "sub_query_counts": {sq.title: sq.row_count for sq in sub_executions},
                            "merged_nodes": len(merged_topology.nodes),
                            "merged_edges": len(merged_topology.edges),
                        },
                    )
                )
                _emit("stage_done", stage_key="merge", stage="多子图归并去重", status="ok", duration_s=round(dur_merge / 1000, 2), summary=sum_merge)
            else:
                # Standard single closed-loop path
                exec_res, merged_topology, resolved_provider, resolved_model = self._run_single_closed_loop(
                    question=req.question,
                    title="主查询",
                    sub_id="main",
                    mechanism="GENERAL",
                    enhanced_schema=enhanced_schema,
                    grounded_entities=grounded_entities,
                    examples=examples,
                    skills_text=self.skills.format_for_prompt(selected_skills),
                    provider=provider,
                    model=req.model,
                    api_key=req.api_key,
                    reasoning_effort=reasoning_effort,
                    max_retries=max_retries,
                    allow_empty_as_valid=False,
                    trace=trace,
                    emit=_emit,
                )
                sub_executions.append(exec_res)
                final_cypher = exec_res.cypher
                final_validation = exec_res.validation
                final_columns = exec_res.columns
                final_rows = exec_res.rows
                top_error = exec_res.error
                _emit(
                    "stage_done",
                    stage_key="execute",
                    stage="Cypher 生成·校验·执行闭环",
                    status="ok" if exec_res.error is None else "error",
                    duration_s=round(time.perf_counter() - st_exec_stage, 2),
                    summary=f"命中 {exec_res.row_count} 行、{len(merged_topology.nodes)} 节点、{len(merged_topology.edges)} 关系"
                    if exec_res.error is None
                    else str(exec_res.error)[:120],
                )
                _emit("stage_done", stage_key="merge", stage="多子图归并去重", status="skipped", duration_s=0.0, summary="单查询模式，无需子图合并")

            # Determine overall status
            succeeded_subs = [sq for sq in sub_executions if sq.error is None]
            if len(succeeded_subs) == len(sub_executions) and len(sub_executions) > 0:
                status = "success"
            elif len(succeeded_subs) > 0:
                status = "partial"
                top_error = "; ".join(sq.error for sq in sub_executions if sq.error)
            else:
                status = "error"
                top_error = top_error or "; ".join(sq.error for sq in sub_executions if sq.error)

            # --- Stage 4: Fact-Grounded Natural Language Summarizer ---
            _emit("stage_start", stage_key="summary", stage="结果语义总结", message="正在基于实库命中结果生成自然语言分析结论...")
            st_sum = time.perf_counter()
            summary = self._generate_summary(
                question=req.question,
                cypher=final_cypher,
                rows=final_rows,
                topology=merged_topology,
                sub_executions=sub_executions,
                error=top_error,
                provider=provider,
                model=req.model,
                api_key=req.api_key,
                reasoning_effort=reasoning_effort,
            )
            dur_sum = round((time.perf_counter() - st_sum) * 1000, 1)
            trace.append(
                TraceStep(
                    stage="结果语义总结",
                    status="ok" if status != "error" else "warn",
                    duration_ms=dur_sum,
                    summary="已基于实库执行结果生成自然语言总结",
                )
            )
            _emit(
                "stage_done",
                stage_key="summary",
                stage="结果语义总结",
                status="ok" if status != "error" else "warn",
                duration_s=round(dur_sum / 1000, 2),
                summary="自然语言总结生成完成",
            )

        except Exception as exc:
            status = "error"
            top_error = str(exc)
            merged_topology = TopologyData()
            summary = f"查询执行失败：{top_error}"
            trace.append(
                TraceStep(
                    stage="引擎异常",
                    status="error",
                    duration_ms=0.0,
                    summary=top_error[:240],
                )
            )

        total_ms = round((time.perf_counter() - t0) * 1000, 1)
        response = QueryResponse(
            query_id=query_id,
            question=req.question,
            requested_difficulty=req.difficulty,
            resolved_difficulty=resolved_difficulty,
            intent_category=intent_category,
            provider=resolved_provider,
            model=resolved_model,
            status=status,
            cypher=final_cypher,
            sub_queries=sub_executions,
            columns=final_columns,
            rows=final_rows,
            row_count=len(final_rows),
            topology=merged_topology,
            summary=summary,
            grounded_entities=grounded_entities,
            retrieved_examples=examples,
            loaded_skills=loaded_skill_names,
            validation=final_validation,
            trace=trace,
            total_duration_ms=total_ms,
            created_at=created_at,
            error=top_error,
        )
        self.kb.save_history(response.model_dump())
        return response

    def _semantic_analyze_and_plan(
        self,
        question: str,
        requested_difficulty: str,
        compact_overview: str,
        provider: AllowedProvider,
        model: str | None,
        api_key: str | None,
        reasoning_effort: str | None = None,
    ) -> tuple[dict[str, Any], str, str]:
        """Unified LLM Semantic Analyzer, Schema Filter & Entity Extractor:
        - Evaluates difficulty & intent from graph-structural semantics
        - Decides on-demand schema expansion flags (config / source metadata)
        - Extracts semantic entity mentions & target labels/search terms for live Neo4j grounding
        - Selects needed Skills and decides complex query decomposition
        """
        skill_catalog = self.skills.format_catalog_for_router()
        prompt = f"""你是微服务代码图谱的查询语义分析、实体抽取与任务规划专家。请基于下方图谱骨架与用户问题，完成 6 项语义判断并输出严格 JSON：

1. **intent_category**（从以下 7 类中选择最贴合的一项）：
   {json.dumps(INTENT_CATEGORIES, ensure_ascii=False)}

2. **difficulty**（根据真实图遍历复杂度判定）：
   - `简单`：单点检索、属性过滤、单跳关系或基础计数。
   - `中等`：单通信机制内的多跳调用链、反向调用方查询、去重聚合统计或排名。
   - `复杂`：跨服务多跳变更影响分析、MQ 发布→路由→消费完整三阶段链路、或同步 RPC + 异步 MQ 多子图联合依赖分析。

3. **need_config_schema / need_source_meta**（按需 Schema 展开标志，布尔值）：
   - `need_config_schema`：仅当问题涉及配置文件、端口、环境变量、Spring Bean 等配置节点时为 `true`。
   - `need_source_meta`：仅当问题涉及源码文件路径、行号、图谱版本或分支时为 `true`。

4. **entity_mentions**（语义实体抽取 + 拼写纠错，供后续去 Neo4j 实库探针核实）：
   - 提取问题中涉及的具体微服务、方法、类、API 路径、消息队列或配置项。
   - **容错要求**：用户可能存在中英文打错字、漏字母或倒置（如 `getAllFod`、`ts-presrve-service`、`emial`、`退漂服务`、`站电服务`），请在 `search_terms` 中同时给出纠错后的最可能候选词与原词，以便实库模糊匹配。
   - 每项格式：`{{"mention": "原问题词", "target_label": "微服务|方法|类|上游API|下游API|消息队列|配置", "search_terms": ["纠错后的精确名或关键词", "原词"]}}`；若无特定实体返回 `[]`。

5. **selected_skills**（从下方领域技能目录中按需挑选，简单查询可返回 `[]`）：
{skill_catalog}

6. **decompose & sub_queries**（复杂查询规划）：
   - 仅当问题**同时涉及异构通信机制**（如同步 RPC + 异步 MQ 联合依赖）或**需要双向独立追溯**（上游影响 + 下游依赖）时，设 `decompose=true` 并拆为 2~3 个清晰子查询；否则 `decompose=false`。

仅输出严格合法 JSON：
```json
{{
  "intent_category": "下游服务发现",
  "difficulty": "中等",
  "difficulty_reason": "一句话说明图结构复杂度依据",
  "need_config_schema": false,
  "need_source_meta": false,
  "entity_mentions": [
    {{"mention": "getAllFood", "target_label": "方法", "search_terms": ["getAllFood"]}}
  ],
  "selected_skills": ["downstream-discovery"],
  "decompose": false,
  "sub_queries": []
}}
```
若 `decompose=true`，`sub_queries` 每项格式为：
`{{"title": "子查询标题", "mechanism": "RPC|MQ|UPSTREAM|DOWNSTREAM", "sub_question": "拆解后的明确子问题"}}`

## 图谱骨架与全局枚举
{compact_overview}

## 用户问题（界面档位偏好：{requested_difficulty}）
{question}
"""
        content, resolved_provider, resolved_model = self.llm.chat(
            messages=[
                {"role": "system", "content": "你是严谨的代码图谱查询语义分析与任务规划器，只输出严格合法的 JSON。"},
                {"role": "user", "content": prompt},
            ],
            provider=provider,
            model=model,
            api_key=api_key,
            reasoning_effort=reasoning_effort,
            temperature=0.0,
            max_tokens=1000,
        )
        parsed = extract_json_block(content)
        if not isinstance(parsed, dict):
            parsed = {}

        intent = str(parsed.get("intent_category", "单节点查询"))
        if intent not in INTENT_CATEGORIES:
            intent = "单节点查询"

        diff = str(parsed.get("difficulty", "中等"))
        if diff not in ("简单", "中等", "复杂"):
            diff = "中等"

        reason = str(parsed.get("difficulty_reason", "基于图谱路径跳数与关系复杂度综合判定")).strip()
        need_config_schema = bool(parsed.get("need_config_schema", False))
        need_source_meta = bool(parsed.get("need_source_meta", False))
        raw_entities = parsed.get("entity_mentions", [])
        entity_mentions = [e for e in raw_entities if isinstance(e, dict)] if isinstance(raw_entities, list) else []

        raw_skills = parsed.get("selected_skills", [])
        chosen_skills = [str(s) for s in raw_skills] if isinstance(raw_skills, list) else []

        sub_queries: list[dict[str, str]] = []
        allow_decompose = (diff == "复杂" and requested_difficulty == "自动") or (requested_difficulty == "复杂")
        if allow_decompose and parsed.get("decompose") and isinstance(parsed.get("sub_queries"), list):
            subs = [
                {
                    "title": str(sq.get("title", f"子查询{i}")),
                    "mechanism": str(sq.get("mechanism", "GENERAL")),
                    "sub_question": str(sq.get("sub_question", "")).strip(),
                }
                for i, sq in enumerate(parsed["sub_queries"][:3], 1)
                if isinstance(sq, dict) and sq.get("sub_question")
            ]
            if len(subs) >= 2:
                sub_queries = subs

        if not sub_queries:
            sub_queries = [{"title": "主查询", "mechanism": "GENERAL", "sub_question": question}]

        return (
            {
                "intent_category": intent,
                "difficulty": diff,
                "difficulty_reason": reason,
                "need_config_schema": need_config_schema,
                "need_source_meta": need_source_meta,
                "entity_mentions": entity_mentions,
                "selected_skills": chosen_skills,
                "sub_queries": sub_queries,
            },
            resolved_provider,
            resolved_model,
        )

    def _run_single_closed_loop(
        self,
        question: str,
        title: str,
        sub_id: str,
        mechanism: str,
        enhanced_schema: str,
        grounded_entities: list[GroundedEntity],
        examples: list[dict[str, Any]],
        skills_text: str,
        provider: AllowedProvider,
        model: str | None,
        api_key: str | None,
        reasoning_effort: str | None,
        max_retries: int,
        allow_empty_as_valid: bool,
        trace: list[TraceStep],
        emit: Callable[..., None] | None = None,
    ) -> tuple[SubQueryExecution, TopologyData, str, str]:
        """Generate -> 3-Layer Guardrail -> Read-Only Neo4j Execution -> Execution-Guided Self-Correction."""
        loop_start = time.perf_counter()
        system_prompt = """你是面向微服务代码图谱的 Neo4j Text2Cypher 专家。
请严格遵守以下规则：
1. 只能使用下方真实 Schema 中存在的中文节点标签、关系类型和属性名，严禁凭空捏造。
2. 只允许生成只读 Cypher（MATCH/OPTIONAL MATCH/WITH/WHERE/RETURN/ORDER BY/LIMIT/UNION ALL），严禁任何写操作。
3. 重要图谱结构约束：
   - `(:类)` 和 `(:方法)` 没有直连 `(:微服务)` 的 `[:归属于]` 边！请用 `m.moduleId = '服务名'` 或 `'服务名' IN m.serviceContexts` 过滤所属微服务。
   - `(:上游API)-[:归属于]->(:方法)` 表示入口 API 属于控制器方法；跨服务调用为 `(:方法)-[:调用]->(:下游API)-[:目标服务]->(:微服务)` 及 `(:下游API)-[:调用]->(:上游API)`。
   - MQ 三阶段消息流必须使用 `r1.路由键 = r2.路由键` 约束对齐交换机前后的路由键。
   - 多跳查询必须限制最大深度（如 `[:调用*1..4]`），并加 `DISTINCT` 防止环路重复。
4. 为了支持前端渲染拓扑图，**请尽量在 RETURN 中同时返回可读的中文别名列以及路径/节点/关系变量（如 `p` 或 `m, r, c`）**；若使用 `UNION ALL` 需保证各分支列名完全一致。
5. 只输出一个 ```cypher ... ``` 代码块，不要输出额外解释文字。"""

        user_prompt = "\n\n".join(
            part
            for part in [
                enhanced_schema,
                skills_text,
                "## 实库实体对齐结果\n" + _format_grounded_entities(grounded_entities),
                _format_examples(examples),
                f"## 当前需要转换的问题\n{question}",
            ]
            if part
        )

        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        last_cypher = ""
        last_validation: ValidationReport | None = None
        last_error: str | None = None
        resolved_provider: str = provider
        resolved_model: str = model or ""
        total_attempts = max(1, max_retries + 1)

        for attempt in range(1, total_attempts + 1):
            # 1. LLM Generate
            if emit:
                emit("substep", stage_key="execute", message=f"[{title}] 正在调用大模型生成 Cypher（第 {attempt} 次）...")
            st_gen = time.perf_counter()
            raw_reply, resolved_provider, resolved_model = self.llm.chat(
                messages=messages,
                provider=provider,
                model=model,
                api_key=api_key,
                reasoning_effort=reasoning_effort,
                temperature=0.0,
                max_tokens=1200,
            )
            cypher = extract_cypher(raw_reply)
            last_cypher = cypher
            trace.append(
                TraceStep(
                    stage=f"[{title}] Cypher 生成 (第{attempt}次)",
                    status="ok" if attempt == 1 else "retry",
                    duration_ms=round((time.perf_counter() - st_gen) * 1000, 1),
                    summary=f"模型 {resolved_model} 生成 {len(cypher)} 字符 Cypher",
                    detail={"cypher": cypher},
                )
            )

            # 2. Three-layer Guardrail Validation
            if emit:
                emit("substep", stage_key="execute", message=f"[{title}] 正在进行三层安全、Schema 与 EXPLAIN 校验（第 {attempt} 次）...")
            st_val = time.perf_counter()
            val_report = self.validator.validate(cypher, run_explain=True)
            last_validation = val_report
            trace.append(
                TraceStep(
                    stage=f"[{title}] Cypher 校验 (第{attempt}次)",
                    status="ok" if val_report.valid else "warn",
                    duration_ms=round((time.perf_counter() - st_val) * 1000, 1),
                    summary="全部 5 项校验通过" if val_report.valid else f"校验拦截: {'; '.join(val_report.errors)}",
                    detail=val_report.model_dump(),
                )
            )

            if not val_report.valid:
                last_error = "; ".join(val_report.errors)
                if attempt < total_attempts:
                    if emit:
                        emit("substep", stage_key="execute", message=f"[{title}] 校验拦截，触发反馈自修正（准备第 {attempt + 1} 次）...")
                    messages.append({"role": "assistant", "content": f"```cypher\n{cypher}\n```"})
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                f"上一条 Cypher 校验未通过，具体错误：\n{last_error}\n\n"
                                "请严格按照真实 Schema 修正并仅输出新的 ```cypher ... ``` 代码块。"
                            ),
                        }
                    )
                    continue
                break

            # 3. Controlled Read-Only Neo4j Execution
            if emit:
                emit("substep", stage_key="execute", message=f"[{title}] 正在 Neo4j 只读执行 Cypher（第 {attempt} 次）...")
            st_exec = time.perf_counter()
            try:
                exec_data = self.neo4j.execute_query(cypher)
                row_count = exec_data["row_count"]
                topo: TopologyData = exec_data["topology"]
                trace.append(
                    TraceStep(
                        stage=f"[{title}] Neo4j 受控执行 (第{attempt}次)",
                        status="ok" if row_count > 0 else "warn",
                        duration_ms=exec_data["duration_ms"],
                        summary=f"返回 {row_count} 行数据，提取 {len(topo.nodes)} 个节点、{len(topo.edges)} 条边",
                        detail={"row_count": row_count, "columns": exec_data["columns"]},
                    )
                )

                # Execution-Guided Empty Result Reflection (retry once if suspicious empty result on attempt 1)
                if row_count == 0 and attempt < total_attempts and not allow_empty_as_valid:
                    if emit:
                        emit("substep", stage_key="execute", message=f"[{title}] 命中 0 行结果，正在反思路径方向与属性匹配（重试第 {attempt + 1} 次）...")
                    messages.append({"role": "assistant", "content": f"```cypher\n{cypher}\n```"})
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "上一条 Cypher 语法正确但在目标图谱中返回了 0 行结果。请自检是否存在以下常见问题：\n"
                                "1. 是否错误使用了 `(:类)-[:归属于]->(:微服务)` 或 `(:方法)-[:归属于]->(:微服务)`（实际不存在此边，需改用 `moduleId` 或 `serviceContexts`）？\n"
                                "2. 关系方向是否写反（例如 `(:上游API)-[:归属于]->(:方法)`、`(:下游API)-[:目标服务]->(:微服务)`）？\n"
                                "3. 属性精确匹配过严（可改用 `CONTAINS` 或核对实库实体对齐列表中的精确名称）？\n"
                                "请修正后仅输出一条新的 ```cypher ... ```。"
                            ),
                        }
                    )
                    continue

                return (
                    SubQueryExecution(
                        sub_id=sub_id,
                        title=title,
                        mechanism=mechanism,
                        cypher=cypher,
                        attempts=attempt,
                        validation=val_report,
                        row_count=row_count,
                        columns=exec_data["columns"],
                        rows=exec_data["rows"],
                        error=None,
                        duration_ms=round((time.perf_counter() - loop_start) * 1000, 1),
                    ),
                    topo,
                    resolved_provider,
                    resolved_model,
                )

            except Exception as exc:
                last_error = f"Neo4j 执行异常: {exc}"
                trace.append(
                    TraceStep(
                        stage=f"[{title}] Neo4j 受控执行 (第{attempt}次)",
                        status="error",
                        duration_ms=round((time.perf_counter() - st_exec) * 1000, 1),
                        summary=last_error[:240],
                    )
                )
                if attempt < total_attempts:
                    messages.append({"role": "assistant", "content": f"```cypher\n{cypher}\n```"})
                    messages.append(
                        {
                            "role": "user",
                            "content": f"执行报错：{last_error}\n请优化或修正 Cypher（避免超时或非法操作），仅输出 ```cypher ... ```。",
                        }
                    )

        return (
            SubQueryExecution(
                sub_id=sub_id,
                title=title,
                mechanism=mechanism,
                cypher=last_cypher,
                attempts=total_attempts,
                validation=last_validation,
                row_count=0,
                columns=[],
                rows=[],
                error=last_error or "查询执行失败",
                duration_ms=round((time.perf_counter() - loop_start) * 1000, 1),
            ),
            TopologyData(),
            resolved_provider,
            resolved_model,
        )

    @staticmethod
    def _merge_subquery_rows(sub_executions: list[SubQueryExecution]) -> tuple[list[str], list[dict[str, Any]]]:
        """Combine rows from multiple sub-queries with source tag and deduplication."""
        all_cols: list[str] = ["子查询", "通信机制"]
        for sq in sub_executions:
            for c in sq.columns:
                if c not in all_cols:
                    all_cols.append(c)

        merged: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        for sq in sub_executions:
            for r in sq.rows:
                row = {"子查询": sq.title, "通信机制": sq.mechanism, **r}
                dedup_sig = json.dumps(row, ensure_ascii=False, sort_keys=True)
                if dedup_sig not in seen_keys:
                    seen_keys.add(dedup_sig)
                    merged.append(row)
        return all_cols, merged

    def _generate_summary(
        self,
        question: str,
        cypher: str,
        rows: list[dict[str, Any]],
        topology: TopologyData,
        sub_executions: list[SubQueryExecution],
        error: str | None,
        provider: AllowedProvider,
        model: str | None,
        api_key: str | None,
        reasoning_effort: str | None = None,
    ) -> str:
        if error and not rows:
            return f"查询未能返回结果，原因：{error}"
        if not rows:
            return "查询已在 Neo4j 图谱中合法执行完成，但未命中符合条件的记录（0 条结果）。请检查目标服务/方法名或调整过滤条件。"

        preview_rows = rows[:30]
        sub_overview = [
            {"子查询": sq.title, "机制": sq.mechanism, "命中行数": sq.row_count, "状态": "成功" if not sq.error else sq.error}
            for sq in sub_executions
        ]
        prompt = f"""请基于以下 Neo4j 代码图谱的真实查询结果，用简洁、结构化的中文回答用户问题。
要求：
1. 严格忠于执行结果，不得编造结果中不存在的服务、方法、API 或消息队列。
2. 先给出核心结论（如总数、关键服务/接口/链路），再用要点列表清晰归纳；若同时包含 RPC 与 MQ，请分组说明。
3. 控制在 250 字以内，清晰专业。

用户问题：{question}
执行概况：{json.dumps(sub_overview, ensure_ascii=False)}
拓扑规模：{len(topology.nodes)} 个节点，{len(topology.edges)} 条关系
总命中行数：{len(rows)}（以下展示前 {len(preview_rows)} 行）
结果样本：
{json.dumps(preview_rows, ensure_ascii=False)}
"""
        try:
            content, _, _ = self.llm.chat(
                messages=[
                    {"role": "system", "content": "你是严谨的软件架构与代码图谱分析助手。"},
                    {"role": "user", "content": prompt},
                ],
                provider=provider,
                model=model,
                api_key=api_key,
                reasoning_effort=reasoning_effort,
                temperature=0.2,
                max_tokens=600,
            )
            return content
        except Exception:
            return f"查询成功，共命中 {len(rows)} 条记录，提取拓扑节点 {len(topology.nodes)} 个、关系 {len(topology.edges)} 条。"

    @staticmethod
    def render_markdown_report(item: dict[str, Any]) -> str:
        """Render a complete structured Markdown report for export (Req 4)."""
        lines: list[str] = [
            f"# 代码图谱查询分析报告",
            "",
            f"- **查询编号**: `{item.get('query_id', '')}`",
            f"- **查询时间**: {item.get('created_at', '')}",
            f"- **用户问题**: {item.get('question', '')}",
            f"- **意图类型 / 档位**: {item.get('intent_category', '')} / {item.get('resolved_difficulty', '')}",
            f"- **模型**: `{item.get('provider', '')}` / `{item.get('model', '')}`",
            f"- **状态 / 总耗时**: `{item.get('status', '')}` / {round(float(item.get('total_duration_ms', 0)) / 1000, 2):.2f} s",
            f"- **加载技能 (Skills)**: {', '.join(item.get('loaded_skills', [])) or '无'}",
            "",
            "## 1. 自然语言总结",
            "",
            item.get("summary", "无"),
            "",
            "## 2. 生成的 Cypher",
            "",
            "```cypher",
            item.get("cypher", ""),
            "```",
            "",
        ]

        entities = item.get("grounded_entities", [])
        if entities:
            lines.append("## 3. 实体识别与语义对齐")
            lines.append("")
            for e in entities:
                lines.append(f"- `{e.get('mention')}` → `(:{e.get('label')} {{{e.get('property_key')}: '{e.get('matched_name')}'}})`")
            lines.append("")

        topo = item.get("topology", {})
        nodes = topo.get("nodes", [])
        edges = topo.get("edges", [])
        lines.append("## 4. 查询结果与拓扑概览")
        lines.append("")
        lines.append(f"- 命中记录数: **{item.get('row_count', 0)}**")
        lines.append(f"- 拓扑节点数: **{len(nodes)}**，拓扑关系数: **{len(edges)}**")
        lines.append("")

        cols = item.get("columns", [])
        rows = item.get("rows", [])[:30]
        if cols and rows:
            lines.append("| " + " | ".join(str(c) for c in cols) + " |")
            lines.append("| " + " | ".join("---" for _ in cols) + " |")
            for r in rows:
                vals = []
                for c in cols:
                    v = r.get(c, "")
                    s = json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else str(v)
                    vals.append(s.replace("|", "\\|").replace("\n", " ")[:120])
                lines.append("| " + " | ".join(vals) + " |")
            lines.append("")

        trace = item.get("trace", [])
        if trace:
            lines.append("## 5. 执行全过程追溯 (Trace)")
            lines.append("")
            lines.append("| 阶段 | 状态 | 耗时 (s) | 说明 |")
            lines.append("| --- | --- | --- | --- |")
            for step in trace:
                summary_clean = str(step.get("summary", "")).replace("|", "\\|").replace("\n", " ")
                dur_s = f"{round(float(step.get('duration_ms', 0)) / 1000, 2):.2f}"
                lines.append(
                    f"| {step.get('stage', '')} | {step.get('status', '')} | {dur_s} | {summary_clean} |"
                )
            lines.append("")

        return "\n".join(lines)


engine = Text2CypherEngine()
