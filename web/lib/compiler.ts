import type { CompiledSim, FloorplanData } from '@/types';
import { rasterize } from './rasterize';
import { loadDefaultBundle } from './bundleLoader';

export interface CompileResult {
  ok: true;
  compiled: CompiledSim;
}

export interface CompileError {
  ok: false;
  error: string;
}

// The web is a renderer for a Python-computed simulation. compile() validates
// the editor floorplan against the prebuilt bundle and returns the bundle.
// To regenerate after editing the floorplan, run `npm run sim:export`.
export async function compile(floorplan: FloorplanData): Promise<CompileResult | CompileError> {
  if (!floorplan.entrance) return { ok: false, error: 'Set entrance point first.' };
  if (!floorplan.target) return { ok: false, error: 'Set target point first.' };

  const rasterized = rasterize(floorplan);
  const { rows, cols, wallGrid } = rasterized;

  if (wallGrid[floorplan.entrance.row * cols + floorplan.entrance.col] === 1) {
    return { ok: false, error: 'Entrance is on a wall cell.' };
  }
  if (wallGrid[floorplan.target.row * cols + floorplan.target.col] === 1) {
    return { ok: false, error: 'Target is on a wall cell.' };
  }

  let compiled: CompiledSim;
  try {
    compiled = await loadDefaultBundle();
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }

  if (compiled.rasterized.rows !== rows || compiled.rasterized.cols !== cols) {
    return {
      ok: false,
      error: `Bundle grid (${compiled.rasterized.rows}x${compiled.rasterized.cols}) does not match editor (${rows}x${cols}). Re-run npm run sim:export.`,
    };
  }

  if (compiled.timeline.length === 0) {
    return { ok: false, error: 'Empty simulation timeline in bundle.' };
  }

  return { ok: true, compiled };
}
