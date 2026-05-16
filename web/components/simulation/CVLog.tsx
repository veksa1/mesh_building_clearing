'use client';

import { useEffect, useRef } from 'react';
import type { CvDetection } from '@/types';

const KIND_COLOR: Record<CvDetection['kind'], string> = {
  TARGET: '#ff6060',
  DOORWAY_GAP: '#ffd060',
  CORRIDOR_BRANCH: '#60d0ff',
};

function bearingChar(bdr: number, bdc: number): string {
  if (bdr === -1 && bdc === 0) return 'N';
  if (bdr === 1 && bdc === 0) return 'S';
  if (bdr === 0 && bdc === -1) return 'W';
  if (bdr === 0 && bdc === 1) return 'E';
  return '·';
}

export function CVLog({ detections }: { detections: CvDetection[] }) {
  const scrollerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = scrollerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [detections]);

  return (
    <div>
      <div className="text-[9px] uppercase tracking-widest text-white/60 mb-2 flex justify-between items-center">
        <span>CV Detections (this tick)</span>
        <span className="normal-case tracking-normal text-[8px] text-white/40">YOLO-shaped</span>
      </div>
      <div
        ref={scrollerRef}
        className="h-32 overflow-y-auto bg-black border border-white/10 p-2 font-mono text-[9px] leading-tight"
      >
        {detections.length === 0 ? (
          <div className="text-white/30">&gt; no detections in vision disc</div>
        ) : (
          detections.map((d, i) => {
            const color = KIND_COLOR[d.kind];
            const conf = d.confidence.toFixed(2);
            const bear = bearingChar(d.bearing[0], d.bearing[1]);
            const tag = d.kind === 'TARGET' ? 'TARGET' : 'DOOR  ';
            return (
              <div key={i} style={{ color }} className="whitespace-nowrap">
                drone {String(d.uid).padStart(2, ' ')}  {tag}  conf={conf}  bearing={bear}
                {'  '}anchor=({d.anchor[0]},{d.anchor[1]})
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
