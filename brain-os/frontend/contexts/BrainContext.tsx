'use client';

import { createContext, useCallback, useContext, useMemo, useState } from 'react';

export type BrainKind = 'my' | 'team';

const STORAGE_KEY = 'brainos_brain_context';

function loadStored(): BrainKind {
  if (typeof window === 'undefined') return 'team';
  const v = localStorage.getItem(STORAGE_KEY);
  if (v === 'my' || v === 'team') return v;
  return 'team';
}

/** Namespace in vector store: "my" = My brain, "main" = Team brain (shared). */
export function brainKindToNamespace(kind: BrainKind): string {
  return kind === 'my' ? 'my' : 'main';
}

export function brainKindToLabel(kind: BrainKind): string {
  return kind === 'my' ? 'My brain' : 'Team brain';
}

type BrainContextValue = {
  brainKind: BrainKind;
  setBrainKind: (k: BrainKind) => void;
  namespace: string;
  tenantId: string;
  label: string;
};

const defaultValue: BrainContextValue = {
  brainKind: 'team',
  setBrainKind: () => {},
  namespace: 'main',
  tenantId: 'default',
  label: 'Team brain',
};

const BrainContext = createContext<BrainContextValue>(defaultValue);

export function BrainProvider({ children }: { children: React.ReactNode }) {
  const [brainKind, setState] = useState<BrainKind>(loadStored);

  const setBrainKind = useCallback((k: BrainKind) => {
    setState(k);
    if (typeof window !== 'undefined') localStorage.setItem(STORAGE_KEY, k);
  }, []);

  const value = useMemo<BrainContextValue>(
    () => ({
      brainKind,
      setBrainKind,
      namespace: brainKindToNamespace(brainKind),
      tenantId: 'default',
      label: brainKindToLabel(brainKind),
    }),
    [brainKind, setBrainKind],
  );

  return <BrainContext.Provider value={value}>{children}</BrainContext.Provider>;
}

export function useBrain(): BrainContextValue {
  const ctx = useContext(BrainContext);
  return ctx ?? defaultValue;
}
