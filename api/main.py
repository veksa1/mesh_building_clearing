"""FastAPI service: POST a FloorplanData JSON, get a SimulationBundle JSON back.

This is the thin HTTP shell around ``swarm_sim.export_sim.export_bundle_from_dict``.
It is meant to live on a long-running host (Verda container, plain VM, etc.) — the
static Next.js frontend hits it directly when ``NEXT_PUBLIC_SIM_EXPORT_URL`` is
configured, replacing the prebuilt ``default.bundle.json`` fallback.

Run locally:
    uvicorn api.main:app --host 0.0.0.0 --port 8080

Environment:
    SIM_API_TOKEN          Optional bearer token; when set, every request must
                           include ``Authorization: Bearer <token>``.
    SIM_API_CORS_ORIGINS   Comma-separated list of allowed origins (default: ``*``).
    SIM_API_MAX_TICKS      Upper bound on the ``ticks`` field (default: 2000).
    SIM_API_MAX_DRONES     Upper bound on the ``nDrones`` field (default: 32).
"""

from __future__ import annotations

import logging
import os
import pathlib
import sys
import time
import uuid
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, ValidationError

# Allow ``uvicorn api.main:app`` from the parent of swarm_sim/.
_HERE = pathlib.Path(__file__).resolve().parent
_REPO_PARENT = _HERE.parent.parent
if str(_REPO_PARENT) not in sys.path:
    sys.path.insert(0, str(_REPO_PARENT))

from swarm_sim.export_sim import DEFAULT_PARAMS, export_bundle_from_dict  # noqa: E402

logger = logging.getLogger("sim_api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


# ---------- request / response models ----------------------------------------


class GridPoint(BaseModel):
    row: int
    col: int


class WallSegment(BaseModel):
    id: str
    start: GridPoint
    end: GridPoint
    material: str = "drywall"


class DoorMarker(BaseModel):
    id: str
    wallSegmentId: str
    centerCell: GridPoint
    widthCells: int = 4
    dominantAxis: str = "row"


class Floorplan(BaseModel):
    """Mirror of web/types/index.ts FloorplanData."""

    name: str = "live"
    gridRows: int
    gridCols: int
    cellSizeM: float | None = None
    walls: list[WallSegment] = Field(default_factory=list)
    doors: list[DoorMarker] = Field(default_factory=list)
    entrance: GridPoint
    target: GridPoint


class ExportRequest(BaseModel):
    floorplan: Floorplan
    ticks: int = 1500
    nDrones: int = 7
    seed: int = 0
    explorerPhaseTicks: int | None = 25
    # Optional override of the radio / heatmap params; unspecified keys fall
    # back to DEFAULT_PARAMS, which matches web/constants.ts DEFAULT_SIM_PARAMS.
    params: dict[str, float] | None = None


# ---------- auth + config helpers --------------------------------------------


_TOKEN = os.getenv("SIM_API_TOKEN", "").strip()
_MAX_TICKS = int(os.getenv("SIM_API_MAX_TICKS", "2000"))
_MAX_DRONES = int(os.getenv("SIM_API_MAX_DRONES", "32"))
_bearer = HTTPBearer(auto_error=False)


def require_token(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> None:
    if not _TOKEN:
        return
    if creds is None or creds.scheme.lower() != "bearer" or creds.credentials != _TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _merged_params(override: dict[str, float] | None) -> dict[str, float]:
    params = dict(DEFAULT_PARAMS)
    if override:
        for k, v in override.items():
            params[k] = float(v)
    return params


# ---------- app --------------------------------------------------------------


def _origins() -> list[str]:
    raw = os.getenv("SIM_API_CORS_ORIGINS", "*").strip()
    if not raw or raw == "*":
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


app = FastAPI(
    title="Swarm sim export API",
    version="1.0.0",
    description="POST a floorplan, run the local-sense swarm simulation, return the renderer bundle.",
)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins(),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=False,
)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    rid = uuid.uuid4().hex[:8]
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Request-Id"] = rid
    logger.info("rid=%s %s %s -> %d in %.0fms", rid, request.method, request.url.path, response.status_code, elapsed_ms)
    return response


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    return {"ok": True, "auth": bool(_TOKEN), "maxTicks": _MAX_TICKS, "maxDrones": _MAX_DRONES}


@app.post("/export", dependencies=[Depends(require_token)])
def export(req: ExportRequest) -> dict[str, Any]:
    if req.ticks <= 0 or req.ticks > _MAX_TICKS:
        raise HTTPException(status_code=400, detail=f"ticks must be in 1..{_MAX_TICKS}")
    if req.nDrones <= 0 or req.nDrones > _MAX_DRONES:
        raise HTTPException(status_code=400, detail=f"nDrones must be in 1..{_MAX_DRONES}")

    params = _merged_params(req.params)
    params["nDrones"] = float(req.nDrones)

    try:
        floorplan_dict = req.floorplan.model_dump(exclude_none=True)
        bundle = export_bundle_from_dict(
            floorplan_dict,
            ticks=int(req.ticks),
            n_drones=int(req.nDrones),
            seed=int(req.seed),
            params=params,
            explorer_phase_ticks=req.explorerPhaseTicks,
        )
    except (ValueError, ValidationError) as exc:
        # Floorplan validation errors (e.g. entrance on wall) — caller's fault.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception("simulation failed")
        raise HTTPException(status_code=500, detail="Simulation failed; see server logs.")

    return bundle


# Backwards-compatible path alias for clients that hit /v1/sim/export.
@app.post("/v1/sim/export", dependencies=[Depends(require_token)])
def export_v1(req: ExportRequest) -> dict[str, Any]:
    return export(req)
