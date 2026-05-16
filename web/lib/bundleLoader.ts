import type {
  CompiledSim,
  CommLink,
  CvDetection,
  DroneRC,
  FrameState,
  GridPoint,
  RoomData,
  RoomGraph,
  SimulationBundleMeta,
  TargetWitness,
} from '@/types';
import { fieldStrengthMap } from './propagation/fieldStrengthMap';
import { DEFAULT_SIM_PARAMS } from '@/constants';

interface RawCommLink {
  ticksLeft: number;
  ttlTicks: number;
  r0: number;
  c0: number;
  r1: number;
  c1: number;
  msgType: 'BEACON' | 'TOPOLOGY_MERGE' | 'TOKEN';
  outcome: 'delivered' | 'below_threshold' | 'tx';
}

interface RawCv {
  uid: number;
  kind: CvDetection['kind'];
  bearing: [number, number];
  anchor: [number, number];
  confidence: number;
  signature: string;
}

interface RawFrame {
  tick: number;
  phase: FrameState['phase'];
  dronesRC: DroneRC[];
  commLinks: RawCommLink[];
  rfLogTail: string[];
  cvDetections: RawCv[];
  beliefEdges: [string, string, string][];
  knownFreeDelta: [number, number][];
  treeSegmentsRC: number[] | null;
  targetSeen: boolean;
  targetWitness: TargetWitness | null;
  phaseLine: string;
  discoveredLine: string;
  caption: string;
  oracle: {
    roomsDiscovered: number[];
    queueRooms: number[];
    committedEdges: [number, number][];
    spanningEdges: [number, number][];
  };
}

interface RawBundle {
  schemaVersion: number;
  meta: {
    name: string;
    ticks: number;
    nDrones: number;
    seed: number;
    policy: string;
  };
  rasterized: {
    rows: number;
    cols: number;
    cellSizeM: number;
    wallGrid: number[];
    wallGridFull: number[];
    wallDbGrid: number[];
  };
  floorplan: unknown;
  params: Record<string, number>;
  roomGraph: {
    rooms: { id: number; anchorCell: GridPoint }[];
    adjacency: { room: number; neighbors: number[] }[];
    entranceRoomId: number;
    targetRoomId: number;
    spanningEdges: [number, number][];
  };
  entrance: GridPoint;
  target: GridPoint;
  timeline: RawFrame[];
}

function toUint8(arr: number[]): Uint8Array {
  const out = new Uint8Array(arr.length);
  for (let i = 0; i < arr.length; i++) out[i] = arr[i] | 0;
  return out;
}

function toFloat32(arr: number[]): Float32Array {
  const out = new Float32Array(arr.length);
  for (let i = 0; i < arr.length; i++) out[i] = arr[i];
  return out;
}

function adoptFrame(raw: RawFrame): FrameState {
  return {
    tick: raw.tick,
    phase: raw.phase,
    dronesRC: raw.dronesRC,
    commLinks: raw.commLinks as CommLink[],
    rfLogTail: raw.rfLogTail,
    cvDetections: raw.cvDetections,
    beliefEdges: raw.beliefEdges,
    knownFreeDelta: raw.knownFreeDelta,
    treeSegmentsRC: raw.treeSegmentsRC,
    targetSeen: raw.targetSeen,
    targetWitness: raw.targetWitness,
    phaseLine: raw.phaseLine,
    discoveredLine: raw.discoveredLine,
    caption: raw.caption,
    oracle: raw.oracle,
  };
}

function adoptRoomGraph(raw: RawBundle['roomGraph']): RoomGraph {
  const rooms: RoomData[] = raw.rooms.map((r) => ({
    id: r.id,
    anchorCell: r.anchorCell,
  }));
  const adjacency = new Map<number, number[]>();
  for (const a of raw.adjacency) adjacency.set(a.room, a.neighbors);
  return {
    rooms,
    adjacency,
    entranceRoomId: raw.entranceRoomId,
    targetRoomId: raw.targetRoomId,
  };
}

