import React, { useEffect, useState } from 'react'
import {
  Search,
  Send,
  Loader2,
  Network,
  Table2,
  Code2,
  Activity,
  Download,
  Database,
  BookOpen,
  History,
  CheckCircle2,
  AlertCircle,
  Copy,
  Check,
  Sparkles,
  ExternalLink,
  Settings,
  X,
} from 'lucide-react'
import { api } from './api'
import type {
  AllowedProvider,
  DifficultyTier,
  HealthStatus,
  HistorySummary,
  ProviderInfo,
  QueryResponse,
  ReasoningEffort,
} from './types'
import { TopologyGraph } from './components/TopologyGraph'
import { TraceViewer } from './components/TraceViewer'
import { KnowledgeBaseManager } from './components/KnowledgeBaseManager'
import { SchemaInspector } from './components/SchemaInspector'
import { SkillManager } from './components/SkillManager'
import {
  INITIAL_STAGES,
  LiveStageStepper,
  type LiveStageItem,
  type StageKey,
  type StageState,
} from './components/LiveStageStepper'

type MainTab = 'workspace' | 'kb' | 'skills' | 'schema' | 'history'
type ResultTab = 'topology' | 'table' | 'cypher' | 'trace'

const TIER_DESCS: Record<DifficultyTier, string> = {
  自动: '由大模型基于图结构语义评估难度与意图，自动选择领域技能与拆解方案',
  简单: '单点或单跳事实查询：节点检索、属性过滤、单跳关系、基础计数',
  中等: '路径遍历或聚合分析：多跳调用、反向依赖、聚合统计、去重',
  复杂: '跨服务、多关系、多子图联合：RPC 与 MQ 联合、变更影响、端到端调用链',
}

