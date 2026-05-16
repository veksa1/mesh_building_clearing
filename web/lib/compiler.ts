import type { CompiledSim, FloorplanData, SimParams } from '@/types';
import { rasterize } from './rasterize';
import { labelRegions } from './algorithms/floodFill';
import { buildRoomGraph } from './algorithms/roomGraph';
import { runSwarm } from './algorithms/runSwarm';
import { fieldStrengthMap } from './propagation/fieldStrengthMap';

export interface CompileResult {
  ok: true;
  compiled: CompiledSim;
}

export interface CompileError {
  ok: false;
  error: string;
}

export function compile(floorplan: FloorplanData, params: SimParams): CompileResult | CompileError {
  if (!floorplan.entrance) return { ok: false, error: 'Set entrance point first.' };
  if (!floorplan.target) return { ok: false, error: 'Set target point first.' };

  const rasterized = rasterize(floorplan);
  const { rows, cols, wallGrid, wallGridFull } = rasterized;

  if (wallGrid[floorplan.entrance.row * cols + floorplan.entrance.col] === 1) {
    return { ok: false, error: 'Entrance is on a wall cell.' };
  }
  if (wallGrid[floorplan.target.row * cols + floorplan.target.col] === 1) {
    return { ok: false, error: 'Target is on a wall cell.' };
  }

  // Use wallGridFull (walls intact at door positions) so flood fill produces
  // separate regions per room. Adjacency is reconstructed from door geometry.
  const { labels } = labelRegions(wallGridFull, rows, cols);
  const fullGraph = buildRoomGraph(labels, rows, cols, floorplan.doors, floorplan.entrance, floorplan.target);

  if (fullGraph.entranceRoomId < 0 || fullGraph.targetRoomId < 0) {
    return { ok: false, error: 'Entrance or target not in any room.' };
  }

  // Filter to only rooms reachable from entrance via doors.
  const reachable = new Set<number>([fullGraph.entranceRoomId]);
  const stack = [fullGraph.entranceRoomId];
  while (stack.length > 0) {
    const u = stack.pop()!;
    for (const v of fullGraph.adjacency.get(u) ?? []) {
      if (!reachable.has(v)) {
        reachable.add(v);
        stack.push(v);
      }
    }
  }
  const roomGraph = {
    rooms: fullGraph.rooms.filter((r) => reachable.has(r.id)),
    adjacency: new Map(
      Array.from(fullGraph.adjacency.entries())
        .filter(([k]) => reachable.has(k))
        .map(([k, v]) => [k, v.filter((x) => reachable.has(x))]),
    ),
    entranceRoomId: fullGraph.entranceRoomId,
    targetRoomId: fullGraph.targetRoomId,
  };

  if (!reachable.has(fullGraph.targetRoomId)) {
    return {
      ok: false,
      error: 'Target room not reachable from entrance — add doors.',
    };
  }
  // If they're in the same room, no BFS needed but we still simulate a stage sequence.
  // Allow it — buildTimeline handles single-room case via stage frames only.

  const { timeline } = runSwarm(roomGraph, rasterized, params, labels);

  if (timeline.length === 0) {
    return { ok: false, error: 'Empty simulation timeline.' };
  }

  const firstFrame = timeline[0];
  const { heatmap } = fieldStrengthMap(
    rasterized.wallGrid,
    rasterized.wallDbGrid,
    rows,
    cols,
    firstFrame.dronesRC,
    rasterized.cellSizeM,
    params,
  );

  const finiteVals = Array.from(heatmap).filter((v) => isFinite(v));
  finiteVals.sort((a, b) => a - b);
  const p = (q: number) => finiteVals[Math.floor((finiteVals.length - 1) * q)] ?? 0;
  const vmin = p(0.05) - 5;
  const vmax = p(0.95) + 8;

  return {
    ok: true,
    compiled: {
      rasterized,
      roomGraph,
      timeline,
      heatmapVmin: vmin,
      heatmapVmax: vmax,
    },
  };
}
