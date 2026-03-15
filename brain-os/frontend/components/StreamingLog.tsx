'use client';

import { useRef, useEffect } from 'react';

export type LogEntry = {
  id: string;
  type: 'log' | 'task_start' | 'task_done' | 'task_fail' | 'evaluator' | 'done' | 'error';
  message?: string;
  level?: string;
  task_index?: number;
  action?: string;
  result_excerpt?: string;
  error?: string;
  success?: boolean;
  reason?: string;
  payload?: Record<string, unknown>;
  ts: number;
};

type StreamingLogProps = {
  entries: LogEntry[];
  isStreaming?: boolean;
  className?: string;
};

export function StreamingLog({ entries, isStreaming = false, className = '' }: StreamingLogProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [entries]);

  return (
    <div className={`flex flex-col rounded-xl glass-card overflow-hidden ${className}`}>
      <div className="flex items-center gap-2 border-b border-violet-200/40 bg-violet-50/60 px-4 py-2">
        <span className={`h-2 w-2 rounded-full ${isStreaming ? 'animate-pulse bg-primary' : 'bg-slate-400'}`} />
        <span className="text-xs font-medium text-slate-500">
          {isStreaming ? 'Streaming…' : entries.length ? 'Done' : 'Run the agent to see logs'}
        </span>
      </div>
      <div className="min-h-[200px] max-h-[400px] overflow-y-auto p-4 font-mono text-sm">
        {entries.length === 0 && !isStreaming && (
          <p className="text-slate-500 text-xs">Log output will appear here as the agent runs.</p>
        )}
        {entries.map((e) => (
          <div
            key={e.id}
            className="flex flex-col gap-0.5 py-1.5 border-b border-violet-200/30 last:border-0"
            data-type={e.type}
          >
            {e.type === 'log' && (
              <span className="text-slate-800">
                <span className="text-slate-500 mr-2">[{e.level || 'info'}]</span>
                {e.message}
              </span>
            )}
            {e.type === 'task_start' && (
              <span className="text-primary font-medium">
                ▶ Task {((e.task_index ?? 0) + 1)}: {e.action}
              </span>
            )}
            {e.type === 'task_done' && (
              <>
                <span className="text-emerald-600 font-medium">
                  ✓ Task {((e.task_index ?? 0) + 1)}: {e.action}
                </span>
                {e.result_excerpt && (
                  <span className="text-slate-500 text-xs mt-0.5 block pl-4 truncate max-w-full" title={e.result_excerpt}>
                    {e.result_excerpt}
                  </span>
                )}
              </>
            )}
            {e.type === 'task_fail' && (
              <span className="text-rose-600">
                ✗ Task {((e.task_index ?? 0) + 1)}: {e.action} — {e.error || 'Failed'}
              </span>
            )}
            {e.type === 'evaluator' && (
              <span className={e.success ? 'text-emerald-600' : 'text-amber-600'}>
                Evaluator: {e.success ? 'Goal achieved' : 'Goal not fully achieved'}. {e.reason}
              </span>
            )}
            {e.type === 'done' && (
              <span className="text-slate-500 text-xs mt-1">
                Run completed. Outcome: {(e.payload?.outcome_success as boolean) ? 'Success' : 'Partial/Fail'}
              </span>
            )}
            {e.type === 'error' && (
              <span className="text-rose-600">Error: {e.message || e.error || 'Unknown'}</span>
            )}
          </div>
        ))}
        {isStreaming && entries.length > 0 && (
          <span className="inline-block h-4 w-4 animate-pulse text-primary mt-1">▌</span>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
