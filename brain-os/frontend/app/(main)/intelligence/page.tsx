'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  getClaims,
  extractClaims,
  getClaimTimeline,
  getContradictions,
  detectContradictions,
  getTrustSources,
  getCrawlPriority,
  getAnswersProvedWrong,
} from '@/lib/api';
import { useBrain } from '@/contexts/BrainContext';

type Tab = 'claims' | 'contradictions' | 'trust' | 'crawl' | 'wrong';

export default function IntelligencePage() {
  const { namespace } = useBrain();
  const [tab, setTab] = useState<Tab>('claims');
  const [claims, setClaims] = useState<{ id: string; claim_text: string; document_name: string; valid_from?: string; valid_until?: string }[]>([]);
  const [contradictions, setContradictions] = useState<
    { id: number; document_name_a: string; document_name_b: string; claim_text_a: string; claim_text_b: string; summary?: string; status: string }[]
  >([]);
  const [trust, setTrust] = useState<{ document_id: string; document_name?: string; trust_score: number; citation_count: number; helpful_count: number; correction_count: number }[]>([]);
  const [crawlPriority, setCrawlPriority] = useState<{ document_id: string; document_name?: string; citation_count: number; priority_score: number }[]>([]);
  const [wrongAnswers, setWrongAnswers] = useState<{ id: number; question: string; answer_excerpt: string; marked_at?: string }[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [extracting, setExtracting] = useState(false);
  const [detecting, setDetecting] = useState(false);
  const [timelineClaimId, setTimelineClaimId] = useState<string | null>(null);
  const [timelineData, setTimelineData] = useState<{ timeline?: unknown[]; claims?: unknown[] } | null>(null);

  const loadClaims = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const d = await getClaims('default', namespace);
      setClaims(d.claims || []);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [namespace]);

  const loadContradictions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const d = await getContradictions('default', namespace);
      setContradictions(d.contradictions || []);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [namespace]);

  const loadTrust = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const d = await getTrustSources('default', namespace);
      setTrust(d.sources || []);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [namespace]);

  const loadCrawlPriority = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const d = await getCrawlPriority('default', namespace);
      setCrawlPriority(d.priority || []);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [namespace]);

  const loadWrongAnswers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const d = await getAnswersProvedWrong('default', namespace);
      setWrongAnswers(d.items || []);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [namespace]);

  useEffect(() => {
    if (tab === 'claims') loadClaims();
    else if (tab === 'contradictions') loadContradictions();
    else if (tab === 'trust') loadTrust();
    else if (tab === 'crawl') loadCrawlPriority();
    else if (tab === 'wrong') loadWrongAnswers();
  }, [tab, loadClaims, loadContradictions, loadTrust, loadCrawlPriority, loadWrongAnswers]);

  const handleExtractClaims = async () => {
    setExtracting(true);
    setError(null);
    try {
      await extractClaims('default', namespace, undefined, 100);
      await loadClaims();
    } catch (e) {
      setError(String(e));
    } finally {
      setExtracting(false);
    }
  };

  const handleDetectContradictions = async () => {
    setDetecting(true);
    setError(null);
    try {
      await detectContradictions('default', namespace, 300);
      await loadContradictions();
    } catch (e) {
      setError(String(e));
    } finally {
      setDetecting(false);
    }
  };

  const loadTimeline = async (claimId: string) => {
    setTimelineClaimId(claimId);
    try {
      const d = await getClaimTimeline('default', namespace, claimId);
      setTimelineData(d);
    } catch {
      setTimelineData(null);
    }
  };

  const tabs: { id: Tab; label: string }[] = [
    { id: 'claims', label: 'Claims' },
    { id: 'contradictions', label: 'Contradictions' },
    { id: 'trust', label: 'Trust' },
    { id: 'crawl', label: 'Crawl priority' },
    { id: 'wrong', label: 'Answers proved wrong' },
  ];

  return (
    <div className="flex flex-col h-full overflow-hidden theme-page-bg">
      <header className="shrink-0 border-b border-violet-200/40 glass-header px-6 py-6">
        <h1 className="text-2xl font-semibold tracking-tight text-slate-800">Intelligence</h1>
        <p className="mt-2 text-sm text-slate-500 max-w-2xl">
          Claims, contradictions, trust scores, crawl priority from usage, and answers that proved wrong.
        </p>
        <nav className="mt-6 flex flex-wrap gap-2" aria-label="Intelligence sections">
          {tabs.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
                tab === id ? 'glass-tab-active' : 'glass-tab-inactive'
              }`}
            >
              {label}
            </button>
          ))}
        </nav>
      </header>

      <div className="flex-1 overflow-y-auto p-6 md:p-8">
        {error && (
          <div className="mb-6 rounded-xl border border-rose-200/50 bg-rose-50/80 px-4 py-3 text-sm text-rose-600" role="alert">
            {error}
          </div>
        )}

        {tab === 'claims' && (
          <section className="space-y-6" aria-labelledby="claims-heading">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <h2 id="claims-heading" className="text-lg font-semibold text-slate-800">Claims (extracted from chunks)</h2>
              <button
                type="button"
                onClick={handleExtractClaims}
                disabled={extracting}
                className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                {extracting ? 'Extracting…' : 'Extract claims'}
              </button>
            </div>
            {loading ? (
              <p className="text-slate-500">Loading…</p>
            ) : claims.length === 0 ? (
              <p className="text-slate-500">No claims yet. Run &quot;Extract claims&quot; to derive claims from your knowledge chunks.</p>
            ) : (
              <ul className="space-y-4">
                {claims.slice(0, 100).map((c) => (
                  <li key={c.id} className="rounded-xl glass-card p-5 shadow-sm">
                    <p className="text-sm text-slate-800">{c.claim_text}</p>
                    <p className="mt-2 text-xs text-slate-500">
                      {c.document_name}
                      {c.valid_from && ` · from ${c.valid_from}`}
                      {c.valid_until && ` · until ${c.valid_until}`}
                    </p>
                    <button type="button" onClick={() => loadTimeline(c.id)} className="mt-2 text-xs text-primary hover:underline">
                      Timeline / When did this stop being true?
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {timelineClaimId && timelineData && (
              <div className="rounded-xl border border-violet-200/40 bg-violet-50/30 p-4">
                <h3 className="text-sm font-medium text-slate-800">Timeline for claim</h3>
                <pre className="mt-2 overflow-auto text-xs text-slate-500">{JSON.stringify(timelineData, null, 2)}</pre>
                <button type="button" onClick={() => { setTimelineClaimId(null); setTimelineData(null); }} className="mt-2 text-xs text-primary hover:underline">
                  Close
                </button>
              </div>
            )}
          </section>
        )}

        {tab === 'contradictions' && (
          <section className="space-y-6" aria-labelledby="contradictions-heading">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <h2 id="contradictions-heading" className="text-lg font-semibold text-slate-800">Policies that disagree</h2>
              <button
                type="button"
                onClick={handleDetectContradictions}
                disabled={detecting}
                className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                {detecting ? 'Detecting…' : 'Detect contradictions'}
              </button>
            </div>
            {loading ? (
              <p className="text-slate-500">Loading…</p>
            ) : contradictions.length === 0 ? (
              <p className="text-slate-500">No contradictions detected. Extract claims first, then run &quot;Detect contradictions&quot;.</p>
            ) : (
              <ul className="space-y-4">
                {contradictions.map((c) => (
                  <li key={c.id} className="rounded-xl border border-rose-200/30 glass-card p-5 shadow-sm">
                    <p className="text-xs font-medium text-slate-500">{c.document_name_a} vs {c.document_name_b}</p>
                    <p className="mt-1 text-sm text-slate-800">&quot;{c.claim_text_a}&quot;</p>
                    <p className="mt-1 text-sm text-slate-800">&quot;{c.claim_text_b}&quot;</p>
                    {c.summary && <p className="mt-2 text-xs text-slate-500">{c.summary}</p>}
                    <span className="mt-2 inline-block rounded bg-violet-50/80 px-2 py-0.5 text-xs text-slate-500">{c.status}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        {tab === 'trust' && (
          <section className="space-y-6" aria-labelledby="trust-heading">
            <h2 id="trust-heading" className="text-lg font-semibold text-slate-800">Source trust (evolved from citations and feedback)</h2>
            {loading ? (
              <p className="text-slate-500">Loading…</p>
            ) : trust.length === 0 ? (
              <p className="text-slate-500">No trust data yet. Ask questions and give feedback to build trust scores.</p>
            ) : (
              <div className="overflow-x-auto rounded-xl glass-card shadow-sm">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-violet-200/40 bg-violet-50/80">
                      <th className="p-4 text-left font-medium text-slate-800">Document</th>
                      <th className="p-4 text-right font-medium text-slate-800">Trust</th>
                      <th className="p-4 text-right text-slate-500">Citations</th>
                      <th className="p-4 text-right text-slate-500">Helpful</th>
                      <th className="p-4 text-right text-slate-500">Corrections</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trust.map((t) => (
                      <tr key={t.document_id} className="border-b border-violet-200/30 last:border-0">
                        <td className="p-4 text-slate-800">{t.document_name ?? t.document_id}</td>
                        <td className="p-4 text-right font-medium text-slate-800">{(t.trust_score * 100).toFixed(0)}%</td>
                        <td className="p-4 text-right text-slate-500">{t.citation_count}</td>
                        <td className="p-4 text-right text-slate-500">{t.helpful_count}</td>
                        <td className="p-4 text-right text-slate-500">{t.correction_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}

        {tab === 'crawl' && (
          <section className="space-y-6" aria-labelledby="crawl-heading">
            <h2 id="crawl-heading" className="text-lg font-semibold text-slate-800">Crawl priority (from what users ask)</h2>
            {loading ? (
              <p className="text-slate-500">Loading…</p>
            ) : crawlPriority.length === 0 ? (
              <p className="text-slate-500">No data yet. Ask questions so we can score which docs are cited most.</p>
            ) : (
              <ul className="space-y-3">
                {crawlPriority.map((p) => (
                  <li key={p.document_id} className="flex items-center justify-between rounded-xl glass-card px-5 py-4 shadow-sm">
                    <span className="text-sm text-slate-800">{p.document_name || p.document_id}</span>
                    <span className="text-xs text-slate-500">Cited {p.citation_count} · priority {p.priority_score}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        {tab === 'wrong' && (
          <section className="space-y-6" aria-labelledby="wrong-heading">
            <h2 id="wrong-heading" className="text-lg font-semibold text-slate-800">Answers that proved wrong</h2>
            {loading ? (
              <p className="text-slate-500">Loading…</p>
            ) : wrongAnswers.length === 0 ? (
              <p className="text-slate-500">None. When users mark an answer as not helpful we record it here for down-ranking.</p>
            ) : (
              <ul className="space-y-4">
                {wrongAnswers.map((w) => (
                  <li key={w.id} className="rounded-xl glass-card p-5 shadow-sm">
                    <p className="text-sm font-medium text-slate-800">{w.question}</p>
                    <p className="mt-1 text-xs text-slate-500">{w.answer_excerpt}</p>
                    {w.marked_at && <p className="mt-2 text-xs text-slate-500">Marked {w.marked_at}</p>}
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}
      </div>
    </div>
  );
}
