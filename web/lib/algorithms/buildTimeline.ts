import type {
  DroneRC,
  FrameState,
  GridPoint,
  RasterizedMap,
  RoomGraph,
  SimParams,
} from '@/types';
import { bfsPlan } from './bfsPlan';
import {
  concatPaths,
  gridShortestPath,
  interpolatePolyline,
  samplePolyline,
} from './navigation';

const CAPTION = (
  depth: string,
  discoveryTrace: string,
): string =>
  `BFS tree takeover (rooms = vertices)
${depth}
Discovery trace: ${discoveryTrace}

Drone paths: grid shortest paths on walkable cells (no wall clipping).
Relays hold the backbone to the parent room while the scout opens the next edge.

Path loss model (Rep. ITU-R P.2346 eq. (2) style):
  L = 20·log10(f_MHz) + N·log10(d_m) − 27.55 + L_f
  L_f ≈ (wall pixel hits along LOS) × L_wall — heuristic grid penetration.

See side panel for FIFO frontier queue state.`;

function roomsRootToU(
  parent: Map<number, number | null>,
  root: number,
  u: number,
): number[] {
  const seq: number[] = [];
  let cur: number | null = u;
  while (cur !== null) {
    seq.push(cur);
    if (cur === root) break;
    cur = parent.get(cur) ?? null;
  }
  seq.reverse();
  return seq;
}

function findFirstDoorOutCell(
  entranceRoomId: number,
  entranceAnchor: GridPoint,
  labels: Int16Array,
  rows: number,
  cols: number,
): GridPoint {
  // BFS from entrance anchor: find the first walkable cell adjacent to a wall
  // that has an opposite walkable cell in a different room (i.e. a door).
  const visited = new Uint8Array(rows * cols);
  const startIdx = entranceAnchor.row * cols + entranceAnchor.col;
  visited[startIdx] = 1;
  const q: number[] = [startIdx];
  let head = 0;
  let bestCell: GridPoint | null = null;
  let bestDist = Infinity;

  while (head < q.length) {
    const cur = q[head++];
    const r = (cur / cols) | 0;
    const c = cur - r * cols;
    if (labels[cur] !== entranceRoomId) continue;
    for (const [dr, dc] of [
      [-1, 0],
      [1, 0],
      [0, -1],
      [0, 1],
    ]) {
      const nr = r + dr;
      const nc = c + dc;
      if (nr < 0 || nr >= rows || nc < 0 || nc >= cols) continue;
      const ni = nr * cols + nc;
      if (visited[ni]) continue;
      visited[ni] = 1;
      if (labels[ni] === entranceRoomId) {
        // Check if THIS cell (r, c) borders a different room across a wall gap.
        const dist =
          (r - entranceAnchor.row) * (r - entranceAnchor.row) +
          (c - entranceAnchor.col) * (c - entranceAnchor.col);
        if (dist < bestDist) {
          // Heuristic: if this cell is on the boundary of the entrance room
          // (any 4-neighbor either out-of-bounds or has different label including walls),
          // prefer it as a stage target.
          let onBoundary = false;
          for (const [dr2, dc2] of [
            [-1, 0],
            [1, 0],
            [0, -1],
            [0, 1],
          ]) {
            const br = r + dr2;
            const bc = c + dc2;
            if (br < 0 || br >= rows || bc < 0 || bc >= cols) continue;
            const blab = labels[br * cols + bc];
            if (blab >= 0 && blab !== entranceRoomId) {
              onBoundary = true;
              break;
            }
          }
          if (onBoundary) {
            bestDist = dist;
            bestCell = { row: r, col: c };
          }
        }
        q.push(ni);
      }
    }
  }

  return bestCell ?? entranceAnchor;
}

