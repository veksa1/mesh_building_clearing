import type { DoorMarker, GridPoint, RoomGraph, RoomData } from '@/types';

export function buildRoomGraph(
  labels: Int16Array,
  rows: number,
  cols: number,
  doors: DoorMarker[],
  entrance: GridPoint,
  target: GridPoint,
): RoomGraph {
  const regionCells = new Map<number, GridPoint[]>();
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const id = labels[r * cols + c];
      if (id < 0) continue;
      const list = regionCells.get(id);
      if (list) list.push({ row: r, col: c });
      else regionCells.set(id, [{ row: r, col: c }]);
    }
  }

  const rooms: RoomData[] = [];
  for (const [id, cells] of regionCells.entries()) {
    let sumR = 0;
    let sumC = 0;
    for (const cell of cells) {
      sumR += cell.row;
      sumC += cell.col;
    }
    const cr = sumR / cells.length;
    const cc = sumC / cells.length;
    let best = cells[0];
    let bestD = Infinity;
    for (const cell of cells) {
      const d = (cell.row - cr) * (cell.row - cr) + (cell.col - cc) * (cell.col - cc);
      if (d < bestD) {
        bestD = d;
        best = cell;
      }
    }
    rooms.push({ id, anchorCell: best });
  }
  rooms.sort((a, b) => a.id - b.id);

  const adjacency = new Map<number, number[]>();
  for (const room of rooms) adjacency.set(room.id, []);

  const addEdge = (a: number, b: number) => {
    if (a === b || a < 0 || b < 0) return;
    const la = adjacency.get(a)!;
    const lb = adjacency.get(b)!;
    if (!la.includes(b)) la.push(b);
    if (!lb.includes(a)) lb.push(a);
  };

  const sampleRegion = (r: number, c: number): number => {
    if (r < 0 || r >= rows || c < 0 || c >= cols) return -1;
    return labels[r * cols + c];
  };

  for (const door of doors) {
    const { centerCell, dominantAxis } = door;
    let sideA = -1;
    let sideB = -1;
    if (dominantAxis === 'col') {
      for (let off = 1; off <= 3; off++) {
        if (sideA < 0) sideA = sampleRegion(centerCell.row - off, centerCell.col);
        if (sideB < 0) sideB = sampleRegion(centerCell.row + off, centerCell.col);
        if (sideA >= 0 && sideB >= 0) break;
      }
    } else {
      for (let off = 1; off <= 3; off++) {
        if (sideA < 0) sideA = sampleRegion(centerCell.row, centerCell.col - off);
        if (sideB < 0) sideB = sampleRegion(centerCell.row, centerCell.col + off);
        if (sideA >= 0 && sideB >= 0) break;
      }
    }
    if (sideA >= 0 && sideB >= 0 && sideA !== sideB) {
      addEdge(sideA, sideB);
    }
  }

  const entranceRoomId = labels[entrance.row * cols + entrance.col];
  const targetRoomId = labels[target.row * cols + target.col];

  return { rooms, adjacency, entranceRoomId, targetRoomId };
}
