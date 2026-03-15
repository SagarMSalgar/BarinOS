'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  getExportRecords,
  getExportSchema,
  getExportGenerateAlpaca,
  getExportGenerateSharegpt,
  getExportGenerateDpo,
  getExportGeneratePretrain,
  getExportTrainingEstimate,
  saveExportState,
  getExportState,
  getKnowledgeCaptureQueue,
  approveKnowledgeCapture,
  pushExportToHf,
  downloadJsonl,
  downloadCsv,
  downloadParquet,
  runExportAbTest,
  transformExportPersona,
  scoreExportQuality,
  downloadSheetsExport,
} from '@/lib/api';
import { useBrain } from '@/contexts/BrainContext';

const JSONL_FORMATS = [
  { value: 'alpaca', label: 'Alpaca SFT' },
  { value: 'sharegpt', label: 'ShareGPT' },
  { value: 'openai_chat', label: 'OpenAI Chat' },
  { value: 'dpo', label: 'DPO pairs' },
  { value: 'pretrain', label: 'Pre-training' },
];

/** Columns to show in live preview per format (order matters). Falls back to record keys if missing. */
const PREVIEW_COLUMNS: Record<string, string[]> = {
  alpaca: ['instruction', 'input', 'output', 'quality_score', 'source_url', 'id'],
  sharegpt: ['id', 'conversations', 'source_docs'],
  openai_chat: ['id', 'messages'],
  dpo: ['prompt', 'chosen', 'rejected', 'chosen_score', 'rejected_score', 'score_gap', 'rejection_type', 'source_url'],
  pretrain: ['id', 'text', 'source_url', 'domain', 'language', 'quality_score', 'token_count', 'content_hash'],
};

