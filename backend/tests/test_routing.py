import json

import httpx
import pytest
import respx

from app import routing
from app.config import settings


def _ors_geojson_response(routes: list[tuple[float, float, list[tuple[float, float]]]]) -> dict:
    # ORS returns [lng, lat] pairs. `routes` is a list of (distance_m, duration_s, coords).
    return {
        "features": [
            {
                "geometry": {"coordinates": [[lng, lat] for lat, lng in coords]},
                "properties": {"summary": {"distance": distance_m, "duration": duration_s}},
            }
            for distance_m, duration_s, coords in routes
        ]
    }


@pytest.fixture(autouse=True)
def _ors_key(monkeypatch):
    monkeypatch.setattr(settings, "ors_api_key", "test-key")


@pytest.mark.asyncio
async def test_fetch_round_trip_parses_geojson_response():
    route = _ors_geojson_response([(10_000, 1800, [(37.5, 127.0), (37.6, 127.1)])])

    with respx.mock:
        respx.post(f"{settings.ors_base_url}/v2/directions/cycling-regular/geojson").mock(
            return_value=httpx.Response(200, json=route)
        )
        async with httpx.AsyncClient() as client:
            result = await routing.fetch_round_trip(
                client, 37.5, 127.0, 10.0, "cycling-regular", seed=1
            )

    assert result["distance_m"] == 10_000
    assert result["duration_s"] == 1800
    assert result["coordinates"] == [(37.5, 127.0), (37.6, 127.1)]


@pytest.mark.asyncio
async def test_fetch_round_trip_raises_on_error_status():
    with respx.mock:
        respx.post(f"{settings.ors_base_url}/v2/directions/cycling-regular/geojson").mock(
            return_value=httpx.Response(403, text="quota exceeded")
        )
        async with httpx.AsyncClient() as client:
            with pytest.raises(routing.RoutingError):
                await routing.fetch_round_trip(
                    client, 37.5, 127.0, 10.0, "cycling-regular", seed=1
                )


