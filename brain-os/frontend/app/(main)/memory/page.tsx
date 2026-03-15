'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { getMemoryDashboard } from '@/lib/api';
import { useBrain } from '@/contexts/BrainContext';
import { IconMemory, IconRefresh, IconSettings, IconCode } from '@/components/Icons';

type Tab = 'episodic' | 'user' | 'outcomes';

type DashboardCopy = {
  page_title?: string;
  engine_version?: string;
  hero_title?: string;
  hero_subtitle?: string;
  tab_episodic?: string;
  tab_user?: string;
  tab_outcomes?: string;
  section_recent_interactions?: string;
  section_user_preferences?: string;
  section_success_metrics?: string;
  search_placeholder?: string;
  manual_memory_injection?: string;
};

type EpisodicItem = {
  id: string;
  event_id: string;
  title: string;
  question: string;
  facts: string[];
  importance_label: string;
  created_at_relative: string;
};

type UserPref = {
  key: string;
  label: string;
  description: string;
};

type OutcomeItem = {
  id: number;
  run_type: string;
  success: boolean;
  retrieval_method: string;
  tool_used: string;
  satisfaction_stars: number | null;
  when_relative: string;
};

type DashboardData = {
  copy: DashboardCopy;
  episodic: EpisodicItem[];
  user_preferences: UserPref[];
  outcomes: OutcomeItem[];
};

function DocumentIcon({ className = 'w-5 h-5' }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.8}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
    </svg>
  );
}

function UserIcon({ className = 'w-5 h-5' }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.8}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
    </svg>
  );
}

function ChartBarIcon({ className = 'w-5 h-5' }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.8}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
    </svg>
  );
}

function ChatBubbleIcon({ className = 'w-5 h-5' }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.8}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.86 9.86 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
    </svg>
  );
}

function ClockIcon({ className = 'w-5 h-5' }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.8}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}

function CheckIcon({ className = 'w-5 h-5' }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
    </svg>
  );
}

function XIcon({ className = 'w-5 h-5' }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
    </svg>
  );
}

function StarIcon({ className = 'w-4 h-4', filled = false }: { className?: string; filled?: boolean }) {
  return (
    <svg className={className} fill={filled ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M11.48 3.499a.562.562 0 011.04 0l2.125 5.111a.563.563 0 00.475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 00-.182.557l1.285 5.385a.562.562 0 01-.84.61l-4.725-2.885a.563.563 0 00-.586 0L6.982 20.54a.562.562 0 01-.84-.61l1.285-5.386a.562.562 0 00-.182-.557l-4.204-3.602a.563.563 0 01.321-.988l5.518-.442a.563.563 0 00.475-.345L11.48 3.5z" />
    </svg>
  );
}

const preferenceIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  coding_style: IconCode,
  communication: ChatBubbleIcon,
  timezone: ClockIcon,
};

function getPrefIcon(key: string) {
  const Icon = preferenceIcons[key.toLowerCase()] || IconCode;
  return <Icon className="w-5 h-5 text-primary shrink-0" />;
}

