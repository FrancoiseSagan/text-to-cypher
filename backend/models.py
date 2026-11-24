"""Pydantic models for the Text2Cypher Code Graph Agent API."""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field

from .config import AllowedProvider

DifficultyTier = Literal["简单", "中等", "复杂", "自动"]
ReasoningEffort = Literal["none", "low", "medium", "high"]


class TopologyNode(BaseModel):
    id: str
    label: str
    category: str
    properties: dict[str, Any] = Field(default_factory=dict)


class TopologyEdge(BaseModel):
    id: str
    source: str
    target: str
    type: str
    label: str
    mechanism: str = "STRUCTURAL"  # STRUCTURAL | RPC | MQ
    properties: dict[str, Any] = Field(default_factory=dict)


class TopologyData(BaseModel):
    nodes: list[TopologyNode] = Field(default_factory=list)
    edges: list[TopologyEdge] = Field(default_factory=list)


class ValidationReport(BaseModel):
    valid: bool
    checks: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TraceStep(BaseModel):
    stage: str
    status: Literal["ok", "warn", "error", "retry"] = "ok"
    duration_ms: float = 0.0
    summary: str = ""
    detail: dict[str, Any] = Field(default_factory=dict)


class SubQueryExecution(BaseModel):
    sub_id: str
    title: str
    mechanism: str = "GENERAL"
    cypher: str = ""
    attempts: int = 1
    validation: ValidationReport | None = None
    row_count: int = 0
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    duration_ms: float = 0.0


class GroundedEntity(BaseModel):
    mention: str
    label: str
    matched_name: str
    property_key: str
    extra: dict[str, Any] = Field(default_factory=dict)


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    difficulty: DifficultyTier = "自动"
    provider: AllowedProvider | None = None
    model: str | None = None
    api_key: str | None = None
    reasoning_effort: ReasoningEffort | None = None
    max_retries: int | None = None


class BatchQueryRequest(BaseModel):
    questions: list[str] = Field(..., min_length=1, max_length=50)
    difficulty: DifficultyTier = "自动"
    provider: AllowedProvider | None = None
    model: str | None = None
    api_key: str | None = None


class QueryResponse(BaseModel):
    query_id: str
    question: str
    requested_difficulty: str
    resolved_difficulty: str
    intent_category: str
    provider: str
    model: str
    status: Literal["success", "partial", "error"]
    cypher: str
    sub_queries: list[SubQueryExecution] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    topology: TopologyData = Field(default_factory=TopologyData)
    summary: str = ""
    grounded_entities: list[GroundedEntity] = Field(default_factory=list)
    retrieved_examples: list[dict[str, Any]] = Field(default_factory=list)
    loaded_skills: list[str] = Field(default_factory=list)
    validation: ValidationReport | None = None
    trace: list[TraceStep] = Field(default_factory=list)
    total_duration_ms: float = 0.0
    created_at: str = ""
    error: str | None = None


class BatchQueryResponse(BaseModel):
    total: int
    succeeded: int
    failed: int
    results: list[QueryResponse]


class KBItemBase(BaseModel):
    question: str = Field(..., min_length=1)
    cypher: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    complexity: Literal["简单", "中等", "复杂"] = "简单"
    tags: list[str] = Field(default_factory=list)
    description: str = ""


class KBItemCreate(KBItemBase):
    pass


class KBItemUpdate(BaseModel):
    question: str | None = None
    cypher: str | None = None
    category: str | None = None
    complexity: Literal["简单", "中等", "复杂"] | None = None
    tags: list[str] | None = None
    description: str | None = None


class KBItem(KBItemBase):
    id: str
    verified: bool = True
    last_row_count: int | None = None
    created_at: str = ""
    updated_at: str = ""


class KBVerifyRequest(BaseModel):
    cypher: str = Field(..., min_length=1)


class KBVerifyResponse(BaseModel):
    valid: bool
    validation: ValidationReport
    row_count: int = 0
    columns: list[str] = Field(default_factory=list)
    sample_rows: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None


class SkillPayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    version: str = "1.0.0"
    description: str = ""
    triggers: list[str] = Field(default_factory=list)
    body: str = Field(..., min_length=1)


class SkillUpdatePayload(BaseModel):
    version: str | None = None
    description: str | None = None
    triggers: list[str] | None = None
    body: str | None = None
    raw_content: str | None = None
