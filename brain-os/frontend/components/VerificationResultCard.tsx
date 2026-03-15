'use client';

/** Single verification result from API (may include count after backend dedupe). */
export type VerificationResultItem = {
  document_name: string;
  status: string;
  message?: string;
  count?: number;
};

type Props = {
  summary: string;
  results: VerificationResultItem[];
  /** Hub (primary) vs brain (warm) styling */
  useHubStyle?: boolean;
};

/** Deduplicate by (name, status) and sum counts (for backward compatibility with non-dedupe API). */
function dedupeResults(results: VerificationResultItem[]): VerificationResultItem[] {
  const keyTo = new Map<string, VerificationResultItem>();
  for (const r of results) {
    const name = (r.document_name || '').trim();
    const status = r.status || '';
    const msg = (r.message || '').trim();
    const key = `${name}\n${status}\n${msg}`;
    const existing = keyTo.get(key);
    if (existing) {
      existing.count = (existing.count ?? 1) + (r.count ?? 1);
    } else {
      keyTo.set(key, { ...r, document_name: name, status, message: msg || undefined, count: r.count ?? 1 });
    }
  }
  return Array.from(keyTo.values());
}

function statusIcon(status: string) {
  switch (status) {
    case 'updated':
      return <span className="text-amber-500 shrink-0" title="Updated">⚠</span>;
    case 'not_verifiable':
      return <span className="text-slate-500 shrink-0" title="Not verifiable">ℹ</span>;
    case 'current':
      return <span className="text-emerald-600 shrink-0" title="Current">✓</span>;
    case 'error':
    case 'not_found':
      return <span className="text-red-500 shrink-0" title="Error">✕</span>;
    default:
      return <span className="text-slate-400 shrink-0">•</span>;
  }
}

function rowClass(status: string) {
  switch (status) {
    case 'updated':
      return 'verification-card-row-updated';
    case 'not_verifiable':
      return 'verification-card-row-not-verifiable';
    case 'current':
      return 'verification-card-row-current';
    case 'error':
    case 'not_found':
      return 'verification-card-row-error';
    default:
      return 'bg-white/60';
  }
}

export function VerificationResultCard({ summary, results, useHubStyle }: Props) {
  const items = dedupeResults(results);
  const summaryColor = useHubStyle ? 'text-primary' : 'text-primary';

  return (
    <div className="verification-card rounded-xl overflow-hidden">
      <div className="verification-card-header px-4 py-3 border-b border-emerald-200/60">
        <p className={`text-sm font-semibold ${summaryColor}`}>{summary}</p>
      </div>
      <ul className="divide-y divide-emerald-100/80">
        {items.map((r, k) => (
          <li
            key={k}
            className={`px-4 py-2.5 flex items-start gap-3 ${rowClass(r.status)}`}
          >
            {statusIcon(r.status)}
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-slate-800 truncate">
                {r.document_name || 'Unknown source'}
              </p>
              <p className="text-xs text-slate-600 mt-0.5">
                {r.status === 'updated' && r.message
                  ? r.message
                  : r.status === 'not_verifiable' && r.message
                    ? r.message
                    : r.status === 'current'
                      ? 'Source is current.'
                      : r.message || r.status}
              </p>
            </div>
            {(r.count ?? 1) > 1 && (
              <span className="shrink-0 text-[10px] font-bold px-1.5 py-0.5 rounded-md bg-slate-200/80 text-slate-600">
                ×{r.count}
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
