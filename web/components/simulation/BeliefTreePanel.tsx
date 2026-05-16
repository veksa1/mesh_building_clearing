'use client';

import type { FrameState } from '@/types';

// Each drone fuses local sensing into a region graph and gossips portal edges
// over the mesh. This panel surfaces those numbers — the *application* of
// transmission + mesh layers, not just "drones moved".
export function BeliefTreePanel({ frame }: { frame: FrameState }) {
  const beliefEdgeCount = frame.beliefEdges.length;
  const knownDelta = frame.knownFreeDelta.length;
  const treeSegments = frame.treeSegmentsRC ? frame.treeSegmentsRC.length / 4 : 0;

  return (
    <div>
      <div className="text-[9px] uppercase tracking-widest text-white/60 mb-2">
        Drone Belief
      </div>
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        <Stat label="belief edges" value={beliefEdgeCount} />
        <Stat label="newly known" value={knownDelta} />
        <Stat label="tree segs" value={treeSegments} />
      </div>
      <div className="mt-2 text-[9px] text-white/50 leading-snug">
        Belief edges are gossiped portal hypotheses (signature, region&nbsp;A, region&nbsp;B).
        Tree segments are the lead explorer&apos;s frontier-BFS spanning tree on the
        fused known-floor graph.
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="border border-white/10 px-2 py-1 bg-black">
      <div className="text-[9px] uppercase tracking-widest text-white/40">{label}</div>
      <div className="text-base font-mono">{value}</div>
    </div>
  );
}
