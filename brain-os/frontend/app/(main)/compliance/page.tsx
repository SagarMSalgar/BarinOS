'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import Link from 'next/link';
import { piiScan, getComplianceAudit } from '@/lib/api';
import { useBrain } from '@/contexts/BrainContext';

type PIIFinding = { type: string; span: [number, number]; action?: string };

function renderHighlightedText(text: string, findings: PIIFinding[]) {
  if (!findings.length) return text;
  const sorted = [...findings].sort((a, b) => a.span[0] - b.span[0]);
  const parts: Array<{ type: 'text' | 'pii'; start: number; end: number; label?: string }> = [];
  let last = 0;
  for (const f of sorted) {
    if (f.span[0] > last) parts.push({ type: 'text', start: last, end: f.span[0] });
    parts.push({ type: 'pii', start: f.span[0], end: f.span[1], label: f.type });
    last = Math.max(last, f.span[1]);
  }
  if (last < text.length) parts.push({ type: 'text', start: last, end: text.length });
  return parts.map((p) => {
    const s = text.slice(p.start, p.end);
    if (p.type === 'text') return s;
    return { key: `${p.start}-${p.end}`, label: p.label, text: s };
  });
}

function redactText(text: string, findings: PIIFinding[]): string {
  if (!findings.length) return text;
  const sorted = [...findings].sort((a, b) => b.span[0] - a.span[0]);
  let out = text;
  for (const f of sorted) {
    out = out.slice(0, f.span[0]) + `[REDACTED: ${f.type.toUpperCase()}]` + out.slice(f.span[1]);
  }
  return out;
}

