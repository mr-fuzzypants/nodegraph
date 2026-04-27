import React, { useEffect, useRef, useState } from 'react';

interface EditableNodeTitleProps {
  label: string;
  accent: string;
  onRename: (name: string) => Promise<void>;
}

export function EditableNodeTitle({ label, accent, onRename }: EditableNodeTitleProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(label);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!editing) setDraft(label);
  }, [editing, label]);

  useEffect(() => {
    if (editing) inputRef.current?.select();
  }, [editing]);

  const cancel = () => {
    setDraft(label);
    setEditing(false);
  };

  const commit = async () => {
    const nextName = draft.trim();
    if (!nextName || nextName === label || busy) {
      cancel();
      return;
    }
    setBusy(true);
    try {
      await onRename(nextName);
      setEditing(false);
    } finally {
      setBusy(false);
    }
  };

  if (editing) {
    return (
      <input
        ref={inputRef}
        className="nodrag nopan"
        value={draft}
        disabled={busy}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={() => {
          void commit();
        }}
        onMouseDown={(event) => event.stopPropagation()}
        onClick={(event) => event.stopPropagation()}
        onDoubleClick={(event) => event.stopPropagation()}
        onKeyDown={(event) => {
          event.stopPropagation();
          if (event.key === 'Enter') void commit();
          if (event.key === 'Escape') cancel();
        }}
        style={{
          flex: 1,
          minWidth: 0,
          background: 'rgba(15, 23, 42, 0.78)',
          border: `1px solid ${accent}88`,
          borderRadius: 6,
          color: 'var(--foreground)',
          fontFamily: 'ui-sans-serif, sans-serif',
          fontSize: 13,
          fontWeight: 700,
          padding: '3px 6px',
          outline: 'none',
        }}
      />
    );
  }

  return (
    <span
      onDoubleClick={(event) => {
        event.stopPropagation();
        setEditing(true);
      }}
      title={`${label} — double-click to rename`}
      style={{
        fontWeight: 700,
        fontSize: 13,
        color: 'var(--foreground)',
        flex: 1,
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
        fontFamily: 'ui-sans-serif, sans-serif',
        cursor: 'text',
      }}
    >
      {label}
    </span>
  );
}
