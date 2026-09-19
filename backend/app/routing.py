import math

import httpx

from app.config import settings

Coordinate = tuple[float, float]  # (latitude, longitude)

# OpenRouteService의 cycling 프로필은 "steepness_difficulty"(0~3) 가중치로 오르막
# 선호도를 조절할 수 있다: 0=오르막 회피(초보), 3=오르막 선호(고수/업힐 라이더).
STEEPNESS_DIFFICULTY_BY_PREFERENCE = {
    "업힐": 3,
    "밸런스": 1,
    "평지": 0,
}
DEFAULT_CLIMB_PREFERENCE = "밸런스"


class RoutingError(Exception):
    """Raised when the routing provider fails or is unreachable."""


def _require_api_key() -> None:
    if not settings.ors_api_key:
        raise RoutingError(
            "ORS_API_KEY가 설정되어 있지 않습니다. openrouteservice.org에서 "
            "무료 API 키를 발급받아 서버 환경 변수로 설정하세요."
        )


def _build_options(profile: str, climb_preference: str, round_trip: dict | None = None) -> dict:
    options: dict = {}
    if round_trip is not None:
        options["round_trip"] = round_trip

    # steepness_difficulty는 자전거 프로필에서만 지원된다.
    if profile.startswith("cycling"):
        steepness = STEEPNESS_DIFFICULTY_BY_PREFERENCE.get(
            climb_preference, STEEPNESS_DIFFICULTY_BY_PREFERENCE[DEFAULT_CLIMB_PREFERENCE]
        )
        options["profile_params"] = {"weightings": {"steepness_difficulty": steepness}}

    return options


def _haversine_m(a: Coordinate, b: Coordinate) -> float:
    lat1, lon1 = a
    lat2, lon2 = b
    radius = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(h)))


def _offset_via_point(start: Coordinate, end: Coordinate, offset_m: float) -> Coordinate:
    """start->end 구간의 중점에서 그 방향에 수직으로 대략 offset_m미터만큼 비켜난 지점을
    돌려준다. ORS의 alternative_routes가 항상 실제로 다른 길을 찾아주는 건 아니라서
    (특히 도로가 단순한 구간), 이 지점을 경유지로 강제 지정해서 경로 변형을 만든다."""
    lat1, lng1 = start
    lat2, lng2 = end
    mid_lat = (lat1 + lat2) / 2
    mid_lng = (lng1 + lng2) / 2

    meters_per_deg_lat = 111_320.0
    meters_per_deg_lng = 111_320.0 * math.cos(math.radians(mid_lat)) or 1e-6

    dx = (lng2 - lng1) * meters_per_deg_lng
    dy = (lat2 - lat1) * meters_per_deg_lat
    length = math.hypot(dx, dy) or 1.0

    perp_x = -dy / length
    perp_y = dx / length

    offset_lat = (perp_y * offset_m) / meters_per_deg_lat
    offset_lng = (perp_x * offset_m) / meters_per_deg_lng

    return (mid_lat + offset_lat, mid_lng + offset_lng)


def _variant_offset_m(variant_index: int, segment_length_m: float) -> float:
    """variant_index==0은 항상 경유지 없는 기본(최단/최적) 경로. 그 외에는 구간 길이에
    비례하되 150m~2.5km 사이로 제한한 크기만큼, 홀/짝 인덱스마다 반대편으로 비켜난
    경유지를 강제해서 서로 다른 경로가 나오게 한다."""
    if variant_index == 0:
        return 0.0
    base = min(max(segment_length_m * 0.12, 150.0), 2500.0)
    magnitude = base * (1 + (variant_index - 1) * 0.6)
    sign = 1 if variant_index % 2 == 1 else -1
    return sign * magnitude


