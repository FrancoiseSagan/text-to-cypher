import React, { useEffect, useState } from 'react'
import { RefreshCw, Database, GitBranch } from 'lucide-react'
import { api } from '../api'
import type { SchemaData } from '../types'

export const SchemaInspector: React.FC = () => {
  const [schema, setSchema] = useState<SchemaData | null>(null)
  const [loading, setLoading] = useState(false)

  const load = async (refresh = false) => {
    setLoading(true)
    try {
      const s = refresh ? await api.refreshSchema() : await api.getSchema()
      setSchema(s)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load(false)
  }, [])

  if (!schema) {
    return <div className="text-center py-12 text-sm text-slate-500">正在从 Neo4j 自动读取实时 Schema...</div>
  }

  return (
    <div className="space-y-5">
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-base font-semibold text-slate-900 flex items-center gap-2">
              <Database className="w-4 h-4 text-indigo-600" />
              Neo4j 实时 Schema 自动感知（Enhanced Schema）
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              最近同步：{schema.refreshed_at} · 有效节点标签 {schema.active_labels.length} 类 · 关系类型{' '}
              {schema.rel_types.length} 类 · 有向拓扑三元组 {schema.triplets.length} 种
            </p>
          </div>
          <button
            onClick={() => load(true)}
            disabled={loading}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 text-xs font-medium text-slate-700"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            刷新实时 Schema
          </button>
        </div>

        {/* Active Node Labels */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
          {schema.active_labels.map((lbl) => (
            <div key={lbl} className="p-3 rounded-xl border border-slate-200 bg-slate-50/70">
              <div className="flex items-center justify-between mb-1.5">
                <span className="font-semibold text-sm text-indigo-700">:{lbl}</span>
                <span className="font-mono text-xs px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-800">
                  {schema.label_counts[lbl]}
                </span>
              </div>
              <div className="text-[11px] text-slate-600 line-clamp-3">
                属性 ({schema.node_properties[lbl]?.length || 0})：
                {(schema.node_properties[lbl] || []).slice(0, 12).join(', ')}
              </div>
            </div>
          ))}
        </div>

        {/* Directed Triplets */}
        <div className="mb-5">
          <h3 className="text-sm font-semibold text-slate-800 flex items-center gap-1.5 mb-2.5">
            <GitBranch className="w-4 h-4 text-emerald-600" />
            有向关系拓扑三元组 (Start)-[Rel]-&gt;(End)
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
            {schema.triplets.map((t, i) => (
              <div
                key={i}
                className="flex items-center justify-between px-3 py-2 rounded-lg bg-slate-50 border border-slate-200 text-xs font-mono"
              >
                <span className="text-slate-800">
                  (:{t.src})-[:{t.rel}]-&gt;(:{t.dst})
                </span>
                <span className="text-slate-500">{t.count}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Key Enums */}
        <div>
          <h3 className="text-sm font-semibold text-slate-800 mb-2">关键枚举值采样（用于 Value-Aware Grounding）</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 text-xs">
            {Object.entries(schema.enums).map(([k, vals]) => (
              <div key={k} className="p-3 rounded-lg bg-slate-50 border border-slate-200">
                <div className="font-mono font-semibold text-slate-800 mb-1">
                  {k} ({vals.length})
                </div>
                <div className="text-slate-600 break-words leading-relaxed">{vals.join(' · ')}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
