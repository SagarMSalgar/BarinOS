'use client';

import { useState } from 'react';

const SECTIONS = [
  {
    id: 'brain',
    title: 'Brain & retrieval',
    desc: 'LLM model, retrieval params, response style',
    fields: [
      { id: 'llm_provider', label: 'LLM provider', type: 'select', options: ['OpenAI', 'Anthropic', 'Gemini'], placeholder: 'Select provider' },
      { id: 'llm_model', label: 'Model', type: 'text', placeholder: 'e.g. gpt-4o, claude-3-5-sonnet' },
      { id: 'top_k', label: 'Retrieval top-k', type: 'number', placeholder: '5' },
      { id: 'response_style', label: 'Response style', type: 'select', options: ['Concise', 'Detailed', 'Technical'], placeholder: 'Select style' },
    ],
  },
  {
    id: 'team',
    title: 'Team & permissions',
    desc: 'Invite members, roles, per-surface access',
    fields: [
      { id: 'invite_email', label: 'Invite by email', type: 'email', placeholder: 'email@example.com' },
      { id: 'role', label: 'Default role', type: 'select', options: ['Viewer', 'Editor', 'Admin'], placeholder: 'Select role' },
    ],
  },
  {
    id: 'privacy',
    title: 'Privacy & compliance',
    desc: 'PII level, redaction mode, data residency',
    fields: [
      { id: 'pii_level', label: 'PII detection level', type: 'select', options: ['Strict', 'Standard', 'Minimal'], placeholder: 'Select level' },
      { id: 'redaction_mode', label: 'Redaction mode', type: 'select', options: ['Mask', 'Remove', 'Hash'], placeholder: 'Select mode' },
      { id: 'data_residency', label: 'Data residency', type: 'select', options: ['Default', 'EU', 'US'], placeholder: 'Region' },
    ],
  },
  {
    id: 'domain',
    title: 'Domain expert mode',
    desc: 'Training status, cost estimate, endpoint',
    fields: [
      { id: 'domain_expert_enabled', label: 'Domain expert', type: 'checkbox', placeholder: 'Enable fine-tuned model' },
      { id: 'training_status', label: 'Training status', type: 'text', placeholder: 'Not started', readOnly: true },
    ],
  },
];

export default function SettingsPage() {
  const [openSection, setOpenSection] = useState<string | null>(null);

  return (
    <div className="h-full overflow-y-auto theme-page-bg">
      <div className="mx-auto max-w-3xl px-6 py-8">
        <h1 className="text-xl font-semibold text-slate-800">Settings</h1>
        <p className="mt-1 text-sm text-slate-500">Configuration for LLM, retrieval, team, privacy, and domain expert.</p>

        <div className="mt-6 space-y-4">
          {SECTIONS.map((sec) => (
            <div key={sec.id} className="rounded-xl glass-card p-5 shadow-card">
              <button
                type="button"
                onClick={() => setOpenSection(openSection === sec.id ? null : sec.id)}
                className="w-full flex items-center justify-between text-left"
              >
                <div>
                  <h3 className="font-medium text-slate-800">{sec.title}</h3>
                  <p className="mt-0.5 text-sm text-slate-500">{sec.desc}</p>
                </div>
                <span className="text-slate-500">{openSection === sec.id ? '▼' : '▶'}</span>
              </button>
              {openSection === sec.id && (
                <div className="mt-4 pt-4 border-t border-violet-200/40 space-y-3">
                  {sec.fields.map((f) => (
                    <div key={f.id}>
                      <label className="block text-xs font-medium text-slate-500 mb-1">{f.label}</label>
                      {f.type === 'select' && 'options' in f && (
                        <select
                          className="w-full rounded-lg border border-violet-200/40 glass-input px-3 py-2 text-sm text-slate-800"
                        >
                          {(f.options || []).map((opt: string) => (
                            <option key={opt} value={opt}>{opt}</option>
                          ))}
                        </select>
                      )}
                      {f.type === 'checkbox' && (
                        <input type="checkbox" className="rounded border-violet-200/40" />
                      )}
                      {f.type !== 'select' && f.type !== 'checkbox' && (
                        <input
                          type={f.type as 'text' | 'number' | 'email'}
                          readOnly={Boolean((f as { readOnly?: boolean }).readOnly)}
                          placeholder={f.placeholder}
                          className="w-full rounded-lg border border-violet-200/40 glass-input px-3 py-2 text-sm text-slate-800 disabled:opacity-60"
                        />
                      )}
                    </div>
                  ))}
                  <button type="button" className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:opacity-90">
                    Save
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
