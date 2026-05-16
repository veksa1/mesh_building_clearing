'use client';

import type { RoomGraph } from '@/types';
import { GRID_COLS, GRID_ROWS } from '@/constants';

interface Props {
  roomGraph: RoomGraph;
  committedEdges: [number, number][];
  queueRooms: number[];
  discoveredRooms: Set<number>;
}

export function RoomGraphMini({ roomGraph, committedEdges, queueRooms, discoveredRooms }: Props) {
  const W = 280;
  const H = 160;
  const PAD = 20;

  const pos = new Map<number, { x: number; y: number }>();
  for (const room of roomGraph.rooms) {
    const x = (room.anchorCell.col / GRID_COLS) * (W - PAD * 2) + PAD;
    const y = (room.anchorCell.row / GRID_ROWS) * (H - PAD * 2) + PAD;
    pos.set(room.id, { x, y });
  }

  // All adjacency edges (deduplicated).
  const allEdges: [number, number][] = [];
  const seen = new Set<string>();
  for (const [u, neighbors] of roomGraph.adjacency.entries()) {
    for (const v of neighbors) {
      const k = u < v ? `${u}_${v}` : `${v}_${u}`;
      if (seen.has(k)) continue;
      seen.add(k);
      allEdges.push([Math.min(u, v), Math.max(u, v)]);
    }
  }

  const committedKeys = new Set(committedEdges.map(([a, b]) => `${Math.min(a, b)}_${Math.max(a, b)}`));
  const queueSet = new Set(queueRooms);

  return (
    <div>
      <div className="text-[9px] uppercase tracking-widest text-white/60 mb-2">Room Graph</div>
      <svg width={W} height={H} className="bg-black border border-white/10">
        {/* Adjacency edges (faint) */}
        {allEdges.map(([u, v]) => {
          const a = pos.get(u);
          const b = pos.get(v);
          if (!a || !b) return null;
          const isCommitted = committedKeys.has(`${u}_${v}`);
          return (
            <line
              key={`e_${u}_${v}`}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              stroke={isCommitted ? '#ffffff' : 'rgba(255,255,255,0.18)'}
              strokeWidth={isCommitted ? 2 : 1}
              strokeDasharray={isCommitted ? '' : '3,3'}
            />
          );
        })}
        {/* Nodes */}
        {roomGraph.rooms.map((room) => {
          const p = pos.get(room.id);
          if (!p) return null;
          const isEntrance = room.id === roomGraph.entranceRoomId;
          const isTarget = room.id === roomGraph.targetRoomId;
          const inQueue = queueSet.has(room.id);
          const isDiscovered = discoveredRooms.has(room.id);

          let fill = 'rgba(255,255,255,0.15)';
          let stroke = 'rgba(255,255,255,0.4)';
          let labelColor = '#ffffff';
          if (isTarget) {
            fill = '#ff2030';
            stroke = '#ffffff';
            labelColor = '#ffffff';
          } else if (isEntrance) {
            fill = '#ffffff';
            stroke = '#ffffff';
            labelColor = '#000000';
          } else if (isDiscovered) {
            fill = 'rgba(255,255,255,0.7)';
            stroke = '#ffffff';
            labelColor = '#000000';
          }
          return (
            <g key={`n_${room.id}`}>
              {inQueue && !isEntrance && !isTarget && (
                <circle cx={p.x} cy={p.y} r={14} fill="none" stroke="#ffffff" strokeWidth={1.5}>
                  <animate
                    attributeName="opacity"
                    values="0.3;1;0.3"
                    dur="1.2s"
                    repeatCount="indefinite"
                  />
                </circle>
              )}
              <circle cx={p.x} cy={p.y} r={10} fill={fill} stroke={stroke} strokeWidth={1.5} />
              <text
                x={p.x}
                y={p.y + 3}
                textAnchor="middle"
                fontSize={9}
                fontFamily="monospace"
                fill={labelColor}
              >
                R{room.id}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
