'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { getDeployChannelStats, getSourceConnections, connectSourceProvider, meetingSummarize } from '@/lib/api';
import { useBrain } from '@/contexts/BrainContext';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const ZAYA_WEB_APP_DEMO_URL = `${API_BASE.replace(/\/$/, '')}/static/demo.html`;

const CHANNELS = [
  { id: 'widget', name: 'Web Widget', desc: 'Embed live chat on your site', icon: '🌐', path: '/widget' },
  { id: 'slack', name: 'Slack', desc: 'Answers in Slack threads', icon: '💬' },
  { id: 'whatsapp', name: 'WhatsApp', desc: 'Customer-facing via WhatsApp Business', icon: '📱' },
  { id: 'teams', name: 'Microsoft Teams', desc: 'Answers inside Teams channels', icon: '👥' },
  { id: 'api', name: 'REST API', desc: 'JSON payloads for any app', icon: '🔌' },
  { id: 'gpt', name: 'Custom GPT', desc: 'Connect as custom GPT endpoint', icon: '🤖' },
  { id: 'meeting', name: 'Meeting summary', desc: 'Paste transcript → summary, decisions, action items', icon: '📋' },
];

function ConnectSlackBlock({ tenantId }: { tenantId: string }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const handleConnect = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await connectSourceProvider('slack', tenantId);
      if (res?.configured && res?.auth_url) {
        window.location.href = res.auth_url;
        return;
      }
      setError(res?.message || 'Slack OAuth not configured. Set SLACK_CLIENT_ID and SLACK_CLIENT_SECRET.');
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };
  return (
    <div>
      <button
        type="button"
        onClick={handleConnect}
        disabled={loading}
        className="rounded-lg bg-primary text-white px-4 py-2 text-sm font-medium hover:opacity-90 disabled:opacity-50"
      >
        {loading ? 'Connecting…' : 'Connect Slack'}
      </button>
      {error && <p className="mt-2 text-xs text-amber-600">{error}</p>}
    </div>
  );
}

function MeetingSummaryBlock() {
  const [transcript, setTranscript] = useState('');
  const [title, setTitle] = useState('Meeting');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ ok?: boolean; summary?: string; decisions?: string[]; action_items?: Array<{ owner?: string; task?: string; due?: string | null }>; open_questions?: string[]; error?: string } | null>(null);
  const handleSummarize = async () => {
    if (!transcript.trim()) return;
    setLoading(true);
    setResult(null);
    try {
      const data = await meetingSummarize(transcript.trim(), title.trim() || 'Meeting');
      setResult(data);
    } catch (e) {
      setResult({ ok: false, error: String(e) });
    } finally {
      setLoading(false);
    }
  };
  return (
    <div className="space-y-3 mt-3">
      <div>
        <label className="block text-xs font-medium text-slate-500 mb-1">Title</label>
        <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} className="w-full rounded-lg border border-violet-200/40 bg-violet-50/80 px-3 py-2 text-sm" placeholder="Meeting title" />
      </div>
      <div>
        <label className="block text-xs font-medium text-slate-500 mb-1">Transcript (paste here)</label>
        <textarea value={transcript} onChange={(e) => setTranscript(e.target.value)} rows={6} className="w-full rounded-lg border border-violet-200/40 bg-violet-50/80 px-3 py-2 text-sm font-mono" placeholder="Speaker 1: ...&#10;Speaker 2: ..." />
      </div>
      <button type="button" onClick={handleSummarize} disabled={loading || !transcript.trim()} className="rounded-lg bg-primary text-white px-4 py-2 text-sm font-medium hover:opacity-90 disabled:opacity-50">
        {loading ? 'Summarizing…' : 'Generate summary'}
      </button>
      {result && (
        <div className="rounded-lg border border-violet-200/40 bg-violet-50/30 p-3 text-sm">
          {result.ok ? (
            <>
              {result.summary && <p className="text-slate-800">{result.summary}</p>}
              {result.decisions && result.decisions.length > 0 && (
                <p className="mt-2"><strong>Decisions:</strong> {result.decisions.join('; ')}</p>
              )}
              {result.action_items && result.action_items.length > 0 && (
                <ul className="mt-2 list-disc pl-5">
                  {result.action_items.map((a, i) => (
                    <li key={i}>{a.owner}: {a.task}{a.due ? ` (by ${a.due})` : ''}</li>
                  ))}
                </ul>
              )}
              {result.open_questions && result.open_questions.length > 0 && (
                <p className="mt-2"><strong>Open questions:</strong> {result.open_questions.join('; ')}</p>
              )}
            </>
          ) : (
            <p className="text-rose-600">{result.error || 'Failed to summarize.'}</p>
          )}
        </div>
      )}
    </div>
  );
}

