from pydantic import BaseModel, Field


class LocationResponse(BaseModel):
    has_location: bool
    latitude: float | None = None
    longitude: float | None = None


class RouteRequest(BaseModel):
    latitude: float
    longitude: float
    distance_km: float = Field(gt=0, le=200)
    count: int = Field(default=4, ge=1, le=8)
    profile: str = Field(default="cycling-regular")


class Route(BaseModel):
    id: str
    distance_m: float
    duration_s: float
    coordinates: list[tuple[float, float]]  # (lat, lng) pairs, in path order
    gpx_url: str


class RouteListResponse(BaseModel):
    routes: list[Route]
