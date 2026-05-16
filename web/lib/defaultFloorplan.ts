import type { FloorplanData, WallSegment, DoorMarker } from '@/types';

function wall(
  id: string,
  r1: number,
  c1: number,
  r2: number,
  c2: number,
  material: 'concrete' | 'brick' | 'drywall' | 'glass' = 'drywall',
): WallSegment {
  return { id, start: { row: r1, col: c1 }, end: { row: r2, col: c2 }, material };
}

function door(
  id: string,
  wallId: string,
  row: number,
  col: number,
  axis: 'row' | 'col',
): DoorMarker {
  return {
    id,
    wallSegmentId: wallId,
    centerCell: { row, col },
    widthCells: 4,
    dominantAxis: axis,
  };
}

// Default floorplan — kept in lockstep with web/public/floorplans/default.json
// so the Python exporter and the editor seed share identical geometry.
export function defaultFloorplan(): FloorplanData {
  const walls: WallSegment[] = [
    wall('w_top', 8, 10, 8, 70, 'concrete'),
    wall('w_bottom', 55, 10, 55, 70, 'concrete'),
    wall('w_left', 8, 10, 55, 10, 'concrete'),
    wall('w_right', 8, 70, 55, 70, 'concrete'),
    wall('w_slab', 38, 10, 38, 70, 'drywall'),
    wall('w_vert12', 8, 55, 38, 55, 'drywall'),
    wall('w_vert31', 8, 27, 38, 27, 'drywall'),
  ];

  const doors: DoorMarker[] = [
    door('d_lobby', 'w_slab', 38, 42, 'col'),
    door('d_r1r2', 'w_vert12', 24, 55, 'row'),
    door('d_r3r1', 'w_vert31', 30, 27, 'row'),
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