@pytest.mark.asyncio
async def test_generate_round_trip_routes_requests_one_route_per_count_with_distinct_seeds():
    route = _ors_geojson_response([(10_000, 1800, [(37.5, 127.0)])])
    seeds_used = []

    def _responder(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seeds_used.append(body["options"]["round_trip"]["seed"])
        return httpx.Response(200, json=route)

    with respx.mock:
        respx.post(f"{settings.ors_base_url}/v2/directions/cycling-regular/geojson").mock(
            side_effect=_responder
        )
        routes = await routing.generate_routes([(37.5, 127.0)], 10.0, 4, "cycling-regular")

    assert len(routes) == 4
    assert len(set(seeds_used)) == 4  # every request used a different seed


@pytest.mark.asyncio
async def test_generate_routes_requires_api_key(monkeypatch):
    monkeypatch.setattr(settings, "ors_api_key", "")

    with pytest.raises(routing.RoutingError):
        await routing.generate_routes([(37.5, 127.0)], 10.0, 4, "cycling-regular")


@pytest.mark.asyncio
async def test_generate_routes_requires_distance_for_single_waypoint():
    with pytest.raises(routing.RoutingError):
        await routing.generate_routes([(37.5, 127.0)], None, 4, "cycling-regular")


@pytest.mark.asyncio
async def test_generate_waypoint_routes_passes_through_every_waypoint_in_order():
    # Two segments (A->B, B->C), each with 2 alternatives.
    segment_ab = _ors_geojson_response(
        [
            (1000, 100, [(0.0, 0.0), (0.5, 0.5), (1.0, 1.0)]),
            (1200, 120, [(0.0, 0.0), (0.4, 0.6), (1.0, 1.0)]),
        ]
    )
    segment_bc = _ors_geojson_response(
        [
            (2000, 200, [(1.0, 1.0), (1.5, 1.5), (2.0, 2.0)]),
            (2100, 210, [(1.0, 1.0), (1.6, 1.4), (2.0, 2.0)]),
        ]
    )

    call_count = {"n": 0}

    def _responder(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        coords = json.loads(request.content)["coordinates"]
        start = tuple(coords[0])
        # ORS coordinates are [lng, lat]; segment A->B starts at (0,0), B->C at (1,1).
        if start == (0.0, 0.0):
            return httpx.Response(200, json=segment_ab)
        return httpx.Response(200, json=segment_bc)

    with respx.mock:
        respx.post(f"{settings.ors_base_url}/v2/directions/cycling-regular/geojson").mock(
            side_effect=_responder
        )
        routes = await routing.generate_routes(
            [(0.0, 0.0), (1.0, 1.0), (2.0, 2.0)], None, 2, "cycling-regular"
        )

    assert call_count["n"] == 2  # one request per segment, alternatives requested together
    assert len(routes) == 2

    for route in routes:
        # Every generated route must start at A, pass through B, and end at C.
        assert route["coordinates"][0] == (0.0, 0.0)
        assert (1.0, 1.0) in route["coordinates"]
        assert route["coordinates"][-1] == (2.0, 2.0)
        # The shared junction point must not be duplicated.
        assert route["coordinates"].count((1.0, 1.0)) == 1

    # The two variants should differ (they use different alternatives per segment).
    assert routes[0]["coordinates"] != routes[1]["coordinates"]


@pytest.mark.asyncio
async def test_generate_waypoint_routes_reuses_last_alternative_when_fewer_available():
    # Only one alternative available for this segment.
    segment = _ors_geojson_response([(1000, 100, [(0.0, 0.0), (1.0, 1.0)])])

    with respx.mock:
        respx.post(f"{settings.ors_base_url}/v2/directions/cycling-regular/geojson").mock(
            return_value=httpx.Response(200, json=segment)
        )
        routes = await routing.generate_routes(
            [(0.0, 0.0), (1.0, 1.0)], None, 3, "cycling-regular"
        )

    assert len(routes) == 3
    for route in routes:
        assert route["coordinates"] == [(0.0, 0.0), (1.0, 1.0)]


@pytest.mark.asyncio
async def test_generate_waypoint_routes_ignores_distance_km_when_route_already_longer():
    segment = _ors_geojson_response([(5000, 500, [(0.0, 0.0), (1.0, 1.0)])])

    with respx.mock:
        respx.post(f"{settings.ors_base_url}/v2/directions/cycling-regular/geojson").mock(
            return_value=httpx.Response(200, json=segment)
        )
        # Want a 2km ride, but the photos are already 5km apart -> distance_km is ignored.
        routes = await routing.generate_routes(
            [(0.0, 0.0), (1.0, 1.0)], 2.0, 1, "cycling-regular"
        )

    assert routes[0]["distance_m"] == 5000
    assert routes[0]["coordinates"] == [(0.0, 0.0), (1.0, 1.0)]


@pytest.mark.asyncio
async def test_generate_waypoint_routes_extends_route_when_shorter_than_distance_km():
    segment = _ors_geojson_response([(1000, 100, [(0.0, 0.0), (1.0, 1.0)])])
    extension = _ors_geojson_response([(4000, 400, [(1.0, 1.0), (1.2, 1.2), (1.0, 1.0)])])

    def _responder(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if "round_trip" in body.get("options", {}):  # round_trip extension request
            return httpx.Response(200, json=extension)
        return httpx.Response(200, json=segment)

    with respx.mock:
        respx.post(f"{settings.ors_base_url}/v2/directions/cycling-regular/geojson").mock(
            side_effect=_responder
        )
        # Want a 5km ride, but the direct path between the photos is only 1km ->
        # a loop is added at the last waypoint to make up the remaining 4km.
        routes = await routing.generate_routes(
            [(0.0, 0.0), (1.0, 1.0)], 5.0, 1, "cycling-regular"
        )

    route = routes[0]
    assert route["distance_m"] == 5000
    assert route["coordinates"] == [(0.0, 0.0), (1.0, 1.0), (1.2, 1.2), (1.0, 1.0)]


@pytest.mark.parametrize(
    "climb_preference,expected_steepness",
    [("업힐", 3), ("밸런스", 1), ("평지", 0)],
)
@pytest.mark.asyncio
async def test_climb_preference_sets_steepness_difficulty(climb_preference, expected_steepness):
    route = _ors_geojson_response([(10_000, 1800, [(37.5, 127.0)])])
    sent_bodies = []

    def _responder(request: httpx.Request) -> httpx.Response:
        sent_bodies.append(json.loads(request.content))
        return httpx.Response(200, json=route)

    with respx.mock:
        respx.post(f"{settings.ors_base_url}/v2/directions/cycling-regular/geojson").mock(
            side_effect=_responder
        )
        async with httpx.AsyncClient() as client:
            await routing.fetch_round_trip(
                client, 37.5, 127.0, 10.0, "cycling-regular", seed=1, climb_preference=climb_preference
            )

    steepness = sent_bodies[0]["options"]["profile_params"]["weightings"]["steepness_difficulty"]
    assert steepness == expected_steepness


@pytest.mark.asyncio
async def test_fetch_round_trip_parses_elevation_and_ascent_descent():
    response = {
        "features": [
            {
                "geometry": {"coordinates": [[127.0, 37.5, 10.0], [127.1, 37.6, 25.0]]},
                "properties": {
                    "summary": {"distance": 1000, "duration": 200, "ascent": 15.0, "descent": 3.0}
                },
            }
        ]
    }

    with respx.mock:
        respx.post(f"{settings.ors_base_url}/v2/directions/cycling-regular/geojson").mock(
            return_value=httpx.Response(200, json=response)
        )
        async with httpx.AsyncClient() as client:
            result = await routing.fetch_round_trip(
                client, 37.5, 127.0, 1.0, "cycling-regular", seed=1
            )

    assert result["ascent_m"] == 15.0
    assert result["descent_m"] == 3.0
    assert result["coordinates"] == [(37.5, 127.0), (37.6, 127.1)]
    assert result["elevations"] == [10.0, 25.0]
