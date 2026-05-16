import { defaultFloorplan } from '../lib/defaultFloorplan';
import { compile } from '../lib/compiler';
import { DEFAULT_SIM_PARAMS } from '../constants';

const fp = defaultFloorplan();
console.log('walls:', fp.walls.length, 'doors:', fp.doors.length);

const t0 = Date.now();
const result = compile(fp, DEFAULT_SIM_PARAMS);
const ms = Date.now() - t0;
console.log('compile took', ms, 'ms');

if (!result.ok) {
  console.error('COMPILE FAILED:', result.error);
  process.exit(1);
}

const { compiled } = result;
console.log('rooms:', compiled.roomGraph.rooms.map((r) => r.id));
console.log('entranceRoom:', compiled.roomGraph.entranceRoomId);
console.log('targetRoom:', compiled.roomGraph.targetRoomId);
console.log('adjacency:', Array.from(compiled.roomGraph.adjacency.entries()).map(([k, v]) => `${k}->[${v}]`).join(', '));
console.log('timeline frames:', compiled.timeline.length);
console.log('vmin/vmax:', compiled.heatmapVmin.toFixed(1), '/', compiled.heatmapVmax.toFixed(1));

const phases = compiled.timeline.reduce((acc: Record<string, number>, f) => {
  acc[f.phase] = (acc[f.phase] || 0) + 1;
  return acc;
}, {});
console.log('phase counts:', phases);

const neutralFrame = compiled.timeline.find((f) => f.phase === 'neutralised');
console.log('neutralised reached:', neutralFrame ? 'yes' : 'no');

// Inspect comm events
const sample = compiled.timeline[20];
console.log('frame 20 tick:', sample.tick);
console.log('frame 20 drones:', sample.dronesRC.map((d) => `(${d.row},${d.col})`).join(' '));
console.log('frame 20 commLinks:', sample.commLinks.length);
console.log('frame 20 rfLogTail (last 3):');
for (const line of sample.rfLogTail.slice(-3)) console.log('  ', line);

let totalLinks = 0;
let maxLinks = 0;
for (const f of compiled.timeline) {
  totalLinks += f.commLinks.length;
  if (f.commLinks.length > maxLinks) maxLinks = f.commLinks.length;
}
console.log('avg commLinks/frame:', (totalLinks / compiled.timeline.length).toFixed(1));
console.log('max commLinks in a frame:', maxLinks);
