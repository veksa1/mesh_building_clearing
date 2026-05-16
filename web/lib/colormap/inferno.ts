// Matplotlib inferno colormap polynomial fit (Mike Bostock / Shadertoy WlfXRN, public domain).
// Builds a 256-entry RGB lookup table.
function infernoSample(t: number): [number, number, number] {
  const x = Math.max(0, Math.min(1, t));
  const r =
    0.0002189403691192265 +
    x *
      (0.1065134194856116 +
        x *
          (11.602401356046856 +
            x * (-41.70399613139459 + x * (77.162935699427 + x * (-71.31942824499214 + x * 25.13112622477341)))));
  const g =
    0.001651004631001012 +
    x *
      (0.5639564367884091 +
        x *
          (-3.972853965665698 +
            x * (17.43631888905195 + x * (-33.40235894210092 + x * (32.62606426397723 + x * -12.24266895238567)))));
  const b =
    -0.01948089843709184 +
    x *
      (3.932712388889277 +
        x *
          (-15.94253899396549 +
            x * (44.35414519872813 + x * (-81.80730925738993 + x * (73.20951985803202 + x * -23.07032500287172)))));
  return [
    Math.round(Math.max(0, Math.min(255, r * 255))),
    Math.round(Math.max(0, Math.min(255, g * 255))),
    Math.round(Math.max(0, Math.min(255, b * 255))),
  ];
}

export const INFERNO_LUT: Uint8Array = (() => {
  const lut = new Uint8Array(256 * 3);
  for (let i = 0; i < 256; i++) {
    const [r, g, b] = infernoSample(i / 255);
    lut[i * 3] = r;
    lut[i * 3 + 1] = g;
    lut[i * 3 + 2] = b;
  }
  return lut;
})();

export function rssiToRGB(
  rssi: number,
  vmin: number,
  vmax: number,
): [number, number, number] {
  if (!isFinite(rssi)) return [0, 0, 0];
  const span = vmax - vmin;
  const norm = span < 1e-9 ? 0 : (rssi - vmin) / span;
  const idx = Math.max(0, Math.min(255, Math.round(norm * 255)));
  return [INFERNO_LUT[idx * 3], INFERNO_LUT[idx * 3 + 1], INFERNO_LUT[idx * 3 + 2]];
}
