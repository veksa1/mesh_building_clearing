'use client';

import { useEffect } from 'react';
import { ReadmeContent } from './readme/ReadmeContent';

export function ReadmeModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-[min(960px,92vw)] h-[min(85vh,900px)] border border-white/40 bg-black flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-white/20 px-6 py-3 flex-shrink-0">
          <h1 className="text-xs uppercase tracking-widest text-white/80">README.md</h1>
          <button
            type="button"
            onClick={onClose}
            className="border border-white/40 px-2 py-1 text-[11px] text-white/70 hover:border-white hover:text-white"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          <ReadmeContent />
        </div>
      </div>
    </div>
  );
}
