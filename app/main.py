"""Eurofurence Weather -- FastAPI application entry point.

Author: laffiesphere (https://github.com/laffiie/EurofurenceWeather)

The official weather site for the convention. Weather data comes from
Deutscher Wetterdienst OpenData and is used under GeoNutzV; see /api-docs for
the public API and the attribution it requires.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import api_v1, presence, ratelimit, schemas, service
from app.config import settings
from app.dwd import icon, pollen, radar
from app.dwd.client import cache

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
MEDIA_DIR = Path(__file__).resolve().parent.parent / "media"

app = FastAPI(
    title=f"{settings.event.name} — Weather API",
    version="2.1.0",
    description=(
        "Fursuiting index, weather overview, rain radar and ICON model maps for "
        f"{settings.location.name}, built on DWD OpenData.\n\n"
        "**Build against `/api/v1`.** Those shapes are a stable contract. "
        "`/api/summary` serves this project's own frontend and changes without notice.\n\n"
        "Open access, no key. Please respect the rate limit in the `X-RateLimit-*` "
        "headers and cache responses — the upstream data only changes hourly.\n\n"
        "Weather data © Deutscher Wetterdienst (DWD), used under GeoNutzV. "
        "Attribute DWD if you republish it."
    ),
    contact={"name": "Project source", "url": "https://github.com/laffiie/EurofurenceWeather"},
    license_info={"name": "MIT"},
)

# Politeness ceiling for the open API; see app/ratelimit.py on worker scope.
limiter = ratelimit.SlidingWindowLimiter(settings.api.rate_limit_per_minute)
app.middleware("http")(ratelimit.build_middleware(limiter))

# How busy the machine is, so the page can say so. Registered after the limiter
# and therefore wrapping it: a visitor who runs into the 429 is still here, and
# a rush is exactly when we want to be counting.
visitors = presence.PresenceTracker(
    window_seconds=settings.capacity.active_window_seconds,
    busy_at=settings.capacity.busy_at,
    crowded_at=settings.capacity.crowded_at,
)
if settings.capacity.enabled:
    app.middleware("http")(presence.build_middleware(visitors))

if settings.api.public_api_enabled:
    app.include_router(api_v1.router)

# Convenient if someone embeds the widgets elsewhere (e.g. the EF app or info screens).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
    # Without this a cross-origin consumer cannot read any of it -- including
    # the rate limit headers the docs ask them to respect.
    expose_headers=[
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "Retry-After",
        "X-Site-Load",
        "X-Site-Visitors",
        "X-Model-Run",
        "X-Valid-Time",
        "X-Value-Min",
        "X-Value-Max",
    ],
)


@app.get(
    "/api/summary",
    summary="Internal aggregate for this project's own frontend",
    description="Not a stable contract -- its shape follows whatever the site needs. "
    "External consumers should use /api/v1 instead.",
    tags=["Internal"],
)
def get_summary(
    lang: str = Query("en", pattern="^(en|de)$", description="Language for generated text"),
) -> JSONResponse:
    payload = service.build_summary(lang)
    if payload["current"] is None and not payload["daily"]:
        raise HTTPException(status_code=503, detail="No DWD data available right now")
    # Let a CDN or reverse proxy hold this briefly; DWD data is not second-fresh.
    return JSONResponse(payload, headers={"Cache-Control": "public, max-age=120"})


@app.get("/api/radar.png", summary="Rain radar composite as a PNG overlay", tags=["Images"])
def get_radar(
    span: float = Query(1.6, ge=0.2, le=6.0, description="Half-height of the map in degrees"),
    width: int = Query(900, ge=100, le=2000),
    height: int = Query(900, ge=100, le=2000),
    layer: str = Query("radar", pattern="^(radar|warnings)$"),
) -> Response:
    bbox = radar.bbox_around(
        settings.location.latitude, settings.location.longitude, span
    )
    wms_layer = (
        settings.dwd.radar_layer if layer == "radar" else settings.dwd.warnings_layer
    )
    try:
        image = radar.fetch_layer_image(wms_layer, bbox, width, height)
    except Exception as exc:  # noqa: BLE001
        logger.error("Radar fetch failed: %s", exc)
        raise HTTPException(status_code=502, detail="DWD radar service unavailable") from exc

    return Response(
        content=image,
        media_type="image/png",
        headers={"Cache-Control": f"public, max-age={radar.RADAR_TTL}"},
    )


#: The model card's map is far wider than it is tall, so the field is cut to a
#: matching shape -- otherwise it fits the height and leaves empty side margins.
MODEL_ASPECT = 2.3


def _model_bbox(span: float) -> tuple:
    return radar.bbox_around(
        settings.location.latitude, settings.location.longitude, span, aspect=MODEL_ASPECT
    )


@app.get("/api/model", summary="Available ICON model fields and the current run", tags=["Images"])
def get_model_info(span: float = Query(1.6, ge=0.2, le=4.0)) -> JSONResponse:
    bbox = _model_bbox(span)
    payload = icon.describe_parameters(bbox)

    # Pollen rides alongside the ICON fields rather than among them: it is a
    # different model on a different grid in daily steps, and folding it into
    # `parameters` would have every consumer assume those hold for it too.
    if settings.pollen.enabled:
        try:
            payload["pollen"] = pollen.describe(bbox)
        except Exception as exc:  # noqa: BLE001 - one absent layer, not a dead card
            logger.error("Pollen metadata unavailable: %s", exc)

    return JSONResponse(payload, headers={"Cache-Control": "public, max-age=600"})


@app.get("/api/model.png", summary="An ICON-D2 field rendered as a map overlay", tags=["Images"])
def get_model_image(
    param: str = Query("clouds", pattern="^(clouds|temperature|wind)$"),
    step: int = Query(0, ge=0, le=icon.MAX_STEP, description="Forecast hour from the model run"),
    span: float = Query(1.6, ge=0.2, le=4.0),
    width: int = Query(720, ge=100, le=1600),
) -> Response:
    try:
        result = icon.render(param, step, _model_bbox(span), width)
    except Exception as exc:  # noqa: BLE001
        logger.error("ICON render failed for %s +%dh: %s", param, step, exc)
        raise HTTPException(status_code=502, detail="ICON model data unavailable") from exc

    return Response(
        content=result["png"],
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=1800",
            "X-Model-Run": result["run"].isoformat(),
            "X-Value-Min": "" if result["min"] is None else f"{result['min']:.1f}",
            "X-Value-Max": "" if result["max"] is None else f"{result['max']:.1f}",
        },
    )


@app.get(
    "/api/pollen.png",
    summary="An ICON-ART pollen field rendered as a map overlay",
    description="Daily mean concentration for one species. A species outside its "
    "own season answers 404: DWD publishes nothing for it, which is an answer "
    "rather than a fault.",
    tags=["Images"],
)
def get_pollen_image(
    species: str = Query("grasses", pattern="^(hazel|alder|birch|grasses|ragweed)$"),
    step: int = Query(0, ge=0, le=pollen.MAX_STEP, description="Forecast day from the run"),
    span: float = Query(1.6, ge=0.2, le=4.0),
    width: int = Query(720, ge=100, le=1600),
) -> Response:
    if not settings.pollen.enabled:
        raise HTTPException(status_code=404, detail="Pollen layer is switched off")
    try:
        result = pollen.render(species, step, _model_bbox(span), width)
    except LookupError as exc:
        # Out of season. Not an error anyone can fix, and not a 502: the
        # frontend turns this into "DWD publishes birch from 30 Jan".
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("Pollen render failed for %s +%dd: %s", species, step, exc)
        raise HTTPException(status_code=502, detail="Pollen forecast unavailable") from exc

    return Response(
        content=result["png"],
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=3600",
            "X-Model-Run": result["run"].isoformat(),
            "X-Valid-Time": result["valid"].isoformat(),
            "X-Value-Min": "" if result["min"] is None else f"{result['min']:.1f}",
            "X-Value-Max": "" if result["max"] is None else f"{result['max']:.1f}",
        },
    )


@app.get(
    "/api/load",
    response_model=schemas.SiteLoad,
    summary="How busy the site is right now",
    description="A load signal, not an audience metric: visitors are counted per client "
    "address inside a short window, so one shared network counts once and a crawler "
    "counts as a person. Nothing about a visitor is stored -- see /privacy.",
    tags=["Public API v1"],
)
def site_load() -> JSONResponse:
    # `enabled` matters: with counting switched off nothing calls touch(), so
    # the zeros below would otherwise read as a very quiet afternoon.
    payload = {**visitors.snapshot(), "enabled": settings.capacity.enabled}
    # Never cached: a stale "all quiet" is worse than no answer at all.
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


@app.get("/api/health", response_model=schemas.Health, summary="Liveness and cache status", tags=["Public API v1"])
def health() -> dict:
    return {
        "status": "ok",
        "event": settings.event.name,
        "station": settings.dwd.station_id,
        "location": settings.location.name,
        "cache_age_seconds": {
            "observations": _age(f"poi:{settings.dwd.station_id}"),
            "forecast": _age(f"mosmix:{settings.dwd.station_id}:{settings.forecast_hours}"),
            "warnings": _age(f"warnings:{','.join(settings.dwd.warncells)}"),
        },
    }


def _age(key: str):
    age = cache.age(key)
    return None if age is None else int(age)


# Page markup and its scripts are versioned together. If a browser keeps a
# stale app.js while fetching fresh HTML it will look up elements that no
# longer exist and the page dies on load, so make both revalidate every time.
# ETags keep that to a cheap 304; these files are a few kilobytes.
REVALIDATE = "no-cache, must-revalidate"


class RevalidatingStatic(StaticFiles):
    """StaticFiles that pins app assets to revalidate but lets vendor code cache.

    ``vendor/`` holds version-pinned third-party files (Leaflet) that never
    change under a given name, so they are safe to cache for a long time.
    """

    def file_response(self, *args, **kwargs):  # type: ignore[override]
        response = super().file_response(*args, **kwargs)
        path = str(kwargs.get("full_path") or (args[0] if args else ""))
        if "vendor" in path.replace("\\", "/"):
            response.headers["Cache-Control"] = "public, max-age=604800"
        else:
            response.headers["Cache-Control"] = REVALIDATE
        return response


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": REVALIDATE})


@app.get("/display", include_in_schema=False)
def display() -> FileResponse:
    """Full-screen board for the ConOps desk / info screens."""
    return FileResponse(STATIC_DIR / "display.html", headers={"Cache-Control": REVALIDATE})


@app.get("/privacy", include_in_schema=False)
def privacy() -> FileResponse:
    """What the site stores and what it does not. Linked from the storage notice."""
    return FileResponse(STATIC_DIR / "privacy.html", headers={"Cache-Control": REVALIDATE})


@app.get("/datenschutz", include_in_schema=False)
def datenschutz() -> FileResponse:
    """The same page in German -- a privacy notice its readers cannot read is no notice."""
    return FileResponse(STATIC_DIR / "datenschutz.html", headers={"Cache-Control": REVALIDATE})


@app.get("/api-docs", include_in_schema=False)
def api_docs() -> FileResponse:
    """Human-readable API notes. /docs stays the generated, interactive reference.

    Deliberately not under /api/, so the rate limit never turns the explanation
    of the rate limit into a 429.
    """
    return FileResponse(STATIC_DIR / "api-docs.html", headers={"Cache-Control": REVALIDATE})


# Media is content, not code: it can be cached hard and mounts before the
# catch-all so /media/... never falls through to the static handler.
if MEDIA_DIR.is_dir():
    app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")

app.mount("/", RevalidatingStatic(directory=STATIC_DIR), name="static")
