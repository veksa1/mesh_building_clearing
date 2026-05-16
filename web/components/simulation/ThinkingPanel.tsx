'use client';

import { useMemo } from 'react';
import type { FrameState, RoomGraph } from '@/types';
import { RoomGraphMini } from './RoomGraphMini';
import { BfsQueueDisplay } from './BfsQueueDisplay';
import { DecisionLog } from './DecisionLog';
import { CommsLog } from './CommsLog';

export function ThinkingPanel({
  frame,
  roomGraph,
  currentFrame,
}: {
  frame: FrameState;
  roomGraph: RoomGraph;
  currentFrame: number;
}) {
  const discoveredRooms = useMemo(
    () => new Set<number>(frame.oracle.roomsDiscovered),
    [frame.oracle.roomsDiscovered],
  );

  return (
    <div className="flex flex-col gap-5">
      <div className="text-xs uppercase tracking-[0.2em] text-white border-b border-white/20 pb-2">
        Autonomous Mesh System
      </div>

      <RoomGraphMini
        roomGraph={roomGraph}
        committedEdges={frame.oracle.committedEdges}
        queueRooms={frame.oracle.queueRooms}
        discoveredRooms={discoveredRooms}
      />
      <BfsQueueDisplay queue={frame.oracle.queueRooms} />

      <CommsLog rfLogTail={frame.rfLogTail} />
      <DecisionLog
        phaseLine={frame.phaseLine}
        discoveredLine={frame.discoveredLine}
        phase={frame.phase}
        currentFrame={currentFrame}
      />
    </div>
  );
}
