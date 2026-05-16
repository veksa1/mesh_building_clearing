'use client';

import { useEffect, useMemo, useRef } from 'react';
import type { CompiledSim, SimParams, ViewMode } from '@/types';
import { CANVAS_H, CANVAS_W, CELL_PX } from '@/constants';
import { fieldStrengthMap } from '@/lib/propagation/fieldStrengthMap';
import { rssiToRGB } from '@/lib/colormap/inferno';
import { msgKindColor, outcomeAlpha } from '@/lib/radio';

// Per-tick CommLink TTL applied in the browser (Python bundle only emits fresh links).
const LINK_RENDER_TTL = 5;

type RenderLink = {
  r0: number;
  c0: number;
  r1: number;
  c1: number;
  msgType: 'BEACON' | 'TOPOLOGY_MERGE' | 'TOKEN';
  outcome: 'delivered' | 'below_threshold' | 'tx';
  age: number;
};

export function SimCanvas({
  compiled,
  params,
  currentFrame,
  viewMode,
}: {
  compiled: CompiledSim;
  params: SimParams;
  currentFrame: number;
  viewMode: ViewMode;
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

  // Cumulative fog mask: union of every prior frame's knownFreeDelta.
  // Recomputed when currentFrame jumps backwards (seek), otherwise grown forward.
  const fogMask = useMemo(() => {
    const { rows, cols } = compiled.rasterized;
    const mask = new Uint8Array(rows * cols);
    const upTo = Math.min(currentFrame, compiled.timeline.length - 1);
    for (let i = 0; i <= upTo; i++) {
      const delta = compiled.timeline[i].knownFreeDelta;
      for (let k = 0; k < delta.length; k++) {
        const [r, c] = delta[k];
        if (r >= 0 && r < rows && c >= 0 && c < cols) mask[r * cols + c] = 1;
      }
    }
    return mask;
  }, [compiled, currentFrame]);

  // Carry the most recent treeSegmentsRC keyframe forward (renderer-side TTL).
  const treeSegments = useMemo(() => {
    for (let i = Math.min(currentFrame, compiled.timeline.length - 1); i >= 0; i--) {
      const t = compiled.timeline[i].treeSegmentsRC;
      if (t && t.length > 0) return t;
    }
    return null;
  }, [compiled, currentFrame]);

  // Window of recent commLinks to keep visible across a few ticks.
  const recentLinks = useMemo(() => {
    const out: RenderLink[] = [];
    const start = Math.max(0, currentFrame - LINK_RENDER_TTL + 1);
    for (let i = start; i <= currentFrame && i < compiled.timeline.length; i++) {
      const age = currentFrame - i;
      for (const lk of compiled.timeline[i].commLinks) {
        out.push({
          r0: lk.r0,
          c0: lk.c0,
          r1: lk.r1,
          c1: lk.c1,
          msgType: lk.msgType,
          outcome: lk.outcome,
          age,
        });
      }
    }
    return out;
  }, [compiled, currentFrame]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    if (!frame) return;

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

    // 2. Heatmap tiles.
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

    // 4. Drone-view fog: dim every cell the swarm has not seen yet.
    if (viewMode === 'drone') {
      const { rows, cols } = rasterized;
      ctx.fillStyle = 'rgba(0,0,0,0.7)';
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          if (rasterized.wallGrid[r * cols + c] === 1) continue;
          if (fogMask[r * cols + c] === 1) continue;
          ctx.fillRect(c * CELL_PX, r * CELL_PX, CELL_PX, CELL_PX);
        }
      }
    }

    // 5. Belief BFS tree (drone view only).
    if (viewMode === 'drone' && treeSegments && treeSegments.length >= 4) {
      ctx.strokeStyle = 'rgba(180,180,180,0.55)';
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      for (let i = 0; i + 3 < treeSegments.length; i += 4) {
        const r0 = treeSegments[i];
        const c0 = treeSegments[i + 1];
        const r1 = treeSegments[i + 2];
        const c1 = treeSegments[i + 3];
        ctx.moveTo((c0 + 0.5) * CELL_PX, (r0 + 0.5) * CELL_PX);
        ctx.lineTo((c1 + 0.5) * CELL_PX, (r1 + 0.5) * CELL_PX);
      }
      ctx.stroke();
    }

    // 6. Mesh comm links — colored by message type, faded by age.
    for (const link of recentLinks) {
      const fade = Math.max(1 - link.age / LINK_RENDER_TTL, 0.06);
      const alpha = outcomeAlpha(link.outcome) * fade;
      const color = msgKindColor(link.msgType);
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

    // 7. CV detections (drone view): bearing tick from drone to detection anchor.
    if (viewMode === 'drone') {
      for (const det of frame.cvDetections) {
        const drone = frame.dronesRC[det.uid];
        if (!drone) continue;
        const dx = (drone.col + 0.5) * CELL_PX;
        const dy = (drone.row + 0.5) * CELL_PX;
        const ax = (det.anchor[1] + 0.5) * CELL_PX;
        const ay = (det.anchor[0] + 0.5) * CELL_PX;
        const isTarget = det.kind === 'TARGET';
        ctx.strokeStyle = isTarget
          ? `rgba(255,80,80,${(0.45 + 0.5 * det.confidence).toFixed(3)})`
          : `rgba(255,255,180,${(0.25 + 0.5 * det.confidence).toFixed(3)})`;
        ctx.lineWidth = isTarget ? 2 : 1;
        ctx.beginPath();
        ctx.moveTo(dx, dy);
        ctx.lineTo(ax, ay);
        ctx.stroke();
        if (isTarget) {
          ctx.beginPath();
          ctx.arc(ax, ay, 7, 0, Math.PI * 2);
          ctx.stroke();
        } else {
          ctx.fillStyle = 'rgba(255,255,180,0.85)';
          ctx.fillRect(ax - 1.5, ay - 1.5, 3, 3);
        }
      }
    }

    // 8. Entrance marker (always visible).
    {
      const cx = compiled.entrance.col * CELL_PX + CELL_PX / 2;
      const cy = compiled.entrance.row * CELL_PX + CELL_PX / 2;
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(cx, cy - 8);
      ctx.lineTo(cx + 7, cy + 6);
      ctx.lineTo(cx - 7, cy + 6);
      ctx.closePath();
      ctx.stroke();
    }

    // 9. Target marker — hidden until detected (drone view) or always (oracle).
    const targetVisible = viewMode === 'oracle' || frame.targetSeen;
    if (targetVisible && frame.phase !== 'neutralised') {
      const cx = compiled.target.col * CELL_PX + CELL_PX / 2;
      const cy = compiled.target.row * CELL_PX + CELL_PX / 2;
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

    // 10. Oracle-view extras: faint room anchors with IDs.
    if (viewMode === 'oracle') {
      const discovered = new Set(frame.oracle.roomsDiscovered);
      ctx.font = '9px monospace';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      for (const room of compiled.roomGraph.rooms) {
        const cx = room.anchorCell.col * CELL_PX + CELL_PX / 2;
        const cy = room.anchorCell.row * CELL_PX + CELL_PX / 2;
        const isEntrance = room.id === compiled.roomGraph.entranceRoomId;
        const isTarget = room.id === compiled.roomGraph.targetRoomId;
        const isDiscovered = discovered.has(room.id);
        ctx.fillStyle = isTarget
          ? 'rgba(255,80,80,0.9)'
          : isEntrance
            ? 'rgba(255,255,255,0.9)'
            : isDiscovered
              ? 'rgba(255,255,255,0.55)'
              : 'rgba(255,255,255,0.18)';
        ctx.beginPath();
        ctx.arc(cx, cy, 11, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = '#000';
        ctx.fillText(`R${room.id}`, cx, cy);
      }
    }

    // 11. Drones (last layer — always on top).
    const drones = frame.dronesRC;
    const witnessUid = frame.targetWitness?.uid ?? -1;
    for (let i = 0; i < drones.length; i++) {
      const isWitness = i === witnessUid;
      const cx = (drones[i].col + 0.5) * CELL_PX;
      const cy = (drones[i].row + 0.5) * CELL_PX;
      ctx.fillStyle = isWitness ? '#00ffff' : '#ffffff';
      ctx.strokeStyle = '#000';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.arc(cx, cy, isWitness ? 7 : 5, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = '#000';
      ctx.font = '8px monospace';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(String(i), cx, cy);
    }
  }, [frame, compiled, params, wallBitmap, fogMask, treeSegments, recentLinks, viewMode]);

  return (
    <canvas
      ref={canvasRef}
      width={CANVAS_W}
      height={CANVAS_H}
      className="border border-white/10"
    />
  );
}
