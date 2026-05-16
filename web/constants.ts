import type { SimParams, WallMaterial } from './types';

export const GRID_ROWS = 60;
export const GRID_COLS = 80;
export const CELL_PX = 12;
export const CANVAS_W = GRID_COLS * CELL_PX;
export const CANVAS_H = GRID_ROWS * CELL_PX;
export const CELL_SIZE_M = 0.22;
export const DOOR_WIDTH_CELLS = 4;
export const FRAME_INTERVAL_MS = 90;
export const MESH_LINK_THRESHOLD_DBM = -70;

export const WALL_MATERIALS: WallMaterial[] = [
  { id: 'concrete', label: 'Concrete', attenuationDb: 15, displayColor: '#ffffff' },
  { id: 'brick', label: 'Brick', attenuationDb: 10, displayColor: '#ffffff' },
  { id: 'drywall', label: 'Drywall', attenuationDb: 5, displayColor: '#ffffff' },
  { id: 'glass', label: 'Glass', attenuationDb: 3, displayColor: '#ffffff' },
];

export const DEFAULT_SIM_PARAMS: SimParams = {
  freqMhz: 2400,
  txPowerDbm: 20,
  distanceExponent: 28,
  nDrones: 7,
  framesPerEdge: 32,
  dwellFrames: 10,
  heatmapStride: 3,
  raySamples: 48,
};
