'use client';

import { useState, useRef, useCallback } from 'react';
import { streamChat } from '@/lib/api';

const TENANT = 'default';
const NAMESPACE = 'main';

export default function WidgetPage() {
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [streamBuffer, setStreamBuffer] = useState('');
  const [history, setHistory] = useState<Array<{ role: 'user' | 'assistant'; content: string }>>([]);
  const ref = useRef('');

  const send = useCallback(async () => {
    const q = input.trim();
    if (!q || streaming) return;
    setInput('');
    setHistory((h) => [...h, { role: 'user', content: q }]);
    setStreaming(true);
    setStreamBuffer('');
    ref.current = '';
    try {
      await streamChat(TENANT, NAMESPACE, q, (event) => {
        if (event.type === 'token') {
          const t = (event.payload?.text as string) || '';
          ref.current += t;
          setStreamBuffer(ref.current);
        }
      });
    } catch (e) {
      ref.current += ` [Error: ${String(e)}]`;
      setStreamBuffer(ref.current);
    } finally {
      setStreaming(false);
      setHistory((h) => [...h, { role: 'assistant', content: ref.current }]);
      setStreamBuffer('');
    }
  }, [input, streaming]);

  return (
    <div className="min-h-screen theme-page-bg text-slate-800 p-4 flex flex-col max-w-lg mx-auto">
      <h1 className="text-lg font-semibold mb-4">Chat</h1>
      <div className="flex-1 overflow-y-auto space-y-2 mb-4">
        {history.map((m, i) => (
          <div
            key={i}
            className={`rounded px-3 py-2 ${m.role === 'user' ? 'bg-primary/20 ml-4' : 'bg-violet-50/80 mr-4'}`}
          >
            {m.content}
          </div>
        ))}
        {streamBuffer && (
          <div className="rounded bg-violet-50/80 mr-4 px-3 py-2">
            {streamBuffer}
            <span className="stream-cursor" />
          </div>
        )}
      </div>
      <form onSubmit={(e) => { e.preventDefault(); send(); }} className="flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask..."
          className="flex-1 rounded border border-violet-200/40 glass-input px-3 py-2 text-slate-800"
          disabled={streaming}
        />
        <button type="submit" disabled={streaming} className="rounded bg-primary px-4 py-2 text-white">
          Send
        </button>
      </form>
    </div>
  );
}
