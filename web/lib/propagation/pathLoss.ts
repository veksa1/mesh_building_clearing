export function pathLossDb(
  distanceM: number,
  freqMhz: number,
  N: number,
  Lf: number,
): number {
  const d = Math.max(distanceM, 0.5);
  return 20 * Math.log10(freqMhz) + N * Math.log10(d) - 27.55 + Lf;
}
