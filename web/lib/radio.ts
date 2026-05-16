import type { MsgKind, MsgOutcome } from '@/types';
import { pathLossDb } from './propagation/pathLoss';

export interface RadioConfig {
  cellSizeM: number;
  freqMhz: number;
  txPowerDbm: number;
  sensitivityDbm: number;
  distanceExponent: number;
  lfPerWallCellDb: number;
  raySamples: number;
}

export const DEFAULT_RADIO: RadioConfig = {
  cellSizeM: 0.22,
  freqMhz: 2400,
  txPowerDbm: 20,
  sensitivityDbm: -92,
  distanceExponent: 28,
  lfPerWallCellDb: 9,
  raySamples: 32,
};

export const COMM_LINK_TTL_TICKS = 6;
export const RF_LOG_CAPACITY = 20;

export const BEACON_INTERVAL = 4;
export const MERGE_INTERVAL = 10;
export const TOKEN_INTERVAL = 17;

export function pairwiseRssi(
  wallGrid: Uint8Array,
  wallDbGrid: Float32Array,
  cols: number,
  rows: number,
  r0: number,
  c0: number,
  r1: number,
  c1: number,
  cfg: RadioConfig,
): number {
  const dr = (r1 - r0) * cfg.cellSizeM;
  const dc = (c1 - c0) * cfg.cellSizeM;
  const distM = Math.hypot(dr, dc);

  let lf = 0;
  const n = cfg.raySamples;
  for (let s = 0; s < n; s++) {
    const t = s / (n - 1);
    const ri = Math.min(rows - 1, Math.max(0, Math.round(r0 + t * (r1 - r0))));
    const ci = Math.min(cols - 1, Math.max(0, Math.round(c0 + t * (c1 - c0))));
    const idx = ri * cols + ci;
    if (wallGrid[idx] === 1) {
      lf += wallDbGrid[idx];
    }
  }
  return cfg.txPowerDbm - pathLossDb(distM, cfg.freqMhz, cfg.distanceExponent, lf);
}

export function formatRfEvent(
  tick: number,
  msgType: MsgKind,
  srcId: number,
  dstId: number | 'broadcast',
  rssiDbm: number | null,
  outcome: MsgOutcome,
  seq: number,
): string {
  const rs = rssiDbm === null ? '—   ' : rssiDbm.toFixed(1).padStart(6, ' ');
  const dst = typeof dstId === 'number' ? `→${dstId}` : '→ALL';
  const type = msgType.padEnd(14, ' ');
  return `t=${String(tick).padStart(4, '0')}  ${type} ${srcId}${dst.padEnd(5, ' ')}  RSSI=${rs}dBm  [${outcome}] seq=${seq}`;
}

export function msgKindColor(kind: MsgKind): string {
  if (kind === 'BEACON') return '#33bbee';
  if (kind === 'TOPOLOGY_MERGE') return '#ee7733';
  return '#88cc44'; // TOKEN
}

export function outcomeAlpha(outcome: MsgOutcome): number {
  if (outcome === 'delivered') return 0.95;
  if (outcome === 'below_threshold') return 0.35;
  return 0.6;
}