def _parse_directions_response(data: dict) -> list[dict]:
    """Parse an ORS directions/geojson response into a list of route dicts
    (distance_m, duration_s, ascent_m, descent_m, coordinates, elevations) -
    one per returned route (there can be several when alternative_routes was
    requested). `elevation: true`가 요청에 포함되면 좌표는 [lng, lat, elevation]
    형태이고 summary에 ascent/descent가 포함된다."""
    features = data.get("features")
    if not features:
        raise RoutingError("라우팅 응답 형식이 올바르지 않습니다.")

    routes = []
    for feature in features:
        try:
            raw_coords = feature["geometry"]["coordinates"]
            summary = feature["properties"]["summary"]
        except (KeyError, TypeError) as exc:
            raise RoutingError("라우팅 응답 형식이 올바르지 않습니다.") from exc

        coordinates: list[Coordinate] = []
        elevations: list[float | None] = []
        for point in raw_coords:
            lng, lat = point[0], point[1]
            coordinates.append((lat, lng))
            elevations.append(point[2] if len(point) > 2 else None)

        routes.append(
            {
                "distance_m": summary.get("distance", 0.0),
                "duration_s": summary.get("duration", 0.0),
                "ascent_m": summary.get("ascent"),
                "descent_m": summary.get("descent"),
                "coordinates": coordinates,
                "elevations": elevations,
            }
        )
    return routes


async def _post_directions(client: httpx.AsyncClient, profile: str, body: dict) -> dict:
    url = f"{settings.ors_base_url}/v2/directions/{profile}/geojson"
    headers = {
        "Authorization": settings.ors_api_key,
        "Content-Type": "application/json",
    }
    print(f"[ORS request] {profile} options={body.get('options')} coords={body.get('coordinates')}")
    try:
        response = await client.post(url, json=body, headers=headers, timeout=30.0)
    except httpx.HTTPError as exc:
        raise RoutingError(f"라우팅 서버에 연결할 수 없습니다: {exc}") from exc

    if response.status_code != 200:
        raise RoutingError(f"라우팅 서버 오류 ({response.status_code}): {response.text}")

    data = response.json()
    try:
        summary = data["features"][0]["properties"]["summary"]
        n_points = len(data["features"][0]["geometry"]["coordinates"])
        print(
            f"[ORS response] distance={summary.get('distance')} "
            f"ascent={summary.get('ascent')} descent={summary.get('descent')} points={n_points}"
        )
    except (KeyError, IndexError, TypeError):
        print(f"[ORS response] unexpected shape: {data}")

    return data


async def fetch_round_trip(
    client: httpx.AsyncClient,
    latitude: float,
    longitude: float,
    distance_km: float,
    profile: str,
    seed: int,
    points: int = 3,
    climb_preference: str = DEFAULT_CLIMB_PREFERENCE,
) -> dict:
    """단일 지점에서 시작해 그 지점으로 돌아오는, 지정 거리만큼의 순환 경로 하나를 요청한다.
    `seed`를 바꾸면 매번 다른 모양의 순환 경로가 나온다."""
    body = {
        "coordinates": [[longitude, latitude]],
        "elevation": True,
        "options": _build_options(
            profile,
            climb_preference,
            round_trip={"length": distance_km * 1000, "points": points, "seed": seed},
        ),
    }
    data = await _post_directions(client, profile, body)
    return _parse_directions_response(data)[0]


async def fetch_segment_route(
    client: httpx.AsyncClient,
    start: Coordinate,
    end: Coordinate,
    profile: str,
    climb_preference: str = DEFAULT_CLIMB_PREFERENCE,
    via: Coordinate | None = None,
) -> dict:
    """두 지점 사이의 경로 하나를 요청한다. `via`를 지정하면 그 지점을 지나도록 강제해서
    일부러 다른 모양의 경로를 만든다 (ORS의 alternative_routes는 도로가 단순한 구간에서는
    실제로 다른 길을 찾아주지 못하는 경우가 많고, elevation과 같이 쓰면 고도 데이터가
    빠지는 문제도 있어 사용하지 않는다)."""
    points = [start] + ([via] if via is not None else []) + [end]
    body: dict = {
        "coordinates": [[lng, lat] for lat, lng in points],
        "elevation": True,
    }
    options = _build_options(profile, climb_preference)
    if options:
        body["options"] = options

    data = await _post_directions(client, profile, body)
    return _parse_directions_response(data)[0]


async def generate_round_trip_routes(
    latitude: float,
    longitude: float,
    distance_km: float,
    count: int,
    profile: str,
    climb_preference: str = DEFAULT_CLIMB_PREFERENCE,
) -> list[dict]:
    async with httpx.AsyncClient() as client:
        routes = []
        for i in range(count):
            # Vary both the seed and the loop's point count so the routes
            # take visibly different shapes instead of minor variations.
            seed = 1000 * (i + 1) + 7
            points = 3 + (i % 3)
            route = await fetch_round_trip(
                client, latitude, longitude, distance_km, profile, seed, points, climb_preference
            )
            routes.append(route)
        return routes


