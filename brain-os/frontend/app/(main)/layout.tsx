'use client';

import { AppShell } from '@/components/AppShell';
import { BrainProvider } from '@/contexts/BrainContext';
import { ToastProvider } from '@/contexts/ToastContext';
import { Toasts } from '@/components/Toasts';

export default function MainLayout({ children }: { children: React.ReactNode }) {
  return (
    <BrainProvider>
      <ToastProvider>
        <AppShell>{children}</AppShell>
        <Toasts />
      </ToastProvider>
    </BrainProvider>
  );
}
