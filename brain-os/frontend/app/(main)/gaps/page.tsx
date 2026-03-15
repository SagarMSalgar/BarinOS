'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { getGapReportLatest, runGapReportNow, getUnanswered, gapsCheckClose } from '@/lib/api';
import { useBrain } from '@/contexts/BrainContext';

type GapReport = {
  clustered_gaps?: Array<{ question: string; count?: number }>;
  priority_ranking?: Array<{ question: string; frequency?: number; priority?: string }>;
  ai_fix_suggestions?: string[];
  completeness_score?: number;
};

export default function GapsPage() {
  const { tenantId, namespace } = useBrain();
  const [report, setReport] = useState<GapReport | null>(null);
  const [unanswered, setUnanswered] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [checkingClose, setCheckingClose] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      getGapReportLatest().then((data) => setReport(data.report ?? null)),
      getUnanswered(tenantId, namespace, 50).then((d) => setUnanswered((d.questions ?? []) as string[])),
    ]).catch((e) => setError(String(e))).finally(() => setLoading(false));
  }, [tenantId, namespace]);

  useEffect(() => { load(); }, [load]);

  const runNow = async () => {
    setRunning(true);
    setError(null);
    try {
      const data = await runGapReportNow(tenantId, namespace);
      setReport(data as GapReport);
    } catch (e) {
      setError(String(e));
    } finally {
      setRunning(false);
    }
  };

  const handleCheckClose = async () => {
    setCheckingClose(true);
    setError(null);
    try {
      const res = await gapsCheckClose(tenantId, namespace, 30);
      load();
      if (res.closed > 0) setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setCheckingClose(false);
    }
  };

  const totalGaps = report?.clustered_gaps?.length ?? report?.priority_ranking?.length ?? 0;
  const highPriorityCount = report?.priority_ranking?.filter((r) => r.priority === 'High').length ?? 0;
  const alertSeverity = highPriorityCount > 0 ? 'high' : totalGaps > 0 ? 'medium' : 'none';

  return (
    <div className="h-full overflow-y-auto theme-page-bg">
      <div className="mx-auto max-w-4xl px-6 py-8">
        {/* Alert banner */}
        {!loading && (totalGaps > 0 || alertSeverity !== 'none') && (
          <div
            className={`mb-6 rounded-xl border px-4 py-3 flex items-center justify-between flex-wrap gap-2 ${
              alertSeverity === 'high'
                ? 'border-rose-200/50 bg-rose-50/80 text-rose-600'
                : 'border-amber-200/50 bg-amber-50/80 text-amber-600'
            }`}
          >
            <span className="text-sm font-medium">
              {totalGaps} unanswered question{totalGaps !== 1 ? 's' : ''} this week
              {report?.priority_ranking && report.priority_ranking.length > 0 && (
                <span> across {report.priority_ranking.length} topic{report.priority_ranking.length !== 1 ? 's' : ''}</span>
              )}
              {highPriorityCount > 0 && ' · '}
              {highPriorityCount > 0 && (
                <span className="font-semibold">{highPriorityCount} high priority</span>
              )}
            </span>
            <Link
              href="/sources"
              className="rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-white hover:opacity-90"
            >
              + Add Knowledge
            </Link>
          </div>
        )}

        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-xl font-semibold text-slate-800">Knowledge Gaps</h1>
            <p className="mt-1 text-sm text-slate-500">Clustered unanswered questions, priority, AI suggestions.</p>
          </div>
          <div className="flex items-center gap-2">
            <Link href="/sources" className="rounded-xl glass-tab-inactive px-4 py-2 text-sm text-slate-800 hover:bg-violet-50/80">
              + Add Knowledge
            </Link>
            <button type="button" onClick={runNow} disabled={running} className="rounded-xl bg-primary px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50">
              {running ? 'Running…' : 'Run report now'}
            </button>
            <button type="button" onClick={handleCheckClose} disabled={checkingClose} className="rounded-xl glass-tab-inactive px-4 py-2 text-sm font-medium text-slate-700 hover:bg-violet-50/80 disabled:opacity-50">
              {checkingClose ? 'Re-checking…' : 'Re-check gaps (auto-close if answered)'}
            </button>
          </div>
        </div>
        {error && <div className="mb-4 rounded-xl border border-rose-200/50 bg-rose-50/80 px-4 py-3 text-sm text-rose-600">{error}</div>}
        {loading ? (
          <div className="rounded-xl glass-card p-8 text-center text-slate-500">Loading…</div>
        ) : !report && unanswered.length === 0 ? (
          <div className="rounded-xl glass-card p-8 text-center text-slate-500">No gap report yet. Run the report above, or ask questions in Ask BrainOS to surface unanswered ones.</div>
        ) : (
          <div className="space-y-6">
            {unanswered.length > 0 && (
              <section className="rounded-xl glass-card p-6 shadow-glass">
                <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide">Recent unanswered questions</h2>
                <p className="mt-1 text-xs text-slate-500">Questions the brain could not answer well. Add knowledge to close these gaps.</p>
                <ul className="mt-4 space-y-2">
                  {unanswered.slice(0, 15).map((q, i) => (
                    <li key={i} className="text-sm text-slate-800">• {typeof q === 'string' ? q : (q as { question?: string })?.question ?? JSON.stringify(q)}</li>
                  ))}
                  {unanswered.length > 15 && <li className="text-slate-500 text-sm">+{unanswered.length - 15} more</li>}
                </ul>
                <Link href="/sources" className="mt-4 inline-block rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:opacity-90">+ Add Knowledge</Link>
              </section>
            )}
            {report?.priority_ranking && report.priority_ranking.length > 0 && (
              <section className="rounded-xl glass-card p-6 shadow-glass">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Priority ranking</h2>
                <ul className="mt-4 space-y-3">
                  {report.priority_ranking.map((r, i) => (
                    <li key={i} className="rounded-lg border border-violet-200/40 bg-violet-50/30 p-3">
                      <div className="flex items-center gap-2 flex-wrap">
                        {r.priority && (
                          <span className={`rounded-lg px-2 py-0.5 text-xs ${r.priority === 'High' ? 'bg-rose-50 text-rose-600' : r.priority === 'Medium' ? 'bg-amber-50 text-amber-600' : 'bg-emerald-50 text-emerald-600'}`}>{r.priority}</span>
                        )}
                        <span className="text-slate-500">×{r.frequency ?? 0}</span>
                      </div>
                      <p className="mt-1 text-sm text-slate-800">{r.question}</p>
                    </li>
                  ))}
                </ul>
              </section>
            )}
            {report?.clustered_gaps && report.clustered_gaps.length > 0 && (
              <section className="rounded-xl glass-card p-6 shadow-glass">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Unanswered questions</h2>
                <ul className="mt-4 space-y-2">
                  {report.clustered_gaps.slice(0, 20).map((g, i) => (
                    <li key={i} className="text-sm text-slate-800">• {g.question} {g.count != null && g.count > 1 && <span className="text-slate-500">({g.count}×)</span>}</li>
                  ))}
                  {report.clustered_gaps.length > 20 && <li className="text-slate-500 text-sm">+{report.clustered_gaps.length - 20} more</li>}
                </ul>
              </section>
            )}
            {report?.ai_fix_suggestions && report.ai_fix_suggestions.length > 0 && (
              <section className="rounded-xl glass-card p-6 shadow-glass">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">AI fix suggestions</h2>
                <ul className="mt-4 list-disc space-y-2 pl-5 text-sm text-slate-800">{report.ai_fix_suggestions.map((s, i) => <li key={i}>{s}</li>)}</ul>
              </section>
            )}
            {report?.completeness_score != null && (
              <section className="rounded-xl glass-card p-6 shadow-glass">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Completeness score</h2>
                <p className="mt-1 text-xs text-slate-500">Answered questions / (answered + unanswered) — run report to refresh.</p>
                <div className="mt-3 flex items-center gap-3">
                  <div className="flex-1 h-4 rounded-full bg-slate-200 overflow-hidden">
                    <div className="h-full bg-primary transition-all" style={{ width: `${report.completeness_score}%` }} />
                  </div>
                  <span className="text-lg font-semibold text-slate-800 tabular-nums">{report.completeness_score}%</span>
                </div>
              </section>
            )}
            <section className="rounded-xl glass-card p-6 shadow-glass">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Employee knowledge capture</h2>
              <p className="mt-1 text-sm text-slate-600">When someone answers a question in Slack (e.g. @Sarah), the bot can prompt to add that answer to the knowledge base. Enable in your Slack channel settings and connect Slack in Deploy.</p>
              <Link href="/deploy" className="mt-3 inline-block rounded-lg bg-primary/20 text-primary px-4 py-2 text-sm font-medium">Configure Slack &rarr;</Link>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
