'use client';

import { useEffect, type RefObject, type Dispatch } from 'react';
import type { AppAction, AppState, GridPoint } from '@/types';
import { CELL_PX, GRID_COLS, GRID_ROWS } from '@/constants';

function cellFromMouse(e: MouseEvent, rect: DOMRect): GridPoint {
  const x = e.clientX - rect.left;
  const y = e.clientY - rect.top;
  const col = Math.max(0, Math.min(GRID_COLS - 1, Math.floor(x / CELL_PX)));
  const row = Math.max(0, Math.min(GRID_ROWS - 1, Math.floor(y / CELL_PX)));
  return { row, col };
}

function uid(prefix: string): string {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}

export function useEditorCanvas(
  canvasRef: RefObject<HTMLCanvasElement | null>,
  state: AppState,
  dispatch: Dispatch<AppAction>,
) {
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const onMouseMove = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      const cell = cellFromMouse(e, rect);
      dispatch({ type: 'SET_HOVERED', cell });
    };

    const onMouseLeave = () => {
      dispatch({ type: 'SET_HOVERED', cell: null });
    };

    const onMouseDown = (e: MouseEvent) => {
      if (e.button !== 0) return;
      const rect = canvas.getBoundingClientRect();
      const cell = cellFromMouse(e, rect);
      const { tool, selectedMaterial, pendingWallStart } = state.editor;

      if (tool === 'wall') {
        if (!pendingWallStart) {
          dispatch({ type: 'SET_PENDING_WALL_START', cell });
        } else {
          // Don't create zero-length walls
          if (pendingWallStart.row === cell.row && pendingWallStart.col === cell.col) {
            dispatch({ type: 'SET_PENDING_WALL_START', cell: null });
            return;
          }
          dispatch({
            type: 'ADD_WALL',
            segment: {
              id: uid('w'),
              start: pendingWallStart,
              end: cell,
              material: selectedMaterial,
            },
          });
          dispatch({ type: 'SET_PENDING_WALL_START', cell: null });
        }
      } else if (tool === 'door') {
        // Find nearest wall segment to clicked cell.
        const walls = state.floorplan.walls;
        if (walls.length === 0) return;
        let bestSeg = walls[0];
        let bestDist = Infinity;
        for (const seg of walls) {
          // Distance from point to line segment (in grid cells).
          const ax = seg.start.col;
          const ay = seg.start.row;
          const bx = seg.end.col;
          const by = seg.end.row;
          const dx = bx - ax;
          const dy = by - ay;
          const len2 = dx * dx + dy * dy || 1;
          let t = ((cell.col - ax) * dx + (cell.row - ay) * dy) / len2;
          t = Math.max(0, Math.min(1, t));
          const px = ax + t * dx;
          const py = ay + t * dy;
          const d = Math.hypot(cell.col - px, cell.row - py);
          if (d < bestDist) {
            bestDist = d;
            bestSeg = seg;
          }
        }
        if (bestDist > 3) return; // require click near a wall

        const dr = Math.abs(bestSeg.end.row - bestSeg.start.row);
        const dc = Math.abs(bestSeg.end.col - bestSeg.start.col);
        const dominantAxis: 'row' | 'col' = dc >= dr ? 'col' : 'row';

        // Project clicked cell onto the segment to get exact door center.
        const ax = bestSeg.start.col;
        const ay = bestSeg.start.row;
        const bx = bestSeg.end.col;
        const by = bestSeg.end.row;
        const dx = bx - ax;
        const dy = by - ay;
        const len2 = dx * dx + dy * dy || 1;
        let t = ((cell.col - ax) * dx + (cell.row - ay) * dy) / len2;
        t = Math.max(0, Math.min(1, t));
        const centerCol = Math.round(ax + t * dx);
        const centerRow = Math.round(ay + t * dy);

        dispatch({
          type: 'ADD_DOOR',
          door: {
            id: uid('d'),
            wallSegmentId: bestSeg.id,
            centerCell: { row: centerRow, col: centerCol },
            widthCells: 4,
            dominantAxis,
          },
        });
      } else if (tool === 'entrance') {
        dispatch({ type: 'SET_ENTRANCE', cell });
      } else if (tool === 'target') {
        dispatch({ type: 'SET_TARGET', cell });
      }
    };

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        dispatch({ type: 'SET_PENDING_WALL_START', cell: null });
      }
    };

    canvas.addEventListener('mousemove', onMouseMove);
    canvas.addEventListener('mouseleave', onMouseLeave);
    canvas.addEventListener('mousedown', onMouseDown);
    window.addEventListener('keydown', onKeyDown);
    return () => {
      canvas.removeEventListener('mousemove', onMouseMove);
      canvas.removeEventListener('mouseleave', onMouseLeave);
      canvas.removeEventListener('mousedown', onMouseDown);
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [canvasRef, state, dispatch]);
}
