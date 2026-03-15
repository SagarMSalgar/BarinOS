'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { listDocuments, runFreshnessWatchdog, getStats, getSourceHealth, getDocumentChangesTimeline } from '@/lib/api';
import { useBrain } from '@/contexts/BrainContext';

type Doc = { id: string; name: string; status: string; source_type?: string; freshness_score?: number };
type HealthDoc = { id: string; name: string; source_type?: string; freshness_score?: number | null; decay_rate?: number };

export default function FreshnessPage() {
  const { tenantId, namespace } = useBrain();
  const [docs, setDocs] = useState<Doc[]>([]);
  const [healthDocs, setHealthDocs] = useState<HealthDoc[]>([]);
  const [stats, setStats] = useState<{ average_freshness?: number } | null>(null);
  const [running, setRunning] = useState(false);
  const [loading, setLoading] = useState(true);
  const [timeline, setTimeline] = useState<Array<{ id: number; document_id: string; document_name: string; changed_at: string | null; semantic_summary?: string }>>([]);

  const load = useCallback(() => {
    listDocuments(tenantId, namespace).then((d) => setDocs(d as Doc[])).catch(() => setDocs([]));
    getStats(tenantId, namespace).then((s) => setStats(s)).catch(() => setStats(null));
    getSourceHealth(tenantId, namespace).then((h) => setHealthDocs((h.documents || []) as HealthDoc[])).catch(() => setHealthDocs([]));
    getDocumentChangesTimeline(tenantId, 30).then((t) => setTimeline(t.entries || [])).catch(() => setTimeline([]));
  }, [tenantId, namespace]);

  useEffect(() => {
    load();
    setLoading(false);
  }, [load]);

  const runWatchdog = async () => {
    setRunning(true);
    try {
      await runFreshnessWatchdog();
      load();
    } finally {
      setRunning(false);
    }
  };

  const decayLabel = (rate: number) => (rate >= 0.1 ? 'High' : rate >= 0.05 ? 'Medium' : 'Low');

  return (
    <div className="h-full overflow-y-auto theme-page-bg">
      <div className="mx-auto max-w-4xl px-6 py-8">
        <h1 className="text-xl font-semibold text-slate-800">Knowledge Freshness</h1>
        <p className="mt-1 text-sm text-slate-500">
          Monitor and refresh source freshness. Decay rate by source type (URL/crawl higher, file/paste lower). Run the watchdog to re-fetch URLs and re-embed changed chunks.
        </p>
        <div className="mt-6 flex flex-wrap items-center gap-4">
          <div className="rounded-xl glass-card p-4 shadow-card min-w-[160px]">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">Average freshness</p>
            <p className="mt-1 text-2xl font-semibold text-slate-800">
              {stats?.average_freshness != null ? `${stats.average_freshness}%` : '—'}
            </p>
          </div>
          <button type="button" onClick={runWatchdog} disabled={running} className="rounded-xl bg-primary px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50">
            {running ? 'Running…' : 'Run freshness watchdog'}
          </button>
          <Link href="/sources" className="rounded-xl glass-card px-4 py-2 text-sm text-slate-800 hover:bg-violet-50/80">View sources</Link>
        </div>
        <section className="mt-8">
          <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide">Sources by freshness (decay rate by type)</h2>
          {loading && <p className="mt-2 text-sm text-slate-500">Loading…</p>}
          {!loading && docs.length === 0 && <p className="mt-2 text-sm text-slate-500">No sources yet. Add documents in Knowledge Sources.</p>}
          {!loading && (healthDocs.length > 0 || docs.length > 0) && (
            <ul className="mt-3 space-y-2">
              {(healthDocs.length ? healthDocs : docs).map((d) => (
                <li key={d.id} className="flex items-center justify-between rounded-xl glass-card px-4 py-3 shadow-card">
                  <span className="font-medium text-slate-800">{d.name}</span>
                  <div className="flex items-center gap-2">
                    {(d as HealthDoc).decay_rate != null && (
                      <span className="text-xs text-slate-500" title="Decay rate">Decay: {decayLabel((d as HealthDoc).decay_rate!)}</span>
                    )}
                    {d.freshness_score != null ? (
                      <span className="rounded-full px-2 py-0.5 text-xs bg-emerald-50 text-emerald-600">{(d.freshness_score * 100).toFixed(0)}%</span>
                    ) : (
                      <span className="text-xs text-slate-500">—</span>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="mt-8">
          <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide">Change log timeline</h2>
          <p className="mt-1 text-xs text-slate-500">When URL sources were re-fetched and what changed (semantic summary).</p>
          {timeline.length === 0 && <p className="mt-2 text-sm text-slate-500">No change log entries yet. Run the watchdog on URL sources or use &quot;What changed?&quot; in Knowledge Sources.</p>}
          {timeline.length > 0 && (
            <ul className="mt-3 space-y-2">
              {timeline.map((e) => (
                <li key={e.id} className="rounded-xl border border-violet-200/40 bg-white/80 px-4 py-3 text-sm">
                  <div className="flex items-center gap-2 text-slate-500">
                    <span>{e.changed_at ? new Date(e.changed_at).toLocaleString() : '—'}</span>
                    <span className="font-medium text-slate-700">{e.document_name || e.document_id}</span>
                  </div>
                  {e.semantic_summary && <p className="mt-1 text-slate-700 whitespace-pre-wrap">{e.semantic_summary}</p>}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
