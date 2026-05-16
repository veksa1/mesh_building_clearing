'use client';

import { useEffect, useRef, useState } from 'react';
import type { SimPhase } from '@/types';

interface LogEntry {
  frame: number;
  text: string;
  cls: string;
}

interface Props {
  phaseLine: string;
  discoveredLine: string;
  phase: SimPhase;
  currentFrame: number;
}

export function DecisionLog({ phaseLine, discoveredLine, phase, currentFrame }: Props) {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const lastPhaseLineRef = useRef<string>('');
  const lastDiscoveryRef = useRef<string>('');
  const scrollerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setEntries((prev) => {
      const next = [...prev];
      let added = false;
      if (phaseLine !== lastPhaseLineRef.current) {
        lastPhaseLineRef.current = phaseLine;
        next.push({
          frame: currentFrame,
          text: phaseLine,
          cls: phase === 'neutralised' ? 'text-red-400' : 'text-white',
        });
        added = true;
      }
      if (discoveredLine !== lastDiscoveryRef.current) {
        lastDiscoveryRef.current = discoveredLine;
        next.push({
          frame: currentFrame,
          text: `TRACE: ${discoveredLine}`,
          cls: 'text-white/60',
        });
        added = true;
      }
      if (!added) return prev;
      if (next.length > 50) return next.slice(next.length - 50);
      return next;
    });
  }, [phaseLine, discoveredLine, phase, currentFrame]);

  useEffect(() => {
    const el = scrollerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [entries]);

  return (
    <div>
      <div className="text-[9px] uppercase tracking-widest text-white/60 mb-2">Decision Log</div>
      <div
        ref={scrollerRef}
        className="h-40 overflow-y-auto bg-black border border-white/10 p-2 font-mono text-[10px] leading-tight"
      >
        {entries.length === 0 && <div className="text-white/30">&gt; awaiting start...</div>}
        {entries.map((e, i) => (
          <div key={i} className={e.cls}>
            <span className="text-white/30">[{String(e.frame).padStart(3, '0')}]</span> &gt; {e.text}
          </div>
        ))}
      </div>
    </div>
  );
}
