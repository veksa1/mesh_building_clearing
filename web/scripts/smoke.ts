import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { adoptBundle } from '../lib/bundleLoader';

// Smoke-test the static bundle without spinning up Next.
// Run: npx tsx scripts/smoke.ts
const bundlePath = resolve(__dirname, '../public/sim/default.bundle.json');
const raw = JSON.parse(readFileSync(bundlePath, 'utf-8'));

const t0 = Date.now();
const compiled = adoptBundle(raw);
const ms = Date.now() - t0;
console.log('adoptBundle took', ms, 'ms');

console.log('schemaVersion:', raw.schemaVersion);
console.log('meta:', compiled.meta);
console.log('rooms:', compiled.roomGraph.rooms.map((r) => r.id));
console.log('entranceRoom:', compiled.roomGraph.entranceRoomId);
console.log('targetRoom:', compiled.roomGraph.targetRoomId);
console.log('timeline frames:', compiled.timeline.length);
console.log('vmin/vmax:', compiled.heatmapVmin.toFixed(1), '/', compiled.heatmapVmax.toFixed(1));

const phases: Record<string, number> = {};
for (const f of compiled.timeline) phases[f.phase] = (phases[f.phase] ?? 0) + 1;
console.log('phase counts:', phases);

const targetFirst = compiled.timeline.findIndex((f) => f.targetSeen);
const neutralFrame = compiled.timeline.find((f) => f.phase === 'neutralised');
console.log('first target detection at frame:', targetFirst);
console.log('neutralised reached:', neutralFrame ? 'yes' : 'no');

const sample = compiled.timeline[Math.min(20, compiled.timeline.length - 1)];
console.log('sample frame tick:', sample.tick);
console.log('sample drones:', sample.dronesRC.map((d) => `(${d.row},${d.col})`).join(' '));
console.log('sample commLinks:', sample.commLinks.length);
console.log('sample cvDetections:', sample.cvDetections.length);
console.log('sample knownFreeDelta:', sample.knownFreeDelta.length);

let totalKnown = 0;
let totalCv = 0;
let maxLinks = 0;
for (const f of compiled.timeline) {
  totalKnown += f.knownFreeDelta.length;
  totalCv += f.cvDetections.length;
  if (f.commLinks.length > maxLinks) maxLinks = f.commLinks.length;
}
console.log('total known cells (union):', totalKnown);
console.log('total CV detections:', totalCv);
console.log('max commLinks in a single frame:', maxLinks);

if (compiled.timeline.length === 0) {
  console.error('FAIL: empty timeline');
  process.exit(1);
}
if (!neutralFrame) {
  console.warn('WARN: no neutralised frame — try a longer --ticks horizon');
}
console.log('OK');
