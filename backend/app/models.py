from pydantic import BaseModel, Field, model_validator


class LocationResponse(BaseModel):
    has_location: bool
    latitude: float | None = None
    longitude: float | None = None
    taken_at: str | None = None  # ISO 8601, from EXIF DateTimeOriginal if present


class Waypoint(BaseModel):
    latitude: float
    longitude: float


class RouteRequest(BaseModel):
    waypoints: list[Waypoint] = Field(min_length=1, max_length=20)
    # Required when there is exactly one waypoint (target round-trip length).
    # Optional with 2+ waypoints: treated as a minimum target length - if the
    # road path through all waypoints is already longer, this is ignored; if
    # shorter, a loop is added at the end to make up the difference.
    distance_km: float | None = Field(default=None, gt=0, le=200)
    count: int = Field(default=4, ge=1, le=8)
    profile: str = Field(default="cycling-regular")

    @model_validator(mode="after")
    def _distance_required_for_single_waypoint(self) -> "RouteRequest":
        if len(self.waypoints) == 1 and self.distance_km is None:
            raise ValueError("사진이 1장일 때는 distance_km(원하는 경로 거리)가 필요합니다.")
        return self


class Route(BaseModel):
    id: str
    distance_m: float
    duration_s: float
    coordinates: list[tuple[float, float]]  # (lat, lng) pairs, in path order
    gpx_url: str


class RouteListResponse(BaseModel):
    routes: list[Route]
