'use client';

import { useEffect, useMemo, useRef } from 'react';
import type { CompiledSim, SimParams } from '@/types';
import { CANVAS_H, CANVAS_W, CELL_PX } from '@/constants';
import { fieldStrengthMap } from '@/lib/propagation/fieldStrengthMap';
import { rssiToRGB } from '@/lib/colormap/inferno';
import { msgKindColor, outcomeAlpha } from '@/lib/radio';

export function SimCanvas({
  compiled,
  params,
  currentFrame,
}: {
  compiled: CompiledSim;
  params: SimParams;
  currentFrame: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const frame = compiled.timeline[Math.min(currentFrame, compiled.timeline.length - 1)];

  // Stable wall image: render walls to a hidden offscreen canvas once.
  const wallBitmap = useMemo(() => {
    const off = document.createElement('canvas');
    off.width = CANVAS_W;
    off.height = CANVAS_H;
    const ctx = off.getContext('2d')!;
    ctx.fillStyle = '#ffffff';
    const { wallGrid, rows, cols } = compiled.rasterized;
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        if (wallGrid[r * cols + c] === 1) {
          ctx.fillRect(c * CELL_PX, r * CELL_PX, CELL_PX, CELL_PX);
        }
      }
    }
    return off;
  }, [compiled.rasterized]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    if (!frame) return;

    // Compute RSSI heatmap synchronously.
    const { rasterized, heatmapVmin, heatmapVmax } = compiled;
    const { heatmap, hRows, hCols } = fieldStrengthMap(
      rasterized.wallGrid,
      rasterized.wallDbGrid,
      rasterized.rows,
      rasterized.cols,
      frame.dronesRC,
      rasterized.cellSizeM,
      params,
    );

    // 1. Black background.
    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, CANVAS_W, CANVAS_H);

    // 2. Paint heatmap tiles.
    const stride = params.heatmapStride;
    const tilePx = stride * CELL_PX;
    for (let hi = 0; hi < hRows; hi++) {
      for (let hj = 0; hj < hCols; hj++) {
        const v = heatmap[hi * hCols + hj];
        if (!isFinite(v)) continue;
        const [rC, gC, bC] = rssiToRGB(v, heatmapVmin, heatmapVmax);
        ctx.fillStyle = `rgba(${rC},${gC},${bC},0.75)`;
        ctx.fillRect(hj * tilePx, hi * tilePx, tilePx, tilePx);
      }
    }

    // 3. Wall overlay.
    ctx.drawImage(wallBitmap, 0, 0);

    // 4. Mesh comm links — driven by FrameState.commLinks (BEACON / TOPOLOGY_MERGE / TOKEN).
    const drones = frame.dronesRC;
    for (const link of frame.commLinks) {
      const fade = Math.max(link.ticksLeft / link.ttlTicks, 0.06);
      const alpha = outcomeAlpha(link.outcome) * fade;
      const color = msgKindColor(link.msgType);
      // Convert rgba: parse hex.
      const r = parseInt(color.slice(1, 3), 16);
      const g = parseInt(color.slice(3, 5), 16);
      const b = parseInt(color.slice(5, 7), 16);
      ctx.strokeStyle = `rgba(${r},${g},${b},${alpha.toFixed(3)})`;
      ctx.lineWidth = link.outcome === 'delivered' ? 1.6 : 1;
      ctx.setLineDash(link.outcome === 'below_threshold' ? [4, 3] : []);
      ctx.beginPath();
      ctx.moveTo(link.c0 * CELL_PX, link.r0 * CELL_PX);
      ctx.lineTo(link.c1 * CELL_PX, link.r1 * CELL_PX);
      ctx.stroke();
    }
    ctx.setLineDash([]);

    // 5. Entrance marker.
    const entrance = (() => {
      // approximate from compiled.roomGraph entrance anchor
      const room = compiled.roomGraph.rooms.find((r) => r.id === compiled.roomGraph.entranceRoomId);
      return room?.anchorCell ?? null;
    })();
    if (entrance) {
      const cx = entrance.col * CELL_PX + CELL_PX / 2;
      const cy = entrance.row * CELL_PX + CELL_PX / 2;
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(cx, cy - 8);
      ctx.lineTo(cx + 7, cy + 6);
      ctx.lineTo(cx - 7, cy + 6);
      ctx.closePath();
      ctx.stroke();
    }

    // 6. Target marker (hide if neutralised).
    if (frame.phase !== 'neutralised') {
      const tgtRoom = compiled.roomGraph.rooms.find((r) => r.id === compiled.roomGraph.targetRoomId);
      if (tgtRoom) {
        const { row, col } = tgtRoom.anchorCell;
        const cx = col * CELL_PX + CELL_PX / 2;
        const cy = row * CELL_PX + CELL_PX / 2;
        ctx.strokeStyle = '#ff2030';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(cx, cy, 9, 0, Math.PI * 2);
        ctx.moveTo(cx - 14, cy);
        ctx.lineTo(cx + 14, cy);
        ctx.moveTo(cx, cy - 14);
        ctx.lineTo(cx, cy + 14);
        ctx.stroke();
      }
    }

    // 7. Drones.
    for (let i = 0; i < drones.length; i++) {
      const isScout = frame.droneRoles[i] === 'scout';
      // Cell-center pixel coordinates.
      const cx = (drones[i].col + 0.5) * CELL_PX;
      const cy = (drones[i].row + 0.5) * CELL_PX;
      ctx.fillStyle = isScout ? '#00ffff' : '#ffffff';
      ctx.strokeStyle = '#000';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.arc(cx, cy, isScout ? 7 : 5, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      // UID label
      ctx.fillStyle = '#000';
      ctx.font = '8px monospace';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(String(i), cx, cy);
    }
  }, [frame, compiled, params, wallBitmap]);

  return (
    <canvas
      ref={canvasRef}
      width={CANVAS_W}
      height={CANVAS_H}
      className="border border-white/10"
    />
  );
}
