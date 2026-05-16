import type { DroneRC, GridPoint } from '@/types';

export function gridShortestPath(
  wallGrid: Uint8Array,
  rows: number,
  cols: number,
  start: GridPoint,
  end: GridPoint,
): GridPoint[] {
  if (start.row === end.row && start.col === end.col) {
    return [{ ...start }];
  }
  const startIdx = start.row * cols + start.col;
  const endIdx = end.row * cols + end.col;
  if (wallGrid[startIdx] === 1 || wallGrid[endIdx] === 1) {
    return [start, end];
  }
  const prev = new Int32Array(rows * cols);
  prev.fill(-1);
  prev[startIdx] = startIdx;
  const queue: number[] = [startIdx];
  let head = 0;
  let found = false;

  while (head < queue.length) {
    const cur = queue[head++];
    if (cur === endIdx) {
      found = true;
      break;
    }
    const r = (cur / cols) | 0;
    const c = cur - r * cols;
    const moves = [
      [r - 1, c],
      [r + 1, c],
      [r, c - 1],
      [r, c + 1],
    ];
    for (const [nr, nc] of moves) {
      if (nr < 0 || nr >= rows || nc < 0 || nc >= cols) continue;
      const ni = nr * cols + nc;
      if (wallGrid[ni] === 1) continue;
      if (prev[ni] !== -1) continue;
      prev[ni] = cur;
      queue.push(ni);
    }
  }

  if (!found) {
    return [start, end];
  }

  const path: GridPoint[] = [];
  let cur = endIdx;
  while (cur !== startIdx) {
    const r = (cur / cols) | 0;
    const c = cur - r * cols;
    path.push({ row: r, col: c });
    cur = prev[cur];
  }
  path.push({ row: start.row, col: start.col });
  path.reverse();
  return path;
}

function cellCenter(p: GridPoint): DroneRC {
  return { row: p.row + 0.5, col: p.col + 0.5 };
}

export function interpolatePolyline(path: GridPoint[], t: number): DroneRC {
  if (path.length === 0) return { row: 0, col: 0 };
  if (path.length === 1) return cellCenter(path[0]);
  const pts = path.map(cellCenter);
  const segLens: number[] = [];
  let total = 0;
  for (let i = 0; i < pts.length - 1; i++) {
    const dr = pts[i + 1].row - pts[i].row;
    const dc = pts[i + 1].col - pts[i].col;
    const ln = Math.hypot(dr, dc);
    segLens.push(ln);
    total += ln;
  }
  if (total < 1e-9) return pts[0];
  const clamped = Math.max(0, Math.min(1, t));
  const target = clamped * total;
  let acc = 0;
  for (let i = 0; i < segLens.length; i++) {
    const ln = segLens[i];
    if (acc + ln >= target - 1e-12) {
      const u = ln < 1e-12 ? 0 : (target - acc) / ln;
      return {
        row: pts[i].row + u * (pts[i + 1].row - pts[i].row),
        col: pts[i].col + u * (pts[i + 1].col - pts[i].col),
      };
    }
    acc += ln;
  }
  return pts[pts.length - 1];
}

export function samplePolyline(path: GridPoint[], k: number): DroneRC[] {
  if (k <= 0) return [];
  if (path.length === 0) return [];
  if (k === 1) return [interpolatePolyline(path, 0.5)];
  const out: DroneRC[] = [];
  for (let j = 0; j < k; j++) {
    out.push(interpolatePolyline(path, j / (k - 1)));
  }
  return out;
}

export function concatPaths(parts: GridPoint[][]): GridPoint[] {
  const full: GridPoint[] = [];
  for (const p of parts) {
    if (p.length === 0) continue;
    if (
      full.length > 0 &&
      full[full.length - 1].row === p[0].row &&
      full[full.length - 1].col === p[0].col
    ) {
      for (let i = 1; i < p.length; i++) full.push(p[i]);
    } else {
      for (const cell of p) full.push(cell);
    }
  }
  return full;
}
