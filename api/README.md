# Swarm simulation export API

FastAPI service that wraps `swarm_sim.export_sim.export_bundle_from_dict`. The
static Next.js renderer at [`../web/`](../web/) hits this endpoint when its
`NEXT_PUBLIC_SIM_EXPORT_URL` env var is set, replacing the prebuilt
`public/sim/default.bundle.json` fallback.

```
Browser (edited floorplan) ──POST /export──► FastAPI
                                                │
                                                ▼
                                  rasterize → run_decentralized → serialize
                                                │
                                       ◄──SimulationBundle JSON──
```

The request body matches `FloorplanData` in [`../web/types/index.ts`](../web/types/index.ts);
the response body matches the schema produced by
[`../export_sim.py`](../export_sim.py) (`schemaVersion: 1`).

## Endpoints

- `GET /healthz` — readiness probe; returns `{ ok, auth, maxTicks, maxDrones, commBackend, udpBasePort }`.
- `POST /export` (and `POST /v1/sim/export`) — runs the simulation. Body:

  ```json
  {
    "floorplan": { "gridRows": 54, "gridCols": 72, "walls": [...], "doors": [...], "entrance": {...}, "target": {...} },
    "ticks": 1500,
    "nDrones": 7,
    "seed": 0,
    "explorerPhaseTicks": 25,
    "params": { "freqMhz": 2400, "txPowerDbm": 20, "distanceExponent": 28, "raySamples": 48 },
    "commBackend": "udp",
    "udpBasePort": 8700
  }
  ```

  All fields except `floorplan` are optional. `commBackend` defaults to
  `SIM_COMM_BACKEND` (server-side) and accepts `udp` (primary, multiprocess
  mesh) or `inprocess` (single-process fallback). UDP failures auto-fall back
  to `inprocess`; the backend actually used is reported in `meta.commBackend`.

## Environment variables

| Name | Default | Purpose |
|------|---------|---------|
| `SIM_API_TOKEN` | _(empty — auth disabled)_ | If set, every `/export` call must send `Authorization: Bearer <token>`. |
| `SIM_API_CORS_ORIGINS` | `*` | Comma-separated allow-list, e.g. `https://app.vercel.app,https://localhost:3000`. |
| `SIM_API_MAX_TICKS` | `2000` | Hard cap on the `ticks` field to prevent runaway requests. |
| `SIM_API_MAX_DRONES` | `32` | Hard cap on `nDrones`. |
| `SIM_COMM_BACKEND` | `udp` | Default mesh backend. `udp` runs one OS process per drone with localhost UDP propagation; `inprocess` is the single-process fallback. UDP exceptions auto-fall back to `inprocess` and the actual backend is reported in `meta.commBackend`. |
| `SIM_UDP_BASE_PORT` | `8700` | Base listen port for UDP workers (drone uid `i` binds `BASE+i`). If the block is busy, the kernel scans upward for a free block. |

## Run locally

The simulation package lives one directory up and is reachable on the Python
path as `swarm_sim` via the symlink described in [`../CLAUDE.md`](../CLAUDE.md).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r api/requirements.txt

# From the parent of swarm_sim/:
PYTHONPATH="$PWD/..:$PWD" \
  uvicorn api.main:app --host 127.0.0.1 --port 8080 --reload
```

Then in another shell:

```bash
curl -s http://127.0.0.1:8080/healthz

curl -s http://127.0.0.1:8080/export \
  -H 'Content-Type: application/json' \
  -d "{\"floorplan\": $(cat web/public/floorplans/default.json), \"ticks\": 200, \"nDrones\": 5}" \
  | jq '.meta'
```

Point the frontend at it:

```bash
echo 'NEXT_PUBLIC_SIM_EXPORT_URL=http://127.0.0.1:8080/export' >> web/.env.local
( cd web && npm run dev )
```

Edit the floorplan in the editor, hit Run, and the renderer replays whatever
the API computes from the current geometry.

## Docker

```bash
# From the swarm_sim package root (parent of api/):
docker build -f api/Dockerfile -t swarm-sim-api .
docker run --rm -p 8080:8080 \
  -e SIM_API_CORS_ORIGINS='https://your-frontend.example.com' \
  -e SIM_API_TOKEN='change-me' \
  swarm-sim-api
```

## Deploying on Verda

1. Push the repo to a Verda-accessible registry or wire Verda directly to GitHub.
2. Build using [`Dockerfile`](Dockerfile); expose port `8080`.
3. Set the env vars from the table above in the Verda project settings.
   `SIM_API_TOKEN` and `SIM_API_CORS_ORIGINS` are the two you almost certainly
   want in production.
4. Note the public URL Verda assigns, e.g. `https://swarm-sim.api.verda.com`.
5. In Vercel project settings for the frontend, add:
   - `NEXT_PUBLIC_SIM_EXPORT_URL=https://swarm-sim.api.verda.com/export`
   - `NEXT_PUBLIC_SIM_EXPORT_TOKEN=<same value as SIM_API_TOKEN>` (only if you
     enabled auth — note this is browser-visible, so prefer IP allow-listing or
     a short-lived signed URL pattern for anything sensitive).
6. Redeploy the frontend so the new env var is baked into the static build.

## Performance and security notes

- The bundle returned for a 1500-tick / 7-drone run is ~2 MB; gzip middleware is
  enabled by default. Keep `ticks` modest if you care about cold-start latency.
- Each `/export` request runs the full simulation synchronously and can take
  tens of seconds. Configure Verda's request timeout accordingly (60–120s).
- For public deployments either set `SIM_API_TOKEN` or front the service with
  a Cloudflare / Vercel proxy that handles rate-limiting.

## Mesh backend (UDP vs in-process)

UDP is the primary simulation backend: each drone runs in its own OS process
with a real UDP socket on loopback (`SIM_UDP_BASE_PORT + uid`). Only port 8080
needs to be exposed externally — all mesh traffic stays inside the container.

If `spawn`-style multiprocessing isn't available (locked-down Verda images,
short-lived sandboxes), the kernel logs a warning and falls back to the
in-process kernel for that request, so exports always succeed. Force the
fallback globally with `SIM_COMM_BACKEND=inprocess` or per-request with
`"commBackend": "inprocess"` in the POST body.
