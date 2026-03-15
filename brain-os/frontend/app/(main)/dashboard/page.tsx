'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { getStats, getSourceHealth } from '@/lib/api';
import { useBrain } from '@/contexts/BrainContext';

const quickLinks = [
  { href: '/chat', label: 'Ask BrainOS', icon: '💬', desc: 'Chat with your knowledge base' },
  { href: '/sources', label: 'Knowledge Sources', icon: '🗂️', desc: 'Add and manage documents' },
  { href: '/gaps', label: 'Knowledge Gaps', icon: '🔍', desc: 'Unanswered questions report' },
  { href: '/freshness', label: 'Freshness', icon: '🔄', desc: 'Source freshness & watchdog' },
  { href: '/compliance', label: 'Compliance', icon: '🛡️', desc: 'PII scan & audit' },
  { href: '/health', label: 'Health Monitor', icon: '📊', desc: 'Agents & activity log' },
  { href: '/export', label: 'Export Studio', icon: '🧪', desc: 'Export data & compliance gate' },
  { href: '/deploy', label: 'Deploy', icon: '🚀', desc: 'Widget, Slack, API channels' },
  { href: '/settings', label: 'Settings', icon: '⚙️', desc: 'LLM, team, privacy' },
];

function TrendArrow({ current, previous }: { current: number; previous?: number | null }) {
  if (previous == null || previous === current) return <span className="text-slate-400 ml-1" aria-hidden>→</span>;
  if (current > previous) return <span className="text-emerald-500 ml-1" aria-hidden title="Up vs last fetch">↑</span>;
  return <span className="text-amber-500 ml-1" aria-hidden title="Down vs last fetch">↓</span>;
}

