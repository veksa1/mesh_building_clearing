'use client';

export function NeutralisedOverlay({ visible }: { visible: boolean }) {
  if (!visible) return null;
  return (
    <div className="pointer-events-none fixed inset-0 z-50 flex items-center justify-center neutralised-overlay">
      <div className="text-white text-7xl font-mono font-bold tracking-[0.3em] uppercase neutralised-text">
        Neutralised
      </div>
    </div>
  );
}
