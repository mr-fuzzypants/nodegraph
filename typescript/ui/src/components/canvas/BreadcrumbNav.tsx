import React from 'react';
import { usePaneStore } from './PaneContext';

export function BreadcrumbNav() {
  const breadcrumb = usePaneStore((s) => s.breadcrumb);
  const exitTo = usePaneStore((s) => s.exitTo);

  if (breadcrumb.length === 0) return null;

  return (
    <nav
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 4,
        padding: '6px 12px',
        background: '#13141f',
        borderBottom: '1px solid #2c2f45',
        fontFamily: 'monospace',
        fontSize: 12,
        color: '#9ea3c0',
        zIndex: 10,
      }}
    >
      {breadcrumb.map((entry, index) => (
        <React.Fragment key={entry.id}>
          {index > 0 && (
            <span style={{ color: '#535677', margin: '0 2px' }}>/</span>
          )}
          <button
            onClick={() => exitTo(index)}
            disabled={index === breadcrumb.length - 1}
            style={{
              background: 'none',
              border: 'none',
              cursor: index === breadcrumb.length - 1 ? 'default' : 'pointer',
              color: index === breadcrumb.length - 1 ? '#a78bfa' : '#6d7de8',
              fontFamily: 'monospace',
              fontSize: 12,
              fontWeight: index === breadcrumb.length - 1 ? 'bold' : 'normal',
              padding: '1px 3px',
              borderRadius: 3,
              textDecoration: index === breadcrumb.length - 1 ? 'none' : 'underline',
            }}
            title={index === breadcrumb.length - 1 ? undefined : `Go back to ${entry.name}`}
          >
            {entry.name}
          </button>
        </React.Fragment>
      ))}
    </nav>
  );
}