export default function App() {
  const [activeTab, setActiveTab] = useState<MainTab>('workspace')
  const [resultTab, setResultTab] = useState<ResultTab>('topology')

  // System & Model settings (configured via Settings modal, persisted in localStorage)
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [provider, setProvider] = useState<AllowedProvider>(
    () => (localStorage.getItem('cg_provider') as AllowedProvider) || 'deepseek',
  )
  const [model, setModel] = useState<string>(() => localStorage.getItem('cg_model') || '')
  const [reasoningEffort, setReasoningEffort] = useState<ReasoningEffort>(
    () => (localStorage.getItem('cg_reasoning') as ReasoningEffort) || 'low',
  )
  const [maxRetries, setMaxRetries] = useState<number>(() => {
    const saved = Number(localStorage.getItem('cg_max_retries'))
    return Number.isFinite(saved) && saved >= 0 && saved <= 5 ? saved : 5
  })
  const [apiKey, setApiKey] = useState<string>('')
  const [showSettings, setShowSettings] = useState(false)

  // Single query state
  const [question, setQuestion] = useState('')
  const [difficulty, setDifficulty] = useState<DifficultyTier>('自动')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<QueryResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  // Live stage execution progress state
  const [liveStages, setLiveStages] = useState<LiveStageItem[]>([])
  const [liveMessage, setLiveMessage] = useState('')
  const [elapsedSec, setElapsedSec] = useState(0)

  // History state
  const [history, setHistory] = useState<HistorySummary[]>([])

  useEffect(() => {
    api.getHealth().then(setHealth).catch(() => {})
    api
      .getProviders()
      .then((res) => {
        setProviders(res.providers)
        const savedProvider = localStorage.getItem('cg_provider') as AllowedProvider | null
        const targetProvider =
          savedProvider && res.providers.some((p) => p.id === savedProvider)
            ? savedProvider
            : res.default_provider
        setProvider(targetProvider)
        const spec = res.providers.find((p) => p.id === targetProvider)
        const savedModel = localStorage.getItem('cg_model')
        if (spec) {
          setModel(savedModel && spec.models.includes(savedModel) ? savedModel : spec.default_model)
        }
        if (localStorage.getItem('cg_max_retries') === null && typeof res.default_max_retries === 'number') {
          setMaxRetries(res.default_max_retries)
        }
      })
      .catch(() => {})
  }, [])

  const loadHistory = () => {
    api
      .getHistory(50)
      .then((res) => setHistory(res.items))
      .catch(() => {})
  }

  useEffect(() => {
    if (activeTab === 'history') loadHistory()
  }, [activeTab])

  const handleProviderChange = (pid: AllowedProvider) => {
    setProvider(pid)
    const spec = providers.find((p) => p.id === pid)
    if (spec) setModel(spec.default_model)
  }

  const runSingleQuery = async (overrideQ?: string, overrideDiff?: DifficultyTier) => {
    const q = (overrideQ ?? question).trim()
    const d = overrideDiff ?? difficulty
    if (!q) return
    setLoading(true)
    setError(null)
    setLiveStages(INITIAL_STAGES.map((s) => ({ ...s })))
    setLiveMessage('正在启动智能体执行引擎...')
    setElapsedSec(0)

    const startTs = performance.now()
    const timer = window.setInterval(() => {
      setElapsedSec((performance.now() - startTs) / 1000)
    }, 100)

    try {
      const res = await api.runQueryStream(
        {
          question: q,
          difficulty: d,
          provider,
          model: model || undefined,
          api_key: apiKey || undefined,
          reasoning_effort: reasoningEffort,
          max_retries: maxRetries,
        },
        (evt) => {
          const evType = String(evt.event || '')
          const stageKey = evt.stage_key as StageKey | undefined
          if (evType === 'stage_start' && stageKey) {
            setLiveStages((prev) =>
              prev.map((s) => (s.key === stageKey ? { ...s, state: 'running' } : s)),
            )
            if (evt.message) setLiveMessage(String(evt.message))
          } else if (evType === 'substep') {
            if (evt.message) setLiveMessage(String(evt.message))
          } else if (evType === 'stage_done' && stageKey) {
            const st = (evt.status as StageState) || 'ok'
            const dur = typeof evt.duration_s === 'number' ? evt.duration_s : undefined
            const sum = evt.summary ? String(evt.summary) : undefined
            setLiveStages((prev) =>
              prev.map((s) =>
                s.key === stageKey ? { ...s, state: st, duration_s: dur, summary: sum } : s,
              ),
            )
            if (sum) setLiveMessage(sum)
          }
        },
      )
      setElapsedSec(res.total_duration_ms / 1000)
      setLiveMessage(`已完成 · 命中 ${res.row_count} 行数据`)
      setResult(res)
      setResultTab(res.topology.nodes.length > 0 ? 'topology' : 'table')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setLiveMessage('执行过程中发生错误')
    } finally {
      window.clearInterval(timer)
      setLoading(false)
    }
  }

  const handleCopyCypher = () => {
    if (!result?.cypher) return
    navigator.clipboard.writeText(result.cypher)
    setCopied(true)
    setTimeout(() => setCopied(false), 1800)
  }

  const currentProviderSpec = providers.find((p) => p.id === provider)

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      {/* Top Navbar */}
      <header className="sticky top-0 z-30 bg-white/95 backdrop-blur border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-600 to-purple-600 text-white flex items-center justify-center shadow-sm">
              <Network className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-sm sm:text-base font-bold text-slate-900 leading-tight">
                代码图谱 Text2Cypher 查询智能体
              </h1>
              <div className="flex items-center gap-2 text-[11px] text-slate-500">
                <span className="inline-flex items-center gap-1">
                  <span
                    className={`w-2 h-2 rounded-full ${
                      health?.neo4j_connected ? 'bg-emerald-500' : 'bg-amber-400'
                    }`}
                  />
                  Neo4j {health?.neo4j_connected ? '已连接' : '检测中'}
                </span>
                {health?.neo4j_browser_url && (
                  <a
                    href={health.neo4j_browser_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-0.5 text-indigo-600 hover:underline"
                  >
                    Browser <ExternalLink className="w-2.5 h-2.5" />
                  </a>
                )}
              </div>
            </div>
          </div>

          {/* Settings Trigger (Model & Runtime Config moved into Settings Modal) */}
          <div className="flex items-center gap-2 text-xs">
            <button
              onClick={() => setShowSettings(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 font-medium shadow-sm transition"
              title="配置模型、思考强度与重试次数"
            >
              <Settings className="w-3.5 h-3.5 text-slate-500" />
              <span>系统配置</span>
            </button>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="max-w-7xl mx-auto px-4 sm:px-6 flex items-center gap-1 overflow-x-auto border-t border-slate-100">
          {(
            [
              { id: 'workspace', label: '智能查询工作台', icon: Search },
              { id: 'kb', label: 'NL-Cypher 知识库', icon: BookOpen },
              { id: 'skills', label: 'Skills 技能管理', icon: Sparkles },
              { id: 'schema', label: '图谱 Schema', icon: Database },
              { id: 'history', label: '查询历史与追溯', icon: History },
            ] as const
          ).map((t) => {
            const Icon = t.icon
            const active = activeTab === t.id
            return (
              <button
                key={t.id}
                onClick={() => setActiveTab(t.id)}
                className={`inline-flex items-center gap-1.5 px-3.5 py-2.5 text-xs font-medium border-b-2 whitespace-nowrap transition ${
                  active
                    ? 'border-indigo-600 text-indigo-700'
                    : 'border-transparent text-slate-500 hover:text-slate-800'
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                {t.label}
              </button>
            )
          })}
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-6">
        {activeTab === 'workspace' && (
          <div className="space-y-5">
            {/* Query Input Card */}
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              {/* 3-Tier Difficulty Selector */}
              <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-medium text-slate-500 mr-1">查询档位：</span>
                  {(['自动', '简单', '中等', '复杂'] as DifficultyTier[]).map((tier) => (
                    <button
                      key={tier}
                      onClick={() => setDifficulty(tier)}
                      className={`px-3 py-1 rounded-full text-xs font-medium transition ${
                        difficulty === tier
                          ? tier === '复杂'
                            ? 'bg-purple-600 text-white shadow-sm'
                            : tier === '中等'
                              ? 'bg-amber-600 text-white shadow-sm'
                              : tier === '简单'
                                ? 'bg-emerald-600 text-white shadow-sm'
                                : 'bg-indigo-600 text-white shadow-sm'
                          : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                      }`}
                    >
                      {tier === '自动' ? '自动路由' : `${tier}查询`}
                    </button>
                  ))}
                </div>
                <span className="text-[11px] text-slate-400">{TIER_DESCS[difficulty]}</span>
              </div>

              {/* Input Box */}
              <div className="flex gap-2.5">
                <input
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && !loading && runSingleQuery()}
                  placeholder="请输入自然语言代码图谱查询问题..."
                  className="flex-1 px-4 py-3 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
                <button
                  onClick={() => runSingleQuery()}
                  disabled={loading || !question.trim()}
                  className="inline-flex items-center gap-2 px-5 py-3 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-medium shadow-sm shrink-0"
                >
                  {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                  {loading ? '分析执行中...' : '执行查询'}
                </button>
              </div>

              {error && (
                <div className="mt-3 p-3 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-700 flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0" />
                  {error}
                </div>
              )}
            </div>

            {/* Live Stage Execution Progress Bar */}
            {liveStages.length > 0 && (
              <LiveStageStepper
                stages={liveStages}
                running={loading}
                liveMessage={liveMessage}
                elapsedSec={elapsedSec}
              />
            )}

            {/* Result Area */}
            {result && (
              <div className="space-y-4">
                {/* Summary Banner */}
                <div className="rounded-2xl border border-indigo-100 bg-gradient-to-r from-indigo-50/70 via-white to-purple-50/50 p-5 shadow-sm">
                  <div className="flex flex-wrap items-center justify-between gap-3 mb-2.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="inline-flex items-center gap-1.5 text-sm font-bold text-slate-900">
                        <Sparkles className="w-4 h-4 text-indigo-600" />
                        自然语言分析总结
                      </span>
                      <span
                        className={`px-2 py-0.5 rounded-full text-[11px] font-medium ${
                          result.status === 'success'
                            ? 'bg-emerald-100 text-emerald-800'
                            : result.status === 'partial'
                              ? 'bg-amber-100 text-amber-800'
                              : 'bg-rose-100 text-rose-800'
                        }`}
                      >
                        {result.status === 'success' ? '执行成功' : result.status === 'partial' ? '部分成功' : '执行失败'}
                      </span>
                      <span className="px-2 py-0.5 rounded-full bg-white border border-slate-200 text-[11px] text-slate-600">
                        {result.intent_category} · {result.resolved_difficulty}
                      </span>
                      <span className="px-2 py-0.5 rounded-full bg-white border border-slate-200 text-[11px] font-mono text-slate-600">
                        {result.row_count} 行 · {result.topology.nodes.length}N/{result.topology.edges.length}E ·{' '}
                        {(result.total_duration_ms / 1000).toFixed(2)} s
                      </span>
                    </div>

                    <a
                      href={api.getMarkdownUrl(result.query_id)}
                      download={`${result.query_id}.md`}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-slate-200 hover:bg-slate-50 text-xs font-medium text-slate-700 shadow-sm"
                    >
                      <Download className="w-3.5 h-3.5" />
                      导出 Markdown 报告
                    </a>
                  </div>

                  <div className="text-sm text-slate-800 whitespace-pre-wrap leading-relaxed">{result.summary}</div>
                </div>

                {/* Result Sub-tabs */}
                <div className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
                  <div className="flex items-center justify-between border-b border-slate-200 px-4 bg-slate-50/70">
                    <div className="flex items-center gap-1">
                      {(
                        [
                          { id: 'topology', label: `结果拓扑图 (${result.topology.nodes.length})`, icon: Network },
                          { id: 'table', label: `结果明细表 (${result.row_count})`, icon: Table2 },
                          { id: 'cypher', label: `Cypher 与子查询 (${result.sub_queries.length})`, icon: Code2 },
                          { id: 'trace', label: `过程追溯 (${result.trace.length})`, icon: Activity },
                        ] as const
                      ).map((t) => {
                        const Icon = t.icon
                        return (
                          <button
                            key={t.id}
                            onClick={() => setResultTab(t.id)}
                            className={`inline-flex items-center gap-1.5 px-3.5 py-3 text-xs font-medium border-b-2 transition ${
                              resultTab === t.id
                                ? 'border-indigo-600 text-indigo-700 bg-white'
                                : 'border-transparent text-slate-500 hover:text-slate-800'
                            }`}
                          >
                            <Icon className="w-3.5 h-3.5" />
                            {t.label}
                          </button>
                        )
                      })}
                    </div>
                  </div>

                  <div className="p-4">
                    {resultTab === 'topology' && <TopologyGraph topology={result.topology} />}

                    {resultTab === 'table' && (
                      <div className="overflow-x-auto max-h-[480px]">
                        {result.rows.length === 0 ? (
                          <div className="py-10 text-center text-sm text-slate-400">未返回数据行</div>
                        ) : (
                          <table className="w-full text-left border-collapse text-xs">
                            <thead className="sticky top-0 bg-slate-100 text-slate-600">
                              <tr>
                                <th className="py-2 px-3 border-b border-slate-200">#</th>
                                {result.columns.map((c) => (
                                  <th key={c} className="py-2 px-3 border-b border-slate-200 whitespace-nowrap">
                                    {c}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                              {result.rows.map((r, idx) => (
                                <tr key={idx} className="hover:bg-slate-50">
                                  <td className="py-2 px-3 font-mono text-slate-400">{idx + 1}</td>
                                  {result.columns.map((c) => (
                                    <td key={c} className="py-2 px-3 text-slate-700 max-w-md break-all">
                                      {typeof r[c] === 'object' && r[c] !== null
                                        ? JSON.stringify(r[c])
                                        : String(r[c] ?? '')}
                                    </td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        )}
                      </div>
                    )}

                    {resultTab === 'cypher' && (
                      <div className="space-y-4">
                        <div className="relative">
                          <div className="flex items-center justify-between mb-2">
                            <span className="text-xs font-semibold text-slate-700">最终执行的 Cypher</span>
                            <button
                              onClick={handleCopyCypher}
                              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-100 hover:bg-slate-200 text-xs text-slate-700"
                            >
                              {copied ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                              {copied ? '已复制' : '复制 Cypher'}
                            </button>
                          </div>
                          <pre className="p-4 rounded-xl bg-slate-900 text-slate-100 font-mono text-xs overflow-x-auto leading-relaxed">
                            {result.cypher}
                          </pre>
                        </div>

                        {result.sub_queries.length > 1 && (
                          <div className="space-y-2.5">
                            <div className="text-xs font-semibold text-slate-700">子查询分解执行明细</div>
                            {result.sub_queries.map((sq) => (
                              <div key={sq.sub_id} className="p-3.5 rounded-xl border border-slate-200 bg-slate-50 text-xs">
                                <div className="flex items-center justify-between mb-1.5">
                                  <span className="font-semibold text-slate-800">
                                    {sq.title} ({sq.mechanism})
                                  </span>
                                  <span className="font-mono text-slate-500">
                                    尝试 {sq.attempts} 次 · 命中 {sq.row_count} 行 · {(sq.duration_ms / 1000).toFixed(2)} s
                                  </span>
                                </div>
                                <pre className="p-2.5 rounded-lg bg-slate-900 text-slate-100 font-mono text-[11px] overflow-x-auto">
                                  {sq.cypher}
                                </pre>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}

                    {resultTab === 'trace' && <TraceViewer result={result} />}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === 'kb' && (
          <KnowledgeBaseManager
            onReuseQuestion={(q, diff) => {
              setQuestion(q)
              setDifficulty(diff)
              setActiveTab('workspace')
              runSingleQuery(q, diff)
            }}
          />
        )}

        {activeTab === 'skills' && <SkillManager />}

        {activeTab === 'schema' && <SchemaInspector />}

        {activeTab === 'history' && (
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-semibold text-slate-900">历史查询与过程追溯记录</h2>
              <button
                onClick={loadHistory}
                className="px-3 py-1.5 rounded-lg border border-slate-200 text-xs font-medium text-slate-600 hover:bg-slate-50"
              >
                刷新列表
              </button>
            </div>
            {history.length === 0 ? (
              <div className="py-10 text-center text-sm text-slate-400">暂无历史查询记录</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="border-b border-slate-200 text-slate-500">
                      <th className="py-2 pr-3">时间</th>
                      <th className="py-2 pr-3">问题</th>
                      <th className="py-2 pr-3">意图 / 档位</th>
                      <th className="py-2 pr-3">模型</th>
                      <th className="py-2 pr-3">状态 / 命中</th>
                      <th className="py-2 text-right">操作</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {history.map((h) => (
                      <tr key={h.query_id} className="hover:bg-slate-50">
                        <td className="py-2.5 pr-3 text-slate-400 font-mono whitespace-nowrap">{h.created_at}</td>
                        <td className="py-2.5 pr-3 font-medium text-slate-800 max-w-sm truncate">{h.question}</td>
                        <td className="py-2.5 pr-3 text-slate-600 whitespace-nowrap">
                          {h.intent_category} · {h.difficulty}
                        </td>
                        <td className="py-2.5 pr-3 font-mono text-slate-500 whitespace-nowrap">{h.model}</td>
                        <td className="py-2.5 pr-3 whitespace-nowrap">
                          <span className="inline-flex items-center gap-1 text-emerald-700 font-mono">
                            <CheckCircle2 className="w-3.5 h-3.5" /> {h.row_count} 行 ({(h.total_duration_ms / 1000).toFixed(2)} s)
                          </span>
                        </td>
                        <td className="py-2.5 text-right whitespace-nowrap space-x-2">
                          <button
                            onClick={async () => {
                              const full = await api.getHistoryDetail(h.query_id)
                              setResult(full)
                              setQuestion(full.question)
                              setActiveTab('workspace')
                            }}
                            className="px-2.5 py-1 rounded-lg bg-indigo-50 hover:bg-indigo-100 text-indigo-700 font-medium"
                          >
                            回放
                          </button>
                          <a
                            href={api.getMarkdownUrl(h.query_id)}
                            download={`${h.query_id}.md`}
                            className="inline-block px-2.5 py-1 rounded-lg border border-slate-200 hover:bg-slate-100 text-slate-700"
                          >
                            导出 MD
                          </a>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </main>

      {/* System Configuration Modal */}
      {showSettings && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-xl w-full max-w-md p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-semibold text-slate-900 flex items-center gap-2">
                <Settings className="w-4 h-4 text-indigo-600" />
                模型与执行参数配置
              </h3>
              <button onClick={() => setShowSettings(false)} className="text-slate-400 hover:text-slate-700">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-4 text-xs">
              <div>
                <label className="block font-medium text-slate-700 mb-1">大模型提供商（限定 DeepSeek / GLM / Kimi）</label>
                <select
                  value={provider}
                  onChange={(e) => handleProviderChange(e.target.value as AllowedProvider)}
                  className="w-full px-3 py-2 rounded-lg border border-slate-200 bg-white font-medium text-slate-700"
                >
                  {providers.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} {p.configured ? '（服务端已配置 Key）' : '（需手动填写 Key）'}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block font-medium text-slate-700 mb-1">模型名称</label>
                <select
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-slate-200 bg-white font-mono text-slate-700"
                >
                  {(currentProviderSpec?.models || []).map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block font-medium text-slate-700 mb-1">思考强度（推理模型生效）</label>
                <select
                  value={reasoningEffort}
                  onChange={(e) => setReasoningEffort(e.target.value as ReasoningEffort)}
                  className="w-full px-3 py-2 rounded-lg border border-slate-200 bg-white text-slate-700"
                >
                  <option value="none">默认 / 关闭 (none)</option>
                  <option value="low">低 (low · 推荐)</option>
                  <option value="medium">中 (medium)</option>
                  <option value="high">高 (high)</option>
                </select>
              </div>

              <div>
                <label className="block font-medium text-slate-700 mb-1">
                  最大自修正重试轮数（当前：{maxRetries} 轮）
                </label>
                <input
                  type="range"
                  min={0}
                  max={5}
                  value={maxRetries}
                  onChange={(e) => setMaxRetries(Number(e.target.value))}
                  className="w-full accent-indigo-600"
                />
                <div className="flex justify-between text-[11px] text-slate-400">
                  <span>0 轮（不重试）</span>
                  <span>默认 5 轮</span>
                </div>
              </div>

              <div>
                <label className="block font-medium text-slate-700 mb-1">
                  自定义 API Key（可选，留空则使用服务端环境变量）
                </label>
                <input
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="sk-..."
                  className="w-full px-3 py-2 rounded-lg border border-slate-200 font-mono"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 mt-6">
              <button
                onClick={() => setShowSettings(false)}
                className="px-4 py-2 rounded-lg border border-slate-200 text-xs font-medium text-slate-600 hover:bg-slate-50"
              >
                取消
              </button>
              <button
                onClick={() => {
                  localStorage.setItem('cg_provider', provider)
                  localStorage.setItem('cg_model', model)
                  localStorage.setItem('cg_reasoning', reasoningEffort)
                  localStorage.setItem('cg_max_retries', String(maxRetries))
                  setShowSettings(false)
                }}
                className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-medium"
              >
                保存配置
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
