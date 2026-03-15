'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { getBrainName } from '@/lib/onboarding';
import { useBrain, brainKindToLabel, type BrainKind } from '@/contexts/BrainContext';
import {
  IconDashboard,
  IconChat,
  IconMemory,
  IconTarget,
  IconSources,
  IconIntelligence,
  IconDeploy,
  IconGaps,
  IconFreshness,
  IconCompliance,
  IconHealth,
  IconExport,
  IconSettings,
} from '@/components/Icons';

const navItems = [
  { href: '/dashboard', label: 'Dashboard', Icon: IconDashboard },
  { href: '/chat', label: 'Ask BrainOS', Icon: IconChat },
  { href: '/memory', label: 'Memory', Icon: IconMemory },
  { href: '/agent', label: 'Goal Engine', Icon: IconTarget },
  { href: '/sources', label: 'Knowledge Sources', Icon: IconSources },
  { href: '/intelligence', label: 'Intelligence', Icon: IconIntelligence },
  { href: '/deploy', label: 'Deploy', Icon: IconDeploy },
  { href: '/gaps', label: 'Knowledge Gaps', Icon: IconGaps },
  { href: '/freshness', label: 'Freshness', Icon: IconFreshness },
  { href: '/compliance', label: 'Compliance', Icon: IconCompliance },
  { href: '/health', label: 'Health Monitor', Icon: IconHealth },
  { href: '/export', label: 'Export Studio', Icon: IconExport },
  { href: '/settings', label: 'Settings', Icon: IconSettings },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [brainName, setBrainName] = useState('');
  const { brainKind, setBrainKind, label } = useBrain();
  useEffect(() => setBrainName(getBrainName()), []);

  return (
    <div className="flex h-screen w-full overflow-hidden bg-gradient-to-br from-violet-50/90 via-white/80 to-purple-50/80">
      {/* Sidebar — glassmorphic + purple primary */}
      <aside
        className={`flex shrink-0 flex-col glass-header border-r border-white/20 backdrop-blur-xl transition-[width] duration-200 ${
          sidebarOpen ? 'w-56' : 'w-14'
        }`}
      >
        <div className="flex h-14 items-center justify-between border-b border-white/20 px-4">
          {sidebarOpen ? (
            <Link href="/chat" className="text-base font-semibold text-slate-800 no-underline truncate min-w-0">
              {brainName || 'BrainOS'}
            </Link>
          ) : (
            <span className="flex w-8 h-8 items-center justify-center rounded-xl bg-primary-gradient text-white shadow-glass border border-white/20">
              <IconIntelligence className="w-4 h-4" />
            </span>
          )}
          <button
            type="button"
            onClick={() => setSidebarOpen((o) => !o)}
            className="rounded-xl p-1.5 text-slate-500 hover:bg-white/50 hover:text-primary backdrop-blur-sm"
            aria-label={sidebarOpen ? 'Close sidebar' : 'Open sidebar'}
          >
            {sidebarOpen ? '◀' : '▶'}
          </button>
        </div>
        {sidebarOpen && (
          <div className="border-b border-white/20 px-3 py-2">
            <p className="text-xs font-medium text-slate-500 mb-1.5">Workspace</p>
            <div className="flex rounded-xl glass-tab-inactive p-0.5">
              {(['my', 'team'] as BrainKind[]).map((k) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => setBrainKind(k)}
                  className={`flex-1 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors ${
                    brainKind === k ? 'glass-tab-active' : 'text-slate-600 hover:text-slate-800 bg-transparent'
                  }`}
                >
                  {brainKindToLabel(k)}
                </button>
              ))}
            </div>
            <p className="text-[10px] text-slate-500 mt-2 leading-tight">
              {brainKind === 'team' ? 'Team brain = shared workspace.' : 'My brain = private workspace.'}
            </p>
          </div>
        )}
        <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-0.5" aria-label="Main navigation">
          {navItems.map(({ href, label, Icon }) => {
            const active = path === href;
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-colors min-h-[40px] ${
                  active ? 'glass-tab-active' : 'text-slate-600 hover:bg-white/50 hover:text-slate-800'
                }`}
              >
                <span className="shrink-0 [&_svg]:w-5 [&_svg]:h-5"><Icon className="w-5 h-5" /></span>
                {sidebarOpen && <span className="truncate">{label}</span>}
              </Link>
            );
          })}
        </nav>
      </aside>

      <main className="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden bg-transparent">
        {children}
      </main>
    </div>
  );
}