export default function CompliancePage() {
  const { tenantId } = useBrain();
  const [text, setText] = useState('');
  const [result, setResult] = useState<{ pattern_findings?: PIIFinding[]; llm_findings?: unknown[]; total_count?: number; actions_taken?: string } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [auditEntries, setAuditEntries] = useState<Array<{ id: number; kind: string; payload: Record<string, unknown>; created_at: string | null }>>([]);
  const [auditLoading, setAuditLoading] = useState(true);
  const [auditKind, setAuditKind] = useState<string>('');
  const [auditPage, setAuditPage] = useState(0);
  const [showRedacted, setShowRedacted] = useState(false);

  const loadAudit = useCallback(() => {
    setAuditLoading(true);
    getComplianceAudit(tenantId, auditKind || undefined, 100)
      .then((data: { entries?: Array<{ id: number; kind: string; payload: Record<string, unknown>; created_at: string | null }> }) => {
        setAuditEntries(data.entries || []);
      })
      .catch(() => setAuditEntries([]))
      .finally(() => setAuditLoading(false));
  }, [tenantId, auditKind]);

  useEffect(() => {
    loadAudit();
  }, [loadAudit]);

  const runPiiScan = async () => {
    if (!text.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await piiScan(text);
      setResult(data as { pattern_findings?: PIIFinding[]; llm_findings?: unknown[]; total_count?: number; actions_taken?: string });
      loadAudit();
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  const findings = useMemo(() => {
    const p = (result?.pattern_findings || []) as PIIFinding[];
    const l = (result?.llm_findings || []) as PIIFinding[];
    return [...p, ...l];
  }, [result]);

  const summaryByType = useMemo(() => {
    const m: Record<string, number> = {};
    findings.forEach((f) => { m[f.type] = (m[f.type] || 0) + 1; });
    return m;
  }, [findings]);

  const highlighted = useMemo(() => result && text ? renderHighlightedText(text, findings) : null, [result, text, findings]);
  const redacted = useMemo(() => (result && text ? redactText(text, findings) : ''), [result, text, findings]);

  return (
    <div className="h-full overflow-y-auto theme-page-bg">
      <div className="mx-auto max-w-4xl px-6 py-8">
        <h1 className="text-xl font-semibold text-slate-800">Compliance & audit</h1>
        <p className="mt-1 text-sm text-slate-500">PII scanning, GDPR-style audit trail, and scraping compliance.</p>
        <section className="mt-6 rounded-xl glass-card p-6 shadow-card">
          <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide">PII scanner</h2>
          <p className="mt-1 text-xs text-slate-500">Paste text; regex + LLM detect emails, phones, SSNs, names, addresses. Results shown in place with labels; use Redact all to get clean text.</p>
          <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste sample text..." rows={5} className="mt-3 w-full rounded-lg border border-violet-200/40 bg-violet-50/80 px-3 py-2 text-sm text-slate-800 resize-none font-mono" />
          <div className="mt-3 flex flex-wrap gap-2 items-center">
            <button type="button" onClick={runPiiScan} disabled={loading || !text.trim()} className="rounded-xl bg-primary px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50">
              {loading ? 'Scanning…' : 'Scan'}
            </button>
            {result && findings.length > 0 && (
              <button
                type="button"
                onClick={() => {
                  setShowRedacted(true);
                  navigator.clipboard.writeText(redacted);
                }}
                className="rounded-xl border border-amber-200/60 bg-amber-50/80 px-4 py-2 text-sm font-medium text-amber-800 hover:bg-amber-100/80"
              >
                Redact all & copy
              </button>
            )}
          </div>
          {error && <p className="mt-2 text-sm text-rose-600">{error}</p>}
          {result && (
            <div className="mt-4 rounded-lg border border-violet-200/40 bg-white/80 p-4">
              <h3 className="text-xs font-semibold text-slate-500 uppercase">Summary</h3>
              <p className="mt-1 text-sm text-slate-800">
                Found {result.total_count ?? 0} PII instance{(result.total_count ?? 0) !== 1 ? 's' : ''}
                {Object.keys(summaryByType).length > 0 && ` — ${Object.entries(summaryByType).map(([k, v]) => `${v} ${k}`).join(', ')}`}.
              </p>
              <p className="mt-0.5 text-xs text-slate-500">Action: {result.actions_taken ?? 'none'}</p>
              {highlighted && (
                <div className="mt-3 p-3 rounded-lg bg-slate-50 border border-slate-200/40">
                  <p className="text-xs font-medium text-slate-500 mb-2">Highlighted text (PII in place)</p>
                  <p className="text-sm text-slate-800 whitespace-pre-wrap font-mono">
                    {Array.isArray(highlighted)
                      ? highlighted.map((part, i) =>
                          typeof part === 'string' ? (
                            part
                          ) : (
                            <mark key={part.key} className="bg-amber-200/80 text-amber-900 px-0.5 rounded" title={part.label}>
                              {part.text}
                              <span className="ml-1 text-[10px] font-semibold text-amber-700">({part.label})</span>
                            </mark>
                          )
                        )
                      : highlighted}
                  </p>
                </div>
              )}
              {showRedacted && (
                <div className="mt-3 p-3 rounded-lg bg-emerald-50/80 border border-emerald-200/40">
                  <p className="text-xs font-medium text-emerald-700 mb-2">Redacted text (copied to clipboard)</p>
                  <pre className="text-sm text-slate-800 whitespace-pre-wrap font-mono">{redacted}</pre>
                </div>
              )}
            </div>
          )}
        </section>
        <section className="mt-6 rounded-xl glass-card p-6 shadow-card">
          <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide">Audit log</h2>
          <p className="mt-1 text-sm text-slate-500">Chronological list of PII scans and URL compliance verdicts. Filter by event type.</p>
          <div className="mt-3 flex gap-2 items-center flex-wrap">
            <label className="text-sm text-slate-600">Filter:</label>
            <select value={auditKind} onChange={(e) => setAuditKind(e.target.value)} className="rounded-lg border border-violet-200/40 px-3 py-1.5 text-sm">
              <option value="">All</option>
              <option value="pii_scan">PII scan</option>
              <option value="url_verdict">URL verdict</option>
            </select>
            <button type="button" onClick={loadAudit} className="rounded-lg border border-violet-200/40 px-3 py-1.5 text-sm text-slate-700 hover:bg-violet-50/80">Refresh</button>
          </div>
          {auditLoading && <p className="mt-3 text-sm text-slate-500">Loading…</p>}
          {!auditLoading && auditEntries.length === 0 && <p className="mt-3 text-sm text-slate-500">No audit entries yet. Run a PII scan or check a URL in Sources to see entries here.</p>}
          {!auditLoading && auditEntries.length > 0 && (
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead>
                  <tr className="border-b border-violet-200/40">
                    <th className="py-2 pr-4 font-medium text-slate-500">Time</th>
                    <th className="py-2 pr-4 font-medium text-slate-500">Type</th>
                    <th className="py-2 font-medium text-slate-500">Details</th>
                  </tr>
                </thead>
                <tbody>
                  {auditEntries.slice(auditPage * 20, (auditPage + 1) * 20).map((entry) => (
                    <tr key={entry.id} className="border-b border-violet-200/30">
                      <td className="py-2 pr-4 text-slate-600">{entry.created_at ? new Date(entry.created_at).toLocaleString() : '—'}</td>
                      <td className="py-2 pr-4 font-medium text-slate-700">{entry.kind}</td>
                      <td className="py-2 text-slate-600">
                        {entry.kind === 'pii_scan' && `Count: ${String(entry.payload?.total_count ?? 0)}, ${String(entry.payload?.summary ?? '—')}`}
                        {entry.kind === 'url_verdict' && `${String(entry.payload?.url ?? '').slice(0, 60)}… → ${String(entry.payload?.verdict ?? '—')}`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {auditEntries.length > 20 && (
                <div className="mt-2 flex gap-2">
                  <button type="button" onClick={() => setAuditPage((p) => Math.max(0, p - 1))} disabled={auditPage === 0} className="text-xs text-primary disabled:opacity-50">Previous</button>
                  <span className="text-xs text-slate-500">Page {auditPage + 1} of {Math.ceil(auditEntries.length / 20)}</span>
                  <button type="button" onClick={() => setAuditPage((p) => Math.min(Math.ceil(auditEntries.length / 20) - 1, p + 1))} disabled={auditPage >= Math.ceil(auditEntries.length / 20) - 1} className="text-xs text-primary disabled:opacity-50">Next</button>
                </div>
              )}
            </div>
          )}
        </section>
        <section className="mt-6 rounded-xl glass-card p-6 shadow-card">
          <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide">Scraping compliance log</h2>
          <p className="mt-1 text-sm text-slate-500">URLs added as sources: verdict (ALLOW/WARN/DENY), robots.txt and ToS summary. Legal evidence for data use.</p>
          {!auditLoading && auditEntries.filter((e) => e.kind === 'url_verdict').length === 0 && (
            <p className="mt-3 text-sm text-slate-500">No URL verdicts yet. Add a URL in Knowledge Sources to run compliance check.</p>
          )}
          {!auditLoading && auditEntries.filter((e) => e.kind === 'url_verdict').length > 0 && (
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead>
                  <tr className="border-b border-violet-200/40">
                    <th className="py-2 pr-4 font-medium text-slate-500">Time</th>
                    <th className="py-2 pr-4 font-medium text-slate-500">URL</th>
                    <th className="py-2 pr-4 font-medium text-slate-500">Verdict</th>
                    <th className="py-2 font-medium text-slate-500">Evidence</th>
                  </tr>
                </thead>
                <tbody>
                  {auditEntries.filter((e) => e.kind === 'url_verdict').slice(0, 30).map((entry) => (
                    <tr key={entry.id} className="border-b border-violet-200/30">
                      <td className="py-2 pr-4 text-slate-600">{entry.created_at ? new Date(entry.created_at).toLocaleString() : '—'}</td>
                      <td className="py-2 pr-4 max-w-[200px] truncate" title={String(entry.payload?.url ?? '')}>{String(entry.payload?.url ?? '—')}</td>
                      <td className="py-2 pr-4">
                        <span className={`font-medium ${(entry.payload?.verdict as string) === 'ALLOWED' ? 'text-emerald-600' : (entry.payload?.verdict as string) === 'DENIED' ? 'text-red-600' : 'text-amber-600'}`}>
                          {String(entry.payload?.verdict ?? '—')}
                        </span>
                      </td>
                      <td className="py-2 text-slate-600 max-w-xs truncate" title={String(entry.payload?.evidence ?? '')}>{String(entry.payload?.evidence ?? '—')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
        <section className="mt-6 rounded-xl glass-card p-6 shadow-card">
          <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide">Audit & export</h2>
          <p className="mt-1 text-sm text-slate-500">Export compliance gate and privacy settings.</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Link href="/export" className="rounded-lg border border-violet-200/40 bg-violet-50/80 px-3 py-2 text-sm text-slate-800 hover:bg-violet-200/40">Export Studio</Link>
            <Link href="/settings" className="rounded-lg border border-violet-200/40 bg-violet-50/80 px-3 py-2 text-sm text-slate-800 hover:bg-violet-200/40">Settings</Link>
            <button
              type="button"
              onClick={async () => {
                try {
                  const { getComplianceAudit } = await import('@/lib/api');
                  const data = await getComplianceAudit(tenantId, undefined, 500);
                  const report = {
                    generated_at: new Date().toISOString(),
                    tenant_id: tenantId,
                    entries: data.entries || [],
                  };
                  const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url;
                  a.download = `compliance-report-${tenantId}-${new Date().toISOString().slice(0, 10)}.json`;
                  a.click();
                  URL.revokeObjectURL(url);
                } catch (e) {
                  console.error(e);
                }
              }}
              className="rounded-lg border border-violet-200/40 bg-violet-50/80 px-3 py-2 text-sm text-slate-800 hover:bg-violet-200/40"
            >
              Download compliance report (JSON)
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}
