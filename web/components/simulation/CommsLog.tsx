'use client';

import { useEffect, useRef } from 'react';
import { msgKindColor } from '@/lib/radio';

const MSG_TYPES = ['BEACON', 'TOPOLOGY_MERGE', 'TOKEN'] as const;

export function CommsLog({ rfLogTail }: { rfLogTail: string[] }) {
  const scrollerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = scrollerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [rfLogTail]);

  return (
    <div>
      <div className="text-[9px] uppercase tracking-widest text-white/60 mb-2 flex justify-between items-center">
        <span>RF Comms Log</span>
        <div className="flex gap-2 normal-case tracking-normal">
          {MSG_TYPES.map((m) => (
            <span key={m} className="flex items-center gap-1 text-[8px]">
              <span
                className="inline-block w-2 h-2"
                style={{ backgroundColor: msgKindColor(m) }}
              />
              {m === 'TOPOLOGY_MERGE' ? 'MERGE' : m}
            </span>
          ))}
        </div>
      </div>
      <div
        ref={scrollerRef}
        className="h-40 overflow-y-auto bg-black border border-white/10 p-2 font-mono text-[9px] leading-tight"
      >
        {rfLogTail.length === 0 ? (
          <div className="text-white/30">&gt; awaiting first broadcast...</div>
        ) : (
          rfLogTail.map((line, i) => {
            // Color line by detecting msg type substring.
            const type = MSG_TYPES.find((m) => line.includes(m));
            const color = type ? msgKindColor(type) : '#ffffff';
            return (
              <div key={i} style={{ color }} className="whitespace-nowrap">
                {line}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