export function buildTimeline(
  roomGraph: RoomGraph,
  rasterized: RasterizedMap,
  params: SimParams,
  labels: Int16Array,
): FrameState[] {
  const { wallGrid, rows, cols } = rasterized;
  const nRelays = Math.max(0, params.nDrones - 1);
  const root = roomGraph.entranceRoomId;
  const targetId = roomGraph.targetRoomId;

  const anchors = new Map<number, GridPoint>();
  for (const room of roomGraph.rooms) anchors.set(room.id, room.anchorCell);

  const { parent, edges, queueSnapshots } = bfsPlan(roomGraph.adjacency, root);

  const edgePaths = new Map<string, GridPoint[]>();
  const edgeKey = (u: number, v: number) => `${u}_${v}`;
  for (const [u, v] of edges) {
    const path = gridShortestPath(wallGrid, rows, cols, anchors.get(u)!, anchors.get(v)!);
    edgePaths.set(edgeKey(u, v), path);
  }

  const entranceAnchor = anchors.get(root)!;
  const stageEnd = findFirstDoorOutCell(root, entranceAnchor, labels, rows, cols);
  const stagePath = gridShortestPath(wallGrid, rows, cols, entranceAnchor, stageEnd);

  const backboneUpto = (roomId: number): GridPoint[] => {
    const chain = roomsRootToU(parent, root, roomId);
    if (chain.length === 1) return stagePath;
    const parts: GridPoint[][] = [];
    for (let i = 0; i < chain.length - 1; i++) {
      parts.push(edgePaths.get(edgeKey(chain[i], chain[i + 1]))!);
    }
    return concatPaths(parts);
  };

  const timeline: FrameState[] = [];
  const committedBfsEdges: [number, number][] = [];
  let discoveredLine = `${root}`;

  let relayPts: DroneRC[] = samplePolyline(stagePath, nRelays);
  const scoutIdle = interpolatePolyline(stagePath, 1.0);
  const idleSwarm: DroneRC[] = [...relayPts, scoutIdle];

  for (let i = 0; i < params.dwellFrames; i++) {
    timeline.push({
      dronesRC: idleSwarm.map((p) => ({ ...p })),
      phase: 'staging',
      caption: CAPTION(
        'Staging at entrance — relays line toward primary doorway.',
        discoveredLine,
      ),
      queueRooms: [root],
      phaseLine: 'Idle — waiting to expand first frontier.',
      discoveredLine,
      committedBfsEdges: [],
    });
  }

  let neutralised = false;
  for (let ei = 0; ei < edges.length; ei++) {
    if (neutralised) break;
    const [u, w] = edges[ei];
    const qSnap = queueSnapshots[ei];
    const motionPath = edgePaths.get(edgeKey(u, w))!;
    discoveredLine = `${discoveredLine} → ${w}`;
    committedBfsEdges.push([u, w]);
    const committedSnapshot: [number, number][] = committedBfsEdges.map(([a, b]) => [a, b]);

    for (let k = 0; k < params.framesPerEdge; k++) {
      const t = (k + 1) / params.framesPerEdge;
      const scout = interpolatePolyline(motionPath, t);
      timeline.push({
        dronesRC: [...relayPts.map((p) => ({ ...p })), scout],
        phase: 'traversing',
        caption: CAPTION(
          `Edge (${u}→${w}) — relays frozen; scout follows corridor grid path.`,
          discoveredLine,
        ),
        queueRooms: qSnap.slice(),
        phaseLine: `Scout moving along tree edge ${u} → ${w} (${k + 1}/${params.framesPerEdge})`,
        discoveredLine,
        committedBfsEdges: committedSnapshot,
      });
    }

    const backbone = backboneUpto(w);
    relayPts = samplePolyline(backbone, nRelays);
    const scoutSettled = interpolatePolyline(backbone, 1.0);

    const settledFrames = Math.max(1, Math.floor(params.dwellFrames / 2));
    for (let k = 0; k < settledFrames; k++) {
      timeline.push({
        dronesRC: [...relayPts.map((p) => ({ ...p })), scoutSettled],
        phase: 'settled',
        caption: CAPTION(
          `Committed parent[${w}]=${u}; relays redistributed along backbone to room ${w}.`,
          discoveredLine,
        ),
        queueRooms: qSnap.slice(),
        phaseLine: `Committed parent[${w}]=${u}; relays redistributed.`,
        discoveredLine,
        committedBfsEdges: committedSnapshot,
      });
    }

    if (w === targetId) {
      neutralised = true;
      for (let k = 0; k < params.dwellFrames; k++) {
        timeline.push({
          dronesRC: [...relayPts.map((p) => ({ ...p })), scoutSettled],
          phase: 'neutralised',
          caption: CAPTION(`TARGET ACQUIRED in room ${w}. Mesh holds.`, discoveredLine),
          queueRooms: [],
          phaseLine: 'TARGET ACQUIRED — NEUTRALISED.',
          discoveredLine,
          committedBfsEdges: committedSnapshot,
        });
      }
    }
  }

  return timeline;
}
