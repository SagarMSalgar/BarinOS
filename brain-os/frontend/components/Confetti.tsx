'use client';

import { useEffect, useState } from 'react';

const COLORS = ['#C9A86C', '#7EB8A4', '#D4A574', '#6B9B7A', '#E8E4F0'];
const COUNT = 60;

export function Confetti({ onComplete }: { onComplete?: () => void }) {
  const [mounted, setMounted] = useState(true);
  useEffect(() => {
    const t = setTimeout(() => {
      setMounted(false);
      onComplete?.();
    }, 2200);
    return () => clearTimeout(t);
  }, [onComplete]);

  if (!mounted) return null;
  return (
    <div className="fixed inset-0 pointer-events-none z-50 overflow-hidden" aria-hidden>
      {Array.from({ length: COUNT }).map((_, i) => (
        <div
          key={i}
          className="absolute w-2 h-2 rounded-sm animate-confetti-fall"
          style={{
            left: `${Math.random() * 100}%`,
            top: '-8px',
            backgroundColor: COLORS[i % COLORS.length],
            animationDelay: `${Math.random() * 0.4}s`,
            animationDuration: `${1.6 + Math.random() * 0.5}s`,
          }}
        />
      ))}
    </div>
  );
}
