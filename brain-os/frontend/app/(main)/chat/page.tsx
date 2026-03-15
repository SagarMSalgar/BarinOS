'use client';

import { useState, useCallback, useEffect } from 'react';
import Link from 'next/link';
import { ChatPanel, type Citation } from '@/components/ChatPanel';
import { RightPanel } from '@/components/RightPanel';
import { getRecentUpdates, getSavedQuestions, addSavedQuestion, deleteSavedQuestion, getSuggestQuestion, getRelatedQuestions, listDocuments } from '@/lib/api';
import { useBrain } from '@/contexts/BrainContext';

const PERSONA_OPTIONS = [
  { value: '', label: 'Guided Explorer' },
  { value: 'customer_support', label: 'As support' },
  { value: 'legal', label: 'As legal' },
  { value: 'sales', label: 'As sales' },
  { value: 'internal_expert', label: 'As expert' },
];

const LANGUAGE_OPTIONS = [
  { value: '', label: 'English' },
  { value: 'English', label: 'English' },
  { value: 'Spanish', label: 'Spanish' },
  { value: 'Hindi', label: 'Hindi' },
  { value: 'French', label: 'French' },
  { value: 'German', label: 'German' },
];

export default function ChatPage() {
  const { tenantId, namespace } = useBrain();
  const [citations, setCitations] = useState<Citation[]>([]);
  const [confidence, setConfidence] = useState<number | null>(null);
  const [followUps, setFollowUps] = useState<string[]>([]);
  const [selectedDoc, setSelectedDoc] = useState<string | null>(null);
  const [persona, setPersona] = useState('');
  const [pastedContext, setPastedContext] = useState('');
  const [strictMode, setStrictMode] = useState(false);
  const [recentUpdates, setRecentUpdates] = useState<{ documents: Array<{ name: string; last_verified_at?: string | null; updated_at?: string | null }>; count: number } | null>(null);
  const [savedQuestions, setSavedQuestions] = useState<Array<{ id: string; question: string; label?: string | null }>>([]);
  const [savedQuestionsOpen, setSavedQuestionsOpen] = useState(false);
  const [triggerQuestion, setTriggerQuestion] = useState<string | null>(null);
  const [suggestQuestion, setSuggestQuestion] = useState<string | null>(null);
  const [relatedQuestions, setRelatedQuestions] = useState<string[]>([]);
  const [answerLanguage, setAnswerLanguage] = useState('');
  const [documents, setDocuments] = useState<Array<{ id: string; name: string }>>([]);
  const [sourceFilter, setSourceFilter] = useState<string[]>([]);
  const [sourceFilterOpen, setSourceFilterOpen] = useState(false);
  /** Sidebar hidden by default; shown when user clicks "Expand for technical detail & full citations" */
  const [expandedSidebar, setExpandedSidebar] = useState<{
    citations: Citation[];
    confidence: number | null;
    content: string;
  } | null>(null);

  useEffect(() => {
    getRecentUpdates(tenantId, 60, namespace).then(setRecentUpdates).catch(() => setRecentUpdates(null));
  }, [tenantId, namespace]);
  useEffect(() => {
    getSavedQuestions(tenantId).then((r) => setSavedQuestions(r.items || [])).catch(() => setSavedQuestions([]));
  }, [tenantId]);
  useEffect(() => {
    getSuggestQuestion(tenantId, namespace).then((r) => setSuggestQuestion(r.suggestion || null)).catch(() => setSuggestQuestion(null));
  }, [tenantId, namespace]);
  useEffect(() => {
    getRelatedQuestions(tenantId, namespace, 8).then((r) => setRelatedQuestions(r.questions || [])).catch(() => setRelatedQuestions([]));
  }, [tenantId, namespace]);
  useEffect(() => {
    listDocuments(tenantId, namespace).then((r) => setDocuments(Array.isArray(r) ? r : [])).catch(() => setDocuments([]));
  }, [tenantId, namespace]);

  useEffect(() => {
    const saved = typeof window !== 'undefined' ? localStorage.getItem('brainos_chat_persona') : null;
    if (saved) setPersona(saved);
  }, []);
  useEffect(() => {
    if (persona && typeof window !== 'undefined') localStorage.setItem('brainos_chat_persona', persona);
  }, [persona]);
  useEffect(() => {
    const v = typeof window !== 'undefined' ? localStorage.getItem('brainos_strict_mode') : null;
    setStrictMode(v === '1');
  }, []);
  useEffect(() => {
    if (typeof window !== 'undefined') localStorage.setItem('brainos_strict_mode', strictMode ? '1' : '0');
  }, [strictMode]);

  const onStreamEvent = useCallback((event: { type: string; payload?: Record<string, unknown> }) => {
    if (event.type === 'citation') setCitations((event.payload?.citations as Citation[]) || []);
    if (event.type === 'confidence') setConfidence((event.payload?.score as number) ?? null);
    if (event.type === 'follow_ups') setFollowUps((event.payload?.questions as string[]) || []);
  }, []);

  const clearMetadata = useCallback(() => {
    setCitations([]);
    setConfidence(null);
    setFollowUps([]);
    setSelectedDoc(null);
  }, []);

  const handleSaveCurrentQuestion = useCallback((question: string) => {
    if (!question.trim()) return;
    addSavedQuestion(tenantId, question.trim()).then(() => {
      getSavedQuestions(tenantId).then((r) => setSavedQuestions(r.items || []));
    }).catch(() => {});
  }, []);

  const handleRunSavedQuestion = useCallback((question: string) => {
    setTriggerQuestion(question);
  }, []);

  return (
    <div className="flex h-full w-full overflow-hidden min-h-0 bg-gradient-to-br from-violet-50/90 via-white/80 to-purple-50/80 font-display text-slate-900">
      <div className="flex-1 flex flex-col min-w-0 min-h-0">
        {/* Header — glassmorphic, aligned to content */}
        <header className="glass-header shrink-0 z-10">
          <div className="h-16 mx-auto max-w-5xl px-6 flex items-center justify-between gap-4">
          <div className="flex items-center gap-6 min-w-0">
            <div className="flex items-center gap-2">
              <div className="bg-primary-gradient p-1.5 rounded-xl text-white flex items-center justify-center shadow-glass border border-white/20">
                <span className="text-xl font-bold">◆</span>
              </div>
              <h1 className="text-xl font-bold tracking-tight text-primary">BrainOS</h1>
            </div>
            <nav className="hidden md:flex items-center gap-1">
              <select
                value={persona}
                onChange={(e) => setPersona(e.target.value)}
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg hover:bg-primary/5 text-sm font-semibold transition-colors bg-transparent border-none cursor-pointer"
              >
                {PERSONA_OPTIONS.map((o) => (
                  <option key={o.value || 'default'} value={o.value}>{o.label}</option>
                ))}
              </select>
              <div className="w-px h-4 bg-slate-200 mx-1" />
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg hover:bg-primary/5 text-sm font-medium transition-colors">
                <select value={answerLanguage} onChange={(e) => setAnswerLanguage(e.target.value)} className="bg-transparent border-none cursor-pointer font-medium">
                  {LANGUAGE_OPTIONS.map((o) => (
                    <option key={o.value || 'default'} value={o.value}>{o.label}</option>
                  ))}
                </select>
                <span className="text-slate-400">▾</span>
              </div>
            </nav>
          </div>
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 glass-card px-3 py-1.5 rounded-full cursor-pointer">
              <input type="checkbox" checked={strictMode} onChange={(e) => setStrictMode(e.target.checked)} className="rounded border-primary text-primary focus:ring-primary h-4 w-4" />
              <span className="text-xs font-bold uppercase tracking-wider text-primary">Strict Mode</span>
              <span className="flex h-2 w-2 rounded-full bg-primary animate-pulse" />
            </label>
            <div className="relative">
              <button type="button" onClick={() => setSavedQuestionsOpen((o) => !o)} className="flex items-center gap-2 px-4 py-1.5 rounded-xl glass-tab-inactive text-sm font-semibold transition-colors text-slate-700">
                <span className="text-primary">🔖</span>
                Saved Questions ({savedQuestions.length})
              </button>
              {savedQuestionsOpen && (
                <div className="absolute right-0 top-full mt-2 z-20 rounded-xl glass-card-strong p-3 w-80 max-h-64 overflow-y-auto">
                  <p className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-2">Saved questions</p>
                  {savedQuestions.length === 0 && <p className="text-sm text-slate-500 py-2">Save a question for one-click answers.</p>}
                  {savedQuestions.map((sq) => (
                    <div key={sq.id} className="flex items-center gap-2 group py-1.5 border-b border-slate-100 last:border-0">
                      <button type="button" onClick={() => { handleRunSavedQuestion(sq.question); setSavedQuestionsOpen(false); }} className="text-left text-sm text-slate-800 hover:text-primary truncate flex-1">
                        {sq.label || sq.question.slice(0, 50)}{sq.question.length > 50 ? '…' : ''}
                      </button>
                      <button type="button" onClick={() => deleteSavedQuestion(sq.id, tenantId).then(() => getSavedQuestions(tenantId).then((r) => setSavedQuestions(r.items || [])))} className="text-slate-400 hover:text-red-500 text-sm opacity-0 group-hover:opacity-100" aria-label="Remove">×</button>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="flex items-center gap-2 ml-2">
              <Link href="/settings" className="p-2 rounded-xl hover:bg-white/50 text-slate-500 backdrop-blur-sm" aria-label="Settings">⚙️</Link>
              <div className="h-8 w-8 rounded-full bg-primary-gradient border-2 border-white/40 shadow-glass flex items-center justify-center text-white text-xs font-bold" aria-hidden>GE</div>
            </div>
          </div>
          </div>
        </header>
        <ChatPanel
          tenantId={tenantId}
          namespace={namespace}
          citations={citations}
          confidence={confidence}
          followUps={followUps}
          onStreamEvent={onStreamEvent}
          onNewQuery={clearMetadata}
          persona={persona || undefined}
          pastedContext={pastedContext}
          onPastedContextChange={setPastedContext}
          strictMode={strictMode}
          triggerQuestion={triggerQuestion}
          onTriggerQuestionConsumed={() => setTriggerQuestion(null)}
          onSaveQuestion={handleSaveCurrentQuestion}
          relatedQuestions={relatedQuestions}
          suggestQuestion={suggestQuestion}
          answerLanguage={answerLanguage || undefined}
          sourceFilter={sourceFilter.length > 0 ? sourceFilter : undefined}
          useHubStyle
          documents={documents}
          onSourceFilterChange={setSourceFilter}
          onExpandCitations={(cits, content, conf) => setExpandedSidebar({ citations: cits, confidence: conf ?? null, content })}
        />
      </div>
      {expandedSidebar && (
        <RightPanel
          citations={expandedSidebar.citations}
          confidence={expandedSidebar.confidence}
          followUps={followUps}
          selectedDoc={selectedDoc}
          onSelectDoc={setSelectedDoc}
          useHubStyle
          fullContent={expandedSidebar.content}
          onClose={() => setExpandedSidebar(null)}
          recentUpdates={recentUpdates}
        />
      )}
    </div>
  );
}
