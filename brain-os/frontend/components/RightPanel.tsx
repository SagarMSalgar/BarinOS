'use client';

import type { Citation } from '@/components/ChatPanel';
import { IconRefresh, IconLegal, IconCode, IconBook } from '@/components/Icons';

export type RecentUpdates = {
  documents: Array<{ name: string; last_verified_at?: string | null; updated_at?: string | null }>;
  count: number;
} | null;

export interface RightPanelProps {
  citations: Citation[];
  confidence: number | null;
  followUps: string[];
  selectedDoc: string | null;
  onSelectDoc: (doc: string | null) => void;
  useHubStyle?: boolean;
  fullContent?: string;
  onClose?: () => void;
  recentUpdates?: RecentUpdates;
}

export function RightPanel({
  citations,
  confidence,
  followUps,
  selectedDoc,
  onSelectDoc,
  useHubStyle = false,
  fullContent,
  onClose,
  recentUpdates = null,
}: RightPanelProps) {
  const hasCitations = citations.length > 0;
  const isIdle = !hasCitations;
  const selectedCitation = selectedDoc ? citations.find((c) => c.document_name === selectedDoc) : null;

  const freshnessLabel = (score: number) =>
    score >= 0.8 ? 'Recent' : score >= 0.5 ? 'Moderate' : 'Stale';
  const freshnessColor = (score: number) =>
    score >= 0.8 ? 'text-emerald-600' : score >= 0.5 ? 'text-amber-600' : 'text-rose-600';
  const riskLevel = confidence != null ? (confidence >= 80 ? 'Low' : confidence >= 50 ? 'Moderate' : 'High') : null;

  if (useHubStyle) {
    const riskMarkerLeft = riskLevel === 'High' ? 85 : riskLevel === 'Moderate' ? 45 : 15;
    const freshnessText = recentUpdates?.count != null && recentUpdates.count > 0
      ? `${recentUpdates.count} source${recentUpdates.count !== 1 ? 's' : ''} updated recently`
      : hasCitations || confidence != null
        ? 'Based on doc last verified recently'
        : null;
    const isLive = recentUpdates?.count != null && recentUpdates.count > 0;

    // Key themes: unique tokens from citation names (e.g. "Legal_Regs_2024" -> "Legal", "Regs", "2024")
    const themeTokens = Array.from(
      new Set(
        citations.flatMap((c) =>
          (c.document_name || '')
            .replace(/[-_.]/g, ' ')
            .split(/\s+/)
            .filter((t) => t.length > 2 && !/^\d+$/.test(t))
        )
      )
    ).slice(0, 6);

    // Group citations into categories by name heuristic (data-driven)
    const legal = citations.filter((c) => /legal|reg|gdpr|compliance|law|regulation/i.test(c.document_name || ''));
    const technical = citations.filter((c) => /manual|spec|technical|tech|api|v\d|\.pdf/i.test(c.document_name || ''));
    const wiki = citations.filter((c) => !legal.includes(c) && !technical.includes(c));
    const sourceCategories = [
      { key: 'legal', label: 'Legal Compliance', count: legal.length, desc: `${legal.length} major document${legal.length !== 1 ? 's' : ''} found`, Icon: IconLegal },
      { key: 'technical', label: 'Technical Specs', count: technical.length, desc: technical.length ? 'Infrastructure & manuals' : 'No technical docs', Icon: IconCode },
      { key: 'wiki', label: 'Industry Wiki', count: wiki.length, desc: wiki.length ? 'Best practices & guides' : 'Other sources', Icon: IconBook },
    ].filter((c) => c.count > 0);

    return (
      <aside className="w-80 shrink-0 flex flex-col border-l border-white/20 glass-header flex">
        <div className="p-6 border-b border-white/20">
          <div className="flex items-center justify-between gap-2 mb-4">
            <h2 className="text-sm font-bold text-slate-800">Contextual Overview</h2>
            {onClose && (
              <button type="button" onClick={onClose} className="p-1.5 rounded-xl hover:bg-white/50 text-slate-500" title="Close">✕</button>
            )}
          </div>
          <div className="space-y-3">
            {confidence != null && (
              <div className="glass-card p-4">
                <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2">Understanding Score</p>
                <div className="flex justify-between items-center mb-2">
                  <span className="text-xs text-slate-600">Confidence</span>
                  <span className="text-sm font-bold text-primary">{confidence}%</span>
                </div>
                <div className="h-2 w-full bg-primary/10 rounded-full overflow-hidden">
                  <div className="h-full bg-primary-gradient rounded-full transition-[width]" style={{ width: `${Math.min(100, confidence)}%` }} />
                </div>
              </div>
            )}
            {(hasCitations || confidence != null) && (
              <div className="flex items-center justify-between gap-2 px-3 py-2.5 rounded-xl glass-card">
                <div className="flex items-center gap-2">
                  <IconRefresh className="w-4 h-4 text-primary" />
                  <span className="text-xs font-bold text-slate-700">Freshness Level</span>
                </div>
                {isLive ? (
                  <span className="px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-700 text-[10px] font-bold border border-emerald-200 uppercase">Live</span>
                ) : freshnessText ? (
                  <span className="text-[10px] font-semibold text-slate-600 truncate max-w-[100px]" title={freshnessText}>{freshnessText}</span>
                ) : (
                  <span className="text-[10px] font-semibold text-slate-500">Recent</span>
                )}
              </div>
            )}
            {isIdle && !confidence && (
              <div className="rounded-xl glass-card p-4 text-center">
                <p className="text-sm text-slate-500">Ask a question, then click &quot;Expand for Technical Detail & Full Citations&quot; to see this overview.</p>
              </div>
            )}
          </div>
        </div>
        <div className="flex-1 overflow-y-auto custom-scrollbar p-6 space-y-6">
          {themeTokens.length > 0 && (
            <div>
              <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">Key Themes Detected</h3>
              <div className="flex flex-wrap gap-2">
                {themeTokens.map((t, i) => (
                  <span key={i} className="px-2.5 py-1 rounded-lg bg-slate-100 text-slate-700 text-xs font-medium border border-slate-200">
                    {t}
                  </span>
                ))}
              </div>
            </div>
          )}

          {sourceCategories.length > 0 && (
            <div>
              <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">Top Source Categories</h3>
              <div className="space-y-2">
                {sourceCategories.map(({ key, label, count, desc, Icon }) => (
                  <div key={key} className="flex items-center gap-3 p-3 rounded-xl border border-slate-200 bg-white">
                    <span className="flex shrink-0 w-9 h-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
                      <Icon className="w-5 h-5" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-bold text-slate-800">{label}</p>
                      <p className="text-[10px] text-slate-500 mt-0.5">{desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {fullContent && (
            <div>
              <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">Technical Detail & Full Answer</h3>
              <div className="p-3 rounded-xl glass-card text-sm text-slate-700 whitespace-pre-wrap leading-relaxed">
                {fullContent}
              </div>
            </div>
          )}
          {confidence != null && (
            <div>
              <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">Risk Assessment</h3>
              <div className="space-y-2">
                <div className="flex justify-between text-[10px] font-bold">
                  <span>Regulatory / answer certainty</span>
                  <span className={riskLevel === 'High' ? 'text-red-500' : riskLevel === 'Moderate' ? 'text-amber-500' : 'text-emerald-600'}>{riskLevel}</span>
                </div>
                <div className="h-2 w-full risk-gradient rounded-full relative">
                  <div className="absolute top-0 bottom-0 w-1 bg-slate-900 border border-white shadow-sm rounded" style={{ left: `${riskMarkerLeft}%` }} />
                </div>
              </div>
            </div>
          )}

          {followUps.length > 0 && (
            <div>
              <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">Recommendations</h3>
              <div className="space-y-2">
                {followUps.slice(0, 3).map((q, i) => (
                  <div key={i} className="p-3 bg-primary/5 border-l-2 border-primary rounded-r-lg">
                    <p className="text-xs font-medium text-slate-800">{q}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {hasCitations && (
            <div>
              <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">Cited Sources</h3>
              <div className="space-y-2">
                {citations.map((c, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => onSelectDoc(selectedDoc === c.document_name ? null : c.document_name)}
                    className="group w-full p-2.5 rounded-xl bg-white border border-slate-200 hover:border-primary/20 hover:shadow-md transition-all cursor-pointer text-left"
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[10px] font-bold truncate text-slate-700">{c.document_name}</span>
                      <span className="text-[9px] font-bold text-primary">{(c.score * 100).toFixed(0)}% match</span>
                    </div>
                    <div className="h-1 w-full bg-slate-100 rounded-full overflow-hidden">
                      <div className="h-full bg-primary/40 rounded-full transition-[width]" style={{ width: `${(c.score * 100).toFixed(0)}%` }} />
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
        <div className="p-6 mt-auto shrink-0">
          <button
            type="button"
            className="w-full py-3 rounded-xl bg-primary-gradient text-white text-sm font-semibold hover:opacity-95 transition-opacity flex items-center justify-center gap-2 shadow-sm"
          >
            <span>+</span> Add exploration sources
          </button>
        </div>
      </aside>
    );
  }

  return (
    <aside className="flex w-[320px] shrink-0 flex-col border-l border-violet-200/40 glass-card shadow-glass">
      <div className="border-b border-violet-200/40 p-3">
        <h2 className="text-sm font-semibold text-slate-800">Source viewer</h2>
        <p className="text-xs text-slate-500">Cited documents</p>
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-4">
        {isIdle && (
          <div className="rounded-xl border border-violet-200/40 bg-violet-50/50 p-4 text-center">
            <p className="text-sm text-slate-500">Ask a question to see sources.</p>
            <p className="mt-2 text-xs text-slate-500">Knowledge freshness</p>
            <p className="text-xs text-slate-800">Based on doc last verified recently</p>
          </div>
        )}

        {hasCitations && selectedCitation && (
          <section>
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Selected source</h3>
              <button type="button" onClick={() => onSelectDoc(null)} className="text-xs text-primary hover:underline">Clear</button>
            </div>
            <div className="mt-2 rounded-lg border border-primary/30 bg-emerald-50/50 p-3">
              <p className="font-medium text-slate-800">{selectedCitation.document_name}</p>
              {selectedCitation.page != null && <p className="text-xs text-slate-500 mt-0.5">Page {selectedCitation.page}</p>}
              <p className="text-xs text-slate-500 mt-2 italic">Content from this source was used in the answer.</p>
            </div>
          </section>
        )}

        {hasCitations && (
          <section>
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Citations</h3>
            <ul className="mt-2 space-y-1">
              {citations.map((c, i) => (
                <li key={i}>
                  <button
                    type="button"
                    onClick={() => onSelectDoc(selectedDoc === c.document_name ? null : c.document_name)}
                    className={`w-full rounded-lg px-2 py-1.5 text-left text-sm border ${
                      selectedDoc === c.document_name ? 'bg-primary/20 text-slate-800 border-primary/40' : 'text-slate-500 hover:bg-violet-50/80 border-transparent'
                    }`}
                  >
                    <span className="flex items-center justify-between gap-1">
                      <span>{c.document_name}</span>
                      <span className={`text-xs ${freshnessColor(c.score)}`}>{freshnessLabel(c.score)}</span>
                    </span>
                    {c.page != null && <span className="text-xs text-slate-500">p.{c.page}</span>}
                    <span className="ml-1 text-primary">{(c.score * 100).toFixed(0)}%</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {confidence != null && (
          <section>
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Confidence</h3>
            <div className="mt-2 flex items-center gap-2">
              <div className="h-2 flex-1 rounded-full bg-violet-100">
                <div className="h-2 rounded-full bg-primary transition-[width]" style={{ width: `${Math.min(100, confidence)}%` }} />
              </div>
              <span className="text-sm font-mono text-slate-800">{confidence}%</span>
            </div>
            {confidence < 50 && (
              <p className="mt-1 text-xs text-amber-600">Low confidence — answer may be uncertain. Consider adding more relevant sources.</p>
            )}
          </section>
        )}

        {hasCitations && (
          <section>
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Knowledge freshness</h3>
            <p className="mt-1 text-xs text-slate-500">Based on doc last verified recently</p>
          </section>
        )}

        {followUps.length > 0 && (
          <section>
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Follow-up questions</h3>
            <ul className="mt-2 space-y-1">
              {followUps.map((q, i) => (
                <li key={i} className="rounded-lg border border-violet-200/40 bg-violet-50/50 px-2 py-1.5 text-xs text-slate-800">{q}</li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </aside>
  );
}
