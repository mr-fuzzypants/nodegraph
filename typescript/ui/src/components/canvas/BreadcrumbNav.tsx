import React from 'react';
import { usePaneStore } from './PaneContext';
import { HugeiconsIcon } from '@hugeicons/react';
import { ArrowRight01Icon } from '@hugeicons/core-free-icons';
import { cn } from '../../lib/utils';

export function BreadcrumbNav() {
  const breadcrumb = usePaneStore((s) => s.breadcrumb);
  const exitTo = usePaneStore((s) => s.exitTo);

  if (breadcrumb.length === 0) return null;

  return (
    <nav className="flex items-center gap-1 px-3 h-8 bg-background border-b border-border text-sm text-muted-foreground z-10 shrink-0 panel">
      {breadcrumb.map((entry, index) => (
        <React.Fragment key={entry.id}>
          {index > 0 && (
            <HugeiconsIcon icon={ArrowRight01Icon} className="!size-3 text-muted-foreground/40 mx-0.5" />
          )}
          <button
            onClick={() => exitTo(index)}
            disabled={index === breadcrumb.length - 1}
            className={cn(
              'font-sans text-xs px-1 py-0.5 rounded-sm transition-colors',
              index === breadcrumb.length - 1
                ? 'text-foreground font-medium cursor-default'
                : 'text-primary underline-offset-2 hover:underline cursor-pointer',
            )}
            title={index === breadcrumb.length - 1 ? undefined : `Go back to ${entry.name}`}
          >
            {entry.name}
          </button>
        </React.Fragment>
      ))}
    </nav>
  );
}
