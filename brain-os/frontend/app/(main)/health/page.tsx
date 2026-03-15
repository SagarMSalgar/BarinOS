'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import Link from 'next/link';
import { listDocuments, getActivityLog, getHealthScores } from '@/lib/api';
import { useBrain } from '@/contexts/BrainContext';

const HEALTH_CARDS = [
  { id: 'knowledge', label: 'Knowledge Health', key: 'knowledge_health', sub: 'Freshness + completeness + volume' },
  { id: 'freshness', label: 'Average Freshness', key: 'average_freshness', sub: 'Sources up to date' },
  { id: 'accuracy', label: 'Answer Accuracy', key: 'answer_accuracy', sub: 'From thumbs up/down feedback' },
  { id: 'pii', label: 'PII Shield', key: 'pii_shield', sub: 'Pre-ingestion scan' },
];

const AGENT_PANELS = [
  { id: 'ingestion', name: 'Ingestion Agent', status: 'Idle' },
  { id: 'query', name: 'Query Agent', status: 'Ready' },
  { id: 'freshness', name: 'Freshness Agent', status: 'Scheduled' },
  { id: 'gap', name: 'Gap Detection Agent', status: 'Weekly' },
  { id: 'quality', name: 'Quality Agent', status: 'Idle' },
  { id: 'synthesis', name: 'Synthesis Agent', status: 'On demand' },
];

function actionEmoji(action: string): string {
  const u = (action || '').toUpperCase();
  if (u.includes('READY') || u.includes('INDEXED')) return '✅';
  if (u.includes('REFRESH') || u.includes('PATCH')) return '🔄';
  if (u.includes('WATCHDOG') || u.includes('SYNC')) return '📡';
  if (u.includes('GAP')) return '📋';
  if (u.includes('INGEST') || u.includes('CHUNK')) return '📥';
  if (u.includes('ERROR') || u.includes('FAIL')) return '❌';
  return '•';
}

export default function HealthPage() {
  const { tenantId, namespace } = useBrain();
  const [scores, setScores] = useState<Record<string, number> | null>(null);
  const [activity, setActivity] = useState<Array<{ ts: string; action: string }>>([]);
  const [logPaused, setLogPaused] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadScores = useCallback(() => {
    getHealthScores(tenantId, namespace).then(setScores).catch(() => setScores(null));
  }, [tenantId, namespace]);

  useEffect(() => {
    loadScores();
  }, [loadScores]);

  useEffect(() => {
    const interval = setInterval(loadScores, 60_000);
    return () => clearInterval(interval);
  }, [loadScores]);

  useEffect(() => {
    getActivityLog(tenantId, 50).then((events) => setActivity(events as Array<{ ts: string; action: string }>)).catch(() => setActivity([]));
    if (!logPaused) {
      intervalRef.current = setInterval(() => {
        getActivityLog(tenantId, 50).then((events) => setActivity(events as Array<{ ts: string; action: string }>));
      }, 5000);
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [logPaused, tenantId]);

  return (
    <div className="h-full overflow-y-auto theme-page-bg">
      <div className="mx-auto max-w-5xl px-6 py-8">
        <h1 className="text-xl font-semibold text-slate-800">Health Monitor</h1>
        <p className="mt-1 text-sm text-slate-500">Health scores and agent status.</p>

        {/* 4 health score cards */}
        <section className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {HEALTH_CARDS.map((c) => {
            const value = scores?.[c.key];
            const display = value != null ? (typeof value === 'number' ? `${Number(value).toFixed(1)}%` : value) : '—';
            return (
              <div key={c.id} className="rounded-xl glass-card p-5 shadow-card">
                <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{c.label}</p>
                <p className="mt-1 text-xl font-semibold text-slate-800">{display}</p>
                <p className="mt-0.5 text-xs text-slate-500">{c.sub}</p>
              </div>
            );
          })}
        </section>

        {/* 6 agent status panels */}
        <section className="mt-8">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Agent status</h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {AGENT_PANELS.map((a) => (
              <div key={a.id} className="rounded-xl border border-violet-200/40 bg-emerald-50/50 p-4">
                <p className="font-medium text-slate-800">{a.name}</p>
                <p className="mt-0.5 text-xs text-primary">{a.status}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Live streaming agent log */}
        <section className="mt-8">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Agent activity log</h2>
            <button
              type="button"
              onClick={() => setLogPaused((p) => !p)}
              className={`rounded-lg px-3 py-1 text-xs font-medium ${logPaused ? 'bg-amber-50 text-amber-600' : 'bg-violet-50/80 text-slate-500'}`}
            >
              {logPaused ? 'Resume' : 'Pause'}
            </button>
          </div>
          <div className="mt-3 rounded-xl glass-card overflow-hidden">
            <ul className="max-h-64 overflow-y-auto p-3 font-mono text-xs text-slate-500 space-y-0.5">
              {activity.length === 0 && <li>No activity yet.</li>}
              {activity.slice(0, 40).map((e, i) => (
                <li key={i}>
                  <span className="mr-1">{actionEmoji(e.action)}</span>
                  [{typeof e.ts === 'string' ? e.ts.slice(11, 19) : ''}] {e.action}
                </li>
              ))}
            </ul>
          </div>
        </section>
      </div>
    </div>
  );
}