export default function DeployPage() {
  const { tenantId } = useBrain();
  const [previewOpen, setPreviewOpen] = useState(true);
  const [panelChannel, setPanelChannel] = useState<typeof CHANNELS[0] | null>(null);
  const [channelStats, setChannelStats] = useState<Record<string, { connected?: boolean; queries_today?: number }>>({});

  useEffect(() => {
    getDeployChannelStats(tenantId).then((d) => setChannelStats(d.channels || {})).catch(() => setChannelStats({}));
  }, [tenantId]);

  return (
    <div className="h-full flex overflow-hidden">
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-6 py-8">
          <h1 className="text-xl font-semibold text-slate-800">Deploy</h1>
          <p className="mt-1 text-sm text-slate-500">Deployment channels. Click a channel to configure.</p>
          <div className="mt-4 rounded-lg border border-violet-200/40 bg-violet-50/30 px-4 py-3 flex items-center justify-between gap-2 flex-wrap">
            <span className="text-sm text-slate-700">ZAYA Web App Support — try the embeddable widget (Zendesk, CRM, Jira, Notion, HR, etc.)</span>
            <a href={ZAYA_WEB_APP_DEMO_URL} target="_blank" rel="noopener noreferrer" className="rounded-lg bg-primary text-white px-3 py-1.5 text-sm font-medium hover:opacity-90 whitespace-nowrap">
              Open ZAYA Web App Demo
            </a>
          </div>
          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            {CHANNELS.map((ch) => {
              const stats = channelStats[ch.id];
              const connected = stats?.connected ?? false;
              const queries = stats?.queries_today ?? 0;
              return (
                <div
                  key={ch.id}
                  className="rounded-xl border border-violet-200/40 glass-card p-5 shadow-card hover:border-primary/40 transition-colors cursor-pointer"
                  onClick={() => setPanelChannel(ch)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => e.key === 'Enter' && setPanelChannel(ch)}
                >
                  <span className="text-2xl">{ch.icon}</span>
                  <h3 className="mt-2 font-medium text-slate-800">{ch.name}</h3>
                  <p className="mt-0.5 text-sm text-slate-500">{ch.desc}</p>
                  <div className="mt-2 flex items-center gap-2 flex-wrap">
                    {connected && <span className="text-xs font-medium text-emerald-600 bg-emerald-50/80 px-2 py-0.5 rounded">Connected</span>}
                    {queries > 0 && <span className="text-xs text-slate-500">Queries today: {queries}</span>}
                  </div>
                  {ch.path ? (
                    <Link href={ch.path} className="mt-3 inline-block rounded-lg bg-primary/20 text-primary px-3 py-1.5 text-sm" onClick={(e) => e.stopPropagation()}>
                      Preview
                    </Link>
                  ) : (
                    <span className="mt-3 inline-block rounded-lg bg-violet-50/80 text-slate-500 px-3 py-1.5 text-sm">Configure</span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Slide-in setup panel */}
      {panelChannel && (
        <aside className="w-[400px] shrink-0 border-l border-violet-200/40 glass-card flex flex-col shadow-soft">
          <div className="flex items-center justify-between border-b border-violet-200/40 p-4">
            <h2 className="font-semibold text-slate-800">{panelChannel.name} setup</h2>
            <button type="button" onClick={() => setPanelChannel(null)} className="text-slate-500 hover:text-slate-800">✕</button>
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {panelChannel.id === 'widget' && (
              <>
                <div>
                  <label className="block text-xs font-medium text-slate-500 mb-1">Widget title</label>
                  <input type="text" defaultValue="Chat with us" className="w-full rounded-lg border border-violet-200/40 bg-violet-50/80 px-3 py-2 text-sm" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-500 mb-1">Welcome message</label>
                  <input type="text" defaultValue="Ask me anything." className="w-full rounded-lg border border-violet-200/40 bg-violet-50/80 px-3 py-2 text-sm" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-500 mb-1">Accent color</label>
                  <input type="color" defaultValue="#7EB8A4" className="h-10 w-full rounded border border-violet-200/40" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-500 mb-1">Embed code</label>
                  <pre className="rounded-lg border border-violet-200/40 bg-violet-50/80 p-3 text-xs text-slate-500 overflow-x-auto">
                    {`<script src="https://your-brainos.app/widget.js" data-brain="default"></script>`}
                  </pre>
                  <button type="button" className="mt-2 rounded-lg border border-violet-200/40 px-3 py-1.5 text-xs text-slate-800">Copy</button>
                </div>
              </>
            )}
            {panelChannel.id === 'api' && (
              <>
                <div>
                  <label className="block text-xs font-medium text-slate-500 mb-1">API key</label>
                  <input type="password" placeholder="sk-••••••••" className="w-full rounded-lg border border-violet-200/40 bg-violet-50/80 px-3 py-2 text-sm" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-500 mb-1">Endpoint URL</label>
                  <input type="url" placeholder="https://api.brainos.app/v1/chat" className="w-full rounded-lg border border-violet-200/40 bg-violet-50/80 px-3 py-2 text-sm" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-500 mb-1">Request builder</label>
                  <pre className="rounded-lg border border-violet-200/40 bg-violet-50/80 p-3 text-xs text-slate-500">
                    POST /v1/chat{'\n'}
                    {`{ "question": "..." }`}
                  </pre>
                </div>
              </>
            )}
            {(panelChannel.id === 'slack' || panelChannel.id === 'teams' || panelChannel.id === 'whatsapp') && (
              <>
                {panelChannel.id === 'slack' && (
                  <>
                    <p className="text-sm text-slate-500">Connect your Slack workspace via OAuth. After connecting, add the bot to channels and set Event Subscriptions URL in your Slack app.</p>
                    <ConnectSlackBlock tenantId={tenantId} />
                    <div className="rounded-lg border border-violet-200/40 bg-violet-50/50 p-3 text-xs text-slate-600 space-y-1">
                      <p className="font-medium text-slate-700">Slack app setup:</p>
                      <p>1. Create an app at api.slack.com. Add redirect URI: <code className="bg-white px-1 rounded">https://your-backend/api/sources/connections/slack/callback</code></p>
                      <p>2. Set Event Subscriptions Request URL to your backend: <code className="bg-white px-1 rounded">/api/bots/slack/events</code></p>
                      <p>3. Subscribe to <strong>app_mention</strong>. Add scopes: app_mentions:read, chat:write, channels:read.</p>
                      <p>4. Set SLACK_CLIENT_ID, SLACK_CLIENT_SECRET, BACKEND_URL (and optionally SLACK_SIGNING_SECRET) in backend env.</p>
                    </div>
                  </>
                )}
                {(panelChannel.id === 'whatsapp' || panelChannel.id === 'teams') && (
                  <>
                    <p className="text-sm text-slate-500">Connect via OAuth in Settings. Configure webhook URL and channels.</p>
                    <p className="text-xs text-amber-600 mt-2">WhatsApp &amp; Teams OAuth: coming soon. Use Slack for now.</p>
                  </>
                )}
              </>
            )}
            {panelChannel.id === 'gpt' && (
              <p className="text-sm text-slate-500">Use your BrainOS API endpoint as the Custom GPT backend URL.</p>
            )}
            {panelChannel.id === 'meeting' && (
              <>
                <p className="text-sm text-slate-500">Paste a meeting transcript to generate a summary (decisions, action items, open questions). Connect Zoom/Meet for automatic notes.</p>
                <MeetingSummaryBlock />
              </>
            )}
          </div>
        </aside>
      )}

      {previewOpen && !panelChannel && (
        <aside className="w-[380px] shrink-0 border-l border-violet-200/40 bg-violet-50/95 flex flex-col">
          <div className="flex items-center justify-between border-b border-violet-200/40 p-3">
            <span className="text-sm font-medium text-slate-800">Widget preview</span>
            <button type="button" onClick={() => setPreviewOpen(false)} className="text-slate-500">Close</button>
          </div>
          <div className="flex-1 min-h-[400px]">
            <iframe src="/widget" title="Widget" className="w-full h-full rounded-b-xl" />
          </div>
        </aside>
      )}
      {!previewOpen && !panelChannel && (
        <button type="button" onClick={() => setPreviewOpen(true)} className="fixed right-4 bottom-4 rounded-full bg-primary text-white p-2">Preview</button>
      )}
    </div>
  );
}
