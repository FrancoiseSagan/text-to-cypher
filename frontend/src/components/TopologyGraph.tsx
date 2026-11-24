import React, { useEffect, useRef, useState } from 'react'
import cytoscape, { Core } from 'cytoscape'
import { Maximize2, RefreshCw, Info } from 'lucide-react'
import type { TopologyData, TopologyEdge, TopologyNode } from '../types'

const CATEGORY_COLORS: Record<string, string> = {
  微服务: '#4f46e5',
  类: '#0284c7',
  方法: '#059669',
  上游API: '#d97706',
  下游API: '#ea580c',
  消息交换机: '#9333ea',
  消息队列: '#db2777',
  配置: '#64748b',
}

interface Props {
  topology: TopologyData
}

export const TopologyGraph: React.FC<Props> = ({ topology }) => {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const cyRef = useRef<Core | null>(null)
  const [layoutName, setLayoutName] = useState<'cose' | 'breadthfirst' | 'circle'>('cose')
  const [selected, setSelected] = useState<{ kind: 'node' | 'edge'; data: TopologyNode | TopologyEdge } | null>(null)

  useEffect(() => {
    if (!containerRef.current) return
    if (cyRef.current) {
      cyRef.current.destroy()
      cyRef.current = null
    }
    setSelected(null)
    if (topology.nodes.length === 0) return

    const elements = [
      ...topology.nodes.map((n) => ({
        data: {
          id: n.id,
          label: n.label.length > 28 ? n.label.slice(0, 26) + '…' : n.label,
          fullLabel: n.label,
          category: n.category,
          color: CATEGORY_COLORS[n.category] || '#475569',
          raw: n,
        },
      })),
      ...topology.edges.map((e) => ({
        data: {
          id: e.id,
          source: e.source,
          target: e.target,
          label: e.label,
          mechanism: e.mechanism,
          raw: e,
        },
      })),
    ]

    const cy = cytoscape({
      container: containerRef.current,
      elements,
      style: [
        {
          selector: 'node',
          style: {
            'background-color': 'data(color)',
            label: 'data(label)',
            color: '#0f172a',
            'font-size': '11px',
            'font-weight': 600,
            'text-valign': 'bottom',
            'text-halign': 'center',
            'text-margin-y': 5,
            'text-background-color': '#ffffff',
            'text-background-opacity': 0.85,
            'text-background-padding': '2px',
            width: 34,
            height: 34,
            'border-width': 2,
            'border-color': '#ffffff',
          },
        },
        {
          selector: 'node[category = "微服务"]',
          style: {
            shape: 'round-rectangle',
            width: 44,
            height: 32,
          },
        },
        {
          selector: 'node[category = "消息队列"], node[category = "消息交换机"]',
          style: {
            shape: 'diamond',
            width: 38,
            height: 38,
          },
        },
        {
          selector: 'node:selected',
          style: {
            'border-width': 3,
            'border-color': '#0f172a',
          },
        },
        {
          selector: 'edge',
          style: {
            width: 2,
            'line-color': '#94a3b8',
            'target-arrow-color': '#94a3b8',
            'target-arrow-shape': 'triangle',
            'curve-style': 'bezier',
            label: 'data(label)',
            'font-size': '10px',
            color: '#475569',
            'text-background-color': '#f8fafc',
            'text-background-opacity': 0.9,
            'text-background-padding': '2px',
            'text-rotation': 'autorotate',
          },
        },
        {
          selector: 'edge[mechanism = "RPC"]',
          style: {
            'line-color': '#ea580c',
            'target-arrow-color': '#ea580c',
            width: 2.5,
          },
        },
        {
          selector: 'edge[mechanism = "MQ"]',
          style: {
            'line-color': '#9333ea',
            'target-arrow-color': '#9333ea',
            'line-style': 'dashed',
            width: 2.8,
          },
        },
      ],
      layout: {
        name: layoutName,
        animate: false,
        padding: 32,
        ...(layoutName === 'breadthfirst' ? { directed: true, spacingFactor: 1.35 } : {}),
        ...(layoutName === 'cose' ? { idealEdgeLength: 110, nodeRepulsion: 6000 } : {}),
      } as cytoscape.LayoutOptions,
    })

    cy.on('tap', 'node', (evt) => {
      setSelected({ kind: 'node', data: evt.target.data('raw') })
    })
    cy.on('tap', 'edge', (evt) => {
      setSelected({ kind: 'edge', data: evt.target.data('raw') })
    })
    cy.on('tap', (evt) => {
      if (evt.target === cy) setSelected(null)
    })

    cyRef.current = cy
    return () => {
      cy.destroy()
      cyRef.current = null
    }
  }, [topology, layoutName])

  const presentCategories = Array.from(new Set(topology.nodes.map((n) => n.category)))

  if (topology.nodes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-80 rounded-xl border border-dashed border-slate-300 bg-slate-50/70 text-slate-500 text-sm">
        <Info className="w-6 h-6 mb-2 text-slate-400" />
        当前查询结果以标量统计为主，未包含可绘制的图拓扑节点。
      </div>
    )
  }

  return (
    <div className="relative rounded-xl border border-slate-200 bg-white overflow-hidden">
      {/* Toolbar & Legend */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 border-b border-slate-100 bg-slate-50/80">
        <div className="flex flex-wrap items-center gap-3 text-xs">
          {presentCategories.map((cat) => (
            <span key={cat} className="inline-flex items-center gap-1.5 text-slate-700 font-medium">
              <span
                className="w-2.5 h-2.5 rounded-full"
                style={{ backgroundColor: CATEGORY_COLORS[cat] || '#475569' }}
              />
              {cat}
            </span>
          ))}
          <span className="text-slate-300">|</span>
          <span className="inline-flex items-center gap-1 text-orange-600 font-medium">
            <span className="w-4 h-0.5 bg-orange-600 inline-block" /> RPC
          </span>
          <span className="inline-flex items-center gap-1 text-purple-600 font-medium">
            <span className="w-4 border-t-2 border-dashed border-purple-600 inline-block" /> MQ
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          {(['cose', 'breadthfirst', 'circle'] as const).map((l) => (
            <button
              key={l}
              onClick={() => setLayoutName(l)}
              className={`px-2 py-1 rounded text-xs font-medium transition ${
                layoutName === l
                  ? 'bg-indigo-600 text-white'
                  : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-100'
              }`}
            >
              {l === 'cose' ? '力导向' : l === 'breadthfirst' ? '层次链路' : '环形'}
            </button>
          ))}
          <button
            onClick={() => cyRef.current?.fit(undefined, 32)}
            className="p-1.5 rounded bg-white border border-slate-200 text-slate-600 hover:bg-slate-100"
            title="自适应视图"
          >
            <Maximize2 className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => cyRef.current?.layout({ name: layoutName, animate: false } as cytoscape.LayoutOptions).run()}
            className="p-1.5 rounded bg-white border border-slate-200 text-slate-600 hover:bg-slate-100"
            title="重排布局"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Canvas */}
      <div ref={containerRef} className="w-full h-[460px] bg-slate-50/30" />

      {/* Node/Edge Inspector Overlay */}
      {selected && (
        <div className="absolute right-3 bottom-3 w-80 max-h-60 overflow-y-auto rounded-lg border border-slate-200 bg-white/95 backdrop-blur shadow-lg p-3 text-xs">
          <div className="flex items-center justify-between mb-2">
            <span className="font-semibold text-slate-800">
              {selected.kind === 'node'
                ? `节点 · ${(selected.data as TopologyNode).category}`
                : `关系 · ${(selected.data as TopologyEdge).type}`}
            </span>
            <button onClick={() => setSelected(null)} className="text-slate-400 hover:text-slate-700">
              ✕
            </button>
          </div>
          <div className="font-mono text-indigo-700 break-all mb-2">{selected.data.label}</div>
          <div className="space-y-1">
            {Object.entries(selected.data.properties || {}).map(([k, v]) => (
              <div key={k} className="flex gap-2">
                <span className="text-slate-400 shrink-0">{k}:</span>
                <span className="text-slate-700 break-all">
                  {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
