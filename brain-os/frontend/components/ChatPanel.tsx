'use client';

import { useState, useRef, useCallback, useEffect } from 'react';
import { streamChat, verifyCitations, addToBrain, suggestEdit, simplifyAnswer, submitFeedback, addSavedAnswer, logQueryCitations, recordInteraction } from '@/lib/api';
import { VerificationResultCard } from '@/components/VerificationResultCard';
import { IconComplianceChart, IconComparison, IconActionPlan, IconTechnical } from '@/components/Icons';

export type Citation = { document_id?: string; document_name: string; page?: number; section?: string; score: number };

type Message = {
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  confidence?: number;
  noAnswerFromDocs?: boolean; // "What's missing?" — brain couldn't answer from docs
};

export interface ChatPanelProps {
  tenantId: string;
  namespace: string;
  citations: Citation[];
  confidence: number | null;
  followUps: string[];
  onStreamEvent: (event: { type: string; payload?: Record<string, unknown> }) => void;
  onNewQuery: () => void;
  onSuggestionClick?: (question: string) => void;
  persona?: string;
  pastedContext?: string;
  onPastedContextChange?: (value: string) => void;
  strictMode?: boolean;
  triggerQuestion?: string | null;
  onTriggerQuestionConsumed?: () => void;
  onSaveQuestion?: (question: string) => void;
  relatedQuestions?: string[];
  suggestQuestion?: string | null;
  answerLanguage?: string;
  sourceFilter?: string[];
  onExportConversation?: () => void;
  /** Hub-style: purple bubble, wide answer card, primary-colored bullets, box buttons */
  useHubStyle?: boolean;
  documents?: Array<{ id: string; name: string }>;
  onSourceFilterChange?: (names: string[]) => void;
  /** When user clicks Expand for technical detail & citations, open sidebar with this data */
  onExpandCitations?: (citations: Citation[], content: string, confidence?: number) => void;
}

