# Mesh / CV swarm web renderer

This Next.js app is a static renderer for a Python-computed swarm simulation. It
plays back drone trajectories, RF mesh links, CV doorway / target detections,
and a ground-truth oracle overlay from a prebuilt JSON bundle.

```
Editor floorplan ──► npm run sim:export (Python swarm_sim)
                          │
                          ▼
              public/sim/default.bundle.json
                          │
                          ▼
           Next.js renderer  (drone view ⟷ oracle view)
```

## Workflow

1. Edit the floorplan in the in-browser editor (or hand-edit
   `public/floorplans/default.json` — the Python exporter reads it directly).
2. Run the export to compute a fresh simulation:
   ```bash
   npm run sim:export
   ```
   This invokes `python -m swarm_sim.export_sim` against the default floorplan
   and writes `public/sim/default.bundle.json`. The repository must be reachable
   as `swarm_sim` from the parent directory (via symlink or rename).
3. Develop or build the site:
   ```bash
   npm run dev
   npm run build   # also runs sim:export via prebuild
   ```
4. Sanity-check the bundle without spinning up Next:
   ```bash
   npm run smoke
   ```

## Drone view vs oracle view

The simulation logic is *only* CV-driven exploration; the in-browser toggle is
a presentation choice and never feeds back into agent decisions:

| View   | What you see |
|--------|--------------|
| Drone  | Fog mask of cells the swarm has actually observed; CV detection bearings; lead explorer's frontier-BFS belief tree; target marker hidden until first TARGET detection. |
| Oracle | Full floorplan; ground-truth room graph with discovery order; BFS queue snapshot; target visible. Useful for explaining what mesh + CV bought you. |

## Live simulation API (optional)

The renderer can either replay a prebuilt bundle (default) or POST the editor
floorplan to a Python HTTP service and replay whatever comes back. The contract
is identical — the API returns the exact same `SimulationBundle` JSON that
`npm run sim:export` writes — so `compile()` swaps the two transparently:

| `NEXT_PUBLIC_SIM_EXPORT_URL` | Run button behavior |
|------------------------------|---------------------|
| Unset / empty | `fetch('/sim/default.bundle.json')`; grid must match the editor. |
| Set, e.g. `https://api.example.com/export` | `POST { floorplan, ticks, nDrones, seed }`; the API runs `export_bundle_from_dict` and returns the bundle. |

Set the URL (and an optional bearer token) in `.env.local` for `npm run dev` or
in Vercel project env vars for production:

```
NEXT_PUBLIC_SIM_EXPORT_URL=https://api.example.com/export
# Optional — only set if the API requires Authorization: Bearer <token>
NEXT_PUBLIC_SIM_EXPORT_TOKEN=...
```

The backend lives at [`../api/`](../api/) and is documented in [`../api/README.md`](../api/README.md).

## Bundle schema

Frame fields the renderer understands (see `lib/bundleLoader.ts` and
`types/index.ts`):

- `dronesRC` — drone poses
- `commLinks` — fresh RF links this tick (BEACON / TOPOLOGY_MERGE / TOKEN)
- `rfLogTail` — short RF telemetry tail
- `cvDetections` — YOLO-shaped per-drone detections
- `beliefEdges` — gossiped portal hypotheses
- `knownFreeDelta` — cells newly observed this tick (delta-encoded fog mask)
- `treeSegmentsRC` — keyframe-encoded BFS spanning tree on the explorer's known floor
- `targetSeen`, `targetWitness`, `phase` — neutralisation milestone
- `oracle` — `roomsDiscovered`, `queueRooms`, `committedEdges`, `spanningEdges`
  (rendered only in oracle view)
