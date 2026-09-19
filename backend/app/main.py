import uuid

from fastapi import FastAPI, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.exif import extract_gps, extract_taken_at
from app.gpx import build_gpx
from app.models import LocationResponse, Route, RouteListResponse, RouteRequest
from app.routing import RoutingError, generate_routes
from app.storage import get_gpx, save_gpx

app = FastAPI(title="Photo Cycle Map API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/api/photo/location", response_model=LocationResponse)
async def photo_location(photo: UploadFile) -> LocationResponse:
    image_bytes = await photo.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")

    try:
        gps = extract_gps(image_bytes)
    except Exception as exc:  # Pillow raises various errors on malformed images
        raise HTTPException(status_code=400, detail="이미지를 읽을 수 없습니다.") from exc

    if gps is None:
        return LocationResponse(has_location=False)

    latitude, longitude = gps
    taken_at = extract_taken_at(image_bytes)
    return LocationResponse(
        has_location=True, latitude=latitude, longitude=longitude, taken_at=taken_at
    )


@app.post("/api/routes", response_model=RouteListResponse)
async def create_routes(request: RouteRequest) -> RouteListResponse:
    waypoints = [(point.latitude, point.longitude) for point in request.waypoints]
    try:
        raw_routes = await generate_routes(
            waypoints,
            request.distance_km,
            request.count,
            request.profile,
            request.climb_preference,
        )
    except RoutingError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    routes = []
    for raw in raw_routes:
        route_id = uuid.uuid4().hex
        gpx_xml = build_gpx(
            f"cycling-route-{route_id}", raw["coordinates"], raw.get("elevations")
        )
        save_gpx(route_id, gpx_xml)
        routes.append(
            Route(
                id=route_id,
                distance_m=raw["distance_m"],
                duration_s=raw["duration_s"],
                ascent_m=raw.get("ascent_m"),
                descent_m=raw.get("descent_m"),
                coordinates=raw["coordinates"],
                gpx_url=f"/api/routes/{route_id}/gpx",
            )
        )

    return RouteListResponse(routes=routes)


@app.get("/api/routes/{route_id}/gpx")
async def download_gpx(route_id: str) -> Response:
    gpx_xml = get_gpx(route_id)
    if gpx_xml is None:
        raise HTTPException(status_code=404, detail="경로를 찾을 수 없습니다.")

    return Response(
        content=gpx_xml,
        media_type="application/gpx+xml",
        headers={"Content-Disposition": f'attachment; filename="{route_id}.gpx"'},
    )
