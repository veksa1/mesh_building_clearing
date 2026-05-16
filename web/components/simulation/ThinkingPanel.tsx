'use client';

import { useMemo } from 'react';
import type { FrameState, RoomGraph, ViewMode } from '@/types';
import { RoomGraphMini } from './RoomGraphMini';
import { BfsQueueDisplay } from './BfsQueueDisplay';
import { DecisionLog } from './DecisionLog';
import { CommsLog } from './CommsLog';
import { CVLog } from './CVLog';
import { BeliefTreePanel } from './BeliefTreePanel';

export function ThinkingPanel({
  frame,
  roomGraph,
  currentFrame,
  viewMode,
  setViewMode,
}: {
  frame: FrameState;
  roomGraph: RoomGraph;
  currentFrame: number;
  viewMode: ViewMode;
  setViewMode: (mode: ViewMode) => void;
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

      <ViewToggle viewMode={viewMode} setViewMode={setViewMode} />

      {viewMode === 'oracle' ? (
        <>
          <RoomGraphMini
            roomGraph={roomGraph}
            committedEdges={frame.oracle.committedEdges}
            queueRooms={frame.oracle.queueRooms}
            discoveredRooms={discoveredRooms}
          />
          <BfsQueueDisplay queue={frame.oracle.queueRooms} />
        </>
      ) : (
        <>
          <CVLog detections={frame.cvDetections} />
          <BeliefTreePanel frame={frame} />
        </>
      )}

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

function ViewToggle({
  viewMode,
  setViewMode,
}: {
  viewMode: ViewMode;
  setViewMode: (mode: ViewMode) => void;
}) {
  return (
    <div>
      <div className="text-[9px] uppercase tracking-widest text-white/60 mb-2">View</div>
      <div className="grid grid-cols-2 gap-px bg-white/10 border border-white/10">
        {(['drone', 'oracle'] as const).map((mode) => {
          const active = viewMode === mode;
          return (
            <button
              key={mode}
              type="button"
              onClick={() => setViewMode(mode)}
              className={`text-[10px] uppercase tracking-widest py-2 ${
                active
                  ? 'bg-white text-black'
                  : 'bg-black text-white/70 hover:text-white'
              }`}
            >
              {mode === 'drone' ? 'Drone' : 'Oracle'}
            </button>
          );
        })}
      </div>
      <div className="mt-1 text-[9px] text-white/40 leading-tight">
        {viewMode === 'drone'
          ? 'Showing what the swarm has actually seen via local CV + mesh gossip.'
          : 'Ground truth — the floorplan and room graph the operator has, hidden from drones.'}
      </div>
    </div>
  );
}
