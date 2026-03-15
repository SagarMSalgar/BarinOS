'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

const links = [
  { href: '/', label: 'Chat' },
  { href: '/dashboard', label: 'Dashboard' },
  { href: '/gaps', label: 'Gap report' },
  { href: '/freshness', label: 'Freshness' },
  { href: '/compliance', label: 'Compliance' },
];

export function Nav() {
  const path = usePathname();
  return (
    <nav className="flex items-center gap-1">
      {links.map(({ href, label }) => {
        const active = path === href || (href !== '/' && path.startsWith(href));
        return (
          <Link
            key={href}
            href={href}
            className={`rounded-md px-3 py-2 text-sm transition-colors ${
              active
                ? 'bg-primary/15 text-primary font-medium'
                : 'text-slate-500 hover:bg-violet-50/80 hover:text-slate-800'
            }`}
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
