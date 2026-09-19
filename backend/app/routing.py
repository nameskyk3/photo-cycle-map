import httpx

from app.config import settings

Coordinate = tuple[float, float]  # (latitude, longitude)


class RoutingError(Exception):
    """Raised when the routing provider fails or is unreachable."""


def _require_api_key() -> None:
    if not settings.ors_api_key:
        raise RoutingError(
            "ORS_API_KEY가 설정되어 있지 않습니다. openrouteservice.org에서 "
            "무료 API 키를 발급받아 서버 환경 변수로 설정하세요."
        )


def _parse_directions_response(data: dict) -> list[dict]:
    """Parse an ORS directions/geojson response into a list of
    {distance_m, duration_s, coordinates} dicts - one per returned route
    (there can be several when alternative_routes was requested)."""
    features = data.get("features")
    if not features:
        raise RoutingError("라우팅 응답 형식이 올바르지 않습니다.")

    routes = []
    for feature in features:
        try:
            lng_lat_coords = feature["geometry"]["coordinates"]
            summary = feature["properties"]["summary"]
        except (KeyError, TypeError) as exc:
            raise RoutingError("라우팅 응답 형식이 올바르지 않습니다.") from exc
        routes.append(
            {
                "distance_m": summary.get("distance", 0.0),
                "duration_s": summary.get("duration", 0.0),
                "coordinates": [(lat, lng) for lng, lat in lng_lat_coords],
            }
        )
    return routes


async def _post_directions(client: httpx.AsyncClient, profile: str, body: dict) -> dict:
    url = f"{settings.ors_base_url}/v2/directions/{profile}/geojson"
    headers = {
        "Authorization": settings.ors_api_key,
        "Content-Type": "application/json",
    }
    try:
        response = await client.post(url, json=body, headers=headers, timeout=30.0)
    except httpx.HTTPError as exc:
        raise RoutingError(f"라우팅 서버에 연결할 수 없습니다: {exc}") from exc

    if response.status_code != 200:
        raise RoutingError(f"라우팅 서버 오류 ({response.status_code}): {response.text}")

    return response.json()


async def fetch_round_trip(
    client: httpx.AsyncClient,
    latitude: float,
    longitude: float,
    distance_km: float,
    profile: str,
    seed: int,
    points: int = 3,
) -> dict:
    """단일 지점에서 시작해 그 지점으로 돌아오는, 지정 거리만큼의 순환 경로 하나를 요청한다.
    `seed`를 바꾸면 매번 다른 모양의 순환 경로가 나온다."""
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
    data = await _post_directions(client, profile, body)
    return _parse_directions_response(data)[0]


async def fetch_segment_alternatives(
    client: httpx.AsyncClient,
    start: Coordinate,
    end: Coordinate,
    profile: str,
    target_count: int,
) -> list[dict]:
    """두 지점 사이의 경로를 서로 다른 대안 경로로 최대 target_count개까지 요청한다.
    실제 도로 사정에 따라 ORS가 그보다 적게 돌려줄 수 있다.
    ORS는 target_count로 최대 3까지만 허용한다 (그 이상이면 400 에러)."""
    start_lat, start_lng = start
    end_lat, end_lng = end
    body = {
        "coordinates": [[start_lng, start_lat], [end_lng, end_lat]],
        "alternative_routes": {
            "target_count": min(3, max(1, target_count)),
            "weight_factor": 1.6,
            "share_factor": 0.6,
        },
    }
    data = await _post_directions(client, profile, body)
    return _parse_directions_response(data)


async def generate_round_trip_routes(
    latitude: float,
    longitude: float,
    distance_km: float,
    count: int,
    profile: str,
) -> list[dict]:
    async with httpx.AsyncClient() as client:
        routes = []
        for i in range(count):
            # Vary both the seed and the loop's point count so the routes
            # take visibly different shapes instead of minor variations.
            seed = 1000 * (i + 1) + 7
            points = 3 + (i % 3)
            route = await fetch_round_trip(
                client, latitude, longitude, distance_km, profile, seed, points
            )
            routes.append(route)
        return routes


async def generate_waypoint_routes(
    waypoints: list[Coordinate],
    count: int,
    profile: str,
) -> list[dict]:
    """2개 이상의 지점을 순서대로 모두 지나는 경로를 count개 만든다.

    연속된 두 지점 사이(구간)마다 서로 다른 대안 경로를 구한 뒤, 경로 번호마다
    각 구간에서 다른 대안을 골라 이어 붙여서 서로 다른 전체 경로 count개를 만든다.
    """
    async with httpx.AsyncClient() as client:
        segment_alternatives: list[list[dict]] = []
        for start, end in zip(waypoints, waypoints[1:]):
            alternatives = await fetch_segment_alternatives(client, start, end, profile, count)
            segment_alternatives.append(alternatives)

    routes = []
    for variant_index in range(count):
        combined_coordinates: list[Coordinate] = []
        total_distance = 0.0
        total_duration = 0.0

        for segment in segment_alternatives:
            alternative = segment[min(variant_index, len(segment) - 1)]
            coords = alternative["coordinates"]
            # Avoid duplicating the junction point shared between segments.
            if combined_coordinates and coords and combined_coordinates[-1] == coords[0]:
                coords = coords[1:]
            combined_coordinates.extend(coords)
            total_distance += alternative["distance_m"]
            total_duration += alternative["duration_s"]

        routes.append(
            {
                "distance_m": total_distance,
                "duration_s": total_duration,
                "coordinates": combined_coordinates,
            }
        )

    return routes


async def generate_routes(
    waypoints: list[Coordinate],
    distance_km: float | None,
    count: int,
    profile: str,
) -> list[dict]:
    _require_api_key()

    if len(waypoints) == 1:
        if distance_km is None:
            raise RoutingError("사진이 1장일 때는 원하는 경로 거리가 필요합니다.")
        latitude, longitude = waypoints[0]
        return await generate_round_trip_routes(latitude, longitude, distance_km, count, profile)

    return await generate_waypoint_routes(waypoints, count, profile)
