import type {
  CommLink,
  DroneRC,
  DroneRole,
  FrameState,
  GridPoint,
  MsgKind,
  RFEvent,
  RasterizedMap,
  RoomGraph,
  SimParams,
} from '@/types';
import { bfsPlan } from './bfsPlan';
import { concatPaths, gridShortestPath, samplePolyline } from './navigation';
import {
  BEACON_INTERVAL,
  COMM_LINK_TTL_TICKS,
  DEFAULT_RADIO,
  MERGE_INTERVAL,
  pairwiseRssi,
  RF_LOG_CAPACITY,
  TOKEN_INTERVAL,
} from '../radio';

interface DroneState {
  uid: number;
  r: number;
  c: number;
  role: DroneRole;
  seq: number;
}

const CAPTION = (depth: string, discoveryTrace: string) =>
  `Decentralized BFS takeover (each drone runs identical room plan locally)
${depth}
Discovery trace: ${discoveryTrace}

Every drone senses + decides + transmits each tick — kernel resolves collisions.
Mesh broadcast: BEACON every ${BEACON_INTERVAL} ticks, TOPOLOGY_MERGE every ${MERGE_INTERVAL},
TOKEN every ${TOKEN_INTERVAL}. Delivery = RSSI ≥ −92 dBm.`;

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
          const dist =
            (r - entranceAnchor.row) ** 2 + (c - entranceAnchor.col) ** 2;
          if (dist < bestDist) {
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

function spawnPositions(
  entranceAnchor: GridPoint,
  stagePath: GridPoint[],
  n: number,
): GridPoint[] {
  if (n <= 0) return [];
  if (stagePath.length === 0) {
    return Array.from({ length: n }, () => ({ ...entranceAnchor }));
  }
  // Sample n positions along stage path, then reverse so UID 0 is closest to doorway.
  const picks: GridPoint[] = [];
  if (n === 1) {
    picks.push(stagePath[Math.floor(stagePath.length / 2)]);
  } else {
    for (let i = 0; i < n; i++) {
      const idx = Math.floor((i * (stagePath.length - 1)) / (n - 1));
      picks.push(stagePath[idx]);
    }
  }
  picks.reverse();
  return picks;
}

function stepToward(
  drone: DroneState,
  goal: GridPoint,
  wallGrid: Uint8Array,
  rows: number,
  cols: number,
  occupied: Set<number>,
): GridPoint {
  if (drone.r === goal.row && drone.c === goal.col) {
    return { row: drone.r, col: drone.c };
  }
  // Step along shortest path
  const path = gridShortestPath(
    wallGrid,
    rows,
    cols,
    { row: drone.r, col: drone.c },
    goal,
  );
  if (path.length >= 2) {
    const nxt = path[1];
    const idx = nxt.row * cols + nxt.col;
    if (!occupied.has(idx)) return nxt;
  }
  // Fallback: 4-neighbor that reduces Manhattan distance and is unoccupied.
  const moves: GridPoint[] = [
    { row: drone.r - 1, col: drone.c },
    { row: drone.r + 1, col: drone.c },
    { row: drone.r, col: drone.c - 1 },
    { row: drone.r, col: drone.c + 1 },
  ];
  let best: GridPoint = { row: drone.r, col: drone.c };
  let bestDist = Math.abs(drone.r - goal.row) + Math.abs(drone.c - goal.col);
  for (const m of moves) {
    if (m.row < 0 || m.row >= rows || m.col < 0 || m.col >= cols) continue;
    if (wallGrid[m.row * cols + m.col] === 1) continue;
    if (occupied.has(m.row * cols + m.col)) continue;
    const d = Math.abs(m.row - goal.row) + Math.abs(m.col - goal.col);
    if (d < bestDist) {
      bestDist = d;
      best = m;
    }
  }
  return best;
}

function pickMessageKind(uid: number, tick: number): MsgKind | null {
  // Staggered beacon (one per BEACON_INTERVAL ticks per drone).
  if (tick % BEACON_INTERVAL === uid % BEACON_INTERVAL) return 'BEACON';
  if (tick > 0 && tick % MERGE_INTERVAL === uid % MERGE_INTERVAL) return 'TOPOLOGY_MERGE';
  if (tick > 0 && tick % TOKEN_INTERVAL === uid % TOKEN_INTERVAL) return 'TOKEN';
  return null;
}

export interface SwarmResult {
  timeline: FrameState[];
  rfEvents: RFEvent[];
}

export function runSwarm(
  roomGraph: RoomGraph,
  rasterized: RasterizedMap,
  params: SimParams,
  labels: Int16Array,
): SwarmResult {
  const { wallGrid, wallDbGrid, rows, cols } = rasterized;
  const nDrones = Math.max(1, params.nDrones);
  const root = roomGraph.entranceRoomId;
  const targetId = roomGraph.targetRoomId;

  const anchors = new Map<number, GridPoint>();
  for (const room of roomGraph.rooms) anchors.set(room.id, room.anchorCell);

  const { parent, edges, queueSnapshots } = bfsPlan(roomGraph.adjacency, root);

  const edgePaths = new Map<string, GridPoint[]>();
  const edgeKey = (u: number, v: number) => `${u}_${v}`;
  for (const [u, v] of edges) {
    edgePaths.set(
      edgeKey(u, v),
      gridShortestPath(wallGrid, rows, cols, anchors.get(u)!, anchors.get(v)!),
    );
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

  // Spawn drones along stage path. Last UID = scout.
  const spawns = spawnPositions(entranceAnchor, stagePath, nDrones);
  const drones: DroneState[] = spawns.map((p, i) => ({
    uid: i,
    r: p.row,
    c: p.col,
    role: i === nDrones - 1 ? 'scout' : 'relay',
    seq: 0,
  }));
  const scoutUid = nDrones - 1;

  // Simulation state
  let edgeIdx = 0;
  const roomsSeen = new Set<number>([root]);
  const committedBfsEdges: [number, number][] = [];
  let discoveredLine = `${root}`;
  const commLinks: CommLink[] = [];
  const rfLogRing: string[] = [];
  const rfEvents: RFEvent[] = [];
  const timeline: FrameState[] = [];

  const pushRf = (line: string) => {
    rfLogRing.push(line);
    if (rfLogRing.length > RF_LOG_CAPACITY) rfLogRing.shift();
  };

  // Initial staging dwell — drones settle into spawn positions.
  for (let tick = 0; tick < params.dwellFrames; tick++) {
    timeline.push({
      dronesRC: drones.map((d) => ({ row: d.r, col: d.c })),
      droneRoles: drones.map((d) => d.role),
      phase: 'staging',
      caption: CAPTION('Staging — relays line toward primary doorway.', discoveredLine),
      queueRooms: [root],
      phaseLine: 'Idle — waiting to expand first frontier.',
      discoveredLine,
      committedBfsEdges: [],
      commLinks: [],
      rfLogTail: [],
      tick,
      activeEdge: null,
    });
  }

  const maxTicks = 600;
  let tick = params.dwellFrames;
  let neutralised = false;

  while (tick < maxTicks && !neutralised) {
    // Pick active edge — first edge whose target room is not yet seen.
    let activeEdge: [number, number] | null = null;
    let activeQ: number[] = [];
    for (let i = edgeIdx; i < edges.length; i++) {
      if (!roomsSeen.has(edges[i][1])) {
        activeEdge = edges[i];
        activeQ = queueSnapshots[i].slice();
        edgeIdx = i;
        break;
      } else {
        edgeIdx = i + 1;
      }
    }

    if (!activeEdge) break; // all rooms seen

    const [u, w] = activeEdge;
    const motionPath = edgePaths.get(edgeKey(u, w))!;
    const backboneToU = backboneUpto(u);

    // Compute per-drone targets.
    const nRelays = Math.max(0, nDrones - 1);
    const relaySlots: DroneRC[] = nRelays > 0 ? samplePolyline(backboneToU, nRelays) : [];
    const targets: GridPoint[] = drones.map((d) => {
      if (d.uid === scoutUid) {
        return { row: anchors.get(w)!.row, col: anchors.get(w)!.col };
      }
      // Relay UID i (0..nRelays-1) → slot i
      const slot = relaySlots[Math.min(d.uid, relaySlots.length - 1)];
      if (!slot) return { row: d.r, col: d.c };
      return { row: Math.round(slot.row), col: Math.round(slot.col) };
    });

    // Compute simultaneous intents. Apply scout first (priority) then others.
    const occupied = new Set<number>(drones.map((d) => d.r * cols + d.c));
    const order = [scoutUid, ...drones.map((d) => d.uid).filter((u2) => u2 !== scoutUid)];
    for (const uid of order) {
      const d = drones.find((x) => x.uid === uid)!;
      const target = targets[uid];
      occupied.delete(d.r * cols + d.c);
      const next = stepToward(d, target, wallGrid, rows, cols, occupied);
      d.r = next.row;
      d.c = next.col;
      occupied.add(d.r * cols + d.c);
    }

    // Check scout arrival at target room anchor.
    const scout = drones[scoutUid];
    const wAnchor = anchors.get(w)!;
    const arrived =
      Math.abs(scout.r - wAnchor.row) + Math.abs(scout.c - wAnchor.col) <= 1;

    if (arrived) {
      roomsSeen.add(w);
      committedBfsEdges.push([u, w]);
      discoveredLine = `${discoveredLine} → ${w}`;
      edgeIdx++;
    }

    // Radio transmissions this tick.
    for (const d of drones) {
      const kind = pickMessageKind(d.uid, tick);
      if (!kind) continue;
      d.seq++;

      let deliveries = 0;
      let attempts = 0;
      let bestRssi = -Infinity;
      let bestRxId = -1;

      for (const rx of drones) {
        if (rx.uid === d.uid) continue;
        attempts++;
        const rssi = pairwiseRssi(
          wallGrid,
          wallDbGrid,
          cols,
          rows,
          d.r + 0.5,
          d.c + 0.5,
          rx.r + 0.5,
          rx.c + 0.5,
          DEFAULT_RADIO,
        );
        const outcome = rssi >= DEFAULT_RADIO.sensitivityDbm ? 'delivered' : 'below_threshold';
        const ev: RFEvent = {
          tick,
          msgType: kind,
          srcId: d.uid,
          dstId: rx.uid,
          rssiDbm: rssi,
          outcome,
          seq: d.seq,
        };
        rfEvents.push(ev);

        if (outcome === 'delivered') {
          deliveries++;
          if (rssi > bestRssi) {
            bestRssi = rssi;
            bestRxId = rx.uid;
          }
          // Only delivered links draw on canvas.
          commLinks.push({
            ticksLeft: COMM_LINK_TTL_TICKS,
            ttlTicks: COMM_LINK_TTL_TICKS,
            r0: d.r + 0.5,
            c0: d.c + 0.5,
            r1: rx.r + 0.5,
            c1: rx.c + 0.5,
            msgType: kind,
            outcome,
          });
        }
      }

      // One concise summary line per broadcast.
      const tag = `${kind.padEnd(14, ' ')}`;
      const summary =
        bestRxId >= 0
          ? `t=${String(tick).padStart(4, '0')}  ${tag} ${d.uid}→ALL   ${deliveries}/${attempts} rx, best=${bestRssi.toFixed(1)}dBm seq=${d.seq}`
          : `t=${String(tick).padStart(4, '0')}  ${tag} ${d.uid}→ALL   0/${attempts} rx (out of range) seq=${d.seq}`;
      pushRf(summary);
    }

    // Decay comm links.
    for (let i = commLinks.length - 1; i >= 0; i--) {
      commLinks[i].ticksLeft -= 1;
      if (commLinks[i].ticksLeft <= 0) commLinks.splice(i, 1);
    }

    const phase: FrameState['phase'] = arrived ? 'settled' : 'traversing';
    const phaseLine = arrived
      ? `Tick ${tick} — committed parent[${w}]=${u}; relays redistributed.`
      : `Tick ${tick} — scout → R${w} via edge (${u}→${w}). Mesh broadcasts active.`;

    timeline.push({
      dronesRC: drones.map((d) => ({ row: d.r, col: d.c })),
      droneRoles: drones.map((d) => d.role),
      phase,
      caption: CAPTION(
        arrived
          ? `Committed edge (${u}→${w}); relays now align with backbone≤${w}.`
          : `Active edge (${u}→${w}); scout advancing, relays trailing on backbone≤${u}.`,
        discoveredLine,
      ),
      queueRooms: activeQ,
      phaseLine,
      discoveredLine,
      committedBfsEdges: committedBfsEdges.map(([a, b]) => [a, b]),
      commLinks: commLinks.map((l) => ({ ...l })),
      rfLogTail: rfLogRing.slice(),
      tick,
      activeEdge: [u, w],
    });

    if (arrived && w === targetId) {
      neutralised = true;
      for (let k = 0; k < params.dwellFrames; k++) {
        timeline.push({
          dronesRC: drones.map((d) => ({ row: d.r, col: d.c })),
          droneRoles: drones.map((d) => d.role),
          phase: 'neutralised',
          caption: CAPTION(`TARGET ACQUIRED in room ${w}. Mesh holds.`, discoveredLine),
          queueRooms: [],
          phaseLine: 'TARGET ACQUIRED — NEUTRALISED.',
          discoveredLine,
          committedBfsEdges: committedBfsEdges.map(([a, b]) => [a, b]),
          commLinks: commLinks.map((l) => ({ ...l })),
          rfLogTail: rfLogRing.slice(),
          tick: tick + 1 + k,
          activeEdge: null,
        });
      }
    }

    tick++;
  }

  return { timeline, rfEvents };
}
