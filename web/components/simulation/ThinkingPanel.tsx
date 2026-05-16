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
  const discoveredRooms = useMemo(() => {
    const set = new Set<number>();
    set.add(roomGraph.entranceRoomId);
    for (const [, w] of frame.committedBfsEdges) set.add(w);
    return set;
  }, [frame.committedBfsEdges, roomGraph.entranceRoomId]);

  return (
    <div className="flex flex-col gap-5">
      <div className="text-xs uppercase tracking-[0.2em] text-white border-b border-white/20 pb-2">
        Autonomous Mesh System
      </div>
      <RoomGraphMini
        roomGraph={roomGraph}
        committedEdges={frame.committedBfsEdges}
        queueRooms={frame.queueRooms}
        discoveredRooms={discoveredRooms}
      />
      <BfsQueueDisplay queue={frame.queueRooms} />
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
