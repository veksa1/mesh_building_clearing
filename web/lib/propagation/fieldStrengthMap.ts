import type { DroneRC, SimParams } from '@/types';
import { pathLossDb } from './pathLoss';

export interface FieldStrengthResult {
  heatmap: Float32Array;
  hRows: number;
  hCols: number;
}

export function fieldStrengthMap(
  wallGrid: Uint8Array,
  wallDbGrid: Float32Array,
  rows: number,
  cols: number,
  dronesRC: DroneRC[],
  cellSizeM: number,
  params: SimParams,
): FieldStrengthResult {
  const stride = params.heatmapStride;
  const raySamples = params.raySamples;
  const N = params.distanceExponent;
  const txDbm = params.txPowerDbm;
  const freq = params.freqMhz;

  const hRows = Math.ceil(rows / stride);
  const hCols = Math.ceil(cols / stride);
  const heatmap = new Float32Array(hRows * hCols);
  heatmap.fill(-Infinity);

  for (let hi = 0; hi < hRows; hi++) {
    const sr = hi * stride + stride / 2;
    for (let hj = 0; hj < hCols; hj++) {
      const sc = hj * stride + stride / 2;
      let best = -Infinity;
      for (let di = 0; di < dronesRC.length; di++) {
        const dr = dronesRC[di].row;
        const dc = dronesRC[di].col;
        const distM = Math.hypot((sr - dr) * cellSizeM, (sc - dc) * cellSizeM);

        let lf = 0;
        for (let s = 0; s < raySamples; s++) {
          const t = s / (raySamples - 1);
          const ri = Math.min(rows - 1, Math.max(0, Math.round(dr + t * (sr - dr))));
          const ci = Math.min(cols - 1, Math.max(0, Math.round(dc + t * (sc - dc))));
          const idx = ri * cols + ci;
          if (wallGrid[idx] === 1) {
            lf += wallDbGrid[idx];
          }
        }
        const rssi = txDbm - pathLossDb(distM, freq, N, lf);
        if (rssi > best) best = rssi;
      }
      heatmap[hi * hCols + hj] = best;
    }
  }
  return { heatmap, hRows, hCols };
}
