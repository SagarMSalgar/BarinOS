'use client';

import Link from 'next/link';
import { useToast } from '@/contexts/ToastContext';

const styles: Record<string, string> = {
  success: 'border-emerald-200/50 bg-emerald-50/80 text-emerald-600',
  warning: 'border-amber-200/50 bg-amber-50/80 text-amber-600',
  info: 'border-primary/50 bg-primary/10 text-primary',
  error: 'border-rose-200/50 bg-rose-50/80 text-rose-600',
};

const icons: Record<string, string> = {
  success: '✓',
  warning: '⚠',
  info: '💬',
  error: '🛡️',
};

export function Toasts() {
  const { toasts, removeToast } = useToast();
  if (toasts.length === 0) return null;
  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm" role="region" aria-label="Notifications">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`rounded-xl border px-4 py-3 shadow-soft ${styles[t.type] || styles.info}`}
          role="alert"
        >
          <div className="flex items-start justify-between gap-2">
            <span className="shrink-0">{icons[t.type]}</span>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium">{t.message}</p>
              {t.link && (
                <Link href={t.link.href} className="text-xs underline mt-1 inline-block" onClick={() => removeToast(t.id)}>
                  {t.link.label}
                </Link>
              )}
            </div>
            <button type="button" onClick={() => removeToast(t.id)} className="shrink-0 opacity-70 hover:opacity-100" aria-label="Dismiss">
              ✕
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
