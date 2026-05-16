export type WallMaterialId = 'concrete' | 'brick' | 'drywall' | 'glass';

export interface WallMaterial {
  id: WallMaterialId;
  label: string;
  attenuationDb: number;
  displayColor: string;
}

export interface GridPoint {
  row: number;
  col: number;
}

export interface WallSegment {
  id: string;
  start: GridPoint;
  end: GridPoint;
  material: WallMaterialId;
}

export interface DoorMarker {
  id: string;
  wallSegmentId: string;
  centerCell: GridPoint;
  widthCells: number;
  dominantAxis: 'row' | 'col';
}

export interface FloorplanData {
  gridRows: number;
  gridCols: number;
  walls: WallSegment[];
  doors: DoorMarker[];
  entrance: GridPoint | null;
  target: GridPoint | null;
}

export type EditorTool = 'wall' | 'door' | 'entrance' | 'target';

export interface EditorState {
  tool: EditorTool;
  selectedMaterial: WallMaterialId;
  pendingWallStart: GridPoint | null;
  hoveredCell: GridPoint | null;
}

export type AppMode = 'editing' | 'compiling' | 'simulating' | 'finished';

export interface RasterizedMap {
  wallGrid: Uint8Array;       // navigation grid — doors erased to walkable
  wallGridFull: Uint8Array;   // room-detection grid — walls intact at door positions
  rows: number;
  cols: number;
  cellSizeM: number;
  wallDbGrid: Float32Array;
}

export interface RoomData {
  id: number;
  anchorCell: GridPoint;
}

export interface RoomGraph {
  rooms: RoomData[];
  adjacency: Map<number, number[]>;
  entranceRoomId: number;
  targetRoomId: number;
}

export type DroneRC = { row: number; col: number };

export type SimPhase = 'staging' | 'traversing' | 'settled' | 'neutralised' | 'exploring';

export type MsgKind = 'BEACON' | 'TOPOLOGY_MERGE' | 'TOKEN';
export type MsgOutcome = 'delivered' | 'below_threshold' | 'tx';

export interface CommLink {
  ticksLeft: number;
  ttlTicks: number;
  r0: number;
  c0: number;
  r1: number;
  c1: number;
  msgType: MsgKind;
  outcome: MsgOutcome;
}

export interface RFEvent {
  tick: number;
  msgType: MsgKind;
  srcId: number;
  dstId: number | 'broadcast';
  rssiDbm: number | null;
  outcome: MsgOutcome;
  seq: number;
}

export type DroneRole = 'scout' | 'relay';

// One YOLO-shaped detection emitted by a drone's onboard CV stack.
export interface CvDetection {
  uid: number;
  kind: 'DOORWAY_GAP' | 'CORRIDOR_BRANCH' | 'TARGET';
  bearing: [number, number];
  anchor: [number, number];
  confidence: number;
  signature: string;
}

export interface TargetWitness {
  uid: number;
  row: number;
  col: number;
  confidence: number;
}

// Oracle-only ground truth that lives alongside the per-tick frame.
// Agents do not see this — it is solely for browser-side oracle visualization.
export interface OracleFrameOverlay {
  roomsDiscovered: number[];
  queueRooms: number[];
  committedEdges: [number, number][];
  spanningEdges: [number, number][];
}

export interface FrameState {
  tick: number;
  phase: SimPhase;
  dronesRC: DroneRC[];
  commLinks: CommLink[];
  rfLogTail: string[];
  cvDetections: CvDetection[];
  beliefEdges: [string, string, string][];
  // Cells newly observed since the previous tick — renderer accumulates the fog mask.
  knownFreeDelta: [number, number][];
  // Flat int array [r0,c0,r1,c1,...] for the lead explorer's BFS spanning tree.
  // Refreshed only on keyframes; null between keyframes (renderer carries the last value).
  treeSegmentsRC: number[] | null;
  targetSeen: boolean;
  targetWitness: TargetWitness | null;
  phaseLine: string;
  discoveredLine: string;
  caption: string;
  oracle: OracleFrameOverlay;
}

export interface SimParams {
  freqMhz: number;
  txPowerDbm: number;
  distanceExponent: number;
  nDrones: number;
  framesPerEdge: number;
  dwellFrames: number;
  heatmapStride: number;
  raySamples: number;
}

export interface CompiledSim {
  rasterized: RasterizedMap;
  roomGraph: RoomGraph;
  timeline: FrameState[];
  heatmapVmin: number;
  heatmapVmax: number;
  meta: SimulationBundleMeta;
  entrance: GridPoint;
  target: GridPoint;
}

export interface SimulationBundleMeta {
  name: string;
  ticks: number;
  nDrones: number;
  seed: number;
  policy: string;
  schemaVersion: number;
}

export type AppAction =
  | { type: 'SET_TOOL'; tool: EditorTool }
  | { type: 'SET_MATERIAL'; material: WallMaterialId }
  | { type: 'ADD_WALL'; segment: WallSegment }
  | { type: 'ADD_DOOR'; door: DoorMarker }
  | { type: 'DELETE_WALL'; id: string }
  | { type: 'SET_ENTRANCE'; cell: GridPoint }
  | { type: 'SET_TARGET'; cell: GridPoint }
  | { type: 'SET_HOVERED'; cell: GridPoint | null }
  | { type: 'SET_PENDING_WALL_START'; cell: GridPoint | null }
  | { type: 'CLEAR_FLOORPLAN' }
  | { type: 'SET_N_DRONES'; value: number }
  | { type: 'RUN_SIMULATION' }
  | { type: 'COMPILATION_DONE'; result: CompiledSim }
  | { type: 'COMPILATION_FAILED'; error: string }
  | { type: 'TICK_FRAME' }
  | { type: 'SEEK_FRAME'; frame: number }
  | { type: 'TOGGLE_PLAY' }
  | { type: 'RESET' };

export interface AppState {
  mode: AppMode;
  floorplan: FloorplanData;
  editor: EditorState;
  simParams: SimParams;
  compiled: CompiledSim | null;
  currentFrame: number;
  isPlaying: boolean;
  compilationError: string | null;
}

export interface RSSIRequest {
  type: 'init' | 'compute';
  wallGrid?: ArrayBuffer;
  wallDbGrid?: ArrayBuffer;
  rows?: number;
  cols?: number;
  cellSizeM?: number;
  dronesRC?: Float32Array;
  nDrones?: number;
  params?: SimParams;
  frameId?: number;
}

export interface RSSIResponse {
  type: 'result';
  heatmap: ArrayBuffer;
  hRows: number;
  hCols: number;
  frameId: number;
}
