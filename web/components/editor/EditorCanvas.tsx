'use client';

import { useEffect, useRef, type Dispatch } from 'react';
import type { AppAction, AppState } from '@/types';
import { CANVAS_H, CANVAS_W, CELL_PX, GRID_COLS, GRID_ROWS } from '@/constants';
import { gridLine } from '@/lib/algorithms/bresenham';
import { useEditorCanvas } from '@/hooks/useEditorCanvas';

export function EditorCanvas({ state, dispatch }: { state: AppState; dispatch: Dispatch<AppAction> }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  useEditorCanvas(canvasRef, state, dispatch);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, CANVAS_W, CANVAS_H);

    // Faint grid lines.
    ctx.strokeStyle = '#1a1a1a';
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let c = 0; c <= GRID_COLS; c++) {
      ctx.moveTo(c * CELL_PX + 0.5, 0);
      ctx.lineTo(c * CELL_PX + 0.5, CANVAS_H);
    }
    for (let r = 0; r <= GRID_ROWS; r++) {
      ctx.moveTo(0, r * CELL_PX + 0.5);
      ctx.lineTo(CANVAS_W, r * CELL_PX + 0.5);
    }
    ctx.stroke();

    // Walls.
    ctx.fillStyle = '#ffffff';
    for (const seg of state.floorplan.walls) {
      for (const cell of gridLine(seg.start, seg.end)) {
        ctx.fillRect(cell.col * CELL_PX, cell.row * CELL_PX, CELL_PX, CELL_PX);
      }
    }

    // Door gaps.
    ctx.fillStyle = '#000';
    for (const door of state.floorplan.doors) {
      const radius = Math.floor(door.widthCells / 2);
      for (let off = -radius; off <= radius; off++) {
        let r = door.centerCell.row;
        let c = door.centerCell.col;
        if (door.dominantAxis === 'col') c += off;
        else r += off;
        ctx.fillRect(c * CELL_PX, r * CELL_PX, CELL_PX, CELL_PX);
      }
    }

    // Entrance marker — white triangle pointing up.
    if (state.floorplan.entrance) {
      const { row, col } = state.floorplan.entrance;
      const cx = col * CELL_PX + CELL_PX / 2;
      const cy = row * CELL_PX + CELL_PX / 2;
      ctx.strokeStyle = '#ffffff';
      ctx.fillStyle = '#000';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(cx, cy - 8);
      ctx.lineTo(cx + 7, cy + 6);
      ctx.lineTo(cx - 7, cy + 6);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
    }

    // Target marker — red crosshair + circle.
    if (state.floorplan.target) {
      const { row, col } = state.floorplan.target;
      const cx = col * CELL_PX + CELL_PX / 2;
      const cy = row * CELL_PX + CELL_PX / 2;
      ctx.strokeStyle = '#ff2030';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(cx, cy, 8, 0, Math.PI * 2);
      ctx.moveTo(cx - 12, cy);
      ctx.lineTo(cx + 12, cy);
      ctx.moveTo(cx, cy - 12);
      ctx.lineTo(cx, cy + 12);
      ctx.stroke();
    }

    // Pending wall preview line.
    if (state.editor.tool === 'wall' && state.editor.pendingWallStart) {
      const a = state.editor.pendingWallStart;
      const b = state.editor.hoveredCell ?? a;
      ctx.strokeStyle = 'rgba(255,255,255,0.45)';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(a.col * CELL_PX + CELL_PX / 2, a.row * CELL_PX + CELL_PX / 2);
      ctx.lineTo(b.col * CELL_PX + CELL_PX / 2, b.row * CELL_PX + CELL_PX / 2);
      ctx.stroke();
      // Mark the start corner.
      ctx.fillStyle = '#fff';
      ctx.fillRect(a.col * CELL_PX + 3, a.row * CELL_PX + 3, CELL_PX - 6, CELL_PX - 6);
    }

    // Hovered cell highlight.
    if (state.editor.hoveredCell) {
      const { row, col } = state.editor.hoveredCell;
      ctx.fillStyle = 'rgba(255,255,255,0.10)';
      ctx.fillRect(col * CELL_PX, row * CELL_PX, CELL_PX, CELL_PX);
    }
  }, [state.floorplan, state.editor]);

  return (
    <canvas
      ref={canvasRef}
      width={CANVAS_W}
      height={CANVAS_H}
      className="cursor-crosshair border border-white/10"
    />
  );
}
