export type AllowedProvider = 'deepseek' | 'glm' | 'kimi'
export type DifficultyTier = '自动' | '简单' | '中等' | '复杂'
export type ReasoningEffort = 'none' | 'low' | 'medium' | 'high'

export interface ProviderInfo {
  id: AllowedProvider
  name: string
  default_model: string
  models: string[]
  configured: boolean
}

export interface HealthStatus {
  status: string
  neo4j_connected: boolean
  neo4j_uri: string
  neo4j_browser_url: string
  default_provider: AllowedProvider
}

export interface TopologyNode {
  id: string
  label: string
  category: string
  properties: Record<string, unknown>
}

export interface TopologyEdge {
  id: string
  source: string
  target: string
  type: string
  label: string
  mechanism: 'STRUCTURAL' | 'RPC' | 'MQ' | string
  properties: Record<string, unknown>
}

export interface TopologyData {
  nodes: TopologyNode[]
  edges: TopologyEdge[]
}

export interface ValidationCheck {
  name: string
  passed: boolean
  detail: string
}

export interface ValidationReport {
  valid: boolean
  checks: ValidationCheck[]
  errors: string[]
  warnings: string[]
}

export interface TraceStep {
  stage: string
  status: 'ok' | 'warn' | 'error' | 'retry'
  duration_ms: number
  summary: string
  detail: Record<string, unknown>
}

export interface GroundedEntity {
  mention: string
  label: string
  matched_name: string
  property_key: string
  extra: Record<string, unknown>
}

export interface SubQueryExecution {
  sub_id: string
  title: string
  mechanism: string
  cypher: string
  attempts: number
  validation?: ValidationReport | null
  row_count: number
  columns: string[]
  rows: Record<string, unknown>[]
  error?: string | null
  duration_ms: number
}

export interface QueryResponse {
  query_id: string
  question: string
  requested_difficulty: string
  resolved_difficulty: string
  intent_category: string
  provider: string
  model: string
  status: 'success' | 'partial' | 'error'
  cypher: string
  sub_queries: SubQueryExecution[]
  columns: string[]
  rows: Record<string, unknown>[]
  row_count: number
  topology: TopologyData
  summary: string
  grounded_entities: GroundedEntity[]
  retrieved_examples: {
    id: string
    question: string
    cypher: string
    category: string
    complexity: string
    score: number
  }[]
  loaded_skills: string[]
  validation?: ValidationReport | null
  trace: TraceStep[]
  total_duration_ms: number
  created_at: string
  error?: string | null
}

export interface BatchQueryResponse {
  total: number
  succeeded: number
  failed: number
  results: QueryResponse[]
}

export interface KBItem {
  id: string
  question: string
  cypher: string
  category: string
  complexity: '简单' | '中等' | '复杂'
  tags: string[]
  description: string
  verified: boolean
  last_row_count?: number | null
  created_at: string
  updated_at: string
}

export interface KBVerifyResponse {
  valid: boolean
  validation: ValidationReport
  row_count: number
  columns: string[]
  sample_rows: Record<string, unknown>[]
  error?: string | null
}

export interface SchemaData {
  active_labels: string[]
  empty_labels: string[]
  all_labels: string[]
  label_counts: Record<string, number>
  rel_types: string[]
  rel_counts: Record<string, number>
  triplets: { src: string; rel: string; dst: string; count: number }[]
  node_properties: Record<string, string[]>
  rel_properties: Record<string, string[]>
  enums: Record<string, string[]>
  refreshed_at: string
}

export interface SkillInfo {
  name: string
  version: string
  description: string
  triggers: string[]
  body: string
  raw_content: string
  is_base?: boolean
}

export interface HistorySummary {
  query_id: string
  question: string
  difficulty: string
  intent_category: string
  provider: string
  model: string
  status: string
  cypher: string
  row_count: number
  total_duration_ms: number
  created_at: string
}
