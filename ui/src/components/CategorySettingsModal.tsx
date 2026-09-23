import React, { useState } from 'react';
import { CategoryRule } from '../types';

interface CategorySettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  rules?: CategoryRule[];
  onAddRule: (pattern: string, ruleType: 'process' | 'title', category: string) => Promise<void>;
  onDeleteRule: (ruleId: number, pattern: string, ruleType: 'process' | 'title') => Promise<void>;
}

export const CategorySettingsModal: React.FC<CategorySettingsModalProps> = ({
  isOpen,
  onClose,
  rules = [],
  onAddRule,
  onDeleteRule,
}) => {
  const [pattern, setPattern] = useState('');
  const [ruleType, setRuleType] = useState<'process' | 'title'>('process');
  const [category, setCategory] = useState('productive');
  const [saving, setSaving] = useState(false);

  if (!isOpen) return null;

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!pattern.trim()) return;
    setSaving(true);
    try {
      await onAddRule(pattern.trim(), ruleType, category);
      setPattern('');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
      <div className="bg-slate-900 border border-slate-800 rounded-3xl max-w-xl w-full p-6 shadow-2xl flex flex-col max-h-[85vh]">
        <div className="flex items-center justify-between pb-4 border-b border-slate-800">
          <div>
            <h2 className="text-lg font-bold text-slate-100">Application Categorization</h2>
            <p className="text-xs text-slate-400">Classify processes and window titles into productivity buckets</p>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white p-2 rounded-xl hover:bg-slate-800 transition"
          >
            ?
          </button>
        </div>

        {/* Add New Rule Form */}
        <form onSubmit={handleAdd} className="mt-4 p-4 bg-slate-950/60 rounded-2xl border border-slate-800/80 space-y-3">
          <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider block">Add Custom Override</span>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <input
              type="text"
              placeholder="e.g. spotify.exe or YouTube"
              value={pattern}
              onChange={(e) => setPattern(e.target.value)}
              className="bg-slate-900 border border-slate-700/80 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-indigo-500"
            />
            <select
              value={ruleType}
              onChange={(e) => setRuleType(e.target.value as any)}
              className="bg-slate-900 border border-slate-700/80 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-indigo-500"
            >
              <option value="process">Process Name (.exe)</option>
              <option value="title">Window Title Keyword</option>
            </select>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="bg-slate-900 border border-slate-700/80 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-indigo-500"
            >
              <option value="productive">Productive</option>
              <option value="communication">Communication</option>
              <option value="entertainment">Entertainment</option>
              <option value="browser">Browser</option>
            </select>
          </div>
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={saving || !pattern.trim()}
              className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-xl text-xs font-semibold transition"
            >
              {saving ? 'Adding...' : 'Add Rule'}
            </button>
          </div>
        </form>

        {/* Existing Rules List */}
        <div className="mt-4 flex-1 overflow-y-auto pr-1 space-y-2">
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider block mb-1">Configured Custom Rules</span>
          {rules.length === 0 ? (
            <p className="text-xs text-slate-500 py-3 text-center">No custom override rules configured yet. Default rules are active.</p>
          ) : (
            rules.map((r) => (
              <div
                key={r.id}
                className="flex items-center justify-between p-2.5 bg-slate-950/40 border border-slate-800/80 rounded-xl text-xs"
              >
                <div className="flex items-center gap-2">
                  <span className="font-mono text-slate-200">{r.pattern}</span>
                  <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-400 font-medium">
                    {r.rule_type}
                  </span>
                  <span
                    className={`text-[10px] px-2 py-0.5 rounded font-medium ${
                      r.category === 'productive'
                        ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                        : r.category === 'communication'
                        ? 'bg-sky-500/10 text-sky-400 border border-sky-500/20'
                        : r.category === 'entertainment'
                        ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                        : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                    }`}
                  >
                    {r.category}
                  </span>
                </div>
                <button
                  onClick={() => onDeleteRule(r.id, r.pattern, r.rule_type)}
                  className="text-slate-500 hover:text-rose-400 text-xs px-2 py-1 hover:bg-slate-800 rounded transition"
                >
                  Delete
                </button>
              </div>
            ))
          )}
        </div>

        <div className="mt-4 pt-3 border-t border-slate-800 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-xl text-xs font-semibold transition"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
};