export default function DashboardPage() {
  const { tenantId, namespace } = useBrain();
  const [stats, setStats] = useState<{
    total_chunks?: number;
    average_freshness?: number;
    queries_answered_this_month?: number;
    knowledge_gaps_count?: number;
    previous_total_chunks?: number;
    previous_average_freshness?: number;
    previous_queries_answered_this_month?: number;
    previous_knowledge_gaps_count?: number;
  } | null>(null);
  const [sourceHealth, setSourceHealth] = useState<{ healthy: number; stale: number; need_review: number; expired?: number; needs_review_lifecycle?: number } | null>(null);

  const load = useCallback(() => {
    getStats(tenantId, namespace).then(setStats).catch(() => setStats(null));
    getSourceHealth(tenantId, namespace).then((d) => setSourceHealth(d)).catch(() => setSourceHealth(null));
  }, [tenantId, namespace]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const interval = setInterval(load, 60_000);
    return () => clearInterval(interval);
  }, [load]);

  return (
    <div className="h-full overflow-y-auto bg-gradient-to-br from-violet-50/90 via-white/80 to-purple-50/80">
      <div className="page-container">
        <h1 className="page-title">Dashboard</h1>
        <p className="page-subtitle">
          Your company&apos;s knowledge, one brain. Ask anywhere, cite everything, stay compliant.
        </p>
        <p className="text-xs text-slate-500 mt-0.5">Auto-refreshes every 60s. Click any number to open the relevant tab.</p>

        {/* Stats row — every card links to the tab that produced that number */}
        <div className="mt-8 grid grid-cols-2 sm:grid-cols-4 gap-4">
          <Link href="/sources?from=dashboard" className="glass-card p-5 hover:bg-white/80 block transition-colors">
            <p className="section-title">Total chunks</p>
            <p className="mt-2 text-2xl font-semibold text-slate-800 tabular-nums inline-flex items-baseline">
              {stats?.total_chunks ?? '—'}
              <TrendArrow current={stats?.total_chunks ?? 0} previous={stats?.previous_total_chunks} />
            </p>
          </Link>
          <Link href="/freshness?from=dashboard" className="glass-card p-5 hover:bg-white/80 block transition-colors">
            <p className="section-title">Avg freshness</p>
            <p className={`mt-2 text-2xl font-semibold tabular-nums inline-flex items-baseline ${(stats?.average_freshness ?? 0) >= 80 ? 'text-emerald-600' : (stats?.average_freshness ?? 0) >= 60 ? 'text-amber-600' : 'text-slate-800'}`}>
              {stats?.average_freshness != null ? `${stats.average_freshness}%` : '—'}
              <TrendArrow current={stats?.average_freshness ?? 0} previous={stats?.previous_average_freshness} />
            </p>
          </Link>
          <Link href="/chat?from=dashboard" className="glass-card p-5 hover:bg-white/80 block transition-colors">
            <p className="section-title">Queries this month</p>
            <p className="mt-2 text-2xl font-semibold text-slate-800 tabular-nums inline-flex items-baseline">
              {stats?.queries_answered_this_month ?? '—'}
              <TrendArrow current={stats?.queries_answered_this_month ?? 0} previous={stats?.previous_queries_answered_this_month} />
            </p>
          </Link>
          <Link href="/gaps?from=dashboard" className="glass-card p-5 hover:bg-white/80 block transition-colors">
            <p className="section-title">Knowledge gaps</p>
            <p className="mt-2 text-2xl font-semibold text-slate-800 tabular-nums inline-flex items-baseline">
              {stats?.knowledge_gaps_count ?? '—'}
              <TrendArrow current={stats?.knowledge_gaps_count ?? 0} previous={stats?.previous_knowledge_gaps_count} />
            </p>
            <p className="text-xs text-primary mt-0.5 font-medium">View →</p>
          </Link>
        </div>

        {/* Source health */}
        {sourceHealth && (sourceHealth.healthy > 0 || sourceHealth.stale > 0 || sourceHealth.need_review > 0 || (sourceHealth.expired ?? 0) > 0 || (sourceHealth.needs_review_lifecycle ?? 0) > 0) && (
          <div className="section-spacing glass-card p-5">
            <h2 className="section-title">Source health</h2>
            <p className="mt-1 text-sm text-slate-600">Knowledge base document status. Re-sync stale sources from Knowledge Sources.</p>
            <div className="mt-4 flex flex-wrap gap-4">
              <span className="inline-flex items-center gap-1.5 text-emerald-600">
                <span className="font-semibold">{sourceHealth.healthy}</span> healthy
              </span>
              <span className="inline-flex items-center gap-1.5 text-amber-600">
                <span className="font-semibold">{sourceHealth.stale}</span> stale
              </span>
              <span className="inline-flex items-center gap-1.5 text-red-600">
                <span className="font-semibold">{sourceHealth.need_review}</span> need review
              </span>
              {(sourceHealth.expired ?? 0) > 0 && (
                <span className="inline-flex items-center gap-1.5 text-red-600">
                  <span className="font-semibold">{sourceHealth.expired}</span> expired
                </span>
              )}
              {(sourceHealth.needs_review_lifecycle ?? 0) > 0 && (
                <span className="inline-flex items-center gap-1.5 text-amber-600">
                  <span className="font-semibold">{sourceHealth.needs_review_lifecycle}</span> need review (date)
                </span>
              )}
            </div>
            <Link href="/sources" className="mt-3 inline-block text-sm font-medium text-primary hover:underline">Manage sources →</Link>
          </div>
        )}

        {/* Compliance card */}
        <Link href="/compliance" className="section-spacing flex glass-card p-5 hover:bg-white/80 transition-colors items-center gap-4">
          <span className="text-2xl shrink-0" aria-hidden>🛡️</span>
          <div className="min-w-0">
            <p className="font-medium text-slate-800">Compliance &amp; audit</p>
            <p className="text-sm text-slate-600 mt-0.5">PII scan, scraping verdict, export compliance gate, audit log.</p>
          </div>
        </Link>

        {/* Quick links */}
        <section className="section-spacing">
          <h2 className="section-title">Quick links</h2>
          <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {quickLinks.map(({ href, label, icon, desc }) => (
              <Link
                key={href}
                href={href}
                className="glass-card p-5 hover:bg-white/80 transition-colors flex items-start gap-4"
              >
                <span className="text-2xl shrink-0" aria-hidden>{icon}</span>
                <div className="min-w-0">
                  <p className="font-medium text-slate-800">{label}</p>
                  <p className="text-sm text-slate-600 mt-0.5">{desc}</p>
                </div>
              </Link>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
