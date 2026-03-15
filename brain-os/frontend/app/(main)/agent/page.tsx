'use client';

import { useState, useCallback } from 'react';
import { agentPlan, streamAgentRun } from '@/lib/api';
import { useBrain } from '@/contexts/BrainContext';
import { StreamingLog, type LogEntry } from '@/components/StreamingLog';

export default function AgentPage() {
  const { namespace } = useBrain();
  const [goal, setGoal] = useState('');
  const [plan, setPlan] = useState<{ plan_id: string; goal: string; tasks: { action: string; dependencies?: number[] }[] } | null>(null);
  const [planning, setPlanning] = useState(false);
  const [running, setRunning] = useState(false);
  const [logEntries, setLogEntries] = useState<LogEntry[]>([]);
  const [resultContent, setResultContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handlePlan = useCallback(async () => {
    if (!goal.trim()) return;
    setError(null);
    setPlanning(true);
    setPlan(null);
    try {
      const result = await agentPlan('default', namespace, goal.trim());
      setPlan({
        plan_id: result.plan_id,
        goal: result.goal,
        tasks: result.tasks || [],
      });
    } catch (e) {
      setError(String(e));
    } finally {
      setPlanning(false);
    }
  }, [goal, namespace]);

  const handleRun = useCallback(async () => {
    if (!goal.trim()) return;
    setError(null);
    setLogEntries([]);
    setResultContent(null);
    setRunning(true);
    const entries: LogEntry[] = [];
    const addEntry = (type: LogEntry['type'], payload?: Record<string, unknown>, extra?: Partial<LogEntry>) => {
      const e: LogEntry = {
        id: `e-${Date.now()}-${entries.length}`,
        type,
        ts: Date.now(),
        ...extra,
      };
      if (payload?.message !== undefined) e.message = String(payload.message);
      if (payload?.level !== undefined) e.level = String(payload.level);
      if (payload?.task_index !== undefined) e.task_index = Number(payload.task_index);
      if (payload?.action !== undefined) e.action = String(payload.action);
      if (payload?.result_excerpt !== undefined) e.result_excerpt = String(payload.result_excerpt).slice(0, 300);
      if (payload?.error !== undefined) e.error = String(payload.error);
      if (payload?.success !== undefined) e.success = Boolean(payload.success);
      if (payload?.reason !== undefined) e.reason = String(payload.reason);
      if (payload) e.payload = payload;
      entries.push(e);
      setLogEntries([...entries]);
    };
    try {
      await streamAgentRun(
        'default',
        namespace,
        goal.trim(),
        plan?.plan_id || null,
        (event) => {
          const t = event.type;
          const p = event.payload || {};
          if (t === 'log') addEntry('log', p, { message: p.message as string, level: (p.level as string) || 'info' });
          else if (t === 'task_start') addEntry('task_start', p);
          else if (t === 'task_done') addEntry('task_done', p);
          else if (t === 'task_fail') addEntry('task_fail', p);
          else if (t === 'result') setResultContent((p.content as string) ?? null);
          else if (t === 'evaluator') addEntry('evaluator', p);
          else if (t === 'done') addEntry('done', p);
          else if (t === 'error') addEntry('error', p, { message: (p.message as string) || 'Unknown error' });
        }
      );
    } catch (e) {
      addEntry('error', {}, { message: String(e) });
      setError(String(e));
    } finally {
      setRunning(false);
    }
  }, [goal, namespace, plan?.plan_id]);

  return (
    <div className="flex flex-col h-full overflow-hidden theme-page-bg">
      <header className="shrink-0 border-b border-violet-200/40 glass-header px-6 py-6">
        <h1 className="text-2xl font-semibold tracking-tight text-slate-800">Goal Engine</h1>
        <p className="mt-2 text-sm text-slate-500 max-w-2xl">
          Turn a goal into a task plan (LLM), then run it with search, summarize, and report tools. Watch logs stream in real time.
        </p>
      </header>

      <div className="flex-1 overflow-y-auto p-6 md:p-8 space-y-6">
        {error && (
          <div className="rounded-xl border border-rose-200/50 bg-rose-50/80 px-4 py-3 text-sm text-rose-600" role="alert">
            {error}
          </div>
        )}

        <section className="rounded-xl glass-card p-6 shadow-sm">
          <label htmlFor="agent-goal" className="block text-sm font-medium text-slate-800 mb-2">
            Goal
          </label>
          <div className="flex flex-wrap gap-3 items-end">
            <input
              id="agent-goal"
              type="text"
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              placeholder="e.g. Prepare quarterly support analysis"
              className="flex-1 min-w-[200px] rounded-lg glass-input px-4 py-3 text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary/50"
              disabled={running}
            />
            <button
              type="button"
              onClick={handlePlan}
              disabled={planning || !goal.trim() || running}
              className="rounded-lg glass-tab-inactive px-4 py-3 text-sm font-medium text-slate-700 hover:bg-emerald-50/50 disabled:opacity-50"
            >
              {planning ? 'Planning…' : 'Plan'}
            </button>
            <button
              type="button"
              onClick={handleRun}
              disabled={running || !goal.trim() || !plan}
              className="rounded-lg bg-primary px-4 py-3 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50 btn-primary"
              title={!plan ? 'Create a plan first, then approve & execute' : ''}
            >
              {running ? 'Running…' : plan ? 'Approve & execute' : 'Run'}
            </button>
          </div>
        </section>

        {plan && (
          <section className="rounded-xl glass-card p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-slate-800 mb-3">Task plan</h2>
            <p className="text-sm text-slate-500 mb-4">Review the plan below, then click &quot;Approve & execute&quot; to run.</p>
            <p className="text-sm text-slate-700 mb-4">{plan.goal}</p>
            <ol className="list-decimal list-inside space-y-2 text-sm text-slate-800">
              {plan.tasks.map((t, i) => (
                <li key={i} className="pl-1">
                  {t.action}
                  {Array.isArray(t.dependencies) && t.dependencies.length > 0 && (
                    <span className="text-slate-500 ml-2">(after {t.dependencies.map((d) => d + 1).join(', ')})</span>
                  )}
                </li>
              ))}
            </ol>
          </section>
        )}

        <section>
          <h2 className="text-lg font-semibold text-slate-800 mb-3">Run log</h2>
          <StreamingLog entries={logEntries} isStreaming={running} />
        </section>

        {resultContent != null && (
          <section className="rounded-xl glass-card p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-slate-800 mb-3">Result</h2>
            <p className="text-sm text-slate-500 mb-3">Answer based on your goal and knowledge base:</p>
            <div className="prose prose-sm max-w-none text-slate-800 whitespace-pre-wrap bg-violet-50/50 rounded-lg p-4 border border-violet-200/40">
              {resultContent}
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => { navigator.clipboard.writeText(resultContent); }}
                className="rounded-lg border border-violet-200/40 px-4 py-2 text-sm text-slate-700 hover:bg-violet-50/80"
              >
                Copy to clipboard
              </button>
              <button
                type="button"
                onClick={() => {
                  const blob = new Blob([resultContent], { type: 'text/plain' });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url;
                  a.download = `goal-result-${Date.now()}.txt`;
                  a.click();
                  URL.revokeObjectURL(url);
                }}
                className="rounded-lg border border-violet-200/40 px-4 py-2 text-sm text-slate-700 hover:bg-violet-50/80"
              >
                Download as .txt
              </button>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