export default function MemoryPage() {
  const { tenantId, namespace } = useBrain();
  const [tab, setTab] = useState<Tab>('episodic');
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const d = await getMemoryDashboard(tenantId || 'default', namespace || 'main', 'default', 50, 80);
      setData(d);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [tenantId, namespace]);

  useEffect(() => {
    load();
  }, [load]);

  const copy = data?.copy ?? {};
  const episodic = data?.episodic ?? [];
  const userPrefs = data?.user_preferences ?? [];
  const outcomes = data?.outcomes ?? [];

  const filteredEpisodic = searchQuery.trim()
    ? episodic.filter(
        (m) =>
          m.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
          (m.question || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
          m.facts.some((f) => f.toLowerCase().includes(searchQuery.toLowerCase()))
      )
    : episodic;

  return (
    <div className="flex flex-col h-full overflow-hidden bg-gradient-to-br from-violet-50/90 via-white/80 to-purple-50/80">
      {/* Header — aligned to content width */}
      <header className="glass-header shrink-0">
        <div className="mx-auto max-w-5xl px-6 flex items-center justify-between gap-4 h-16">
          <div className="flex items-center gap-3 min-w-0">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary-gradient text-white shadow-glass">
              <IconMemory className="h-6 w-6" />
            </div>
            <div className="min-w-0">
              <h1 className="page-title truncate">{copy.page_title}</h1>
              <p className="text-xs text-slate-500 mt-0.5">{copy.engine_version}</p>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <input
              type="search"
              placeholder={copy.search_placeholder}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="glass-input w-64 px-3 py-2 text-sm text-slate-800 placeholder-slate-500"
            />
            <button
              type="button"
              onClick={load}
              disabled={loading}
              className="rounded-xl p-2 text-slate-600 hover:bg-white/50 hover:text-primary disabled:opacity-50 backdrop-blur-sm"
              aria-label="Refresh"
            >
              <IconRefresh className="h-5 w-5" />
            </button>
            <Link
              href="/settings"
              className="rounded-xl p-2 text-slate-600 hover:bg-white/50 hover:text-primary backdrop-blur-sm"
              aria-label="Settings"
            >
              <IconSettings className="h-5 w-5" />
            </Link>
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary/20 text-primary backdrop-blur-sm border border-white/30">
              <UserIcon className="h-5 w-5" />
            </div>
          </div>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto">
        <div className="page-container flex flex-col gap-8 pb-24">
          {/* Hero */}
          <div className="rounded-2xl bg-primary-gradient px-8 py-8 text-white shadow-glass-lg border border-white/20 backdrop-blur-sm">
            <h2 className="text-2xl font-bold tracking-tight">{copy.hero_title}</h2>
            <p className="mt-2 max-w-2xl text-sm text-white/90 leading-relaxed">
              {copy.hero_subtitle}
            </p>
          </div>

          {/* Tabs */}
          <nav className="flex flex-wrap gap-2" aria-label="Memory sections">
            {(['episodic', 'user', 'outcomes'] as const).map((id) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={`rounded-xl px-5 py-2.5 text-sm font-medium transition-all ${
                tab === id ? 'glass-tab-active' : 'glass-tab-inactive'
              }`}
            >
              {id === 'episodic' && copy.tab_episodic}
              {id === 'user' && copy.tab_user}
              {id === 'outcomes' && copy.tab_outcomes}
            </button>
          ))}
          </nav>

          {/* Content area */}
          {error && (
            <div className="glass-card rounded-xl border-red-200/50 bg-red-50/80 px-4 py-3 text-sm text-red-800" role="alert">
              {error}
            </div>
          )}

          {loading && !data ? (
            <div className="glass-card flex items-center justify-center gap-3 p-12">
              <span className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
              <span className="text-slate-500">Loading…</span>
            </div>
          ) : (
            <>
              {/* Episodic: Recent Interactions */}
              {tab === 'episodic' && (
                <section className="space-y-4">
                  <h2 className="section-title flex items-center gap-2">
                    <DocumentIcon className="h-5 w-5 text-primary shrink-0" />
                    {copy.section_recent_interactions}
                  </h2>
                  {filteredEpisodic.length === 0 ? (
                    <div className="glass-card p-8 text-center text-slate-500">
                      No interactions yet. Ask questions in Ask BrainOS; summaries and facts will appear here.
                    </div>
                  ) : (
                    <ul className="space-y-4">
                      {filteredEpisodic.map((m) => (
                        <li
                          key={m.id}
                          className="glass-card p-6"
                        >
                          <div className="flex items-start justify-between gap-4">
                            <div>
                              <p className="text-xs font-medium text-slate-500">ID: {m.event_id}</p>
                              <h3 className="mt-1 text-base font-semibold text-slate-800">{m.title}</h3>
                            </div>
                            <div className="flex shrink-0 items-center gap-2">
                              <span
                                className={`rounded-full px-3 py-1 text-xs font-medium backdrop-blur-sm ${
                                  m.importance_label === 'High Importance'
                                    ? 'bg-emerald-100/80 text-emerald-800 border border-emerald-200/50'
                                    : 'bg-primary/15 text-primary border border-primary/20'
                                }`}
                              >
                                {m.importance_label}
                              </span>
                              <span className="text-xs text-slate-500">{m.created_at_relative}</span>
                            </div>
                          </div>
                          {m.question && (
                            <p className="mt-3 text-sm text-slate-700">
                              <span className="font-medium text-slate-800">Q:</span> {m.question}
                            </p>
                          )}
                          {m.facts && m.facts.length > 0 && (
                            <div className="mt-3">
                              <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                                Key Facts Extracted:
                              </p>
                              <ul className="mt-1.5 space-y-1">
                                {m.facts.map((f, i) => (
                                  <li key={i} className="flex items-start gap-2 text-sm text-slate-700">
                                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                                    {f}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              )}

              {/* User: Preferences */}
              {tab === 'user' && (
                <section className="space-y-4">
                  <h2 className="section-title flex items-center gap-2">
                    <UserIcon className="h-5 w-5 text-primary shrink-0" />
                    {copy.section_user_preferences}
                  </h2>
                  {userPrefs.length === 0 ? (
                    <div className="glass-card p-8 text-center text-slate-500">
                      No user preferences stored yet.
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {userPrefs.map((pref) => (
                        <div
                          key={pref.key}
                          className="glass-card flex items-start gap-4 p-5"
                        >
                          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/15 text-primary border border-white/40 backdrop-blur-sm">
                            {getPrefIcon(pref.key)}
                          </div>
                          <div>
                            <h3 className="font-medium text-slate-800">{pref.label}</h3>
                            <p className="mt-1 text-sm text-slate-600">{pref.description}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </section>
              )}

              {/* Outcomes: Success Metrics */}
              {tab === 'outcomes' && (
                <section className="space-y-4">
                  <h2 className="section-title flex items-center gap-2">
                    <ChartBarIcon className="h-5 w-5 text-primary shrink-0" />
                    {copy.section_success_metrics}
                  </h2>
                  {outcomes.length === 0 ? (
                    <div className="glass-card p-8 text-center text-slate-500">
                      No outcome records yet.
                    </div>
                  ) : (
                    <div className="glass-card overflow-hidden">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-white/30 bg-white/50 backdrop-blur-sm">
                            <th className="px-4 py-3 text-left font-semibold uppercase tracking-wide text-slate-600">Type</th>
                            <th className="px-4 py-3 text-left font-semibold uppercase tracking-wide text-slate-600">Success</th>
                            <th className="px-4 py-3 text-left font-semibold uppercase tracking-wide text-slate-600">Retrieval method</th>
                            <th className="px-4 py-3 text-left font-semibold uppercase tracking-wide text-slate-600">Tool used</th>
                            <th className="px-4 py-3 text-left font-semibold uppercase tracking-wide text-slate-600">Satisfaction</th>
                            <th className="px-4 py-3 text-left font-semibold uppercase tracking-wide text-slate-600">When</th>
                          </tr>
                        </thead>
                        <tbody>
                          {outcomes.map((o) => (
                            <tr key={o.id} className="border-t border-white/20">
                              <td className="px-4 py-3 font-medium text-slate-800">{o.run_type}</td>
                              <td className="px-4 py-3">
                                {o.success ? (
                                  <span className="text-emerald-600">
                                    <CheckIcon className="h-5 w-5" />
                                  </span>
                                ) : (
                                  <span className="text-red-500">
                                    <XIcon className="h-5 w-5" />
                                  </span>
                                )}
                              </td>
                              <td className="px-4 py-3 text-slate-600">{o.retrieval_method}</td>
                              <td className="px-4 py-3">
                                <span className="inline-block rounded-full bg-primary/20 px-2.5 py-0.5 text-xs font-medium text-primary border border-primary/20">
                                  {o.tool_used}
                                </span>
                              </td>
                              <td className="px-4 py-3">
                                <span className="flex gap-0.5 text-amber-500">
                                  {[1, 2, 3, 4, 5].map((i) => (
                                    <StarIcon key={i} filled={o.satisfaction_stars != null && i <= o.satisfaction_stars} />
                                  ))}
                                </span>
                              </td>
                              <td className="px-4 py-3 text-slate-500">{o.when_relative}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </section>
              )}
            </>
          )}
        </div>
      </div>

      {/* FAB: Manual Memory injection */}
      <Link
        href="/chat"
        className="fixed bottom-8 right-8 flex items-center gap-2 rounded-xl bg-primary px-5 py-3 text-sm font-medium text-white shadow-glass border border-white/20 transition hover:opacity-95 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
      >
        <span className="text-lg leading-none">+</span>
        {copy.manual_memory_injection}
      </Link>
    </div>
  );
}
