'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import Link from 'next/link';
import { listDocuments, ingestDocument, ingestUrl, ingestCrawl, runFreshnessWatchdog, getStats, getIngestActive, getIngestStatus, patchDocumentLifecycle, getDocumentChanges, getDocumentChunks, getSourceConnections, connectSourceProvider } from '@/lib/api';
import { useToast } from '@/contexts/ToastContext';
import { useBrain } from '@/contexts/BrainContext';

type Doc = {
  id: string;
  name: string;
  status: string;
  source_type?: string;
  freshness_score?: number;
  lifecycle_status?: 'ok' | 'needs_review' | 'expired';
  review_by?: string | null;
  expires_at?: string | null;
  metadata?: { watchdog_schedule?: string; sync_mode?: string; namespace?: string };
};

function SourceCard({ doc, onRefresh, namespace, activeJobDocumentId }: { doc: Doc; onRefresh: () => void; namespace: string; activeJobDocumentId: string | null }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [viewChunksOpen, setViewChunksOpen] = useState(false);
  const [chunksList, setChunksList] = useState<Array<{ chunk_index?: number; content?: string; id?: string }>>([]);
  const [chunksLoading, setChunksLoading] = useState(false);
  const [editMetaOpen, setEditMetaOpen] = useState(false);
  const [changesOpen, setChangesOpen] = useState(false);
  const [changesLoading, setChangesLoading] = useState(false);
  const [changesResult, setChangesResult] = useState<{ semantic_summary?: string; message?: string; error?: string; changed?: boolean } | null>(null);
  const [reviewBy, setReviewBy] = useState(doc.review_by ?? '');
  const [expiresAt, setExpiresAt] = useState(doc.expires_at ?? '');
  const [watchdogSchedule, setWatchdogSchedule] = useState(doc.metadata?.watchdog_schedule ?? 'off');
  const [syncMode, setSyncMode] = useState(doc.metadata?.sync_mode ?? 'batch');
  const [savingLifecycle, setSavingLifecycle] = useState(false);
  const [expandedChunkId, setExpandedChunkId] = useState<string | null>(null);
  const isProcessing = activeJobDocumentId === doc.id;
  const isLive = (doc.metadata?.sync_mode ?? 'batch') === 'live';
  const isIndexed = doc.status === 'ready' && (doc.freshness_score ?? 0) >= 0.8 && !isProcessing;
  const isStale = !isProcessing && ((doc.freshness_score != null && doc.freshness_score < 0.8) || doc.lifecycle_status === 'needs_review' || doc.lifecycle_status === 'expired');
  return (
    <>
      <li className="glass-card flex items-center justify-between px-4 py-3 group">
        <div>
          <span className="font-medium text-slate-800">{doc.name}</span>
          <span className="ml-2 text-xs text-slate-500">{doc.status}</span>
          {doc.source_type === 'url' && <span className="ml-2 text-xs text-primary font-medium">URL</span>}
          {isProcessing && (
            <span className="ml-2 inline-flex items-center gap-1 text-xs font-medium text-blue-600 bg-blue-50/80 px-2 py-0.5 rounded border border-blue-200/60 animate-pulse">Processing</span>
          )}
          {isLive && !isProcessing && (
            <span className="ml-2 text-xs font-medium text-cyan-600 bg-cyan-50/80 px-2 py-0.5 rounded border border-cyan-200/60">Live</span>
          )}
          {isIndexed && (
            <span className="ml-2 text-xs font-medium text-emerald-600 bg-emerald-50/80 px-2 py-0.5 rounded border border-emerald-200/60">Indexed</span>
          )}
          {isStale && (
            <span className="ml-2 text-xs font-medium text-amber-600 bg-amber-50/80 px-2 py-0.5 rounded border border-amber-200/60">Stale</span>
          )}
          {doc.lifecycle_status === 'expired' && (
            <span className="ml-2 text-xs font-medium text-red-600 bg-red-50/80 px-1.5 py-0.5 rounded backdrop-blur-sm">Expired</span>
          )}
          {doc.lifecycle_status === 'needs_review' && !isStale && (
            <span className="ml-2 text-xs font-medium text-amber-600 bg-amber-50/80 px-1.5 py-0.5 rounded backdrop-blur-sm">Needs review</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {doc.freshness_score != null && !isProcessing && (
            <span className="rounded-full bg-primary/15 px-2 py-0.5 text-xs text-primary font-medium border border-primary/20">{(doc.freshness_score * 100).toFixed(0)}%</span>
          )}
          <div className="relative">
            <button
              type="button"
              onClick={() => setMenuOpen((o) => !o)}
              className="p-1.5 rounded-xl text-slate-500 hover:bg-white/50 hover:text-slate-800"
              aria-label="Actions"
            >
              ⋮
            </button>
            {menuOpen && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} aria-hidden="true" />
                <ul className="absolute right-0 top-full mt-1 z-20 min-w-[180px] rounded-xl glass-card-strong py-1">
                  <li>
                    <button
                      type="button"
                      onClick={async () => {
                        setMenuOpen(false);
                        setViewChunksOpen(true);
                        setChunksLoading(true);
                        setChunksList([]);
                        try {
                          const r = await getDocumentChunks(doc.id, namespace);
                          setChunksList(r.chunks || []);
                        } catch {
                          setChunksList([]);
                        } finally {
                          setChunksLoading(false);
                        }
                      }}
                      className="w-full text-left px-3 py-2 text-sm text-slate-800 hover:bg-violet-50/80"
                    >
                      View chunks
                    </button>
                  </li>
                  <li>
                    <button
                      type="button"
                      onClick={() => {
                        setReviewBy(doc.review_by ?? '');
                        setExpiresAt(doc.expires_at ?? '');
                        setWatchdogSchedule(doc.metadata?.watchdog_schedule ?? 'off');
                        setSyncMode(doc.metadata?.sync_mode ?? 'batch');
                        setEditMetaOpen(true);
                        setMenuOpen(false);
                      }}
                      className="w-full text-left px-3 py-2 text-sm text-slate-800 hover:bg-violet-50/80"
                    >
                      Edit metadata / Review by · Expires · Schedule
                    </button>
                  </li>
                  <li>
                    <button type="button" onClick={() => { setMenuOpen(false); onRefresh(); }} className="w-full text-left px-3 py-2 text-sm text-slate-800 hover:bg-violet-50/80">
                      Refresh list
                    </button>
                  </li>
                  <li>
                    <button
                      type="button"
                      onClick={async () => {
                        setMenuOpen(false);
                        setChangesOpen(true);
                        setChangesResult(null);
                        setChangesLoading(true);
                        try {
                          const r = await getDocumentChanges(doc.id);
                          setChangesResult(r);
                        } catch (e) {
                          setChangesResult({ error: String(e) });
                        } finally {
                          setChangesLoading(false);
                        }
                      }}
                      className="w-full text-left px-3 py-2 text-sm text-slate-800 hover:bg-violet-50/80"
                    >
                      What changed?
                    </button>
                  </li>
                  <li className="border-t border-violet-200/40 mt-1 pt-1">
                    <button type="button" onClick={() => setMenuOpen(false)} className="w-full text-left px-3 py-2 text-sm text-rose-600 hover:bg-rose-50/80">
                      Remove
                    </button>
                  </li>
                </ul>
              </>
            )}
          </div>
        </div>
      </li>
      {viewChunksOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" onClick={() => setViewChunksOpen(false)}>
          <div className="rounded-xl border border-violet-200/40 bg-white/90 backdrop-blur-md p-6 max-w-3xl w-full max-h-[85vh] overflow-hidden flex flex-col shadow-glass" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-semibold text-slate-800">Chunks: {doc.name}</h3>
            {chunksLoading && <p className="text-sm text-slate-500 mt-1">Loading chunks…</p>}
            {!chunksLoading && chunksList.length === 0 && <p className="text-sm text-slate-500 mt-1">No chunks found for this document.</p>}
            {!chunksLoading && chunksList.length > 0 && (
              <>
                <div className="mt-2 flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      const text = chunksList.map((c, i) => `[${c.chunk_index ?? i + 1}]\n${(c.content ?? '').trim()}`).join('\n\n');
                      navigator.clipboard.writeText(text);
                    }}
                    className="rounded-lg border border-violet-200/40 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-violet-50/80"
                  >
                    Copy all
                  </button>
                </div>
                <div className="mt-3 overflow-y-auto flex-1 min-h-0 rounded-lg border border-violet-200/40">
                  <table className="w-full text-left text-sm">
                    <thead className="sticky top-0 bg-violet-50/80 border-b border-violet-200/40">
                      <tr>
                        <th className="px-3 py-2 font-medium text-slate-500 w-12">#</th>
                        <th className="px-3 py-2 font-medium text-slate-500">Content</th>
                        <th className="px-3 py-2 font-medium text-slate-500 w-24">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {chunksList.map((c, i) => {
                        const chunkId = (c.id ?? `chunk-${i}`) as string;
                        const expanded = expandedChunkId === chunkId;
                        const content = c.content ?? '';
                        const preview = content.length <= 200 ? content : content.slice(0, 200) + '…';
                        return (
                          <tr key={chunkId} className="border-b border-violet-200/30">
                            <td className="px-3 py-2 text-slate-500">{c.chunk_index ?? i + 1}</td>
                            <td className="px-3 py-2 text-slate-800 max-w-md">
                              <div className="whitespace-pre-wrap">{expanded ? content : preview}</div>
                              {content.length > 200 && (
                                <button type="button" onClick={() => setExpandedChunkId(expanded ? null : chunkId)} className="text-xs text-primary font-medium mt-0.5">
                                  {expanded ? 'Collapse' : 'Expand'}
                                </button>
                              )}
                            </td>
                            <td className="px-3 py-2">
                              <button
                                type="button"
                                onClick={() => navigator.clipboard.writeText(content)}
                                className="text-xs text-slate-600 hover:text-primary font-medium"
                              >
                                Copy
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </>
            )}
            <p className="text-xs text-slate-500 mt-2">{chunksList.length} chunk{chunksList.length !== 1 ? 's' : ''}</p>
            <button type="button" onClick={() => setViewChunksOpen(false)} className="mt-4 rounded-lg bg-primary px-4 py-2 text-sm text-white">Close</button>
          </div>
        </div>
      )}
      {changesOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={() => { setChangesOpen(false); setChangesResult(null); }}>
          <div className="rounded-xl border border-violet-200/40 bg-white/90 backdrop-blur-md p-6 max-w-lg w-full mx-4 shadow-glass" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-semibold text-slate-800">What changed? — {doc.name}</h3>
            <p className="text-xs text-slate-500 mt-0.5">Semantic diff vs last stored content</p>
            {changesLoading && <p className="text-sm text-slate-500 mt-2">Checking…</p>}
            {!changesLoading && changesResult?.error && (
              <div className="mt-3 p-3 rounded-lg bg-red-50/80 border border-red-200/40 text-sm text-red-700">{changesResult.error}</div>
            )}
            {!changesLoading && changesResult?.message && !changesResult?.semantic_summary && (
              <p className="text-sm text-slate-600 mt-2">{changesResult.message}</p>
            )}
            {!changesLoading && changesResult?.semantic_summary && (
              <div className="mt-3 p-4 rounded-xl bg-violet-50/60 border border-violet-200/40">
                <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-2">Change log</p>
                <p className="text-sm text-slate-800 whitespace-pre-wrap">{changesResult.semantic_summary}</p>
                {changesResult.changed === true && <p className="text-xs text-emerald-600 mt-2 font-medium">Content changed; index updated.</p>}
              </div>
            )}
            <button type="button" onClick={() => { setChangesOpen(false); setChangesResult(null); }} className="mt-4 rounded-lg bg-primary px-4 py-2 text-sm text-white">Close</button>
          </div>
        </div>
      )}
      {editMetaOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={() => setEditMetaOpen(false)}>
          <div className="rounded-xl border border-violet-200/40 bg-white/90 backdrop-blur-md p-6 max-w-lg w-full mx-4 shadow-glass" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-semibold text-slate-800">Edit metadata: {doc.name}</h3>
            <div className="mt-4">
              <p className="text-xs font-medium text-slate-500 mb-1">Review by / Expires (optional)</p>
              <div className="grid grid-cols-2 gap-2">
                <input type="date" value={reviewBy.slice(0, 10)} onChange={(e) => setReviewBy(e.target.value || '')} className="rounded-lg border border-violet-200/40 px-3 py-2 text-sm glass-input" placeholder="Review by" />
                <input type="date" value={expiresAt.slice(0, 10)} onChange={(e) => setExpiresAt(e.target.value || '')} className="rounded-lg border border-violet-200/40 px-3 py-2 text-sm glass-input" placeholder="Expires" />
              </div>
              <p className="text-[10px] text-slate-500 mt-1">Answers using expired or past-review sources can be flagged.</p>
            </div>
            <div className="mt-4">
              <p className="text-xs font-medium text-slate-500 mb-1">Re-sync schedule</p>
              <select value={watchdogSchedule} onChange={(e) => setWatchdogSchedule(e.target.value)} className="rounded-lg border border-violet-200/40 px-3 py-2 text-sm glass-input w-full">
                <option value="off">Off</option>
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
              </select>
              <p className="text-[10px] text-slate-500 mt-1">When to re-fetch this source (URLs only).</p>
            </div>
            <div className="mt-3">
              <p className="text-xs font-medium text-slate-500 mb-1">Sync mode</p>
              <select value={syncMode} onChange={(e) => setSyncMode(e.target.value)} className="rounded-lg border border-violet-200/40 px-3 py-2 text-sm glass-input w-full">
                <option value="batch">Batch</option>
                <option value="live">Live</option>
              </select>
              <p className="text-[10px] text-slate-500 mt-1">Live shows a &quot;Live&quot; status pill on the source.</p>
            </div>
            <div className="mt-4 flex gap-2 justify-end">
              <button type="button" onClick={() => setEditMetaOpen(false)} className="rounded-lg border border-violet-200/40 px-4 py-2 text-sm btn-secondary">Cancel</button>
              <button
                type="button"
                disabled={savingLifecycle}
                onClick={async () => {
                  setSavingLifecycle(true);
                  try {
                    await patchDocumentLifecycle(doc.id, {
                      review_by: reviewBy.trim() || null,
                      expires_at: expiresAt.trim() || null,
                      watchdog_schedule: watchdogSchedule || null,
                      sync_mode: syncMode || null,
                    });
                    setEditMetaOpen(false);
                    onRefresh();
                  } finally {
                    setSavingLifecycle(false);
                  }
                }}
                className="rounded-lg bg-primary px-4 py-2 text-sm text-white disabled:opacity-50"
              >
                {savingLifecycle ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export default function SourcesPage() {
  const { tenantId, namespace, label } = useBrain();
  const [docs, setDocs] = useState<Doc[]>([]);
  const [stats, setStats] = useState<{ total_chunks: number; average_freshness: number; queries_answered_this_month: number; knowledge_gaps_count: number } | null>(null);
  const [activeJob, setActiveJob] = useState<{ document_id: string; phase: string; message: string; percentage: number; log?: string[] } | null>(null);
  const [logOpen, setLogOpen] = useState(false);
  const [lastCompletedLog, setLastCompletedLog] = useState<string[] | null>(null);
  const [pollingActive, setPollingActive] = useState(false);
  const pollJobIdRef = useRef<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState<'paste' | 'url' | 'crawl'>('paste');
  const [docName, setDocName] = useState('');
  const [pasteContent, setPasteContent] = useState('');
  const [url, setUrl] = useState('');
  const [seedUrl, setSeedUrl] = useState('');
  const [crawlDepth, setCrawlDepth] = useState(2);
  const [crawlPages, setCrawlPages] = useState(30);
  const [crawlGoal, setCrawlGoal] = useState('');
  const [filterSubstantive, setFilterSubstantive] = useState(true);
  const [useLlmLinks, setUseLlmLinks] = useState(true);
  const [useLlmTopic, setUseLlmTopic] = useState(true);
  const [useLlmClean, setUseLlmClean] = useState(false);
  const [ingestStatus, setIngestStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [ingestMessage, setIngestMessage] = useState('');
  const [watchdogRunning, setWatchdogRunning] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const doneToastRef = useRef<Set<string>>(new Set());
  const { addToast } = useToast();
  const [connections, setConnections] = useState<Array<{ provider: string; status: string; connected_at?: string | null }>>([]);

  const load = useCallback(() => {
    listDocuments(tenantId, namespace).then(setDocs).catch(() => setDocs([]));
    getStats(tenantId, namespace).then(setStats).catch(() => setStats(null));
    getSourceConnections(tenantId).then(setConnections).catch(() => setConnections([]));
  }, [tenantId, namespace]);

  useEffect(() => {
    load();
    setLoading(false);
  }, [load]);

  // Refetch connections when returning from OAuth callback (?connected=gmail etc.)
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const params = new URLSearchParams(window.location.search);
    const connected = params.get('connected');
    if (connected) {
      getSourceConnections(tenantId).then(setConnections).catch(() => setConnections([]));
      window.history.replaceState({}, '', window.location.pathname);
    }
  }, [tenantId]);

  // One-time check on mount: if there’s already an active job, start polling for it
  useEffect(() => {
    getIngestActive(tenantId).then((r) => {
      const jobs = r.jobs || [];
      if (jobs.length > 0) {
        pollJobIdRef.current = jobs[0].document_id;
        setPollingActive(true);
      }
    }).catch(() => {});
  }, [tenantId]);

  // Poll only while we’re tracking a job (after starting ingest or mount found a job)
  useEffect(() => {
    if (!pollingActive) return;
    const jobId = pollJobIdRef.current;
    if (!jobId) {
      setPollingActive(false);
      return;
    }
    const poll = () => {
      const id = pollJobIdRef.current;
      if (!id) return;
      getIngestStatus(id).then((s) => {
        setActiveJob({ document_id: s.document_id, phase: s.phase, message: s.message || '', percentage: s.percentage ?? 0, log: s.log });
        if (s.phase === 'done') {
          if (s.log && s.log.length) setLastCompletedLog(s.log);
          if (!doneToastRef.current.has(s.document_id)) {
            doneToastRef.current.add(s.document_id);
            addToast('success', `Indexed. ${s.current ?? 0} chunks added.`, { href: '/sources', label: 'View sources' });
          }
          pollJobIdRef.current = null;
          setPollingActive(false);
          load();
          setTimeout(() => setLastCompletedLog(null), 12000);
        } else if (s.phase === 'error') {
          addToast('error', s.message || 'Ingestion failed.');
          pollJobIdRef.current = null;
          setPollingActive(false);
          load();
        }
      }).catch(() => {});
    };
    poll();
    pollRef.current = setInterval(poll, 1000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [pollingActive, load]);

  const handlePasteIngest = async () => {
    const name = docName.trim() || 'Pasted document';
    const content = pasteContent.trim();
    if (!content) {
      setIngestMessage('Enter some text.');
      setIngestStatus('error');
      return;
    }
    setIngestStatus('loading');
    setIngestMessage('');
    try {
      const res = await ingestDocument(tenantId, namespace, name, content, false);
      if (res.document_id) {
        pollJobIdRef.current = res.document_id;
        setPollingActive(true);
        setIngestMessage('Processing in background. Watch progress above.');
        setPasteContent('');
        setDocName('');
      } else {
        await ingestDocument(tenantId, namespace, name, content, true);
        setIngestStatus('success');
        setIngestMessage('Document added.');
        setPasteContent('');
        setDocName('');
        load();
      }
    } catch (e) {
      setIngestStatus('error');
      setIngestMessage(String(e));
    }
    setIngestStatus('idle');
  };

  const handleCrawlIngest = async () => {
    const u = seedUrl.trim();
    if (!u) {
      setIngestMessage('Enter a seed URL to crawl.');
      setIngestStatus('error');
      return;
    }
    setIngestStatus('loading');
    setIngestMessage('Starting LLM-guided crawl…');
    setLogOpen(true);
    try {
      const res = await ingestCrawl({
        tenantId,
        namespace,
        seedUrl: u,
        maxDepth: crawlDepth,
        maxPages: crawlPages,
        useLlmLinks,
        useLlmTopic,
        useLlmClean,
        skipVerdict: false,
        crawlGoal: crawlGoal.trim() || undefined,
        filterSubstantive,
      });
      if (res.ok && res.crawl_job_id) {
        pollJobIdRef.current = res.crawl_job_id;
        setPollingActive(true);
        setIngestStatus('idle');
        setIngestMessage('Crawl running. Watch progress above.');
        setSeedUrl('');
      } else if (res.ok) {
        setIngestStatus('success');
        setIngestMessage(`Crawled ${res.pages} pages, created ${res.chunks_created} chunks.`);
        setSeedUrl('');
        load();
        addToast('success', `Crawl done: ${res.pages} pages, ${res.chunks_created} chunks.`, { href: '/sources', label: 'View sources' });
      } else {
        setIngestStatus('error');
        setIngestMessage(res.error || 'Crawl failed.');
      }
    } catch (e) {
      setIngestStatus('error');
      setIngestMessage(String(e));
    }
    setIngestStatus('idle');
  };

  const handleUrlIngest = async () => {
    const u = url.trim();
    if (!u) {
      setIngestMessage('Enter a URL.');
      setIngestStatus('error');
      return;
    }
    setIngestStatus('loading');
    setIngestMessage('');
    try {
      const result = await ingestUrl(tenantId, namespace, u, docName.trim() || undefined);
      if (result.ok) {
        setIngestStatus('success');
        setIngestMessage(`Added. ${result.chunks_created ?? 0} chunks indexed.`);
        setUrl('');
        setDocName('');
        load();
      } else {
        setIngestStatus('error');
        setIngestMessage(result.error || 'Failed');
      }
    } catch (e) {
      setIngestStatus('error');
      setIngestMessage(String(e));
    }
  };

  const runWatchdog = async () => {
    setWatchdogRunning(true);
    try {
      await runFreshnessWatchdog();
      load();
    } finally {
      setWatchdogRunning(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto bg-gradient-to-br from-violet-50/90 via-white/80 to-purple-50/80">
      <div className="page-container-narrow">
        <h1 className="page-title">Knowledge Sources</h1>
        <p className="page-subtitle">Adding to: <strong className="text-slate-800">{label}</strong></p>
        <p className="mt-1 text-sm text-slate-600">Drag & drop files, paste text, or add URLs. Freshness and re-sync below.</p>

        {/* Top stats row */}
        <div className="mt-8 grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div className="glass-card p-5">
            <p className="section-title">Total Chunks</p>
            <p className="mt-2 text-2xl font-semibold text-slate-800 tabular-nums">{stats?.total_chunks ?? '—'}</p>
          </div>
          <div className="glass-card p-5">
            <p className="section-title">Avg Freshness</p>
            <p className={`mt-2 text-2xl font-semibold tabular-nums ${(stats?.average_freshness ?? 0) >= 80 ? 'text-emerald-600' : (stats?.average_freshness ?? 0) >= 60 ? 'text-amber-600' : 'text-slate-800'}`}>
              {stats?.average_freshness != null ? `${stats.average_freshness}%` : '—'}
            </p>
          </div>
          <div className="glass-card p-5">
            <p className="section-title">Queries Answered</p>
            <p className="mt-2 text-2xl font-semibold text-slate-800 tabular-nums">{stats?.queries_answered_this_month ?? '—'}</p>
          </div>
          <Link href="/gaps" className="glass-card p-5 hover:bg-white/80 block transition-colors">
            <p className="section-title">Knowledge Gaps</p>
            <p className="mt-2 text-2xl font-semibold text-slate-800 tabular-nums">{stats?.knowledge_gaps_count ?? '—'}</p>
            <p className="text-xs text-primary mt-0.5 font-medium">View gaps →</p>
          </Link>
        </div>

        {/* Live ingestion card with progress bar and collapsible log */}
        {activeJob && activeJob.phase !== 'done' && activeJob.phase !== 'error' && (
          <div className="section-spacing-sm glass-card p-5 border-primary/20">
            <p className="text-sm font-medium text-slate-800">Currently ingesting</p>
            <div className="mt-2 h-2 w-full rounded-full bg-white/50 overflow-hidden">
              <div className="h-full bg-primary transition-all duration-300" style={{ width: `${activeJob.percentage}%` }} />
            </div>
            <p className="mt-2 font-mono text-xs text-slate-500">{activeJob.message}</p>
            <details className="mt-3 group" open={logOpen} onToggle={(e) => setLogOpen((e.target as HTMLDetailsElement).open)}>
              <summary className="cursor-pointer list-none flex items-center gap-2 text-sm font-medium text-slate-500 hover:text-slate-800">
                <span className="transition group-open:rotate-90">▸</span>
                Live log (reading pages, embedding chunks…)
              </summary>
              <div className="mt-2 max-h-40 overflow-y-auto rounded-lg border border-violet-200/40 bg-white/80 px-3 py-2 font-mono text-xs text-slate-500">
                {(activeJob.log && activeJob.log.length > 0) ? (
                  activeJob.log.map((line, i) => (
                    <div key={i} className="py-0.5 border-b border-violet-200/30 last:border-0">{line}</div>
                  ))
                ) : (
                  <div className="py-1 text-slate-400">Waiting for activity…</div>
                )}
              </div>
            </details>
          </div>
        )}
        {/* Last run log (shown for 12s after completion) */}
        {lastCompletedLog && lastCompletedLog.length > 0 && (
          <div className="mt-6 glass-card p-5">
            <details>
              <summary className="cursor-pointer text-sm font-medium text-slate-600 hover:text-slate-800">View last run log</summary>
              <div className="mt-2 max-h-32 overflow-y-auto rounded-lg border border-violet-200/40 bg-violet-50/50 px-3 py-2 font-mono text-xs text-slate-500">
                {lastCompletedLog.map((line, i) => (
                  <div key={i} className="py-0.5 border-b border-violet-200/30 last:border-0">{line}</div>
                ))}
              </div>
            </details>
          </div>
        )}

        {/* Add source — drop zone */}
        <div className="section-spacing-sm rounded-2xl glass-card border-2 border-dashed border-white/40 p-8 transition-colors">
          <p className="section-title mb-4">Add source</p>
          <div className="flex flex-wrap gap-2 mb-4">
            <button type="button" onClick={() => setMode('paste')} className={`rounded-xl px-4 py-2 text-sm font-medium ${mode === 'paste' ? 'glass-tab-active' : 'glass-tab-inactive'}`}>Paste / file</button>
            <button type="button" onClick={() => setMode('url')} className={`rounded-xl px-4 py-2 text-sm font-medium ${mode === 'url' ? 'glass-tab-active' : 'glass-tab-inactive'}`}>Single URL</button>
            <button type="button" onClick={() => setMode('crawl')} className={`rounded-xl px-4 py-2 text-sm font-medium ${mode === 'crawl' ? 'glass-tab-active' : 'glass-tab-inactive'}`}>Crawl (LLM)</button>
          </div>
          {mode === 'paste' && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Document name (optional)</label>
                <input type="text" value={docName} onChange={(e) => setDocName(e.target.value)} placeholder="e.g. Q3 roadmap" className="glass-input w-full px-4 py-2.5 text-sm" />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Content</label>
                <textarea value={pasteContent} onChange={(e) => setPasteContent(e.target.value)} placeholder="Paste document text or drag a file..." rows={5} className="glass-input w-full px-4 py-2.5 text-sm resize-none" />
              </div>
            </div>
          )}
          {mode === 'url' && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">URL</label>
                <input type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://example.com" className="glass-input w-full px-4 py-2.5 text-sm" />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Name (optional)</label>
                <input type="text" value={docName} onChange={(e) => setDocName(e.target.value)} placeholder="e.g. Docs homepage" className="glass-input w-full px-4 py-2.5 text-sm" />
              </div>
            </div>
          )}
          {mode === 'crawl' && (
            <div className="space-y-4">
              <p className="text-sm text-slate-600">LLM selects which links to follow (content-rich pages, skips nav/footer). Each page becomes a document with topic metadata.</p>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Seed URL</label>
                <input type="url" value={seedUrl} onChange={(e) => setSeedUrl(e.target.value)} placeholder="https://en.wikipedia.org/wiki/Knowledge_management" className="glass-input w-full px-4 py-2.5 text-sm" />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Crawl goal (optional)</label>
                <input type="text" value={crawlGoal} onChange={(e) => setCrawlGoal(e.target.value)} placeholder="e.g. Policies only, FAQ and pricing" className="glass-input w-full px-4 py-2.5 text-sm" />
              </div>
              <div className="flex flex-wrap gap-6">
                <label className="flex items-center gap-2 text-sm text-slate-700">
                  <span>Max depth:</span>
                  <select value={crawlDepth} onChange={(e) => setCrawlDepth(Number(e.target.value))} className="glass-input px-3 py-1.5 text-sm">
                    <option value={1}>1</option>
                    <option value={2}>2</option>
                    <option value={3}>3</option>
                  </select>
                </label>
                <label className="flex items-center gap-2 text-sm text-slate-700">
                  <span>Max pages:</span>
                  <select value={crawlPages} onChange={(e) => setCrawlPages(Number(e.target.value))} className="glass-input px-3 py-1.5 text-sm">
                    <option value={10}>10</option>
                    <option value={20}>20</option>
                    <option value={30}>30</option>
                    <option value={40}>40</option>
                  </select>
                </label>
              </div>
              <div className="flex flex-wrap gap-6 text-sm">
                <label className="flex items-center gap-2 text-slate-700 cursor-pointer"><input type="checkbox" checked={useLlmLinks} onChange={(e) => setUseLlmLinks(e.target.checked)} className="rounded border-primary text-primary" /> LLM link selection</label>
                <label className="flex items-center gap-2 text-slate-700 cursor-pointer"><input type="checkbox" checked={useLlmTopic} onChange={(e) => setUseLlmTopic(e.target.checked)} className="rounded border-primary text-primary" /> LLM topic per page</label>
                <label className="flex items-center gap-2 text-slate-700 cursor-pointer"><input type="checkbox" checked={useLlmClean} onChange={(e) => setUseLlmClean(e.target.checked)} className="rounded border-primary text-primary" /> LLM clean content (slower)</label>
                <label className="flex items-center gap-2 text-slate-700 cursor-pointer"><input type="checkbox" checked={filterSubstantive} onChange={(e) => setFilterSubstantive(e.target.checked)} className="rounded border-primary text-primary" /> Filter boilerplate</label>
              </div>
            </div>
          )}
          <div className="mt-6 flex items-center gap-3">
            <button type="button" onClick={mode === 'paste' ? handlePasteIngest : mode === 'url' ? handleUrlIngest : handleCrawlIngest} disabled={ingestStatus === 'loading'} className="rounded-xl bg-primary px-5 py-2.5 text-sm font-medium text-white shadow-glass border border-white/20 hover:opacity-95 disabled:opacity-50">
              {ingestStatus === 'loading' ? (mode === 'crawl' ? 'Crawling…' : 'Adding…') : mode === 'crawl' ? 'Start LLM crawl' : 'Add to knowledge base'}
            </button>
            {ingestMessage && <p className={`text-sm ${ingestStatus === 'error' ? 'text-red-600' : 'text-emerald-600'}`}>{ingestMessage}</p>}
          </div>
        </div>

        {/* Ingestion progress (inline feedback) */}
        {ingestStatus === 'loading' && (
          <div className="mt-6 glass-card p-5">
            <p className="text-sm text-slate-600">Ingestion in progress…</p>
            <div className="mt-2 h-1.5 w-full rounded-full bg-white/50 overflow-hidden">
              <div className="h-full w-2/3 bg-primary animate-pulse rounded-full" />
            </div>
          </div>
        )}

        {/* Re-sync all */}
        <div className="section-spacing-sm flex flex-wrap items-center gap-3">
          <button type="button" onClick={runWatchdog} disabled={watchdogRunning} className="rounded-xl glass-tab-inactive px-4 py-2.5 text-sm font-medium text-slate-700 disabled:opacity-50">
            {watchdogRunning ? 'Running…' : 'Re-sync all (freshness watchdog)'}
          </button>
        </div>

        {/* Connect tools (OAuth): Gmail, Slack, Google Drive */}
        <div className="section-spacing-sm rounded-2xl glass-card border border-violet-200/30 p-6">
          <h2 className="section-title mb-3">Connected tools</h2>
          <p className="text-sm text-slate-600 mb-4">Connect Gmail, Slack, or Google Drive to sync content. Sources from connected tools can show a Live status.</p>
          <div className="flex flex-wrap gap-4">
            {['gmail', 'slack', 'drive'].map((provider) => {
              const conn = connections.find((c) => c.provider === provider);
              const connected = conn?.status === 'connected';
              const label = provider === 'drive' ? 'Google Drive' : provider.charAt(0).toUpperCase() + provider.slice(1);
              return (
                <div key={provider} className="flex items-center gap-3 rounded-xl border border-violet-200/40 bg-white/60 px-4 py-3 min-w-[180px]">
                  <span className="font-medium text-slate-800">{label}</span>
                  {connected ? (
                    <span className="text-xs font-medium text-emerald-600 bg-emerald-50/80 px-2 py-1 rounded border border-emerald-200/60">Connected</span>
                  ) : (
                    <button
                      type="button"
                      onClick={async () => {
                        try {
                          const res = await connectSourceProvider(provider, tenantId);
                          if (res.configured && res.auth_url) {
                            window.open(res.auth_url, '_blank', 'noopener,noreferrer');
                            addToast('info', 'Complete sign-in in the new window.');
                          } else {
                            addToast('info', res.message || `${label} OAuth not configured.`);
                          }
                        } catch (e) {
                          addToast('error', String(e));
                        }
                      }}
                      className="rounded-lg border border-primary/40 px-3 py-1.5 text-xs font-medium text-primary hover:bg-primary/10"
                    >
                      Connect
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Source list */}
        <section className="section-spacing">
          <h2 className="section-title">Sources</h2>
          {loading ? (
            <p className="mt-3 text-sm text-slate-500">Loading…</p>
          ) : docs.length === 0 ? (
            <p className="mt-3 text-sm text-slate-500">No sources yet. Add one above.</p>
          ) : (
            <ul className="mt-4 space-y-3">
              {docs.map((d) => (
                <SourceCard key={d.id} doc={d} onRefresh={load} namespace={namespace} activeJobDocumentId={activeJob?.document_id ?? null} />
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
