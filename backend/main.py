"""FastAPI application exposing the Code Graph Text2Cypher Agent API."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import ALLOWED_PROVIDERS, PROJECT_ROOT, settings
from .engine import engine
from .guardrail import guardrail
from .kb_store import kb_store
from .models import (
    BatchQueryRequest,
    BatchQueryResponse,
    KBItem,
    KBItemCreate,
    KBItemUpdate,
    KBVerifyRequest,
    KBVerifyResponse,
    QueryRequest,
    QueryResponse,
    SkillPayload,
    SkillUpdatePayload,
)
from .neo4j_client import neo4j_client
from .schema_service import schema_service
from .skill_loader import skill_loader

app = FastAPI(
    title="面向代码图谱的 Text2Cypher 查询智能体",
    version="1.0.0",
    description="支持 Enhanced Schema 感知、实体对齐、Skill/知识库增强、复杂查询拆解、三层校验与执行反馈自修正的代码图谱查询引擎",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, Any]:
    neo4j_ok = neo4j_client.ping()
    return {
        "status": "ok" if neo4j_ok else "degraded",
        "neo4j_connected": neo4j_ok,
        "neo4j_uri": settings.neo4j_uri,
        "neo4j_browser_url": settings.neo4j_browser_url,
        "default_provider": settings.get_default_provider(),
    }


@app.get("/api/providers")
def list_providers() -> dict[str, Any]:
    providers = []
    for pid, spec in ALLOWED_PROVIDERS.items():
        has_key = bool(settings.get_provider_api_key(pid))
        providers.append(
            {
                "id": spec.id,
                "name": spec.name,
                "default_model": spec.default_model,
                "models": spec.models,
                "configured": has_key,
            }
        )
    return {
        "default_provider": settings.get_default_provider(),
        "default_max_retries": settings.max_self_correction_retries,
        "providers": providers,
    }


@app.get("/api/schema")
def get_schema() -> dict[str, Any]:
    return schema_service.get_schema(force_refresh=False)


@app.post("/api/schema/refresh")
def refresh_schema() -> dict[str, Any]:
    return schema_service.get_schema(force_refresh=True)


@app.get("/api/skills")
def list_skills() -> dict[str, Any]:
    skill_loader.reload()
    return {"skills": skill_loader.list_skills()}


@app.get("/api/skills/{name}")
def get_skill_detail(name: str) -> dict[str, Any]:
    skill_loader.reload()
    sk = skill_loader.get_skill(name)
    if not sk:
        raise HTTPException(status_code=404, detail="技能不存在")
    return sk


@app.post("/api/skills")
def create_skill(body: SkillPayload) -> dict[str, Any]:
    try:
        return skill_loader.create_skill(
            name=body.name,
            version=body.version,
            description=body.description,
            triggers=body.triggers,
            body=body.body,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.put("/api/skills/{name}")
def update_skill(name: str, body: SkillUpdatePayload) -> dict[str, Any]:
    updated = skill_loader.update_skill(
        name=name,
        version=body.version,
        description=body.description,
        triggers=body.triggers,
        body=body.body,
        raw_content=body.raw_content,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="技能不存在")
    return updated


@app.delete("/api/skills/{name}")
def delete_skill(name: str) -> dict[str, Any]:
    try:
        ok = skill_loader.delete_skill(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not ok:
        raise HTTPException(status_code=404, detail="技能不存在")
    return {"deleted": True, "name": name}


# --- Query Execution (Single, Live SSE Stream & Batch) ---
@app.post("/api/query", response_model=QueryResponse)
async def execute_query(req: QueryRequest) -> QueryResponse:
    return await asyncio.to_thread(engine.run_query, req)


@app.post("/api/query/stream")
async def execute_query_stream(req: QueryRequest) -> StreamingResponse:
    """Stream real-time stage progress events (SSE) while executing the query."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    def _on_progress(evt: dict[str, Any]) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, evt)

    async def _worker() -> None:
        try:
            res = await asyncio.to_thread(engine.run_query, req, _on_progress)
            await queue.put({"event": "result", "data": res.model_dump()})
        except Exception as exc:
            await queue.put({"event": "error", "message": str(exc)})
        finally:
            await queue.put(None)

    asyncio.create_task(_worker())

    async def _event_gen():
        while True:
            item = await queue.get()
            if item is None:
                break
            evt_name = item.get("event", "message")
            payload = json.dumps(item, ensure_ascii=False)
            yield f"event: {evt_name}\ndata: {payload}\n\n"

    return StreamingResponse(
        _event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/query/batch", response_model=BatchQueryResponse)
async def execute_batch_query(req: BatchQueryRequest) -> BatchQueryResponse:
    cleaned = [q.strip() for q in req.questions if q and q.strip()]
    if not cleaned:
        raise HTTPException(status_code=400, detail="批量问题列表为空")

    # Controlled concurrency (3 workers) so we don't overload LLM or Neo4j
    sem = asyncio.Semaphore(3)

    async def _run_one(q: str) -> QueryResponse:
        async with sem:
            single_req = QueryRequest(
                question=q,
                difficulty=req.difficulty,
                provider=req.provider,
                model=req.model,
                api_key=req.api_key,
            )
            return await asyncio.to_thread(engine.run_query, single_req)

    results = await asyncio.gather(*(_run_one(q) for q in cleaned))
    succeeded = sum(1 for r in results if r.status in ("success", "partial"))
    return BatchQueryResponse(
        total=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
        results=list(results),
    )


# --- History & Markdown Report Export ---
@app.get("/api/history")
def list_history(limit: int = Query(default=40, ge=1, le=200)) -> dict[str, Any]:
    return {"items": kb_store.list_history(limit=limit)}


@app.get("/api/history/{query_id}")
def get_history_detail(query_id: str) -> dict[str, Any]:
    item = kb_store.get_history_item(query_id)
    if not item:
        raise HTTPException(status_code=404, detail="查询记录不存在")
    return item


@app.get("/api/history/{query_id}/markdown", response_class=PlainTextResponse)
def export_history_markdown(query_id: str) -> PlainTextResponse:
    item = kb_store.get_history_item(query_id)
    if not item:
        raise HTTPException(status_code=404, detail="查询记录不存在")
    md = engine.render_markdown_report(item)
    return PlainTextResponse(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{query_id}.md"'},
    )


# --- Knowledge Base Management (T2 + Req 8) ---
@app.get("/api/kb")
def list_kb_items(
    keyword: str = "",
    category: str = "",
    complexity: str = "",
) -> dict[str, Any]:
    items = kb_store.list_items(keyword=keyword, category=category, complexity=complexity)
    categories = kb_store.get_categories()
    return {
        "total": len(items),
        "categories": categories,
        "items": [it.model_dump() for it in items],
    }


@app.post("/api/kb", response_model=KBItem)
def create_kb_item(body: KBItemCreate) -> KBItem:
    val = guardrail.validate(body.cypher, run_explain=True)
    row_count: int | None = None
    verified = False
    if val.valid:
        try:
            res = neo4j_client.execute_query(body.cypher, max_rows=20)
            row_count = res["row_count"]
            verified = row_count > 0
        except Exception:
            verified = False
    return kb_store.create_item(body, verified=verified, last_row_count=row_count)


@app.put("/api/kb/{item_id}", response_model=KBItem)
def update_kb_item(item_id: str, body: KBItemUpdate) -> KBItem:
    verified: bool | None = None
    row_count: int | None = None
    if body.cypher is not None:
        val = guardrail.validate(body.cypher, run_explain=True)
        if val.valid:
            try:
                res = neo4j_client.execute_query(body.cypher, max_rows=20)
                row_count = res["row_count"]
                verified = row_count > 0
            except Exception:
                verified = False
        else:
            verified = False
    updated = kb_store.update_item(item_id, body, verified=verified, last_row_count=row_count)
    if not updated:
        raise HTTPException(status_code=404, detail="知识库条目不存在")
    return updated


@app.delete("/api/kb/{item_id}")
def delete_kb_item(item_id: str) -> dict[str, Any]:
    ok = kb_store.delete_item(item_id)
    if not ok:
        raise HTTPException(status_code=404, detail="知识库条目不存在")
    return {"deleted": True, "id": item_id}


@app.post("/api/kb/verify", response_model=KBVerifyResponse)
def verify_kb_cypher(body: KBVerifyRequest) -> KBVerifyResponse:
    val = guardrail.validate(body.cypher, run_explain=True)
    if not val.valid:
        return KBVerifyResponse(valid=False, validation=val, error="; ".join(val.errors))
    try:
        res = neo4j_client.execute_query(body.cypher, max_rows=20)
        return KBVerifyResponse(
            valid=True,
            validation=val,
            row_count=res["row_count"],
            columns=res["columns"],
            sample_rows=res["rows"][:10],
        )
    except Exception as exc:
        return KBVerifyResponse(valid=False, validation=val, error=str(exc))


# Serve built frontend dist if present
_FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")
