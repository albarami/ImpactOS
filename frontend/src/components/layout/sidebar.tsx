'use client';

import Link from 'next/link';
import { usePathname, useParams } from 'next/navigation';
import {
  FileText,
  GitCompare,
  Layers,
  Play,
  Shield,
  Download,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
}

const NAV_ITEMS: NavItem[] = [
  { label: 'Documents', href: '/documents', icon: FileText },
  { label: 'Compilations', href: '/compilations', icon: GitCompare },
  { label: 'Scenarios', href: '/scenarios', icon: Layers },
  { label: 'Runs', href: '/runs', icon: Play },
  { label: 'Governance', href: '/governance', icon: Shield },
  { label: 'Exports', href: '/exports', icon: Download },
];

export function Sidebar() {
  const pathname = usePathname();
  const params = useParams();
  const workspaceId = params.workspaceId as string;

  return (
    <aside className="flex w-60 flex-col border-r border-slate-200 bg-slate-50">
      <div className="flex h-14 items-center border-b border-slate-200 px-4">
        <span className="text-lg font-bold text-slate-900">ImpactOS</span>
      </div>
      <nav className="flex-1 space-y-1 px-2 py-3">
        {NAV_ITEMS.map((item) => {
          const fullHref = `/w/${workspaceId}${item.href}`;
          const isActive = pathname.startsWith(fullHref);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={fullHref}
              data-active={isActive || undefined}
              className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-slate-200 text-slate-900'
                  : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
              }`}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
