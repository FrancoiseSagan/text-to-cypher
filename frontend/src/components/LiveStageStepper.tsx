import React from 'react'
import { CheckCircle2, Loader2, Circle, SkipForward, AlertTriangle, XCircle, Clock } from 'lucide-react'

export type StageKey = 'schema' | 'plan' | 'execute' | 'merge' | 'summary'
export type StageState = 'pending' | 'running' | 'ok' | 'warn' | 'error' | 'skipped'

export interface LiveStageItem {
  key: StageKey
  label: string
  state: StageState
  duration_s?: number
  summary?: string
}

export const INITIAL_STAGES: LiveStageItem[] = [
  { key: 'plan', label: '语义评估与实体抽取', state: 'pending' },
  { key: 'schema', label: 'Schema装配与实库对齐', state: 'pending' },
  { key: 'execute', label: '生成·校验·执行闭环', state: 'pending' },
  { key: 'merge', label: '多子图归并', state: 'pending' },
  { key: 'summary', label: '结果语义总结', state: 'pending' },
]

interface Props {
  stages: LiveStageItem[]
  running: boolean
  liveMessage: string
  elapsedSec: number
}

export const LiveStageStepper: React.FC<Props> = ({ stages, running, liveMessage, elapsedSec }) => {
  const activeStage = stages.find((s) => s.state === 'running')

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2 text-xs">
          {running ? (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-indigo-50 border border-indigo-200 text-indigo-700 font-semibold">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              当前阶段：{activeStage ? activeStage.label : '初始化中'}
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-700 font-semibold">
              <CheckCircle2 className="w-3.5 h-3.5" />
              执行流程已完成
            </span>
          )}
          {liveMessage && (
            <span className="text-slate-600 truncate max-w-2xl">{liveMessage}</span>
          )}
        </div>

        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-slate-100 text-slate-700 font-mono text-xs font-medium">
          <Clock className="w-3.5 h-3.5 text-slate-500" />
          已用时 {elapsedSec.toFixed(2)} s
        </span>
      </div>

      {/* 5-Stage Horizontal Pipeline */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2.5">
        {stages.map((st, idx) => {
          const isRunning = st.state === 'running'
          const isDone = st.state === 'ok'
          const isSkipped = st.state === 'skipped'
          const isWarn = st.state === 'warn'
          const isError = st.state === 'error'

          const cardClass = isRunning
            ? 'border-indigo-400 bg-indigo-50/70 ring-2 ring-indigo-100'
            : isDone
              ? 'border-emerald-200 bg-emerald-50/40'
              : isError
                ? 'border-rose-300 bg-rose-50/60'
                : isWarn
                  ? 'border-amber-300 bg-amber-50/50'
                  : isSkipped
                    ? 'border-slate-200 bg-slate-50/60 opacity-75'
                    : 'border-slate-200 bg-white opacity-60'

          return (
            <div key={st.key} className={`rounded-xl border p-2.5 transition ${cardClass}`}>
              <div className="flex items-center justify-between gap-1 mb-1">
                <span className="text-[10px] font-mono font-semibold text-slate-400">STEP {idx + 1}</span>
                {isRunning && <Loader2 className="w-3.5 h-3.5 text-indigo-600 animate-spin" />}
                {isDone && <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />}
                {isSkipped && <SkipForward className="w-3.5 h-3.5 text-slate-400" />}
                {isWarn && <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />}
                {isError && <XCircle className="w-3.5 h-3.5 text-rose-600" />}
                {st.state === 'pending' && <Circle className="w-3.5 h-3.5 text-slate-300" />}
              </div>
              <div className="text-xs font-semibold text-slate-800 leading-snug">{st.label}</div>
              <div className="mt-1 flex items-center justify-between text-[11px]">
                <span className="text-slate-500 truncate">
                  {isRunning
                    ? '执行中...'
                    : isSkipped
                      ? '已跳过'
                      : st.state === 'pending'
                        ? '等待中'
                        : isError
                          ? '失败'
                          : '已完成'}
                </span>
                {st.duration_s !== undefined && !isSkipped && (
                  <span className="font-mono text-slate-600 shrink-0">{st.duration_s.toFixed(2)} s</span>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
