import React, { useEffect, useState } from 'react'
import { Plus, Search, Trash2, Edit3, PlayCircle, CheckCircle2, XCircle, Sparkles, X } from 'lucide-react'
import { api } from '../api'
import type { DifficultyTier, KBItem, KBVerifyResponse } from '../types'

interface Props {
  onReuseQuestion: (question: string, difficulty: DifficultyTier) => void
}

const DEFAULT_CATEGORIES = [
  '单节点查询',
  '属性过滤',
  '入口 API 发现',
  '下游服务发现',
  '反向影响分析',
  'MQ 发布者与完整链路',
  'REST 与 MQ 综合依赖',
]

export const KnowledgeBaseManager: React.FC<Props> = ({ onReuseQuestion }) => {
  const [items, setItems] = useState<KBItem[]>([])
  const [categories, setCategories] = useState<{ category: string; count: number }[]>([])
  const [keyword, setKeyword] = useState('')
  const [selectedCategory, setSelectedCategory] = useState('全部')
  const [selectedComplexity, setSelectedComplexity] = useState('全部')
  const [loading, setLoading] = useState(false)

  // Modal state
  const [editing, setEditing] = useState<KBItem | null>(null)
  const [showModal, setShowModal] = useState(false)
  const [formQ, setFormQ] = useState('')
  const [formCypher, setFormCypher] = useState('')
  const [formCat, setFormCat] = useState(DEFAULT_CATEGORIES[0])
  const [formComp, setFormComp] = useState<'简单' | '中等' | '复杂'>('简单')
  const [formTags, setFormTags] = useState('')
  const [formDesc, setFormDesc] = useState('')
  const [verifyRes, setVerifyRes] = useState<KBVerifyResponse | null>(null)
  const [verifying, setVerifying] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const res = await api.listKB({
        keyword,
        category: selectedCategory,
        complexity: selectedComplexity,
      })
      setItems(res.items)
      setCategories(res.categories)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [selectedCategory, selectedComplexity])

  const openCreate = () => {
    setEditing(null)
    setFormQ('')
    setFormCypher('')
    setFormCat(DEFAULT_CATEGORIES[0])
    setFormComp('简单')
    setFormTags('')
    setFormDesc('')
    setVerifyRes(null)
    setShowModal(true)
  }

  const openEdit = (it: KBItem) => {
    setEditing(it)
    setFormQ(it.question)
    setFormCypher(it.cypher)
    setFormCat(it.category)
    setFormComp(it.complexity)
    setFormTags(it.tags.join(', '))
    setFormDesc(it.description)
    setVerifyRes(null)
    setShowModal(true)
  }

  const handleVerify = async () => {
    if (!formCypher.trim()) return
    setVerifying(true)
    try {
      const res = await api.verifyKBCypher(formCypher)
      setVerifyRes(res)
    } finally {
      setVerifying(false)
    }
  }

  const handleSave = async () => {
    if (!formQ.trim() || !formCypher.trim()) return
    const payload = {
      question: formQ.trim(),
      cypher: formCypher.trim(),
      category: formCat,
      complexity: formComp,
      tags: formTags
        .split(/[,，]/)
        .map((s) => s.trim())
        .filter(Boolean),
      description: formDesc.trim(),
    }
    if (editing) {
      await api.updateKB(editing.id, payload)
    } else {
      await api.createKB(payload)
    }
    setShowModal(false)
    await load()
  }

  const handleDelete = async (id: string) => {
    if (!confirm('确定删除该 NL-Cypher 知识库条目吗？')) return
    await api.deleteKB(id)
    await load()
  }

  return (
    <div className="space-y-4">
      {/* Header & Filters */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <div>
            <h2 className="text-base font-semibold text-slate-900">NL–Cypher 查询知识库管理（覆盖 7 类核心模式）</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              支持新增、编辑、删除、分类筛选、关键词检索、Neo4j 实库试跑校验，并作为动态 Few-Shot 支撑语义检索增强。
            </p>
          </div>
          <button
            onClick={openCreate}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-medium shadow-sm"
          >
            <Plus className="w-4 h-4" /> 新增映射示例
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <div className="relative flex-1 min-w-[220px]">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
            <input
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && load()}
              placeholder="按问题、Cypher、标签关键词检索..."
              className="w-full pl-9 pr-3 py-2 rounded-xl border border-slate-200 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <button
            onClick={load}
            className="px-3 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-xs font-medium text-slate-700"
          >
            检索
          </button>
          <select
            value={selectedComplexity}
            onChange={(e) => setSelectedComplexity(e.target.value)}
            className="px-3 py-2 rounded-xl border border-slate-200 text-xs bg-white"
          >
            <option value="全部">全部档位</option>
            <option value="简单">简单</option>
            <option value="中等">中等</option>
            <option value="复杂">复杂</option>
          </select>
        </div>

        <div className="flex flex-wrap gap-1.5 mt-3">
          <button
            onClick={() => setSelectedCategory('全部')}
            className={`px-2.5 py-1 rounded-full text-xs font-medium transition ${
              selectedCategory === '全部'
                ? 'bg-indigo-600 text-white'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            全部 ({categories.reduce((a, b) => a + b.count, 0)})
          </button>
          {categories.map((c) => (
            <button
              key={c.category}
              onClick={() => setSelectedCategory(c.category)}
              className={`px-2.5 py-1 rounded-full text-xs font-medium transition ${
                selectedCategory === c.category
                  ? 'bg-indigo-600 text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {c.category} ({c.count})
            </button>
          ))}
        </div>
      </div>

      {/* Items List */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3.5">
        {loading && <div className="text-xs text-slate-500 col-span-2 py-8 text-center">加载知识库...</div>}
        {!loading &&
          items.map((it) => (
            <div
              key={it.id}
              className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm hover:border-indigo-200 transition flex flex-col justify-between"
            >
              <div>
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div className="font-semibold text-sm text-slate-900">{it.question}</div>
                  <div className="flex items-center gap-1 shrink-0">
                    <span className="px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 text-[11px] font-medium">
                      {it.category}
                    </span>
                    <span
                      className={`px-2 py-0.5 rounded-full text-[11px] font-medium ${
                        it.complexity === '复杂'
                          ? 'bg-purple-50 text-purple-700'
                          : it.complexity === '中等'
                            ? 'bg-amber-50 text-amber-700'
                            : 'bg-emerald-50 text-emerald-700'
                      }`}
                    >
                      {it.complexity}
                    </span>
                  </div>
                </div>
                {it.description && <p className="text-xs text-slate-500 mb-2">{it.description}</p>}
                <pre className="p-2.5 rounded-lg bg-slate-900 text-slate-100 font-mono text-[11px] overflow-x-auto mb-2.5">
                  {it.cypher}
                </pre>
              </div>

              <div className="flex items-center justify-between pt-2 border-t border-slate-100 text-xs">
                <div className="flex items-center gap-1.5 flex-wrap">
                  {it.verified && (
                    <span className="inline-flex items-center gap-1 text-emerald-600 font-medium">
                      <CheckCircle2 className="w-3.5 h-3.5" /> 实库已验证
                    </span>
                  )}
                  {it.tags.slice(0, 3).map((t) => (
                    <span key={t} className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 text-[11px]">
                      #{t}
                    </span>
                  ))}
                </div>
                <div className="flex items-center gap-1.5">
                  <button
                    onClick={() => onReuseQuestion(it.question, it.complexity)}
                    className="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-indigo-50 hover:bg-indigo-100 text-indigo-700 font-medium"
                  >
                    <Sparkles className="w-3 h-3" /> 复用查询
                  </button>
                  <button
                    onClick={() => openEdit(it)}
                    className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500 hover:text-slate-800"
                    title="编辑"
                  >
                    <Edit3 className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={() => handleDelete(it.id)}
                    className="p-1.5 rounded-lg hover:bg-rose-50 text-slate-500 hover:text-rose-600"
                    title="删除"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>
          ))}
      </div>

      {/* Add / Edit Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-semibold text-slate-900">
                {editing ? '编辑 NL–Cypher 知识库示例' : '新增 NL–Cypher 知识库示例'}
              </h3>
              <button onClick={() => setShowModal(false)} className="text-slate-400 hover:text-slate-700">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="block font-medium text-slate-700 mb-1">自然语言问题</label>
                <input
                  value={formQ}
                  onChange={(e) => setFormQ(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-slate-200"
                  placeholder="例如：getAllFood 调用了哪些下游服务"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-medium text-slate-700 mb-1">查询类型</label>
                  <select
                    value={formCat}
                    onChange={(e) => setFormCat(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg border border-slate-200 bg-white"
                  >
                    {DEFAULT_CATEGORIES.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block font-medium text-slate-700 mb-1">复杂度档位</label>
                  <select
                    value={formComp}
                    onChange={(e) => setFormComp(e.target.value as '简单' | '中等' | '复杂')}
                    className="w-full px-3 py-2 rounded-lg border border-slate-200 bg-white"
                  >
                    <option value="简单">简单</option>
                    <option value="中等">中等</option>
                    <option value="复杂">复杂</option>
                  </select>
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="font-medium text-slate-700">Cypher 语句</label>
                  <button
                    onClick={handleVerify}
                    disabled={verifying}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-emerald-50 hover:bg-emerald-100 text-emerald-700 font-medium"
                  >
                    <PlayCircle className="w-3.5 h-3.5" />
                    {verifying ? '校验中...' : 'Neo4j 实库试跑校验'}
                  </button>
                </div>
                <textarea
                  value={formCypher}
                  onChange={(e) => setFormCypher(e.target.value)}
                  rows={5}
                  className="w-full px-3 py-2 rounded-lg border border-slate-200 font-mono"
                  placeholder="MATCH ..."
                />
              </div>

              {verifyRes && (
                <div
                  className={`p-3 rounded-lg border ${
                    verifyRes.valid && verifyRes.row_count > 0
                      ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                      : 'bg-amber-50 border-amber-200 text-amber-800'
                  }`}
                >
                  <div className="flex items-center gap-1.5 font-semibold mb-1.5">
                    {verifyRes.valid ? <CheckCircle2 className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
                    {verifyRes.valid
                      ? `校验通过，实库命中 ${verifyRes.row_count} 行数据`
                      : `校验失败：${verifyRes.error}`}
                  </div>
                  {verifyRes.sample_rows && verifyRes.sample_rows.length > 0 && (
                    <pre className="p-2 rounded bg-white/80 text-slate-700 font-mono text-[11px] max-h-32 overflow-auto">
                      {JSON.stringify(verifyRes.sample_rows.slice(0, 3), null, 2)}
                    </pre>
                  )}
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-medium text-slate-700 mb-1">标签（逗号分隔）</label>
                  <input
                    value={formTags}
                    onChange={(e) => setFormTags(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg border border-slate-200"
                    placeholder="MQ, 下游服务, 跨服务"
                  />
                </div>
                <div>
                  <label className="block font-medium text-slate-700 mb-1">说明</label>
                  <input
                    value={formDesc}
                    onChange={(e) => setFormDesc(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg border border-slate-200"
                    placeholder="简要说明该查询模式用途"
                  />
                </div>
              </div>
            </div>

            <div className="flex justify-end gap-2 mt-5">
              <button
                onClick={() => setShowModal(false)}
                className="px-4 py-2 rounded-lg border border-slate-200 text-xs font-medium text-slate-600 hover:bg-slate-50"
              >
                取消
              </button>
              <button
                onClick={handleSave}
                className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-medium"
              >
                保存条目
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
