import type {
  AllowedProvider,
  BatchQueryResponse,
  DifficultyTier,
  HealthStatus,
  HistorySummary,
  KBItem,
  KBVerifyResponse,
  ProviderInfo,
  QueryResponse,
  ReasoningEffort,
  SchemaData,
  SkillInfo,
} from './types'

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    ...init,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  getHealth: () => request<HealthStatus>('/api/health'),
  getProviders: () =>
    request<{
      default_provider: AllowedProvider
      default_max_retries: number
      providers: ProviderInfo[]
    }>('/api/providers'),
  getSchema: () => request<SchemaData>('/api/schema'),
  refreshSchema: () => request<SchemaData>('/api/schema/refresh', { method: 'POST' }),
  getSkills: () => request<{ skills: SkillInfo[] }>('/api/skills'),
  createSkill: (payload: {
    name: string
    version: string
    description: string
    triggers: string[]
    body: string
  }) =>
    request<SkillInfo>('/api/skills', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateSkill: (
    name: string,
    payload: {
      version?: string
      description?: string
      triggers?: string[]
      body?: string
      raw_content?: string
    },
  ) =>
    request<SkillInfo>(`/api/skills/${encodeURIComponent(name)}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  deleteSkill: (name: string) =>
    request<{ deleted: boolean; name: string }>(`/api/skills/${encodeURIComponent(name)}`, {
      method: 'DELETE',
    }),

  runQuery: (payload: {
    question: string
    difficulty: DifficultyTier
    provider: AllowedProvider
    model?: string
    api_key?: string
    reasoning_effort?: ReasoningEffort
    max_retries?: number
  }) =>
    request<QueryResponse>('/api/query', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  runQueryStream: async (
    payload: {
      question: string
      difficulty: DifficultyTier
      provider: AllowedProvider
      model?: string
      api_key?: string
      reasoning_effort?: ReasoningEffort
      max_retries?: number
    },
    onEvent: (evt: Record<string, unknown>) => void,
  ): Promise<QueryResponse> => {
    const res = await fetch('/api/query/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!res.ok || !res.body) {
      const text = await res.text()
      throw new Error(text || `HTTP ${res.status}`)
    }
    const reader = res.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    let finalResult: QueryResponse | null = null

    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const chunks = buffer.split('\n\n')
      buffer = chunks.pop() || ''

      for (const chunk of chunks) {
        const dataLines = chunk
          .split('\n')
          .filter((l) => l.startsWith('data:'))
          .map((l) => l.slice(5).trim())
        if (dataLines.length === 0) continue
        try {
          const parsed = JSON.parse(dataLines.join('\n')) as Record<string, unknown>
          if (parsed.event === 'result' && parsed.data) {
            finalResult = parsed.data as QueryResponse
          } else if (parsed.event === 'error') {
            throw new Error(String(parsed.message || '流式查询异常'))
          } else {
            onEvent(parsed)
          }
        } catch (err) {
          if (err instanceof Error && err.message !== 'Unexpected end of JSON input') {
            throw err
          }
        }
      }
    }

    if (!finalResult) {
      throw new Error('未收到最终查询结果')
    }
    return finalResult
  },

  runBatchQuery: (payload: {
    questions: string[]
    difficulty: DifficultyTier
    provider: AllowedProvider
    model?: string
    api_key?: string
  }) =>
    request<BatchQueryResponse>('/api/query/batch', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  getHistory: (limit = 40) => request<{ items: HistorySummary[] }>(`/api/history?limit=${limit}`),
  getHistoryDetail: (queryId: string) => request<QueryResponse>(`/api/history/${queryId}`),
  getMarkdownUrl: (queryId: string) => `/api/history/${queryId}/markdown`,

  listKB: (params?: { keyword?: string; category?: string; complexity?: string }) => {
    const sp = new URLSearchParams()
    if (params?.keyword) sp.set('keyword', params.keyword)
    if (params?.category && params.category !== '全部') sp.set('category', params.category)
    if (params?.complexity && params.complexity !== '全部') sp.set('complexity', params.complexity)
    return request<{
      total: number
      categories: { category: string; count: number }[]
      items: KBItem[]
    }>(`/api/kb?${sp.toString()}`)
  },

  createKB: (payload: {
    question: string
    cypher: string
    category: string
    complexity: '简单' | '中等' | '复杂'
    tags: string[]
    description: string
  }) =>
    request<KBItem>('/api/kb', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  updateKB: (
    id: string,
    payload: Partial<{
      question: string
      cypher: string
      category: string
      complexity: '简单' | '中等' | '复杂'
      tags: string[]
      description: string
    }>,
  ) =>
    request<KBItem>(`/api/kb/${id}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  deleteKB: (id: string) =>
    request<{ deleted: boolean; id: string }>(`/api/kb/${id}`, { method: 'DELETE' }),

  verifyKBCypher: (cypher: string) =>
    request<KBVerifyResponse>('/api/kb/verify', {
      method: 'POST',
      body: JSON.stringify({ cypher }),
    }),
}