function deriveHeatmapRange(
  rasterized: { wallGrid: Uint8Array; wallDbGrid: Float32Array; rows: number; cols: number; cellSizeM: number },
  firstFrame: FrameState,
): { vmin: number; vmax: number } {
  const { heatmap } = fieldStrengthMap(
    rasterized.wallGrid,
    rasterized.wallDbGrid,
    rasterized.rows,
    rasterized.cols,
    firstFrame.dronesRC,
    rasterized.cellSizeM,
    DEFAULT_SIM_PARAMS,
  );
  const finite = Array.from(heatmap).filter((v) => Number.isFinite(v));
  finite.sort((a, b) => a - b);
  const pick = (q: number) => finite[Math.floor((finite.length - 1) * q)] ?? 0;
  return { vmin: pick(0.05) - 5, vmax: pick(0.95) + 8 };
}

export interface LoadedSim extends CompiledSim {}

export function adoptBundle(raw: RawBundle): LoadedSim {
  const rows = raw.rasterized.rows;
  const cols = raw.rasterized.cols;
  const wallGrid = toUint8(raw.rasterized.wallGrid);
  const wallGridFull = toUint8(raw.rasterized.wallGridFull);
  const wallDbGrid = toFloat32(raw.rasterized.wallDbGrid);
  const rasterized = {
    wallGrid,
    wallGridFull,
    wallDbGrid,
    rows,
    cols,
    cellSizeM: raw.rasterized.cellSizeM,
  };
  const timeline = raw.timeline.map(adoptFrame);
  const roomGraph = adoptRoomGraph(raw.roomGraph);
  const meta: SimulationBundleMeta = {
    schemaVersion: raw.schemaVersion,
    name: raw.meta.name,
    ticks: raw.meta.ticks,
    nDrones: raw.meta.nDrones,
    seed: raw.meta.seed,
    policy: raw.meta.policy,
  };
  const { vmin, vmax } = deriveHeatmapRange(rasterized, timeline[0]);
  return {
    rasterized,
    roomGraph,
    timeline,
    heatmapVmin: vmin,
    heatmapVmax: vmax,
    meta,
    entrance: raw.entrance,
    target: raw.target,
  };
}

export async function loadDefaultBundle(): Promise<LoadedSim> {
  const url = `${process.env.NEXT_PUBLIC_BASE_PATH ?? ''}/sim/default.bundle.json`;
  const res = await fetch(url, { cache: 'no-store' });
  if (!res.ok) {
    throw new Error(
      `Failed to load /sim/default.bundle.json (${res.status}). ` +
        `Run \`npm run sim:export\` to generate it.`,
    );
  }
  const raw = (await res.json()) as RawBundle;
  if (raw.schemaVersion !== 1) {
    throw new Error(`Unsupported bundle schemaVersion ${raw.schemaVersion}; expected 1.`);
  }
  return adoptBundle(raw);
}

export interface LiveExportOptions {
  ticks?: number;
  nDrones?: number;
  seed?: number;
  explorerPhaseTicks?: number | null;
  params?: Record<string, number>;
}

export async function fetchLiveBundle(
  url: string,
  floorplan: unknown,
  opts: LiveExportOptions = {},
  signal?: AbortSignal,
): Promise<LoadedSim> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  const token = process.env.NEXT_PUBLIC_SIM_EXPORT_TOKEN;
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const body = JSON.stringify({
    floorplan,
    ticks: opts.ticks ?? 200,
    nDrones: opts.nDrones ?? 3,
    seed: opts.seed ?? 0,
    explorerPhaseTicks: opts.explorerPhaseTicks ?? 25,
    // Backend left to the server default (SIM_COMM_BACKEND, normally "udp").
    // UDP startup failures now raise within ~15s (sim_kernel_udp handshake
    // timeout) and _run_local_sense falls back to the in-process kernel.
    ...(opts.params ? { params: opts.params } : {}),
  });

  let res: Response;
  try {
    res = await fetch(url, { method: 'POST', headers, body, signal, cache: 'no-store' });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new Error(`Cannot reach simulation API at ${url}: ${msg}`);
  }
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    let detail = text;
    try {
      const parsed = JSON.parse(text);
      detail = typeof parsed?.detail === 'string' ? parsed.detail : text;
    } catch {
      // text isn't JSON; use as-is
    }
    throw new Error(
      `Simulation API ${url} returned ${res.status}${detail ? `: ${detail}` : ''}`,
    );
  }
  const raw = (await res.json()) as RawBundle;
  if (raw.schemaVersion !== 1) {
    throw new Error(`Unsupported bundle schemaVersion ${raw.schemaVersion}; expected 1.`);
  }
  return adoptBundle(raw);
}
