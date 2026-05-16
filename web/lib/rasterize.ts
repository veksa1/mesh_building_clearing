import type { FloorplanData, RasterizedMap } from '@/types';
import { CELL_SIZE_M, DOOR_WIDTH_CELLS, GRID_COLS, GRID_ROWS, WALL_MATERIALS } from '@/constants';
import { gridLine } from './algorithms/bresenham';

export function rasterize(floorplan: FloorplanData): RasterizedMap {
  const rows = GRID_ROWS;
  const cols = GRID_COLS;
  const wallGridFull = new Uint8Array(rows * cols);
  const wallDbGrid = new Float32Array(rows * cols);

  for (const seg of floorplan.walls) {
    const mat = WALL_MATERIALS.find((m) => m.id === seg.material);
    const db = mat ? mat.attenuationDb : 5;
    const cells = gridLine(seg.start, seg.end);
    for (const cell of cells) {
      const idx = cell.row * cols + cell.col;
      wallGridFull[idx] = 1;
      wallDbGrid[idx] = db;
    }
  }

  // Navigation grid = full grid with door cells erased.
  const wallGrid = new Uint8Array(wallGridFull);
  for (const door of floorplan.doors) {
    const radius = Math.max(1, Math.floor(door.widthCells / 2));
    for (let off = -radius; off <= radius; off++) {
      let r = door.centerCell.row;
      let c = door.centerCell.col;
      if (door.dominantAxis === 'col') c += off;
      else r += off;
      if (r < 0 || r >= rows || c < 0 || c >= cols) continue;
      const idx = r * cols + c;
      wallGrid[idx] = 0;
      wallDbGrid[idx] = 0;
    }
  }

  void DOOR_WIDTH_CELLS;

  return { wallGrid, wallGridFull, wallDbGrid, rows, cols, cellSizeM: CELL_SIZE_M };
}
