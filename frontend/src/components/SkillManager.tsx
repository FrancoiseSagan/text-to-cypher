import React, { useEffect, useState } from 'react'
import { Sparkles, Plus, Save, Trash2, Edit3, Eye, CheckCircle2, X, FileCode2 } from 'lucide-react'
import { api } from '../api'
import type { SkillInfo } from '../types'

export const SkillManager: React.FC = () => {
  const [skills, setSkills] = useState<SkillInfo[]>([])
  const [selectedName, setSelectedName] = useState<string>('')
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [savedTip, setSavedTip] = useState('')
  const [error, setError] = useState<string | null>(null)

  // Editor fields
  const [editVersion, setEditVersion] = useState('')
  const [editDesc, setEditDesc] = useState('')
  const [editTriggers, setEditTriggers] = useState('')
  const [editBody, setEditBody] = useState('')

  // Create modal state
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [newVersion, setNewVersion] = useState('1.0.0')
  const [newDesc, setNewDesc] = useState('')
  const [newTriggers, setNewTriggers] = useState('')
  const [newBody, setNewBody] = useState('# 技能规则说明\n\n- 在此处编写领域图谱查询规范与示例模板...\n')

  const load = async (focusName?: string) => {
    const res = await api.getSkills()
    setSkills(res.skills)
    const target = focusName || selectedName || res.skills[0]?.name || ''
    if (target) {
      const found = res.skills.find((s) => s.name === target) || res.skills[0]
      if (found) {
        selectSkill(found)
      }
    }
  }

  const selectSkill = (sk: SkillInfo) => {
    setSelectedName(sk.name)
    setEditVersion(sk.version)
    setEditDesc(sk.description)
    setEditTriggers(sk.triggers.join(', '))
    setEditBody(sk.body)
    setEditing(false)
    setError(null)
  }

  useEffect(() => {
    load()
  }, [])

  const current = skills.find((s) => s.name === selectedName) || null

  const handleSave = async () => {
    if (!current) return
    setSaving(true)
    setError(null)
    try {
      await api.updateSkill(current.name, {
        version: editVersion.trim() || '1.0.0',
        description: editDesc.trim(),
        triggers: editTriggers
          .split(/[,，]/)
          .map((t) => t.trim())
          .filter(Boolean),
        body: editBody,
      })
      await load(current.name)
      setEditing(false)
      setSavedTip('已保存并热加载到引擎')
      setTimeout(() => setSavedTip(''), 2200)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSaving(false)
    }
  }

  const handleCreate = async () => {
    if (!newName.trim() || !newBody.trim()) return
    setError(null)
    try {
      const created = await api.createSkill({
        name: newName.trim(),
        version: newVersion.trim() || '1.0.0',
        description: newDesc.trim(),
        triggers: newTriggers
          .split(/[,，]/)
          .map((t) => t.trim())
          .filter(Boolean),
        body: newBody,
      })
      setShowCreate(false)
      setNewName('')
      setNewDesc('')
      setNewTriggers('')
      await load(created.name)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  const handleDelete = async (name: string) => {
    if (!confirm(`确定删除技能 "${name}"（将删除对应的 SKILL.md 文件）？`)) return
    setError(null)
    try {
      await api.deleteSkill(name)
      setSelectedName('')
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
      {/* Left Sidebar: Skill List */}
      <div className="lg:col-span-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm flex flex-col">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-slate-900 flex items-center gap-1.5">
            <Sparkles className="w-4 h-4 text-purple-600" />
            领域技能列表 ({skills.length})
          </h2>
          <button
            onClick={() => setShowCreate(true)}
            className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-purple-600 hover:bg-purple-700 text-white text-xs font-medium"
          >
            <Plus className="w-3.5 h-3.5" /> 新建 Skill
          </button>
        </div>

        <div className="space-y-2 flex-1">
          {skills.map((sk) => {
            const active = sk.name === selectedName
            return (
              <button
                key={sk.name}
                onClick={() => selectSkill(sk)}
                className={`w-full text-left p-3 rounded-xl border transition ${
                  active
                    ? 'border-purple-400 bg-purple-50/70 ring-2 ring-purple-100'
                    : 'border-slate-200 bg-white hover:bg-slate-50'
                }`}
              >
                <div className="flex items-center justify-between gap-2 mb-1">
                  <span className="font-mono text-xs font-semibold text-purple-800">{sk.name}</span>
                  <div className="flex items-center gap-1">
                    {sk.is_base && (
                      <span className="px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-700 text-[10px] font-medium">
                        必选基础
                      </span>
                    )}
                    <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 font-mono text-[10px]">
                      v{sk.version}
                    </span>
                  </div>
                </div>
                <p className="text-xs text-slate-600 line-clamp-2">{sk.description || '无描述'}</p>
              </button>
            )
          })}
        </div>
      </div>

      {/* Right Pane: Viewer / Editor */}
      <div className="lg:col-span-8 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        {!current ? (
          <div className="py-20 text-center text-sm text-slate-400">请在左侧选择一个 Skill 查看或编辑</div>
        ) : (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-slate-100">
              <div>
                <div className="flex items-center gap-2">
                  <FileCode2 className="w-4 h-4 text-purple-600" />
                  <span className="font-mono text-base font-bold text-slate-900">{current.name}/SKILL.md</span>
                  <span className="px-2 py-0.5 rounded-full bg-purple-100 text-purple-700 font-mono text-xs">
                    v{current.version}
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-1">{current.description}</p>
              </div>

              <div className="flex items-center gap-2">
                {savedTip && (
                  <span className="inline-flex items-center gap-1 text-xs text-emerald-600 font-medium">
                    <CheckCircle2 className="w-3.5 h-3.5" /> {savedTip}
                  </span>
                )}
                {!editing ? (
                  <>
                    <button
                      onClick={() => setEditing(true)}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-medium"
                    >
                      <Edit3 className="w-3.5 h-3.5" /> 编辑内容
                    </button>
                    {!current.is_base && (
                      <button
                        onClick={() => handleDelete(current.name)}
                        className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-rose-200 text-rose-600 hover:bg-rose-50 text-xs font-medium"
                      >
                        <Trash2 className="w-3.5 h-3.5" /> 删除
                      </button>
                    )}
                  </>
                ) : (
                  <>
                    <button
                      onClick={() => selectSkill(current)}
                      className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 text-xs font-medium"
                    >
                      <Eye className="w-3.5 h-3.5" /> 取消
                    </button>
                    <button
                      onClick={handleSave}
                      disabled={saving}
                      className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white text-xs font-medium"
                    >
                      <Save className="w-3.5 h-3.5" /> {saving ? '保存中...' : '保存并热加载'}
                    </button>
                  </>
                )}
              </div>
            </div>

            {error && (
              <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-xs text-rose-700">{error}</div>
            )}

            {!editing ? (
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-1.5 text-xs">
                  <span className="text-slate-500">适用标签 / 触发词：</span>
                  {current.triggers.length === 0 ? (
                    <span className="text-slate-400">无</span>
                  ) : (
                    current.triggers.map((t) => (
                      <span
                        key={t}
                        className="px-2 py-0.5 rounded-full bg-purple-50 border border-purple-200 text-purple-700"
                      >
                        {t}
                      </span>
                    ))
                  )}
                </div>

                <div>
                  <div className="text-xs font-semibold text-slate-700 mb-1.5">SKILL.md 正文内容</div>
                  <pre className="p-4 rounded-xl bg-slate-900 text-slate-100 font-mono text-xs overflow-x-auto whitespace-pre-wrap leading-relaxed max-h-[540px] overflow-y-auto">
                    {current.body}
                  </pre>
                </div>
              </div>
            ) : (
              <div className="space-y-3 text-xs">
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div>
                    <label className="block font-medium text-slate-700 mb-1">版本号</label>
                    <input
                      value={editVersion}
                      onChange={(e) => setEditVersion(e.target.value)}
                      className="w-full px-3 py-2 rounded-lg border border-slate-200 font-mono"
                    />
                  </div>
                  <div className="sm:col-span-2">
                    <label className="block font-medium text-slate-700 mb-1">适用标签（逗号分隔）</label>
                    <input
                      value={editTriggers}
                      onChange={(e) => setEditTriggers(e.target.value)}
                      className="w-full px-3 py-2 rounded-lg border border-slate-200"
                    />
                  </div>
                </div>

                <div>
                  <label className="block font-medium text-slate-700 mb-1">技能描述（供大模型语义路由参考）</label>
                  <input
                    value={editDesc}
                    onChange={(e) => setEditDesc(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg border border-slate-200"
                  />
                </div>

                <div>
                  <label className="block font-medium text-slate-700 mb-1">SKILL.md Markdown 正文</label>
                  <textarea
                    value={editBody}
                    onChange={(e) => setEditBody(e.target.value)}
                    rows={16}
                    className="w-full p-3 rounded-xl border border-slate-200 font-mono text-xs leading-relaxed focus:outline-none focus:ring-2 focus:ring-purple-500"
                  />
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Create Skill Modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-semibold text-slate-900">新建领域技能 (SKILL.md)</h3>
              <button onClick={() => setShowCreate(false)} className="text-slate-400 hover:text-slate-700">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="space-y-3 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-medium text-slate-700 mb-1">技能标识（英文/数字/-/_）</label>
                  <input
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    placeholder="例如：config-audit"
                    className="w-full px-3 py-2 rounded-lg border border-slate-200 font-mono"
                  />
                </div>
                <div>
                  <label className="block font-medium text-slate-700 mb-1">版本号</label>
                  <input
                    value={newVersion}
                    onChange={(e) => setNewVersion(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg border border-slate-200 font-mono"
                  />
                </div>
              </div>
              <div>
                <label className="block font-medium text-slate-700 mb-1">技能描述</label>
                <input
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  placeholder="说明何时应由语义路由加载本技能"
                  className="w-full px-3 py-2 rounded-lg border border-slate-200"
                />
              </div>
              <div>
                <label className="block font-medium text-slate-700 mb-1">触发标签（逗号分隔）</label>
                <input
                  value={newTriggers}
                  onChange={(e) => setNewTriggers(e.target.value)}
                  placeholder="配置, 端口, 环境变量"
                  className="w-full px-3 py-2 rounded-lg border border-slate-200"
                />
              </div>
              <div>
                <label className="block font-medium text-slate-700 mb-1">Markdown 规则正文</label>
                <textarea
                  value={newBody}
                  onChange={(e) => setNewBody(e.target.value)}
                  rows={10}
                  className="w-full p-3 rounded-lg border border-slate-200 font-mono text-xs"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-5">
              <button
                onClick={() => setShowCreate(false)}
                className="px-4 py-2 rounded-lg border border-slate-200 text-xs font-medium text-slate-600"
              >
                取消
              </button>
              <button
                onClick={handleCreate}
                className="px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-700 text-white text-xs font-medium"
              >
                创建 Skill
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
