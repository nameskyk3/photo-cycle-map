import httpx

from app.config import settings


class RoutingError(Exception):
    """Raised when the routing provider fails or is unreachable."""


async def fetch_round_trip(
    client: httpx.AsyncClient,
    latitude: float,
    longitude: float,
    distance_km: float,
    profile: str,
    seed: int,
    points: int = 3,
) -> dict:
    """Ask OpenRouteService for one round-trip (loop) route starting/ending at the
    given point, roughly `distance_km` long. `seed` varies the shape so repeated
    calls return different loops."""
    url = f"{settings.ors_base_url}/v2/directions/{profile}/geojson"
    body = {
        "coordinates": [[longitude, latitude]],
        "options": {
            "round_trip": {
                "length": distance_km * 1000,
                "points": points,
                "seed": seed,
            }
        },
    }
    headers = {
        "Authorization": settings.ors_api_key,
        "Content-Type": "application/json",
    }

    try:
        response = await client.post(url, json=body, headers=headers, timeout=30.0)
    except httpx.HTTPError as exc:
        raise RoutingError(f"라우팅 서버에 연결할 수 없습니다: {exc}") from exc

    if response.status_code != 200:
        raise RoutingError(
            f"라우팅 서버 오류 ({response.status_code}): {response.text}"
        )

    data = response.json()
    try:
        feature = data["features"][0]
        lng_lat_coords = feature["geometry"]["coordinates"]
        summary = feature["properties"]["summary"]
    except (KeyError, IndexError) as exc:
        raise RoutingError("라우팅 응답 형식이 올바르지 않습니다.") from exc

    coordinates = [(lat, lng) for lng, lat in lng_lat_coords]

    return {
        "distance_m": summary.get("distance", 0.0),
        "duration_s": summary.get("duration", 0.0),
        "coordinates": coordinates,
    }


async def generate_routes(
    latitude: float,
    longitude: float,
    distance_km: float,
    count: int,
    profile: str,
) -> list[dict]:
    if not settings.ors_api_key:
        raise RoutingError(
            "ORS_API_KEY가 설정되어 있지 않습니다. openrouteservice.org에서 "
            "무료 API 키를 발급받아 서버 환경 변수로 설정하세요."
        )

    async with httpx.AsyncClient() as client:
        routes = []
        for i in range(count):
            # Vary both the seed and the loop's point count so the four routes
            # take visibly different shapes instead of minor variations.
            seed = 1000 * (i + 1) + 7
            points = 3 + (i % 3)
            route = await fetch_round_trip(
                client, latitude, longitude, distance_km, profile, seed, points
            )
            routes.append(route)
        return routes
