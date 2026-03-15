'use client';

import { useState, useRef, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { setOnboarded, setBrainName, setDomain, DOMAIN_LABELS, type Domain } from '@/lib/onboarding';
import { ingestDocument, ingestUrl, getIngestStatus, putBrainSettings } from '@/lib/api';
import { Confetti } from './Confetti';

const STEPS = 3;
const DOMAINS: Domain[] = ['medical', 'legal', 'retail', 'saas', 'finance', 'custom'];
const tenantId = 'default';
const namespace = 'main';
const POLL_MS = 800;

export function Onboarding() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [brainName, setBrainNameState] = useState('');
  const [domain, setDomainState] = useState<Domain>('custom');
  const [sourceMode, setSourceMode] = useState<'paste' | 'url'>('paste');
  const [pasteContent, setPasteContent] = useState('');
  const [pasteDocName, setPasteDocName] = useState('');
  const [url, setUrl] = useState('');
  const [urlName, setUrlName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [skipSource, setSkipSource] = useState(false);
  const [ingestLog, setIngestLog] = useState<string[]>([]);
  const [ingestPct, setIngestPct] = useState(0);
  const [showConfetti, setShowConfetti] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const progress = (step / STEPS) * 100;

  const handleStep1Next = async () => {
    const name = brainName.trim() || 'My Brain';
    setBrainName(name);
    setBrainNameState(name);
    try {
      await putBrainSettings(tenantId, name, undefined);
    } catch (_) {}
    setStep(2);
    setError('');
  };

  const handleStep2Next = async () => {
    setDomain(domain);
    setDomainState(domain);
    try {
      await putBrainSettings(tenantId, undefined, domain);
    } catch (_) {}
    setStep(3);
    setError('');
  };

  const finishOnboarding = () => {
    setOnboarded();
    router.push('/chat');
  };

  const handleStep3Finish = async () => {
    setError('');
    if (!skipSource) {
      if (sourceMode === 'paste') {
        const content = pasteContent.trim();
        const docName = pasteDocName.trim() || 'First document';
        if (!content) {
          setError('Add some text or skip for now.');
          return;
        }
        setLoading(true);
        setIngestLog(['Starting ingestion…']);
        setIngestPct(0);
        try {
          const res = await ingestDocument(tenantId, namespace, docName, content, false);
          const docId = res.document_id;
          if (!docId) {
            setError('Could not start ingestion.');
            setLoading(false);
            return;
          }
          const poll = () => {
            getIngestStatus(docId).then((job) => {
              const msg = job.message || job.phase || '';
              setIngestLog((prev) => (prev[prev.length - 1] === msg ? prev : [...prev, msg]));
              setIngestPct(job.percentage ?? 0);
              if (job.phase === 'done') {
                if (pollRef.current) clearInterval(pollRef.current);
                pollRef.current = null;
                setLoading(false);
                setShowConfetti(true);
              } else if (job.phase === 'error') {
                if (pollRef.current) clearInterval(pollRef.current);
                setError(job.message || 'Ingestion failed');
                setLoading(false);
              }
            }).catch(() => {});
          };
          poll();
          pollRef.current = setInterval(poll, POLL_MS);
        } catch (e) {
          setError(String(e));
          setLoading(false);
        }
        return;
      }
      const u = url.trim();
      if (!u) {
        setError('Enter a URL or skip for now.');
        return;
      }
      setLoading(true);
      try {
        const res = await ingestUrl(tenantId, namespace, u, urlName.trim() || undefined);
        if (!res.ok) {
          setError(res.error || 'Failed');
          setLoading(false);
          return;
        }
        setShowConfetti(true);
        setLoading(false);
      } catch (e) {
        setError(String(e));
        setLoading(false);
        return;
      }
      return;
    }
    setOnboarded();
    router.push('/chat');
  };

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  return (
    <div className="min-h-screen theme-page-bg flex flex-col items-center justify-center px-4 py-8">
      {showConfetti && <Confetti onComplete={finishOnboarding} />}
      <div className="w-full max-w-lg">
        <h1 className="text-2xl font-semibold text-slate-800 text-center mb-2">Welcome to BrainOS</h1>
        <p className="text-slate-500 text-sm text-center mb-8">Set up your AI brain in 3 steps</p>
        <div className="h-1.5 w-full rounded-full border-violet-200/40 overflow-hidden mb-10">
          <div className="h-full bg-primary transition-all duration-300 ease-out" style={{ width: `${progress}%` }} />
        </div>

        {step === 1 && (
          <div className="space-y-6 animate-in fade-in slide-in-from-bottom-3 duration-300">
            <h2 className="text-lg font-medium text-slate-800">Step 1: Name your AI brain</h2>
            <input
              type="text"
              value={brainName}
              onChange={(e) => setBrainNameState(e.target.value)}
              placeholder="e.g. MedClinic Assistant"
              className="w-full rounded-xl border border-violet-200/40 glass-input px-4 py-3 text-slate-800 placeholder:text-slate-500 shadow-card focus:border-primary focus:ring-1 focus:ring-primary"
              autoFocus
            />
            <div className="flex justify-end">
              <button type="button" onClick={handleStep1Next} className="rounded-xl bg-primary px-5 py-2.5 text-sm font-medium text-white hover:opacity-90">Next</button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-6 animate-in fade-in slide-in-from-bottom-3 duration-300">
            <h2 className="text-lg font-medium text-slate-800">Step 2: Pick your domain</h2>
            <p className="text-sm text-slate-500">This tunes chunking and prompts for your use case.</p>
            <div className="grid grid-cols-2 gap-3">
              {DOMAINS.map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => setDomainState(d)}
                  className={`rounded-xl border px-4 py-3 text-sm font-medium ${domain === d ? 'border-primary bg-primary/15 text-primary' : 'border border-violet-200/40 glass-card text-slate-800 hover:border-primary/50 shadow-glass'}`}
                >
                  {DOMAIN_LABELS[d]}
                </button>
              ))}
            </div>
            <div className="flex justify-between">
              <button type="button" onClick={() => setStep(1)} className="rounded-xl border border-violet-200/40 glass-input px-4 py-2.5 text-sm text-slate-800 hover:bg-violet-50/80">Back</button>
              <button type="button" onClick={handleStep2Next} className="rounded-xl bg-primary px-5 py-2.5 text-sm font-medium text-white hover:opacity-90">Next</button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-6 animate-in fade-in slide-in-from-bottom-3 duration-300">
            <h2 className="text-lg font-medium text-slate-800">Step 3: Add your first knowledge source</h2>
            <p className="text-sm text-slate-500">Paste text or add a URL. You can add more later.</p>
            <div className="flex gap-2 rounded-xl bg-violet-50/80 p-1">
              <button type="button" onClick={() => setSourceMode('paste')} className={`flex-1 rounded-lg py-2 text-sm font-medium ${sourceMode === 'paste' ? 'glass-card text-slate-800 shadow-glass' : 'text-slate-500'}`}>Paste</button>
              <button type="button" onClick={() => setSourceMode('url')} className={`flex-1 rounded-lg py-2 text-sm font-medium ${sourceMode === 'url' ? 'glass-card text-slate-800 shadow-glass' : 'text-slate-500'}`}>URL</button>
            </div>
            {sourceMode === 'paste' && (
              <>
                <input type="text" value={pasteDocName} onChange={(e) => setPasteDocName(e.target.value)} placeholder="Document name (optional)" className="w-full rounded-xl border border-violet-200/40 glass-input px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-500" />
                <textarea value={pasteContent} onChange={(e) => setPasteContent(e.target.value)} placeholder="Paste document text..." rows={4} className="w-full rounded-xl border border-violet-200/40 glass-input px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-500 resize-none" />
              </>
            )}
            {sourceMode === 'url' && (
              <>
                <input type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://example.com" className="w-full rounded-xl border border-violet-200/40 glass-input px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-500" />
                <input type="text" value={urlName} onChange={(e) => setUrlName(e.target.value)} placeholder="Name (optional)" className="w-full rounded-xl border border-violet-200/40 glass-input px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-500" />
              </>
            )}

            {loading && ingestLog.length > 0 && (
              <div className="rounded-xl border border-violet-200/40 bg-violet-50/50 p-4">
                <div className="h-2 w-full rounded-full border-violet-200/40 overflow-hidden mb-3">
                  <div className="h-full bg-primary transition-all duration-300" style={{ width: `${ingestPct}%` }} />
                </div>
                <ul className="font-mono text-xs text-slate-500 space-y-0.5 max-h-24 overflow-y-auto">
                  {ingestLog.map((line, i) => (
                    <li key={i}>{line}</li>
                  ))}
                </ul>
              </div>
            )}

            <label className="flex items-center gap-2 text-sm text-slate-500">
              <input type="checkbox" checked={skipSource} onChange={(e) => setSkipSource(e.target.checked)} className="rounded border-violet-200/40" />
              Skip for now
            </label>
            {error && <p className="text-sm text-rose-600">{error}</p>}
            <div className="flex justify-between">
              <button type="button" onClick={() => setStep(2)} disabled={loading} className="rounded-xl border border-violet-200/40 glass-input px-4 py-2.5 text-sm text-slate-800 hover:bg-violet-50/80 disabled:opacity-50">Back</button>
              <button type="button" onClick={handleStep3Finish} disabled={loading} className="rounded-xl bg-primary px-5 py-2.5 text-sm font-medium text-white hover:opacity-90 disabled:opacity-60">{loading ? 'Processing…' : 'Finish'}</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
