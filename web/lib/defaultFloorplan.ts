import type { FloorplanData, WallSegment, DoorMarker } from '@/types';

let counter = 0;
const id = (prefix: string) => `${prefix}_${++counter}`;

function wall(
  r1: number,
  c1: number,
  r2: number,
  c2: number,
  material: 'concrete' | 'brick' | 'drywall' | 'glass' = 'drywall',
): WallSegment {
  return { id: id('w'), start: { row: r1, col: c1 }, end: { row: r2, col: c2 }, material };
}

function door(
  wallId: string,
  row: number,
  col: number,
  axis: 'row' | 'col',
): DoorMarker {
  return {
    id: id('d'),
    wallSegmentId: wallId,
    centerCell: { row, col },
    widthCells: 4,
    dominantAxis: axis,
  };
}

export function defaultFloorplan(): FloorplanData {
  // 80x60 grid demo floorplan modeled after build_small_office.
  const walls: WallSegment[] = [];

  // Outer perimeter (concrete).
  const topWall = wall(8, 10, 8, 70, 'concrete');
  const bottomWall = wall(55, 10, 55, 70, 'concrete');
  const leftWall = wall(8, 10, 55, 10, 'concrete');
  const rightWall = wall(8, 70, 55, 70, 'concrete');
  walls.push(topWall, bottomWall, leftWall, rightWall);

  // Horizontal slab between lobby (south) and upper rooms (north).
  const horizSlab = wall(38, 10, 38, 70, 'drywall');
  walls.push(horizSlab);

  // R1/R2 vertical split (col 55, rows 8-38).
  const vert12 = wall(8, 55, 38, 55, 'drywall');
  walls.push(vert12);

  // R3/R1 vertical split (col 27, rows 8-38).
  const vert31 = wall(8, 27, 38, 27, 'drywall');
  walls.push(vert31);

  const doors: DoorMarker[] = [
    // Lobby ↔ Center (R1) — gap on horizontal slab at col ~42.
    door(horizSlab.id, 38, 42, 'col'),
    // R1 ↔ R2 — gap on vertical split at row ~24.
    door(vert12.id, 24, 55, 'row'),
    // R3 ↔ R1 — gap on vertical split at row ~30.
    door(vert31.id, 30, 27, 'row'),
  ];

  return {
    gridRows: 60,
    gridCols: 80,
    walls,
    doors,
    entrance: { row: 52, col: 40 },
    target: { row: 15, col: 63 },
  };
}