export default function ExportPage() {
  const { namespace, tenantId } = useBrain();
  const [records, setRecords] = useState<Record<string, unknown>[]>([]);
  const [captureQueue, setCaptureQueue] = useState<Array<{ id: number; question: string; answer_text: string; source_type: string; quality_score: number; created_at: string | null }>>([]);
  const [captureLoading, setCaptureLoading] = useState(false);
  const [approvingId, setApprovingId] = useState<number | null>(null);
  const [schema, setSchema] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [jsonlFormat, setJsonlFormat] = useState('alpaca');
  const [minQuality, setMinQuality] = useState(0);
  const [dedup, setDedup] = useState(false);
  const [incremental, setIncremental] = useState(false);
  const [saveStateAfterDownload, setSaveStateAfterDownload] = useState(false);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [complianceGateOpen, setComplianceGateOpen] = useState(false);
  const [pendingDownload, setPendingDownload] = useState<'jsonl' | 'csv' | 'parquet' | null>(null);
  const [gateChecks, setGateChecks] = useState({ pii: false, legal: false });
  const [generating, setGenerating] = useState(false);
  const [generatedFormat, setGeneratedFormat] = useState<string | null>(null);
  const [trainingEstimate, setTrainingEstimate] = useState<{
    total_tokens: number;
    recommended_approach: string;
    gpu_memory_gb: number;
    cost_ranges: Array<{ provider: string; range_usd: string; gpu_hours: number }>;
    readiness: { score: number; checks: Array<{ ok: boolean; label: string }> };
  } | null>(null);
  const [hfOpen, setHfOpen] = useState(false);
  const [hfToken, setHfToken] = useState('');
  const [hfRepoId, setHfRepoId] = useState('');
  const [hfPushing, setHfPushing] = useState(false);
  const [hfResult, setHfResult] = useState<string | null>(null);
  const [persona, setPersona] = useState('internal_expert');
  const [personaApplying, setPersonaApplying] = useState(false);
  const [qualityScoring, setQualityScoring] = useState(false);
  const [sheetsDownloading, setSheetsDownloading] = useState(false);
  const [abTestRunning, setAbTestRunning] = useState(false);
  const [abTestResult, setAbTestResult] = useState<{
    variant_a: { label: string; scores: Record<string, number> };
    variant_b: { label: string; scores: Record<string, number> };
    winner: string;
    recommendation: string;
    num_questions: number;
  } | null>(null);
  const [abVariantA, setAbVariantA] = useState('Answer in 1-2 sentences only. Be concise.');
  const [abVariantB, setAbVariantB] = useState('Answer in detail with examples. Be comprehensive.');
  const [exportState, setExportState] = useState<{ exported_count?: number; updated_at?: string | null } | null>(null);

  const loadRecords = useCallback(() => {
    setLoading(true);
    Promise.all([
      getExportRecords(namespace, 5000, { minQuality, dedup, incremental }),
      getExportSchema(),
    ])
      .then(([data, schemaData]) => {
        setRecords(data.records || []);
        setSchema(schemaData);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [namespace, minQuality, dedup, incremental]);

  useEffect(() => {
    loadRecords();
  }, [loadRecords]);

  const loadCaptureQueue = useCallback(() => {
    setCaptureLoading(true);
    getKnowledgeCaptureQueue(tenantId, 'pending', 50)
      .then((d: { items?: Array<{ id: number; question: string; answer_text: string; source_type: string; quality_score: number; created_at: string | null }> }) => setCaptureQueue(d.items || []))
      .catch(() => setCaptureQueue([]))
      .finally(() => setCaptureLoading(false));
  }, [tenantId]);
  useEffect(() => {
    loadCaptureQueue();
  }, [loadCaptureQueue]);

  useEffect(() => {
    getExportState(namespace).then(setExportState).catch(() => setExportState(null));
  }, [namespace]);

  const duplicatePct = (() => {
    if (records.length < 2) return 0;
    const hashes = records.map((r) => (r.content_hash as string) || '').filter(Boolean);
    if (hashes.length < 2) return 0;
    const seen = new Set<string>();
    let dupes = 0;
    for (const h of hashes) {
      if (seen.has(h)) dupes++;
      else seen.add(h);
    }
    return Math.round((dupes / hashes.length) * 1000) / 10;
  })();

  useEffect(() => {
    if (records.length === 0) {
      setTrainingEstimate(null);
      return;
    }
    getExportTrainingEstimate(records.length, jsonlFormat, 300, duplicatePct)
      .then(setTrainingEstimate)
      .catch(() => setTrainingEstimate(null));
  }, [records.length, jsonlFormat, duplicatePct]);

  const doDownload = async (type: 'jsonl' | 'csv' | 'parquet') => {
    if (!records.length) return;
    setDownloading(type);
    try {
      let res: Response;
      if (type === 'jsonl') res = await downloadJsonl(records, jsonlFormat);
      else if (type === 'csv') res = await downloadCsv(records);
      else res = await downloadParquet(records);
      if (!res.ok) throw new Error(await res.text());
      const blob = await res.blob();
      const ext = type === 'jsonl' ? 'jsonl' : type === 'csv' ? 'csv' : 'parquet';
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `brainos_export.${ext}`;
      a.click();
      URL.revokeObjectURL(url);
      if (saveStateAfterDownload) {
        saveExportState(namespace, records).catch(() => {});
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setDownloading(null);
      setPendingDownload(null);
      setComplianceGateOpen(false);
    }
  };

  const handleDownload = (type: 'jsonl' | 'csv' | 'parquet') => {
    setPendingDownload(type);
    setComplianceGateOpen(true);
    setGateChecks({ pii: false, legal: false });
  };

  const confirmComplianceAndDownload = () => {
    if (pendingDownload) doDownload(pendingDownload);
  };

  const opts = { minQuality: minQuality || undefined, dedup };
  const handleGenerateAlpaca = async () => {
    setGenerating(true);
    setError(null);
    try {
      const data = await getExportGenerateAlpaca(namespace, 50, opts);
      setRecords((data.records || []) as Record<string, unknown>[]);
      setGeneratedFormat('alpaca');
      setJsonlFormat('alpaca');
    } catch (e) {
      setError(String(e));
    } finally {
      setGenerating(false);
    }
  };
  const handleGenerateSharegpt = async () => {
    setGenerating(true);
    setError(null);
    try {
      const data = await getExportGenerateSharegpt(namespace, 30, opts);
      setRecords((data.records || []) as Record<string, unknown>[]);
      setGeneratedFormat('sharegpt');
      setJsonlFormat('sharegpt');
    } catch (e) {
      setError(String(e));
    } finally {
      setGenerating(false);
    }
  };
  const handleGenerateDpo = async () => {
    setGenerating(true);
    setError(null);
    try {
      const data = await getExportGenerateDpo(namespace, 30, opts);
      setRecords((data.records || []) as Record<string, unknown>[]);
      setGeneratedFormat('dpo');
      setJsonlFormat('dpo');
    } catch (e) {
      setError(String(e));
    } finally {
      setGenerating(false);
    }
  };
  const handleGeneratePretrain = async () => {
    setGenerating(true);
    setError(null);
    try {
      const data = await getExportGeneratePretrain(namespace, 50, opts);
      setRecords((data.records || []) as Record<string, unknown>[]);
      setGeneratedFormat('pretrain');
      setJsonlFormat('pretrain');
    } catch (e) {
      setError(String(e));
    } finally {
      setGenerating(false);
    }
  };
  const handlePushToHf = async () => {
    if (!hfToken.trim() || !hfRepoId.trim() || !records.length) return;
    setHfPushing(true);
    setHfResult(null);
    try {
      const data = await pushExportToHf(hfToken.trim(), hfRepoId.trim(), records, jsonlFormat, true);
      setHfResult(data.url || `Pushed to ${data.repo_id}`);
    } catch (e) {
      setHfResult(`Error: ${String(e)}`);
    } finally {
      setHfPushing(false);
    }
  };

  const handleApplyPersona = async () => {
    if (!records.length) return;
    setPersonaApplying(true);
    setError(null);
    try {
      const formatHint = generatedFormat || jsonlFormat;
      const data = await transformExportPersona(records, persona, formatHint);
      setRecords((data.records || []) as Record<string, unknown>[]);
    } catch (e) {
      setError(String(e));
    } finally {
      setPersonaApplying(false);
    }
  };

  const handleScoreQuality = async () => {
    if (!records.length) return;
    setQualityScoring(true);
    setError(null);
    try {
      const data = await scoreExportQuality(records, 200);
      setRecords((data.records || []) as Record<string, unknown>[]);
    } catch (e) {
      setError(String(e));
    } finally {
      setQualityScoring(false);
    }
  };

  const handleSheetsExport = async () => {
    if (!records.length) return;
    setSheetsDownloading(true);
    try {
      const blob = await downloadSheetsExport(records, jsonlFormat);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'brainos_sheets_export.zip';
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(String(e));
    } finally {
      setSheetsDownloading(false);
    }
  };

  const handleRunAbTest = async () => {
    setAbTestRunning(true);
    setAbTestResult(null);
    setError(null);
    try {
      const data = await runExportAbTest({
        namespace,
        variant_a_label: 'Variant A',
        variant_b_label: 'Variant B',
        variant_a_instruction: abVariantA,
        variant_b_instruction: abVariantB,
        num_test_questions: 20,
      });
      if (data.error) {
        setError(data.error);
        return;
      }
      setAbTestResult(data);
    } catch (e) {
      setError(String(e));
    } finally {
      setAbTestRunning(false);
    }
  };

  const previewRows = records.slice(0, 20);
  const columns = (() => {
    if (!records.length) return [];
    const keys = Object.keys(records[0]);
    const preferred = PREVIEW_COLUMNS[jsonlFormat];
    if (!preferred) return keys;
    const filtered = preferred.filter((c) => keys.includes(c));
    return filtered.length ? filtered : keys;
  })();

  return (
    <div className="h-full flex overflow-hidden">
      {/* Column 1: Dataset Builder — 240px */}
      <aside className="w-[240px] shrink-0 border-r border-violet-200/40 glass-card flex flex-col overflow-y-auto">
        <div className="p-4 border-b border-violet-200/40">
          <h2 className="text-sm font-semibold text-slate-800">Dataset Builder</h2>
          <p className="text-xs text-slate-500 mt-0.5">Format & filters</p>
        </div>
        <div className="p-4 space-y-4">
          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1">Export format</label>
            <select
              value={jsonlFormat}
              onChange={(e) => setJsonlFormat(e.target.value)}
              className="w-full rounded-lg border border-violet-200/40 bg-violet-50/80 px-3 py-2 text-sm text-slate-800"
            >
              {JSONL_FORMATS.map((f) => (
                <option key={f.value} value={f.value}>{f.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-500 mb-1">Min quality (0–100)</label>
            <input
              type="range"
              min={0}
              max={100}
              value={minQuality}
              onChange={(e) => setMinQuality(Number(e.target.value))}
              className="w-full"
            />
            <span className="text-xs text-slate-500">{minQuality}</span>
          </div>
          <div className="flex flex-col gap-1">
            <label className="flex items-center gap-2 text-sm text-slate-800 cursor-pointer">
              <input type="checkbox" checked={dedup} onChange={(e) => setDedup(e.target.checked)} className="rounded border-violet-200/40" />
              Deduplicate by content hash
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-800 cursor-pointer">
              <input type="checkbox" checked={incremental} onChange={(e) => setIncremental(e.target.checked)} className="rounded border-violet-200/40" />
              Export new/changed only
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-800 cursor-pointer">
              <input type="checkbox" checked={saveStateAfterDownload} onChange={(e) => setSaveStateAfterDownload(e.target.checked)} className="rounded border-violet-200/40" />
              Save state after download
            </label>
            {exportState?.exported_count != null && exportState.exported_count > 0 && (
              <p className="text-xs text-slate-500">Last incremental export: {exportState.exported_count} records{exportState.updated_at ? ` at ${new Date(exportState.updated_at).toLocaleDateString()}` : ''}</p>
            )}
          </div>
          <div className="pt-2 border-t border-violet-200/40 space-y-2">
            <p className="text-xs font-medium text-slate-500">Generate with LLM (per-format)</p>
            <button type="button" onClick={handleGenerateAlpaca} disabled={generating} className="w-full rounded-lg bg-primary px-3 py-2 text-sm font-medium text-white hover:bg-primaryHover disabled:opacity-50">
              {generating ? 'Generating…' : 'Alpaca SFT (instruction/output)'}
            </button>
            <button type="button" onClick={handleGenerateSharegpt} disabled={generating} className="w-full rounded-lg bg-primary/80 px-3 py-2 text-sm font-medium text-white hover:bg-primary disabled:opacity-50">
              {generating ? 'Generating…' : 'ShareGPT (multi-turn)'}
            </button>
            <button type="button" onClick={handleGenerateDpo} disabled={generating} className="w-full rounded-lg bg-primary/80 px-3 py-2 text-sm font-medium text-white hover:bg-primary disabled:opacity-50">
              {generating ? 'Generating…' : 'DPO pairs (chosen/rejected)'}
            </button>
            <button type="button" onClick={handleGeneratePretrain} disabled={generating} className="w-full rounded-lg bg-primary/80 px-3 py-2 text-sm font-medium text-white hover:bg-primary disabled:opacity-50">
              {generating ? 'Generating…' : 'Pre-training (text + metadata)'}
            </button>
            {generatedFormat && <p className="text-xs text-emerald-600">Generated {records.length} records ({generatedFormat})</p>}
          </div>
          <div className="pt-2 border-t border-violet-200/40 space-y-2">
            <p className="text-xs font-medium text-slate-500">Persona transformer</p>
            <p className="text-xs text-slate-500">Rewrites in chosen tone; keeps current format (Alpaca/DPO/ShareGPT/Pretrain).</p>
            <select value={persona} onChange={(e) => setPersona(e.target.value)} className="w-full rounded-lg border border-violet-200/40 bg-violet-50/80 px-2 py-1.5 text-sm text-slate-800">
              <option value="customer_support">Customer support</option>
              <option value="legal">Legal</option>
              <option value="sales">Sales</option>
              <option value="internal_expert">Internal expert</option>
            </select>
            <button type="button" onClick={handleApplyPersona} disabled={personaApplying || !records.length} className="w-full rounded-lg border border-violet-200/40 bg-violet-50/80 px-3 py-2 text-sm text-slate-800 hover:bg-emerald-50/50 disabled:opacity-50">
              {personaApplying ? 'Applying…' : 'Apply persona'}
            </button>
          </div>
          <div className="pt-2 border-t border-violet-200/40 space-y-2">
            <button type="button" onClick={handleScoreQuality} disabled={qualityScoring || !records.length} className="w-full rounded-lg border border-violet-200/40 bg-violet-50/80 px-3 py-2 text-sm text-slate-800 hover:bg-emerald-50/50 disabled:opacity-50">
              {qualityScoring ? 'Scoring…' : 'Score quality (LLM)'}
            </button>
            <button type="button" onClick={handleSheetsExport} disabled={sheetsDownloading || !records.length} className="w-full rounded-lg border border-violet-200/40 bg-violet-50/80 px-3 py-2 text-sm text-slate-800 hover:bg-emerald-50/50 disabled:opacity-50">
              {sheetsDownloading ? 'Preparing…' : 'Export for Google Sheets (ZIP)'}
            </button>
          </div>
        </div>
      </aside>

      {/* Column 2: Live Preview — flex */}
      <main className="flex-1 min-w-0 overflow-y-auto">
        <div className="p-6">
          <h1 className="text-xl font-semibold text-slate-800">Export Studio</h1>
          <p className="mt-1 text-sm text-slate-500">
            Export knowledge base as JSONL, Parquet, or CSV. Compliance gate required before download.
          </p>
          <details className="mt-3 rounded-xl border border-violet-200/40 bg-violet-50/50 p-4 text-sm text-slate-800">
            <summary className="cursor-pointer font-medium text-slate-500">How Export Studio works</summary>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-slate-500">
              <li><strong>Data source:</strong> Records are the indexed chunks from your knowledge base (vector store). The backend scrolls the namespace and returns them for export.</li>
              <li><strong>Dataset Builder (left):</strong> Choose export format (Alpaca SFT, ShareGPT, OpenAI Chat, DPO, Pre-training), optional quality filter, and deduplication. These options shape how the same data is serialized.</li>
              <li><strong>Live Preview (center):</strong> First 20 rows of the current dataset so you can confirm content before exporting.</li>
              <li><strong>Quality Dashboard (right):</strong> Record count and the inferred JSON Schema for the data.</li>
              <li><strong>Compliance gate:</strong> Before any download you must confirm PII scan and legal re-check. The export is then logged for audit. After confirming, the file (JSONL/CSV/Parquet) is generated and downloaded.</li>
              <li><strong>Formats:</strong> JSONL for training pipelines (one JSON object per line); CSV for spreadsheets; Parquet for Hugging Face / data lakes.</li>
            </ul>
          </details>

          {/* Knowledge capture queue — approve Slack/email captures into knowledge base */}
          <section className="mt-6 rounded-xl border border-violet-200/40 glass-card p-4">
            <h2 className="text-sm font-semibold text-slate-800">Knowledge capture queue</h2>
            <p className="text-xs text-slate-500 mt-0.5">Pending Q&A from Slack or email. Approve to add to the knowledge base.</p>
            {captureLoading ? (
              <p className="mt-3 text-sm text-slate-500">Loading…</p>
            ) : captureQueue.length === 0 ? (
              <p className="mt-3 text-sm text-slate-500">No pending captures.</p>
            ) : (
              <ul className="mt-3 space-y-3">
                {captureQueue.map((item) => (
                  <li key={item.id} className="rounded-lg border border-violet-200/40 bg-violet-50/30 p-3">
                    <p className="text-xs text-slate-500">{item.source_type} • quality {Math.round((item.quality_score || 0) * 100)}%</p>
                    <p className="text-sm font-medium text-slate-800 mt-1">Q: {item.question.slice(0, 120)}{item.question.length > 120 ? '…' : ''}</p>
                    <p className="text-xs text-slate-600 mt-1">A: {item.answer_text.slice(0, 200)}{item.answer_text.length > 200 ? '…' : ''}</p>
                    <button
                      type="button"
                      onClick={async () => {
                        setApprovingId(item.id);
                        try {
                          await approveKnowledgeCapture(item.id, tenantId);
                          loadCaptureQueue();
                        } catch (e) {
                          setError(String(e));
                        } finally {
                          setApprovingId(null);
                        }
                      }}
                      disabled={approvingId !== null}
                      className="mt-2 rounded-lg bg-primary text-white px-3 py-1.5 text-xs font-medium hover:opacity-90 disabled:opacity-50"
                    >
                      {approvingId === item.id ? 'Adding…' : 'Approve & add to knowledge base'}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {error && (
            <div className="mt-4 rounded-xl border border-rose-200/50 bg-rose-50/80 px-4 py-3 text-sm text-rose-600">
              {error}
            </div>
          )}
          {loading ? (
            <p className="mt-6 text-slate-500">Loading records…</p>
          ) : (
            <>
              <div className="mt-6 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => handleDownload('jsonl')}
                  disabled={!records.length || downloading !== null}
                  className="rounded-xl bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primaryHover disabled:opacity-50"
                >
                  {downloading === 'jsonl' ? '…' : 'Download JSONL'}
                </button>
                <button
                  type="button"
                  onClick={() => handleDownload('csv')}
                  disabled={!records.length || downloading !== null}
                  className="rounded-xl border border-violet-200/40 glass-card px-4 py-2 text-sm text-slate-800 hover:bg-violet-50/80 disabled:opacity-50"
                >
                  {downloading === 'csv' ? '…' : 'Download CSV'}
                </button>
                <button
                  type="button"
                  onClick={() => handleDownload('parquet')}
                  disabled={!records.length || downloading !== null}
                  className="rounded-xl border border-violet-200/40 glass-card px-4 py-2 text-sm text-slate-800 hover:bg-violet-50/80 disabled:opacity-50"
                >
                  {downloading === 'parquet' ? '…' : 'Download Parquet'}
                </button>
                <button
                  type="button"
                  onClick={() => { setHfOpen(true); setHfResult(null); }}
                  disabled={!records.length}
                  className="rounded-xl border border-primary bg-emerald-50/50 px-4 py-2 text-sm font-medium text-slate-800 hover:bg-emerald-50 disabled:opacity-50"
                >
                  Push to Hugging Face
                </button>
                <button
                  type="button"
                  onClick={handleSheetsExport}
                  disabled={!records.length || sheetsDownloading}
                  className="rounded-xl border border-violet-200/40 glass-card px-4 py-2 text-sm text-slate-800 hover:bg-violet-50/80 disabled:opacity-50"
                >
                  {sheetsDownloading ? '…' : 'Export for Sheets (ZIP)'}
                </button>
              </div>
              <details className="mt-4 rounded-xl border border-violet-200/40 bg-violet-50/30 overflow-hidden">
                <summary className="cursor-pointer px-4 py-2 font-medium text-slate-800">A/B Dataset Tester</summary>
                <div className="p-4 space-y-3 border-t border-violet-200/40">
                  <p className="text-xs text-slate-500">Compare two answer styles. We generate test questions, simulate answers in each style, and score both.</p>
                  <div>
                    <label className="block text-xs text-slate-500 mb-1">Variant A instruction</label>
                    <textarea value={abVariantA} onChange={(e) => setAbVariantA(e.target.value)} className="w-full rounded-lg border border-violet-200/40 px-2 py-1.5 text-sm min-h-[60px]" placeholder="e.g. Answer in 1-2 sentences only." rows={2} />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-500 mb-1">Variant B instruction</label>
                    <textarea value={abVariantB} onChange={(e) => setAbVariantB(e.target.value)} className="w-full rounded-lg border border-violet-200/40 px-2 py-1.5 text-sm min-h-[60px]" placeholder="e.g. Answer in detail with examples." rows={2} />
                  </div>
                  <button type="button" onClick={handleRunAbTest} disabled={abTestRunning} className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
                    {abTestRunning ? 'Running A/B test…' : 'Run A/B test'}
                  </button>
                  {abTestResult && (
                    <div className="rounded-lg border border-violet-200/40 glass-card p-3 text-sm">
                      <p className="font-medium text-emerald-600">Winner: {abTestResult.winner}</p>
                      <p className="text-slate-500 mt-1">{abTestResult.recommendation}</p>
                      <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
                        <div>
                          <p className="font-medium text-slate-800">{abTestResult.variant_a?.label}</p>
                          <p className="text-slate-500">Overall: {abTestResult.variant_a?.scores?.overall ?? 0} · Accuracy: {abTestResult.variant_a?.scores?.accuracy ?? 0}</p>
                        </div>
                        <div>
                          <p className="font-medium text-slate-800">{abTestResult.variant_b?.label}</p>
                          <p className="text-slate-500">Overall: {abTestResult.variant_b?.scores?.overall ?? 0} · Accuracy: {abTestResult.variant_b?.scores?.accuracy ?? 0}</p>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </details>
              <details className="mt-4 rounded-xl border border-violet-200/40 bg-violet-50/30 overflow-hidden">
                <summary className="cursor-pointer px-4 py-2 font-medium text-slate-800">OpenAI fine-tuning</summary>
                <div className="p-4 border-t border-violet-200/40 space-y-2">
                  <p className="text-sm text-slate-600">Export in OpenAI-compatible format (JSONL with messages), then upload to OpenAI Fine-tuning. Use &quot;OpenAI Chat&quot; format above and download JSONL.</p>
                  <p className="text-xs text-slate-500">Direct &quot;Create fine-tuning job&quot; from this UI: coming soon.</p>
                </div>
              </details>
              <p className="mt-2 text-xs text-slate-500">
                {records.length} record{records.length !== 1 ? 's' : ''} from namespace &quot;{namespace}&quot;
              </p>
              <section className="mt-6">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
                  Live preview — {JSONL_FORMATS.find((f) => f.value === jsonlFormat)?.label ?? jsonlFormat}
                </h2>
                <p className="mt-0.5 text-xs text-slate-500">Columns reflect selected export format. Change format in Dataset Builder to update.</p>
                <div className="mt-3 overflow-x-auto rounded-xl border border-violet-200/40 glass-card">
                  {previewRows.length === 0 ? (
                    <p className="p-6 text-sm text-slate-500">No data. Add knowledge sources or generate with LLM for this format.</p>
                  ) : (
                    <table className="w-full text-left text-sm">
                      <thead>
                        <tr className="border-b border-violet-200/40 bg-violet-50/80/50">
                          {columns.map((c) => (
                            <th key={c} className="px-4 py-2 font-medium text-slate-800">{c}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {previewRows.map((row, i) => (
                          <tr key={i} className="border-b border-violet-200/40 last:border-0">
                            {columns.map((col) => {
                              const val = row[col];
                              const str = typeof val === 'object' && val !== null ? JSON.stringify(val).slice(0, 120) : String(val ?? '');
                              return (
                                <td key={col} className="max-w-[220px] truncate px-4 py-2 text-slate-500" title={typeof val === 'object' ? JSON.stringify(val) : str}>
                                  {str}
                                  {str.length >= (typeof val === 'object' ? 120 : 80) ? '…' : ''}
                                </td>
                              );
                            })}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </section>
            </>
          )}
        </div>
      </main>

      {/* Column 3: Quality Dashboard — 320px */}
      <aside className="w-[320px] shrink-0 border-l border-violet-200/40 glass-card flex flex-col overflow-y-auto">
        <div className="p-4 border-b border-violet-200/40">
          <h2 className="text-sm font-semibold text-slate-800">Quality Dashboard</h2>
          <p className="text-xs text-slate-500 mt-0.5">Schema & stats</p>
        </div>
        <div className="p-4 space-y-4">
          <div className="rounded-lg border border-violet-200/40 bg-violet-50/80/50 p-3">
            <p className="text-xs font-medium text-slate-500">Record count</p>
            <p className="text-lg font-semibold text-slate-800">{records.length}</p>
          </div>
          {trainingEstimate && (
            <div className="rounded-lg border border-violet-200/40 bg-emerald-50/30 p-3 space-y-2">
              <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Training cost estimate</h3>
              <p className="text-sm text-slate-800">{trainingEstimate.total_tokens.toLocaleString()} total tokens</p>
              <p className="text-xs text-slate-500">{trainingEstimate.recommended_approach}</p>
              <p className="text-xs text-slate-500">GPU: {trainingEstimate.gpu_memory_gb}GB · {trainingEstimate.cost_ranges?.[0]?.range_usd} (RunPod)</p>
              <p className="text-xs font-medium text-slate-800">Readiness: {trainingEstimate.readiness?.score ?? 0}/100</p>
              <ul className="text-[10px] text-slate-500 list-disc pl-4">
                {(trainingEstimate.readiness?.checks || []).map((c: { ok: boolean; label: string }, i: number) => (
                  <li key={i} className={c.ok ? 'text-emerald-600' : 'text-amber-600'}>{c.label}</li>
                ))}
              </ul>
            </div>
          )}
          {schema && (
            <div>
              <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide">JSON Schema</h3>
              <pre className="mt-2 overflow-x-auto rounded-lg border border-violet-200/40 bg-violet-50/80 p-3 text-xs text-slate-800 max-h-48 overflow-y-auto">
                {JSON.stringify(schema, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </aside>

      {/* Compliance gate modal */}
      {complianceGateOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={() => setComplianceGateOpen(false)}>
          <div className="rounded-xl border border-violet-200/40 glass-card p-6 shadow-soft max-w-md w-full mx-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-semibold text-slate-800">Export compliance gate</h3>
            <p className="text-sm text-slate-500 mt-1">Confirm before exporting data.</p>
            <ul className="mt-4 space-y-2">
              <li className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={gateChecks.pii}
                  onChange={(e) => setGateChecks((c) => ({ ...c, pii: e.target.checked }))}
                  className="rounded border-violet-200/40"
                />
                <span className="text-sm text-slate-800">PII scan passed (no sensitive data in export)</span>
              </li>
              <li className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={gateChecks.legal}
                  onChange={(e) => setGateChecks((c) => ({ ...c, legal: e.target.checked }))}
                  className="rounded border-violet-200/40"
                />
                <span className="text-sm text-slate-800">Legal / terms re-check acknowledged</span>
              </li>
            </ul>
            <p className="text-xs text-slate-500 mt-2">Export will be logged for audit.</p>
            <div className="mt-6 flex gap-2 justify-end">
              <button type="button" onClick={() => setComplianceGateOpen(false)} className="rounded-lg border border-violet-200/40 px-4 py-2 text-sm text-slate-800">
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmComplianceAndDownload}
                disabled={!gateChecks.pii || !gateChecks.legal}
                className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primaryHover disabled:opacity-50"
              >
                Allow download
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Push to Hugging Face modal */}
      {hfOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={() => { setHfOpen(false); setHfResult(null); }}>
          <div className="rounded-xl border border-violet-200/40 glass-card p-6 shadow-soft max-w-md w-full mx-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-semibold text-slate-800">Push to Hugging Face</h3>
            <p className="text-sm text-slate-500 mt-1">Upload current dataset as a private dataset. Requires HF token with write access.</p>
            <input type="password" value={hfToken} onChange={(e) => setHfToken(e.target.value)} placeholder="HF token" className="mt-3 w-full rounded-lg border border-violet-200/40 px-3 py-2 text-sm" />
            <input type="text" value={hfRepoId} onChange={(e) => setHfRepoId(e.target.value)} placeholder="Repo ID (e.g. username/dataset-name)" className="mt-2 w-full rounded-lg border border-violet-200/40 px-3 py-2 text-sm" />
            {hfResult && <p className="mt-2 text-sm text-slate-500 break-all">{hfResult}</p>}
            <div className="mt-4 flex gap-2 justify-end">
              <button type="button" onClick={() => { setHfOpen(false); setHfResult(null); }} className="rounded-lg border border-violet-200/40 px-4 py-2 text-sm text-slate-800">Cancel</button>
              <button type="button" onClick={handlePushToHf} disabled={hfPushing || !hfToken.trim() || !hfRepoId.trim()} className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white disabled:opacity-50">{hfPushing ? 'Pushing…' : 'Push'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