export function ChatPanel({
  tenantId,
  namespace,
  citations,
  confidence,
  followUps,
  onStreamEvent,
  onNewQuery,
  onSuggestionClick,
  persona,
  pastedContext,
  onPastedContextChange,
  strictMode,
  triggerQuestion,
  onTriggerQuestionConsumed,
  onSaveQuestion,
  relatedQuestions = [],
  suggestQuestion,
  answerLanguage,
  sourceFilter,
  onExportConversation,
  useHubStyle = false,
  documents = [],
  onSourceFilterChange,
  onExpandCitations,
}: ChatPanelProps) {
  const [sourceFilterOpen, setSourceFilterOpen] = useState(false);
  const hub = useHubStyle;
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [streamBuffer, setStreamBuffer] = useState('');
  const [showThinking, setShowThinking] = useState(false);
  const [listening, setListening] = useState(false);
  const [verifyResult, setVerifyResult] = useState<{ messageIndex: number; summary: string; results?: Array<{ document_name: string; status: string; message?: string; count?: number }> } | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [showPasteContext, setShowPasteContext] = useState(false);
  const [livePhase, setLivePhase] = useState<'idle' | 'searching' | 'sources' | 'answering'>('idle');
  const [liveDocuments, setLiveDocuments] = useState<Array<{ document_name: string; document_id?: string }>>([]);
  const [liveMessage, setLiveMessage] = useState('');
  const [suggestEditIndex, setSuggestEditIndex] = useState<number | null>(null);
  const [suggestEditValue, setSuggestEditValue] = useState('');
  const [addToBrainIndex, setAddToBrainIndex] = useState<number | null>(null);
  const [addToBrainSubmitting, setAddToBrainSubmitting] = useState(false);
  const [suggestEditSubmitting, setSuggestEditSubmitting] = useState(false);
  const [simplifiedIndex, setSimplifiedIndex] = useState<number | null>(null);
  const [simplifiedContent, setSimplifiedContent] = useState<string | null>(null);
  const [simplifying, setSimplifying] = useState(false);
  const [feedbackIndex, setFeedbackIndex] = useState<number | null>(null);
  const [feedbackSent, setFeedbackSent] = useState<Set<number>>(new Set());
  const [whatWrong, setWhatWrong] = useState('');
  const [saveAnswerIndex, setSaveAnswerIndex] = useState<number | null>(null);
  const [saveAnswerTag, setSaveAnswerTag] = useState('');
  const [saveAnswerNote, setSaveAnswerNote] = useState('');
  const [saveAnswerSubmitting, setSaveAnswerSubmitting] = useState(false);
  const streamContentRef = useRef('');
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const currentResponseCites = useRef<Citation[]>([]);
  const currentResponseConf = useRef<number | null>(null);
  const currentResponseGap = useRef(false);

  const toggleVoice = useCallback(() => {
    if (listening) {
      setListening(false);
      return;
    }
    type SpeechRecognitionCtor = new () => { continuous: boolean; interimResults: boolean; lang: string; onresult: (e: { results: { [i: number]: { [j: number]: { transcript: string } } }; resultIndex: number }) => void; onend: () => void; onerror: () => void; start: () => void };
    const win = typeof window !== 'undefined' ? window : null;
    const SR = win && ((win as unknown as { SpeechRecognition?: SpeechRecognitionCtor }).SpeechRecognition ?? (win as unknown as { webkitSpeechRecognition?: SpeechRecognitionCtor }).webkitSpeechRecognition);
    if (!SR) {
      return;
    }
    const rec = new SR();
    rec.continuous = false;
    rec.interimResults = false;
    rec.lang = 'en-US';
    rec.onresult = (e: { results: { [i: number]: { [j: number]: { transcript: string } } }; resultIndex: number }) => {
      const t = e.results[e.resultIndex][0].transcript;
      setInput((prev) => (prev ? `${prev} ${t}` : t));
    };
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    rec.start();
    setListening(true);
  }, [listening]);

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamBuffer, scrollToBottom]);

  // "BrainOS is thinking..." show when streaming and no token yet (e.g. first ~200ms)
  useEffect(() => {
    if (!streaming) {
      setShowThinking(false);
      return;
    }
    const t = setTimeout(() => setShowThinking(true), 150);
    return () => clearTimeout(t);
  }, [streaming]);

  useEffect(() => {
    if (streamBuffer) setShowThinking(false);
  }, [streamBuffer]);

  // Auto-resize textarea max 4 lines
  const handleTextareaChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const ta = e.target;
    ta.style.height = 'auto';
    const lineHeight = 24;
    const maxHeight = lineHeight * 4;
    ta.style.height = `${Math.min(ta.scrollHeight, maxHeight)}px`;
  }, []);

  const send = useCallback(async () => {
    const q = input.trim();
    if (!q || streaming) return;
    setInput('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
    onNewQuery();
    setMessages((m) => [...m, { role: 'user', content: q }]);
    setStreaming(true);
    setStreamBuffer('');
    setLivePhase('searching');
    setLiveDocuments([]);
    setLiveMessage('Searching your knowledge…');
    streamContentRef.current = '';
    currentResponseCites.current = [];
    currentResponseConf.current = null;
    currentResponseGap.current = false;

    try {
      await streamChat(
        tenantId,
        namespace,
        q,
        (event) => {
        if (event.type === 'phase') {
          const p = event.payload as { phase?: string; message?: string; documents?: Array<{ document_name: string; document_id?: string }> };
          if (p?.phase === 'searching') {
            setLivePhase('searching');
            setLiveMessage(p?.message || 'Searching your knowledge…');
            setLiveDocuments([]);
          } else if (p?.phase === 'sources') {
            setLivePhase('sources');
            setLiveMessage(p?.message || 'Reading sources…');
            setLiveDocuments(p?.documents || []);
          } else if (p?.phase === 'answering') {
            setLivePhase('answering');
            setLiveMessage(p?.message || 'Answering…');
          }
        } else if (event.type === 'no_answer_from_docs') {
          currentResponseGap.current = true;
        } else if (event.type === 'token') {
          const text = (event.payload?.text as string) || '';
          streamContentRef.current += text;
          setStreamBuffer(streamContentRef.current);
        } else {
          if (event.type === 'citation')
            currentResponseCites.current = (event.payload?.citations as Citation[]) || [];
          if (event.type === 'confidence')
            currentResponseConf.current = (event.payload?.score as number) ?? null;
          onStreamEvent(event);
        }
      },
        { persona, pastedContext: pastedContext?.trim() || undefined, strictMode, answerLanguage, sourceFilter },
      );
    } catch (e) {
      streamContentRef.current += `\n[Error: ${String(e)}]`;
      setStreamBuffer(streamContentRef.current);
    } finally {
      setStreaming(false);
      setLivePhase('idle');
      setLiveDocuments([]);
      setLiveMessage('');
      const finalContent = streamContentRef.current;
      const hadGap = currentResponseGap.current;
      setMessages((m) => {
        const newMsg: Message = {
          role: 'assistant',
          content: finalContent,
          citations: currentResponseCites.current.length ? currentResponseCites.current : undefined,
          confidence: currentResponseConf.current ?? undefined,
          noAnswerFromDocs: hadGap,
        };
        return [...m, newMsg];
      });
      const citedIds = (currentResponseCites.current || [])
        .map((c) => c.document_id)
        .filter((id): id is string => Boolean(id));
      if (citedIds.length) logQueryCitations(tenantId, namespace, q, citedIds).catch(() => {});
      if (finalContent) recordInteraction(tenantId, namespace, q, finalContent).catch(() => {});
      setStreamBuffer('');
      streamContentRef.current = '';
    }
  }, [input, streaming, tenantId, namespace, onStreamEvent, onNewQuery, persona, pastedContext, strictMode, answerLanguage, sourceFilter]);

  // One-click saved question: run when triggerQuestion is set
  const runQuestion = useCallback(async (q: string) => {
    if (!q.trim() || streaming) return;
    onNewQuery();
    setMessages((m) => [...m, { role: 'user', content: q.trim() }]);
    setStreaming(true);
    setStreamBuffer('');
    setLivePhase('searching');
    setLiveDocuments([]);
    setLiveMessage('Searching your knowledge…');
    streamContentRef.current = '';
    currentResponseCites.current = [];
    currentResponseConf.current = null;
    currentResponseGap.current = false;
    try {
      await streamChat(
        tenantId,
        namespace,
        q.trim(),
        (event) => {
          if (event.type === 'phase') {
            const p = event.payload as { phase?: string; message?: string; documents?: Array<{ document_name: string; document_id?: string }> };
            if (p?.phase === 'searching') {
              setLivePhase('searching');
              setLiveMessage(p?.message || 'Searching your knowledge…');
              setLiveDocuments([]);
            } else if (p?.phase === 'sources') {
              setLivePhase('sources');
              setLiveMessage(p?.message || 'Reading sources…');
              setLiveDocuments(p?.documents || []);
            } else if (p?.phase === 'answering') {
              setLivePhase('answering');
              setLiveMessage(p?.message || 'Answering…');
            }
          } else if (event.type === 'no_answer_from_docs') {
            currentResponseGap.current = true;
          } else if (event.type === 'token') {
            const text = (event.payload?.text as string) || '';
            streamContentRef.current += text;
            setStreamBuffer(streamContentRef.current);
          } else {
            if (event.type === 'citation')
              currentResponseCites.current = (event.payload?.citations as Citation[]) || [];
            if (event.type === 'confidence')
              currentResponseConf.current = (event.payload?.score as number) ?? null;
            onStreamEvent(event);
          }
        },
        { persona, pastedContext: pastedContext?.trim() || undefined, strictMode, answerLanguage, sourceFilter },
      );
    } catch (e) {
      streamContentRef.current += `\n[Error: ${String(e)}]`;
      setStreamBuffer(streamContentRef.current);
    } finally {
      setStreaming(false);
      setLivePhase('idle');
      setLiveDocuments([]);
      setLiveMessage('');
      const finalContent = streamContentRef.current;
      const hadGap = currentResponseGap.current;
      setMessages((m) => {
        const newMsg: Message = {
          role: 'assistant',
          content: finalContent,
          citations: currentResponseCites.current.length ? currentResponseCites.current : undefined,
          confidence: currentResponseConf.current ?? undefined,
          noAnswerFromDocs: hadGap,
        };
        return [...m, newMsg];
      });
      const citedIds = (currentResponseCites.current || [])
        .map((c) => c.document_id)
        .filter((id): id is string => Boolean(id));
      if (citedIds.length) logQueryCitations(tenantId, namespace, q.trim(), citedIds).catch(() => {});
      if (finalContent) recordInteraction(tenantId, namespace, q.trim(), finalContent).catch(() => {});
      setStreamBuffer('');
      streamContentRef.current = '';
    }
  }, [streaming, tenantId, namespace, onStreamEvent, onNewQuery, persona, pastedContext, strictMode, answerLanguage, sourceFilter]);

  useEffect(() => {
    if (triggerQuestion && triggerQuestion.trim()) {
      runQuestion(triggerQuestion.trim());
      onTriggerQuestionConsumed?.();
    }
  }, [triggerQuestion]); // eslint-disable-line react-hooks/exhaustive-deps -- only run when triggerQuestion is set

  const onVerify = useCallback(
    async (messageIndex: number, citationsList: Citation[]) => {
      const ids = citationsList.map((c) => (c as Citation & { document_id?: string }).document_id).filter(Boolean) as string[];
      if (!ids.length) {
        setVerifyResult({ messageIndex, summary: 'No citable sources to verify (document IDs missing).' });
        return;
      }
      setVerifying(true);
      setVerifyResult(null);
      try {
        const data = await verifyCitations(tenantId, ids);
        setVerifyResult({
          messageIndex,
          summary: data.summary ?? 'Done',
          results: data.results,
        });
      } catch (e) {
        setVerifyResult({ messageIndex, summary: `Verification failed: ${String(e)}` });
      } finally {
        setVerifying(false);
      }
    },
    [tenantId],
  );

  const currentCites = streamBuffer ? citations : [];
  const currentConf = streamBuffer ? confidence : null;

  const freshnessColor = (score: number) => {
    if (hub) {
      if (score >= 0.8) return 'bg-emerald-50 text-emerald-700 border-emerald-100';
      if (score >= 0.5) return 'bg-amber-50 text-amber-700 border-amber-100';
      return 'bg-red-50 text-red-700 border-red-100';
    }
    if (score >= 0.8) return 'bg-emerald-50 text-emerald-600 border-emerald-200/50';
    if (score >= 0.5) return 'bg-amber-50 text-amber-600 border-amber-200/50';
    return 'bg-rose-50 text-rose-600 border-rose-200/50';
  };

  const firstLine = (text: string) => text.trim().split(/\n/)[0]?.slice(0, 80) || 'Summary';
  const coreAnswer = (text: string) => text.trim().slice(0, 120) + (text.length > 120 ? '…' : '');
  const keyImplication = (text: string) => {
    const lines = text.trim().split(/\n/).filter(Boolean);
    return (lines[1] || lines[0] || '').slice(0, 100) + (text.length > 100 ? '…' : '');
  };

  /** Render answer content with primary (purple) bullet lines for Hub style */
  const renderAnswerWithPurpleBullets = (content: string) => {
    const lines = content.split(/\n/);
    return (
      <>
        {lines.map((line, idx) => {
          const trimmed = line.trim();
          const bulletMatch = trimmed.match(/^[-•*]\s+(.+)$/) || trimmed.match(/^\d+\.\s+(.+)$/);
          if (bulletMatch) {
            return (
              <div key={idx} className="flex gap-2 mt-2">
                <span className="text-primary shrink-0 mt-1.5 w-1.5 h-1.5 rounded-full bg-primary" />
                <p className="text-sm font-medium text-slate-800 leading-relaxed">{bulletMatch[1]}</p>
              </div>
            );
          }
          if (trimmed) {
            return <p key={idx} className="text-sm text-slate-700 leading-relaxed mt-2 first:mt-0">{line}</p>;
          }
          return <br key={idx} />;
        })}
      </>
    );
  };

  return (
    <main className={`flex flex-1 flex-col min-w-0 min-h-0 ${hub ? 'bg-transparent' : 'theme-page-bg'}`}>
      {/* Hub: Analyzing documents bar — glassmorphic */}
      {hub && (livePhase !== 'idle' || (sourceFilter && sourceFilter.length > 0)) && (
        <div className="glass-header px-6 py-3 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <span className="text-primary text-sm">⟳</span>
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                {livePhase !== 'idle' ? 'Knowledge active...' : 'Search scope'}
              </span>
            </div>
            <div className="flex gap-2">
              {(livePhase === 'sources' ? liveDocuments : []).length > 0
                ? liveDocuments.map((doc, idx) => (
                    <span key={doc.document_id || idx} className="px-2 py-0.5 rounded-md bg-primary/15 text-[10px] font-bold text-primary border border-primary/20">
                      {doc.document_name.replace(/\s+/g, '_').slice(0, 24)}
                    </span>
                  ))
                : sourceFilter?.map((name) => (
                    <span key={name} className="px-2 py-0.5 rounded-md bg-primary/15 text-[10px] font-bold text-primary border border-primary/20">
                      {name.replace(/\s+/g, '_').slice(0, 24)}
                    </span>
                  ))}
            </div>
          </div>
          <div className="relative">
            <button type="button" onClick={() => setSourceFilterOpen((o) => !o)} className="text-xs font-semibold text-primary hover:underline flex items-center gap-1">
              Only search in...
            </button>
            {sourceFilterOpen && onSourceFilterChange && (
              <div className="absolute right-0 top-full mt-1 z-20 rounded-xl glass-card-strong p-3 max-h-48 overflow-y-auto min-w-[200px]">
                {documents.length === 0 && <p className="text-xs text-slate-500">No sources yet.</p>}
                {documents.map((d) => (
                  <label key={d.id} className="flex items-center gap-2 py-1.5 text-sm cursor-pointer">
                    <input type="checkbox" checked={sourceFilter?.includes(d.name) ?? false} onChange={(e) => { const next = e.target.checked ? [...(sourceFilter || []), d.name] : (sourceFilter || []).filter((n) => n !== d.name); onSourceFilterChange(next); }} className="rounded border-primary text-primary h-4 w-4" />
                    <span className="truncate text-slate-800">{d.name}</span>
                  </label>
                ))}
                {(sourceFilter?.length ?? 0) > 0 && <button type="button" onClick={() => onSourceFilterChange?.([])} className="mt-1 text-xs text-primary font-semibold">Clear</button>}
              </div>
            )}
          </div>
        </div>
      )}
      <div className={`flex-1 overflow-y-auto min-h-0 ${hub ? 'p-6 space-y-8 custom-scrollbar' : 'p-4 space-y-4'}`}>
        {/* Live retrieval (non-Hub or when not in analyzing strip) */}
        {!hub && livePhase !== 'idle' && (
          <div className="glass-card px-4 py-3 mb-4">
            <p className="text-sm font-medium text-slate-800 flex items-center gap-2">
              <span className="inline-block w-2 h-2 rounded-full bg-primary animate-pulse" />
              {liveMessage}
            </p>
            {livePhase === 'sources' && liveDocuments.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {liveDocuments.map((doc, idx) => (
                  <span key={doc.document_id || idx} className="inline-flex items-center rounded-md glass-tab-inactive px-2 py-0.5 text-xs text-slate-600">
                    {doc.document_name}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}
        {messages.length === 0 && !streamBuffer && !showThinking && (
          <div className={`flex flex-col h-full min-h-[12rem] items-center justify-center text-sm text-center px-4 ${hub ? 'text-slate-500' : 'text-slate-500'}`}>
            <p>Ask a question. Answers are grounded in your knowledge base with citations and confidence.</p>
            {suggestQuestion && (
              <button type="button" onClick={() => onSuggestionClick?.(suggestQuestion)} className="mt-4 rounded-xl px-4 py-2 font-medium glass-tab-inactive text-slate-800 hover:bg-white/70">
                Try: {suggestQuestion}
              </button>
            )}
          </div>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            className={msg.role === 'user'
              ? hub ? 'flex justify-end max-w-4xl ml-auto w-full' : 'rounded-xl px-4 py-3 ml-8 glass-card'
              : hub ? 'flex flex-col gap-4 max-w-5xl w-full' : 'rounded-xl px-4 py-3 mr-8 glass-card'
            }
          >
            {msg.role === 'user' && (
              <div className={hub ? 'bg-primary-gradient text-white p-5 rounded-2xl rounded-tr-none shadow-glass max-w-[85%] border border-white/20' : 'px-4 py-3'}>
                <p className={`text-sm leading-relaxed whitespace-pre-wrap ${hub ? 'font-medium text-white' : 'text-slate-800'}`}>{msg.content}</p>
              </div>
            )}
            {msg.role === 'assistant' && hub && (
              <>
                <div className="flex items-start gap-3 w-full max-w-5xl">
                  <div className="size-9 rounded-xl bg-primary-gradient text-white flex items-center justify-center shrink-0 shadow-glass border border-white/20">✦</div>
                  <div className="flex-1 min-w-0 space-y-4">
                    <div className="glass-card-strong overflow-hidden w-full">
                      <div className="p-6">
                        <div className="flex flex-wrap items-center gap-2 mb-3">
                          {(msg.confidence == null || msg.confidence >= 70) && msg.content && (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 text-xs font-semibold border border-emerald-100">
                              <span className="text-emerald-600">✓</span> Verified Legal Sources
                            </span>
                          )}
                          {msg.citations && msg.citations.length > 0 && (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-primary/10 text-primary text-xs font-medium border border-primary/20">
                              <span>🕐</span> Freshness: Recent {msg.confidence != null && msg.confidence >= 80 ? '(High)' : msg.confidence != null && msg.confidence >= 50 ? '(Medium)' : '(Q1 2024)'}
                            </span>
                          )}
                        </div>
                        <div className="text-slate-700">
                          {renderAnswerWithPurpleBullets(simplifiedIndex === i && simplifiedContent ? simplifiedContent : msg.content)}
                        </div>
                        <button
                          type="button"
                          onClick={() => onExpandCitations?.(msg.citations ?? [], msg.content, msg.confidence)}
                          className="mt-4 text-sm font-semibold text-primary hover:underline"
                        >
                          Expand for Technical Detail & Full Citations
                        </button>
                      </div>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                        <button
                          type="button"
                          onClick={() => {
                            const refs = msg.citations?.map((c, j) => `[${j + 1}] ${c.document_name}${c.page != null ? ` p.${c.page}` : ''}`).join('\n') ?? '';
                            const text = (simplifiedIndex === i && simplifiedContent ? simplifiedContent : msg.content) + (refs ? '\n\nSources:\n' + refs : '');
                            navigator.clipboard?.writeText(text).then(() => {}, () => {});
                          }}
                        className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-xl glass-tab-inactive text-slate-600 text-sm font-medium transition-colors"
                        title="Copy"
                      >
                        <span className="text-base">⎘</span> Copy
                      </button>
                      <button
                        type="button"
                        disabled={simplifying}
                        onClick={async () => {
                          if (simplifiedIndex === i) { setSimplifiedIndex(null); setSimplifiedContent(null); return; }
                          setSimplifying(true);
                          try {
                            const res = await simplifyAnswer(msg.content, msg.citations);
                            setSimplifiedIndex(i);
                            setSimplifiedContent(res.simplified || null);
                          } finally {
                            setSimplifying(false);
                          }
                        }}
                        className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-xl glass-tab-inactive text-slate-700 text-sm font-medium transition-colors disabled:opacity-50"
                      >
                        <span className="text-primary">💡</span> {simplifiedIndex === i ? 'Show original' : simplifying ? 'Simplifying…' : 'Explain simply'}
                      </button>
                      <button
                        type="button"
                        onClick={() => onVerify(i, msg.citations ?? [])}
                        disabled={verifying || !(msg.citations?.length)}
                        className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-xl glass-tab-inactive text-slate-700 text-sm font-medium transition-colors disabled:opacity-50"
                      >
                        <span className="text-primary">✓</span> {verifying ? 'Checking…' : 'Verify data'}
                      </button>
                      {(msg.confidence == null || msg.confidence < 60) && msg.content && (
                        <button
                          type="button"
                          onClick={() => { setSuggestEditIndex(suggestEditIndex === i ? null : i); setSuggestEditValue(''); }}
                          className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-xl border border-amber-200/80 bg-amber-50/80 text-amber-800 text-sm font-medium hover:bg-amber-100/80 backdrop-blur-sm transition-colors"
                        >
                          We&apos;re not sure – suggest edit
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => setAddToBrainIndex(i)}
                        className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-xl bg-primary-gradient text-white text-sm font-semibold border border-white/20 shadow-glass hover:opacity-95 transition-opacity"
                      >
                        <span className="text-white">💾</span> Save to project
                      </button>
                    </div>
                    {verifyResult?.messageIndex === i && (
                      <div className="mt-3">
                        <VerificationResultCard
                          summary={verifyResult.summary}
                          results={verifyResult.results ?? []}
                          useHubStyle
                        />
                      </div>
                    )}
                    {suggestEditIndex === i && (
                      <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50/50 p-3 space-y-2">
                        <p className="text-xs font-semibold text-amber-800">Suggest a correction</p>
                        <textarea
                          placeholder="Your corrected answer..."
                          value={suggestEditValue}
                          onChange={(e) => setSuggestEditValue(e.target.value)}
                          className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm min-h-[80px]"
                          rows={3}
                        />
                        <div className="flex gap-2">
                          <button
                            type="button"
                            disabled={suggestEditSubmitting || !suggestEditValue.trim()}
                            onClick={async () => {
                              const question = messages[i - 1]?.role === 'user' ? messages[i - 1].content : '';
                              if (!question) return;
                              setSuggestEditSubmitting(true);
                              try {
                                await suggestEdit(tenantId, namespace, question, suggestEditValue.trim(), msg.content);
                                setSuggestEditIndex(null);
                                setSuggestEditValue('');
                              } finally {
                                setSuggestEditSubmitting(false);
                              }
                            }}
                            className="px-3 py-1.5 rounded-lg bg-primary text-white text-xs font-bold disabled:opacity-50"
                          >
                            {suggestEditSubmitting ? 'Sending…' : 'Submit edit'}
                          </button>
                          <button type="button" onClick={() => { setSuggestEditIndex(null); setSuggestEditValue(''); }} className="px-3 py-1.5 rounded-lg border border-slate-200 text-xs font-bold">Cancel</button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </>
            )}
            {msg.role === 'assistant' && !hub && (
              <p className="text-slate-800 whitespace-pre-wrap">{simplifiedIndex === i && simplifiedContent ? simplifiedContent : msg.content}</p>
            )}
            {msg.role === 'assistant' && msg.content && !hub && (
              <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                <button
                  type="button"
                  onClick={() => {
                    const refs = msg.citations?.map((c, j) => `[${j + 1}] ${c.document_name}${c.page != null ? ` p.${c.page}` : ''}`).join('\n') ?? '';
                    const text = (simplifiedIndex === i && simplifiedContent ? simplifiedContent : msg.content) + (refs ? '\n\nSources:\n' + refs : '');
                    navigator.clipboard?.writeText(text).then(() => {}, () => {});
                  }}
                  className="text-primary hover:underline"
                >
                  Copy answer + sources
                </button>
                <button
                  type="button"
                  disabled={simplifying}
                  onClick={async () => {
                    if (simplifiedIndex === i) { setSimplifiedIndex(null); setSimplifiedContent(null); return; }
                    setSimplifying(true);
                    try {
                      const res = await simplifyAnswer(msg.content, msg.citations);
                      setSimplifiedIndex(i);
                      setSimplifiedContent(res.simplified || null);
                    } finally {
                      setSimplifying(false);
                    }
                  }}
                  className="text-primary hover:underline disabled:opacity-50"
                >
                  {simplifiedIndex === i ? 'Show original' : simplifying ? 'Simplifying…' : "Explain like I'm new"}
                </button>
                {!feedbackSent.has(i) && (
                  <>
                    <span className="text-slate-500">Was this helpful?</span>
                    <button type="button" onClick={async () => { await submitFeedback(tenantId, namespace, messages[i - 1]?.role === 'user' ? messages[i - 1].content : '', true, msg.content.slice(0, 500), undefined, msg.citations?.map((c) => c.document_id).filter((id): id is string => Boolean(id))); setFeedbackSent((s) => new Set(s).add(i)); setFeedbackIndex(null); }} className="text-green-600 hover:underline">👍</button>
                    <button type="button" onClick={() => setFeedbackIndex(feedbackIndex === i ? null : i)} className="text-red-600 hover:underline">👎</button>
                    {feedbackIndex === i && (
                      <span className="flex items-center gap-1">
                        <select value={whatWrong} onChange={(e) => setWhatWrong(e.target.value)} className="rounded border border-violet-200/40 px-1 py-0.5 text-xs">
                          <option value="">What was wrong?</option>
                          <option value="missing_info">Missing info</option>
                          <option value="wrong">Wrong</option>
                          <option value="outdated">Outdated</option>
                          <option value="other">Other</option>
                        </select>
                        <button type="button" onClick={async () => { await submitFeedback(tenantId, namespace, messages[i - 1]?.role === 'user' ? messages[i - 1].content : '', false, msg.content.slice(0, 500), whatWrong, msg.citations?.map((c) => c.document_id).filter((id): id is string => Boolean(id))); setFeedbackSent((s) => new Set(s).add(i)); setFeedbackIndex(null); setWhatWrong(''); }} className="text-primary text-xs">Send</button>
                      </span>
                    )}
                  </>
                )}
                <button type="button" onClick={() => { setSaveAnswerIndex(i); setSaveAnswerTag(''); setSaveAnswerNote(''); }} className="text-primary hover:underline">Save this answer</button>
              </div>
            )}
            {saveAnswerIndex === i && (
              <div className="mt-2 rounded-lg border border-violet-200/40 bg-emerald-50/50 p-2 space-y-2">
                <input type="text" placeholder="Tag (optional)" value={saveAnswerTag} onChange={(e) => setSaveAnswerTag(e.target.value)} className="w-full rounded border border-violet-200/40 px-2 py-1 text-sm glass-input" />
                <input type="text" placeholder="Note (optional)" value={saveAnswerNote} onChange={(e) => setSaveAnswerNote(e.target.value)} className="w-full rounded border border-violet-200/40 px-2 py-1 text-sm glass-input" />
                <div className="flex gap-2">
                  <button type="button" disabled={saveAnswerSubmitting} onClick={async () => { setSaveAnswerSubmitting(true); try { await addSavedAnswer(tenantId, namespace, messages[i - 1]?.role === 'user' ? messages[i - 1].content : '', msg.content, msg.citations, saveAnswerTag || undefined, saveAnswerNote || undefined); setSaveAnswerIndex(null); } finally { setSaveAnswerSubmitting(false); } }} className="text-xs bg-primary text-white px-2 py-1 rounded">Save</button>
                  <button type="button" onClick={() => setSaveAnswerIndex(null)} className="text-xs text-slate-500 hover:underline">Cancel</button>
                </div>
              </div>
            )}
            {msg.role === 'assistant' && msg.citations && msg.citations.length > 0 && !hub && (
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <div className="flex flex-wrap gap-1.5">
                  {msg.citations.map((c, j) => (
                    <span
                      key={j}
                      className={`cite-pill inline-flex items-center rounded-lg border px-2 py-0.5 text-xs font-medium ${freshnessColor(c.score)}`}
                      style={{ animationDelay: `${j * 70}ms` }}
                      title={`Score: ${(c.score * 100).toFixed(0)}%`}
                    >
                      {c.document_name}
                      {c.page != null && ` · p.${c.page}`}
                    </span>
                  ))}
                </div>
                <button
                  type="button"
                  onClick={() => onVerify(i, msg.citations!)}
                  disabled={verifying}
                  className="text-xs font-medium text-primary hover:underline disabled:opacity-50"
                >
                  {verifying ? 'Checking…' : 'Verify this answer'}
                </button>
              </div>
            )}
            {msg.role === 'assistant' && msg.content && !hub && (
              <button
                type="button"
                onClick={() => setAddToBrainIndex(i)}
                className="mt-2 text-xs font-medium text-primary hover:underline block"
              >
                Add this to the brain
              </button>
            )}
            {msg.role === 'assistant' && (msg.confidence == null || msg.confidence < 60) && msg.content && (
              <div className="mt-2">
                {suggestEditIndex !== i ? (
                  <button
                    type="button"
                    onClick={() => { setSuggestEditIndex(i); setSuggestEditValue(''); }}
                    className="text-xs font-medium text-slate-500 hover:text-primary"
                  >
                    We&apos;re not sure. Suggest an edit?
                  </button>
                ) : (
                  <div className="rounded-lg border border-violet-200/40 bg-emerald-50/50 p-2 space-y-2">
                    <textarea
                      placeholder="Your corrected answer..."
                      value={suggestEditValue}
                      onChange={(e) => setSuggestEditValue(e.target.value)}
                      className="w-full rounded border border-violet-200/40 glass-input px-2 py-1.5 text-sm min-h-[60px]"
                      rows={2}
                    />
                    <div className="flex gap-2">
                      <button
                        type="button"
                        disabled={suggestEditSubmitting || !suggestEditValue.trim()}
                        onClick={async () => {
                          const question = messages[i - 1]?.role === 'user' ? messages[i - 1].content : '';
                          if (!question) return;
                          setSuggestEditSubmitting(true);
                          try {
                            await suggestEdit(tenantId, namespace, question, suggestEditValue.trim(), msg.content);
                            setSuggestEditIndex(null);
                            setSuggestEditValue('');
                          } finally {
                            setSuggestEditSubmitting(false);
                          }
                        }}
                        className="text-xs font-medium text-primary hover:underline disabled:opacity-50"
                      >
                        {suggestEditSubmitting ? 'Sending…' : 'Submit edit'}
                      </button>
                      <button type="button" onClick={() => { setSuggestEditIndex(null); setSuggestEditValue(''); }} className="text-xs text-slate-500 hover:underline">Cancel</button>
                    </div>
                  </div>
                )}
              </div>
            )}
            {msg.role === 'assistant' && msg.noAnswerFromDocs && (
              <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50/80 dark:bg-violet-50/80 px-3 py-2 text-sm">
                <p className="font-medium text-amber-800 dark:text-slate-800">We don&apos;t have this in the brain.</p>
                <p className="text-slate-500 text-xs mt-1">Add it so next time we can answer. Use &quot;Add this to the brain&quot; below after you paste or write an answer, or add a source in Knowledge Sources.</p>
              </div>
            )}
            {addToBrainIndex === i && (
              <div className="mt-3 rounded-lg border border-violet-200/40 bg-emerald-50/50 p-3 space-y-2">
                <p className="text-xs text-slate-500">Save this Q&A to the knowledge base. The brain will use it for future answers.</p>
                <div className="flex gap-2 items-center flex-wrap">
                  <button
                    type="button"
                    disabled={addToBrainSubmitting}
                    onClick={async () => {
                      const question = messages[i - 1]?.role === 'user' ? messages[i - 1].content : 'From chat';
                      setAddToBrainSubmitting(true);
                      try {
                        await addToBrain(tenantId, namespace, question.slice(0, 200), msg.content);
                        setAddToBrainIndex(null);
                      } finally {
                        setAddToBrainSubmitting(false);
                      }
                    }}
                    className="text-xs font-medium bg-primary text-white px-2 py-1 rounded hover:opacity-90 disabled:opacity-50"
                  >
                    {addToBrainSubmitting ? 'Adding…' : 'Add to brain'}
                  </button>
                  <button type="button" onClick={() => setAddToBrainIndex(null)} className="text-xs text-slate-500 hover:underline">Cancel</button>
                </div>
              </div>
            )}
            {verifyResult?.messageIndex === i && (
              <div className="mt-3">
                <VerificationResultCard
                  summary={verifyResult.summary}
                  results={verifyResult.results ?? []}
                  useHubStyle={false}
                />
              </div>
            )}
          </div>
        ))}
        {showThinking && !streamBuffer && (
          <div className="mr-8 rounded-xl px-4 py-3 glass-card">
            <p className="text-sm text-slate-500">
              BrainOS is thinking
              <span className="inline-block animate-pulse">...</span>
            </p>
          </div>
        )}
        {streamBuffer && (
          <div className="mr-8 rounded-xl px-4 py-3 glass-card max-w-3xl">
            <p className={`whitespace-pre-wrap ${hub ? 'text-slate-900' : 'text-slate-800'}`}>
              {streamBuffer}
              <span className="stream-cursor" />
            </p>
            {currentCites.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {currentCites.map((c, j) => (
                  <span
                    key={j}
                    className={`cite-pill inline-flex items-center rounded-lg border px-2 py-0.5 text-xs font-medium ${freshnessColor(c.score)}`}
                    style={{ animationDelay: `${j * 70}ms` }}
                  >
                    {c.document_name}
                    {c.page != null && ` · p.${c.page}`}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        {/* People also asked — inside scroll for single continuous view */}
        {relatedQuestions.length > 0 && !streaming && messages.some((m) => m.role === 'assistant') && (
          <div className={hub ? 'pt-2' : 'px-0'}>
            <p className={`text-xs font-medium mb-1.5 ${hub ? 'text-slate-400 uppercase tracking-widest' : 'text-slate-500'}`}>People also asked</p>
            <div className="flex flex-wrap gap-2">
              {relatedQuestions.slice(0, 8).map((q, i) => (
                <button key={i} type="button" onClick={() => { setInput(q); onSuggestionClick?.(q); }} className={hub ? 'px-4 py-2 rounded-full border border-primary/20 hover:border-primary hover:bg-primary/5 text-sm font-medium transition-all' : 'rounded-full border border-violet-200/40 bg-violet-50/80 px-3 py-1.5 text-xs text-slate-800 hover:bg-emerald-50/50 hover:border-primary/50'}>
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Guided Next Steps — inside scroll, single flow; cards match reference (Category - Question, purple icons) */}
        {followUps.length > 0 && !streaming && (
          <div className={hub ? 'space-y-4 pt-6' : 'pt-4'}>
            <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-3">Guided Next Steps</h3>
            {hub ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-4xl">
                {[
                  { Icon: IconComplianceChart, label: 'Compliance' },
                  { Icon: IconComparison, label: 'Comparison' },
                  { Icon: IconActionPlan, label: 'Action Plan' },
                  { Icon: IconTechnical, label: 'Technical' },
                ].map(({ Icon, label }, i) => {
                  const question = followUps[i] ?? (i === 0 ? 'What are the key compliance requirements?' : i === 1 ? 'How does this compare with other approaches?' : i === 2 ? 'What are the recommended next steps?' : 'What are the technical details?');
                  return (
                    <button
                      key={i}
                      type="button"
                      onClick={() => { setInput(question); onSuggestionClick?.(question); }}
                      className="flex items-start gap-3 p-4 rounded-xl glass-card hover:bg-white/80 transition-all text-left"
                    >
                      <span className="flex shrink-0 w-10 h-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                        <Icon className="w-5 h-5" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm text-slate-700 leading-snug">
                          <span className="font-semibold text-slate-800">{label}</span>
                          <span className="text-slate-500"> – </span>
                          <span>{question}</span>
                        </p>
                      </div>
                    </button>
                  );
                })}
              </div>
            ) : (
              <div className="flex flex-wrap gap-2">
                {followUps.map((q, i) => (
                  <button key={i} type="button" onClick={() => { setInput(q); onSuggestionClick?.(q); }} className="rounded-full border border-violet-200/40 bg-violet-50/80 px-3 py-1.5 text-xs text-slate-800 hover:bg-emerald-50/50 hover:border-primary/50">
                    {q}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Status bar + Export — inside scroll */}
        <div className={`py-4 flex items-center justify-between gap-2 flex-wrap text-xs ${hub ? 'text-slate-500' : 'text-slate-500'}`}>
          <span>
            {(currentCites.length > 0 || currentConf != null) && `Querying ${currentCites.length} source${currentCites.length !== 1 ? 's' : ''} · chunks from knowledge base · Last verified recently`}
          </span>
          {messages.length > 0 && (
            <button
              type="button"
              onClick={() => {
                const lines: string[] = ['# Conversation export', ''];
                messages.forEach((m) => {
                  lines.push(m.role === 'user' ? `## Question\n${m.content}` : `## Answer\n${m.content}`);
                  if (m.role === 'assistant' && m.citations?.length) {
                    lines.push('\n**Sources:**');
                    m.citations.forEach((c, j) => lines.push(`- [${j + 1}] ${c.document_name}${c.page != null ? ` p.${c.page}` : ''}`));
                  }
                  lines.push('');
                });
                const blob = new Blob([lines.join('\n')], { type: 'text/markdown' });
                const a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = `brainos-chat-${new Date().toISOString().slice(0, 10)}.md`;
                a.click();
                URL.revokeObjectURL(a.href);
              }}
              className={hub ? 'text-primary hover:underline font-semibold' : 'text-primary hover:underline'}
            >
              Export conversation
            </button>
          )}
        </div>

        {/* Refine Context — inside scroll for single continuous view */}
        <details className={hub ? 'group' : 'max-w-3xl'} open={showPasteContext}>
          <summary
            className={`cursor-pointer list-none ${hub ? 'flex items-center gap-2 text-[10px] font-bold text-slate-400 uppercase tracking-widest hover:text-primary transition-colors' : 'text-sm font-medium text-slate-500 hover:text-slate-800'}`}
            onClick={(e) => { e.preventDefault(); setShowPasteContext((v) => !v); }}
          >
            {hub && <span className="transition-transform group-open:rotate-180">▾</span>}
            {hub ? 'Refine Context (Current Project)' : 'Ask about this — paste text from a doc, email, or Confluence'}
          </summary>
          <textarea
            placeholder={hub ? 'Add specific decision parameters or internal constraints...' : 'Paste selected text here; your question will be answered using both this and your knowledge base.'}
            value={pastedContext ?? ''}
            onChange={(e) => onPastedContextChange?.(e.target.value)}
            rows={2}
            className={`mt-2 w-full rounded-xl text-sm resize-none ${hub ? 'bg-slate-50 border border-slate-200 focus:ring-primary focus:border-primary' : 'border border-violet-200/40 glass-input text-slate-800 placeholder:text-slate-400'}`}
          />
        </details>

        <div ref={bottomRef} />
      </div>

      {/* Fixed footer: input only — glassmorphic */}
      <div className="shrink-0 p-6 pt-0 border-t border-white/20 bg-white/50 backdrop-blur-md">
        <form
          onSubmit={(e) => { e.preventDefault(); send(); }}
          className={hub ? 'flex items-center gap-3 glass-card p-2 focus-within:ring-2 ring-primary/20 transition-all' : 'flex gap-2 max-w-3xl items-end glass-card p-2 rounded-2xl'}
        >
          <button type="button" onClick={toggleVoice} title="Voice" disabled={streaming} className={`p-2 shrink-0 ${hub ? 'text-slate-400 hover:text-primary transition-colors' : 'rounded-lg p-2.5 ' + (listening ? 'bg-rose-50 text-rose-600' : 'bg-violet-50/80 text-slate-500 hover:bg-violet-200/40')}`}>🎤</button>
          <textarea
            ref={textareaRef}
            value={input}
            onChange={handleTextareaChange}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
            placeholder={hub ? 'Explore further or ask a new question...' : 'Ask about your knowledge base...'}
            rows={1}
            className={`flex-1 min-h-[44px] max-h-[96px] rounded-lg border px-4 py-2 resize-none overflow-y-auto disabled:opacity-60 bg-transparent border-none focus:ring-0 ${
              hub ? 'text-sm py-2 placeholder:text-slate-400' : 'border border-violet-200/40 glass-input text-slate-800 placeholder:text-slate-400 focus:border-primary focus:ring-1 focus:ring-primary'
            }`}
            disabled={streaming}
          />
          {onSaveQuestion && input.trim() && (
            <button type="button" onClick={() => onSaveQuestion(input.trim())} disabled={streaming} className={`p-2 shrink-0 ${hub ? 'text-slate-400 hover:text-primary' : 'text-sm text-slate-500 hover:text-primary'}`} title="Save question">💾</button>
          )}
          <button type="submit" disabled={streaming || !input.trim()} className="shrink-0 bg-primary-gradient text-white p-2.5 rounded-xl flex items-center justify-center hover:opacity-95 transition-opacity shadow-glass border border-white/20 disabled:opacity-50">
            {streaming ? '…' : '➤'}
          </button>
        </form>
      </div>
    </main>
  );
}
