'use client';

export function BfsQueueDisplay({ queue }: { queue: number[] }) {
  return (
    <div>
      <div className="text-[9px] uppercase tracking-widest text-white/60 mb-2">
        BFS Frontier Q (head → tail)
      </div>
      <div className="flex items-center gap-1 flex-wrap min-h-[28px]">
        {queue.length === 0 ? (
          <span className="text-white/40 font-mono text-lg">∅</span>
        ) : (
          queue.map((roomId, i) => (
            <span key={`${i}_${roomId}`} className="flex items-center gap-1">
              <span className="inline-block min-w-[28px] text-center border border-white/60 px-1 py-0.5 font-mono text-xs bg-black">
                R{roomId}
              </span>
              {i < queue.length - 1 && <span className="text-white/40 text-xs">→</span>}
            </span>
          ))
        )}
      </div>
    </div>
  );
}
