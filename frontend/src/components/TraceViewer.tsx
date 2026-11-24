import React from 'react'
import { CheckCircle2, AlertTriangle, XCircle, RefreshCw, Sparkles, BookOpen, ShieldCheck, Tag } from 'lucide-react'
import type { QueryResponse } from '../types'

interface Props {
  result: QueryResponse
}

export const TraceViewer: React.FC<Props> = ({ result }) => {
  return (
    <div className="space-y-5">
      {/* Grounded Entities & Skills */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-800 mb-3">
            <Tag className="w-4 h-4 text-indigo-600" />
            实体识别与实库语义对齐 ({result.grounded_entities.length})
          </div>
          {result.grounded_entities.length === 0 ? (
            <p className="text-xs text-slate-400">未检测到特定实体名（使用通用 Schema 模式查询）</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {result.grounded_entities.map((e, i) => (
                <div
                  key={i}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-indigo-50 border border-indigo-100 text-xs"
                >
                  <span className="text-slate-600">{e.mention}</span>
                  <span className="text-slate-400">→</span>
                  <span className="font-mono font-medium text-indigo-700">
                    :{e.label}({e.matched_name})
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-800 mb-3">
            <Sparkles className="w-4 h-4 text-purple-600" />
            动态加载的领域技能 (Skills)
          </div>
          <div className="flex flex-wrap gap-2 mb-3">
            {result.loaded_skills.map((s) => (
              <span
                key={s}
                className="px-2.5 py-1 rounded-full bg-purple-50 text-purple-700 border border-purple-200 text-xs font-mono"
              >
                {s}
              </span>
            ))}
          </div>
          <div className="text-xs text-slate-500">
            意图分类：<span className="font-medium text-slate-800">{result.intent_category}</span> · 执行档位：
            <span className="font-medium text-slate-800">{result.resolved_difficulty}</span> · 模型：
            <span className="font-mono text-slate-800">
              {result.provider}/{result.model}
            </span>
          </div>
        </div>
      </div>

      {/* Guardrail Validation */}
      {result.validation && (
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-800">
              <ShieldCheck className="w-4 h-4 text-emerald-600" />
              Cypher 三层安全与合法性校验
            </div>
            <span
              className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                result.validation.valid
                  ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                  : 'bg-rose-50 text-rose-700 border border-rose-200'
              }`}
            >
              {result.validation.valid ? '校验通过' : '存在拦截项'}
            </span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2.5">
            {result.validation.checks.map((c, idx) => (
              <div
                key={idx}
                className={`p-2.5 rounded-lg border text-xs ${
                  c.passed ? 'bg-emerald-50/40 border-emerald-100' : 'bg-rose-50/50 border-rose-200'
                }`}
              >
                <div className="flex items-center gap-1.5 font-medium text-slate-800 mb-1">
                  {c.passed ? (
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                  ) : (
                    <XCircle className="w-3.5 h-3.5 text-rose-600 shrink-0" />
                  )}
                  <span className="truncate">{c.name}</span>
                </div>
                <div className="text-slate-600 break-all">{c.detail}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Retrieved KB Examples */}
      {result.retrieved_examples.length > 0 && (
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-800 mb-3">
            <BookOpen className="w-4 h-4 text-amber-600" />
            知识库语义召回参考示例 (Top-{result.retrieved_examples.length})
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
            {result.retrieved_examples.map((ex) => (
              <div key={ex.id} className="p-3 rounded-lg bg-slate-50 border border-slate-200 text-xs">
                <div className="flex items-center justify-between gap-2 mb-1">
                  <span className="font-medium text-slate-800">{ex.question}</span>
                  <span className="shrink-0 px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 font-mono">
                    sim {ex.score}
                  </span>
                </div>
                <div className="text-slate-500 mb-1.5">
                  {ex.category} · {ex.complexity}
                </div>
                <pre className="p-2 rounded bg-slate-900 text-slate-100 font-mono text-[11px] overflow-x-auto">
                  {ex.cypher}
                </pre>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Execution Timeline */}
      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <div className="text-sm font-semibold text-slate-800 mb-3">
          全过程执行追溯时间线（总耗时 {(result.total_duration_ms / 1000).toFixed(2)} s）
        </div>
        <div className="space-y-2.5">
          {result.trace.map((step, i) => (
            <div key={i} className="flex items-start gap-3 p-2.5 rounded-lg bg-slate-50/80 border border-slate-100 text-xs">
              <div className="mt-0.5 shrink-0">
                {step.status === 'ok' && <CheckCircle2 className="w-4 h-4 text-emerald-600" />}
                {step.status === 'warn' && <AlertTriangle className="w-4 h-4 text-amber-500" />}
                {step.status === 'retry' && <RefreshCw className="w-4 h-4 text-indigo-600" />}
                {step.status === 'error' && <XCircle className="w-4 h-4 text-rose-600" />}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold text-slate-800">{step.stage}</span>
                  <span className="font-mono text-slate-400">{(step.duration_ms / 1000).toFixed(2)} s</span>
                </div>
                <p className="text-slate-600 mt-0.5 break-all">{step.summary}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
