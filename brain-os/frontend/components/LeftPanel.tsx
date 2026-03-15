'use client';

import { useState, useEffect } from 'react';
import { listDocuments, getActivityLog, ingestDocument, ingestUrl } from '@/lib/api';

type Doc = { id: string; name: string; status: string; source_type?: string; freshness_score?: number };
type Activity = { ts: string; action: string; details?: { document?: string; question?: string } };

export function LeftPanel({
  tenantId,
  namespace,
  onIngestSuccess,
}: {
  tenantId: string;
  namespace: string;
  onIngestSuccess?: () => void;
}) {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [activity, setActivity] = useState<Activity[]>([]);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [mode, setMode] = useState<'paste' | 'url'>('paste');
  const [docName, setDocName] = useState('');
  const [pasteContent, setPasteContent] = useState('');
  const [url, setUrl] = useState('');
  const [ingestStatus, setIngestStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [ingestMessage, setIngestMessage] = useState('');

  const load = () => {
    listDocuments(tenantId).then(setDocs).catch(() => setDocs([]));
    getActivityLog(tenantId, 30).then(setActivity).catch(() => setActivity([]));
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [docList, events] = await Promise.all([
          listDocuments(tenantId),
          getActivityLog(tenantId, 30),
        ]);
        if (!cancelled) {
          setDocs(docList);
          setActivity(events);
        }
      } catch (_) {
        if (!cancelled) setDocs([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    const t = setInterval(() => {
      getActivityLog(tenantId, 30).then((events) => !cancelled && setActivity(events));
    }, 5000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [tenantId]);

  const handlePasteIngest = async () => {
    const name = docName.trim() || 'Pasted document';
    const content = pasteContent.trim();
    if (!content) {
      setIngestMessage('Enter some text to ingest.');
      setIngestStatus('error');
      return;
    }
    setIngestStatus('loading');
    setIngestMessage('');
    try {
      await ingestDocument(tenantId, namespace, name, content);
      setIngestStatus('success');
      setIngestMessage('Document added to knowledge base.');
      setPasteContent('');
      setDocName('');
      load();
      onIngestSuccess?.();
    } catch (e) {
      setIngestStatus('error');
      setIngestMessage(String(e));
    }
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
        onIngestSuccess?.();
      } else {
        setIngestStatus('error');
        setIngestMessage(result.error || 'Failed');
      }
    } catch (e) {
      setIngestStatus('error');
      setIngestMessage(String(e));
    }
  };

  return (
    <aside className="flex w-[280px] shrink-0 flex-col border-r border-violet-200/40 glass-card shadow-card">
      <div className="border-b border-violet-200/40 p-3">
        <h2 className="text-sm font-semibold text-slate-800">Knowledge sources</h2>
        <p className="mt-0.5 text-xs text-slate-500">Namespace: {namespace}</p>
      </div>

      {/* Add knowledge */}
      <div className="border-b border-violet-200/40 p-3">
        <button
          type="button"
          onClick={() => setAddOpen(!addOpen)}
          className="flex w-full items-center justify-between rounded-lg bg-primary px-3 py-2 text-sm font-medium text-white hover:opacity-90"
        >
          Add knowledge
          <span className="text-xs">{addOpen ? '−' : '+'}</span>
        </button>
        {addOpen && (
          <div className="mt-3 space-y-3">
            <div className="flex gap-1 rounded-lg bg-violet-50/80 p-1">
              <button
                type="button"
                onClick={() => setMode('paste')}
                className={`flex-1 rounded px-2 py-1.5 text-xs font-medium ${mode === 'paste' ? 'glass-card text-slate-800 shadow-glass' : 'text-slate-500'}`}
              >
                Paste / upload
              </button>
              <button
                type="button"
                onClick={() => setMode('url')}
                className={`flex-1 rounded px-2 py-1.5 text-xs font-medium ${mode === 'url' ? 'glass-card text-slate-800 shadow-glass' : 'text-slate-500'}`}
              >
                Web URL
              </button>
            </div>
            {mode === 'paste' ? (
              <>
                <input
                  type="text"
                  value={docName}
                  onChange={(e) => setDocName(e.target.value)}
                  placeholder="Document name (optional)"
                  className="w-full rounded-lg border border-violet-200/40 glass-input px-3 py-2 text-sm text-slate-800 placeholder:text-slate-500"
                />
                <textarea
                  value={pasteContent}
                  onChange={(e) => setPasteContent(e.target.value)}
                  placeholder="Paste document text here..."
                  rows={4}
                  className="w-full resize-none rounded-lg border border-violet-200/40 glass-input px-3 py-2 text-sm text-slate-800 placeholder:text-slate-500"
                />
                <button
                  type="button"
                  onClick={handlePasteIngest}
                  disabled={ingestStatus === 'loading'}
                  className="w-full rounded-lg bg-primary px-3 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
                >
                  {ingestStatus === 'loading' ? 'Adding…' : 'Add to knowledge base'}
                </button>
              </>
            ) : (
              <>
                <input
                  type="url"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://example.com/page"
                  className="w-full rounded-lg border border-violet-200/40 glass-input px-3 py-2 text-sm text-slate-800 placeholder:text-slate-500"
                />
                <input
                  type="text"
                  value={docName}
                  onChange={(e) => setDocName(e.target.value)}
                  placeholder="Name (optional)"
                  className="w-full rounded-lg border border-violet-200/40 glass-input px-3 py-2 text-sm text-slate-800 placeholder:text-slate-500"
                />
                <button
                  type="button"
                  onClick={handleUrlIngest}
                  disabled={ingestStatus === 'loading'}
                  className="w-full rounded-lg bg-primary px-3 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
                >
                  {ingestStatus === 'loading' ? 'Checking & adding…' : 'Add URL (scrape)'}
                </button>
              </>
            )}
            {ingestMessage && (
              <p className={`text-xs ${ingestStatus === 'error' ? 'text-rose-600' : 'text-emerald-600'}`}>
                {ingestMessage}
              </p>
            )}
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        {loading ? (
          <p className="text-xs text-slate-500">Loading sources…</p>
        ) : docs.length === 0 ? (
          <p className="text-xs text-slate-500">No documents yet. Use “Add knowledge” above.</p>
        ) : (
          <ul className="space-y-1">
            {docs.map((d) => (
              <li key={d.id} className="rounded-lg border border-violet-200/40 bg-violet-50/50 px-2 py-1.5 text-xs">
                <span className="font-medium text-slate-800">{d.name}</span>
                <span className="ml-1 text-slate-500">({d.status})</span>
                {d.source_type === 'url' && <span className="ml-1 text-primary">URL</span>}
                {d.freshness_score != null && (
                  <span className="ml-1 text-primary">{(d.freshness_score * 100).toFixed(0)}%</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="border-t border-violet-200/40 p-2">
        <h3 className="text-xs font-semibold text-slate-800">Agent activity</h3>
        <ul className="mt-1 max-h-36 overflow-y-auto space-y-0.5 text-xs text-slate-500">
          {activity.slice(0, 10).map((e, i) => {
            const detail = e.details?.document ?? e.details?.question;
            return (
              <li key={i} className="flex gap-1">
                <span className="shrink-0 text-primary">[{typeof e.ts === 'string' ? e.ts.slice(11, 19) : ''}]</span>
                <span>{e.action}</span>
                {detail != null && detail !== '' ? (
                  <span className="truncate">→ {String(detail)}</span>
                ) : null}
              </li>
            );
          })}
        </ul>
      </div>
    </aside>
  );
}
