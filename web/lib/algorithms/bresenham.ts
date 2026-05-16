import type { GridPoint } from '@/types';
import { GRID_COLS, GRID_ROWS } from '@/constants';

export function gridLine(start: GridPoint, end: GridPoint): GridPoint[] {
  const out: GridPoint[] = [];
  let r0 = start.row;
  let c0 = start.col;
  const r1 = end.row;
  const c1 = end.col;
  const dr = Math.abs(r1 - r0);
  const dc = Math.abs(c1 - c0);
  const sr = r0 < r1 ? 1 : -1;
  const sc = c0 < c1 ? 1 : -1;
  let err = dc - dr;

  while (true) {
    if (r0 >= 0 && r0 < GRID_ROWS && c0 >= 0 && c0 < GRID_COLS) {
      out.push({ row: r0, col: c0 });
    }
    if (r0 === r1 && c0 === c1) break;
    const e2 = 2 * err;
    if (e2 > -dr) {
      err -= dr;
      c0 += sc;
    }
    if (e2 < dc) {
      err += dc;
      r0 += sr;
    }
  }
  return out;
}