async def generate_waypoint_routes(
    waypoints: list[Coordinate],
    count: int,
    profile: str,
    distance_km: float | None = None,
    climb_preference: str = DEFAULT_CLIMB_PREFERENCE,
) -> list[dict]:
    """2개 이상의 지점을 순서대로 모두 지나는 경로를 count개 만든다.

    각 변형(variant)마다, 연속된 두 지점 사이(구간)를 이을 때 살짝 다른 경유지를 강제로
    지정해서(첫 번째 변형은 경유지 없이 기본 경로) 서로 다른 모양의 전체 경로 count개를
    만든다.

    `distance_km`을 지정하면 최소 목표 거리로 취급한다: 사진들을 지나는 실제 경로가
    이미 그보다 길면 입력값은 무시하고, 더 짧으면 마지막 사진 위치에서 순환 구간을
    추가해 부족한 만큼 채운다.
    """
    target_m = distance_km * 1000 if distance_km is not None else None
    last_point = waypoints[-1]
    segments = list(zip(waypoints, waypoints[1:]))

    async with httpx.AsyncClient() as client:
        routes = []
        for variant_index in range(count):
            combined_coordinates: list[Coordinate] = []
            combined_elevations: list[float | None] = []
            total_distance = 0.0
            total_duration = 0.0
            total_ascent = 0.0
            total_descent = 0.0

            for start, end in segments:
                offset_m = _variant_offset_m(variant_index, _haversine_m(start, end))
                via = _offset_via_point(start, end, offset_m) if offset_m else None

                piece = await fetch_segment_route(client, start, end, profile, climb_preference, via)
                coords = piece["coordinates"]
                elevs = piece.get("elevations") or [None] * len(coords)
                # Avoid duplicating the junction point shared between segments.
                if combined_coordinates and coords and combined_coordinates[-1] == coords[0]:
                    coords = coords[1:]
                    elevs = elevs[1:]
                combined_coordinates.extend(coords)
                combined_elevations.extend(elevs)
                total_distance += piece["distance_m"]
                total_duration += piece["duration_s"]
                total_ascent += piece.get("ascent_m") or 0.0
                total_descent += piece.get("descent_m") or 0.0

            if target_m is not None and total_distance < target_m:
                shortfall_km = (target_m - total_distance) / 1000
                seed = 2000 * (variant_index + 1) + 31
                points = 3 + (variant_index % 3)
                try:
                    extension = await fetch_round_trip(
                        client,
                        last_point[0],
                        last_point[1],
                        shortfall_km,
                        profile,
                        seed,
                        points,
                        climb_preference,
                    )
                except RoutingError:
                    # 부족분을 못 채워도 원래(사진들을 잇는) 경로는 그대로 돌려준다.
                    extension = None

                if extension is not None:
                    ext_coords = extension["coordinates"]
                    ext_elevs = extension.get("elevations") or [None] * len(ext_coords)
                    if (
                        combined_coordinates
                        and ext_coords
                        and combined_coordinates[-1] == ext_coords[0]
                    ):
                        ext_coords = ext_coords[1:]
                        ext_elevs = ext_elevs[1:]
                    combined_coordinates.extend(ext_coords)
                    combined_elevations.extend(ext_elevs)
                    total_distance += extension["distance_m"]
                    total_duration += extension["duration_s"]
                    total_ascent += extension.get("ascent_m") or 0.0
                    total_descent += extension.get("descent_m") or 0.0

            routes.append(
                {
                    "distance_m": total_distance,
                    "duration_s": total_duration,
                    "ascent_m": total_ascent,
                    "descent_m": total_descent,
                    "coordinates": combined_coordinates,
                    "elevations": combined_elevations,
                }
            )

    return routes


async def generate_routes(
    waypoints: list[Coordinate],
    distance_km: float | None,
    count: int,
    profile: str,
    climb_preference: str = DEFAULT_CLIMB_PREFERENCE,
) -> list[dict]:
    _require_api_key()

    if len(waypoints) == 1:
        if distance_km is None:
            raise RoutingError("사진이 1장일 때는 원하는 경로 거리가 필요합니다.")
        latitude, longitude = waypoints[0]
        return await generate_round_trip_routes(
            latitude, longitude, distance_km, count, profile, climb_preference
        )

    return await generate_waypoint_routes(
        waypoints, count, profile, distance_km, climb_preference
    )
