import type { CompiledSim, FloorplanData } from '@/types';
import { rasterize } from './rasterize';
import { fetchLiveBundle, loadDefaultBundle } from './bundleLoader';

export interface CompileResult {
  ok: true;
  compiled: CompiledSim;
  source: 'live' | 'static';
}

export interface CompileError {
  ok: false;
  error: string;
}

// The web is a renderer for a Python-computed simulation. compile() validates
// the editor floorplan, then either POSTs it to NEXT_PUBLIC_SIM_EXPORT_URL for
// a fresh run (live mode) or loads the prebuilt /sim/default.bundle.json
// (static mode, `npm run sim:export`).
export async function compile(
  floorplan: FloorplanData,
  opts: { signal?: AbortSignal; nDrones?: number } = {},
): Promise<CompileResult | CompileError> {
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

  const liveUrl = process.env.NEXT_PUBLIC_SIM_EXPORT_URL?.trim();

  let compiled: CompiledSim;
  let source: 'live' | 'static';
  try {
    if (liveUrl) {
      compiled = await fetchLiveBundle(liveUrl, floorplan, { nDrones: opts.nDrones }, opts.signal);
      source = 'live';
    } else {
      compiled = await loadDefaultBundle();
      source = 'static';
    }
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }

  // In static mode the editor must match the prebuilt grid. In live mode the
  // server raster *is* the editor raster (same JSON in → same dimensions out),
  // so a dimension drift here is a server bug worth surfacing.
  if (compiled.rasterized.rows !== rows || compiled.rasterized.cols !== cols) {
    const hint =
      source === 'live'
        ? 'API returned a different grid than the floorplan; check server version.'
        : 'Re-run npm run sim:export.';
    return {
      ok: false,
      error: `Bundle grid (${compiled.rasterized.rows}x${compiled.rasterized.cols}) does not match editor (${rows}x${cols}). ${hint}`,
    };
  }

  if (compiled.timeline.length === 0) {
    return { ok: false, error: 'Empty simulation timeline in bundle.' };
  }

  return { ok: true, compiled, source };
}
