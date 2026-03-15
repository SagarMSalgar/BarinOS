'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { getOnboarded } from '@/lib/onboarding';
import { Onboarding } from '@/components/Onboarding';

export default function Home() {
  const router = useRouter();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted) return;
    if (getOnboarded()) {
      router.replace('/chat');
    }
  }, [mounted, router]);

  if (!mounted) {
    return (
      <div className="min-h-screen theme-page-bg flex items-center justify-center">
        <p className="text-slate-500">Loading…</p>
      </div>
    );
  }

  if (getOnboarded()) {
    return (
      <div className="min-h-screen theme-page-bg flex items-center justify-center">
        <p className="text-slate-500">Redirecting…</p>
      </div>
    );
  }

  return <Onboarding />;
}
