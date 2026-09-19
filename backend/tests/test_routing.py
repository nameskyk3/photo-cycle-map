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
async def test_fetch_segment_route_without_via_sends_two_coordinates():
    route = _ors_geojson_response([(1000, 100, [(0.0, 0.0), (1.0, 1.0)])])
    sent_bodies = []

    def _responder(request: httpx.Request) -> httpx.Response:
        sent_bodies.append(json.loads(request.content))
        return httpx.Response(200, json=route)

    with respx.mock:
        respx.post(f"{settings.ors_base_url}/v2/directions/cycling-regular/geojson").mock(
            side_effect=_responder
        )
        async with httpx.AsyncClient() as client:
            result = await routing.fetch_segment_route(
                client, (0.0, 0.0), (1.0, 1.0), "cycling-regular"
            )

    assert len(sent_bodies[0]["coordinates"]) == 2
    assert "round_trip" not in sent_bodies[0].get("options", {})
    assert result["coordinates"] == [(0.0, 0.0), (1.0, 1.0)]


@pytest.mark.asyncio
async def test_fetch_segment_route_with_via_sends_three_coordinates():
    route = _ors_geojson_response([(1500, 150, [(0.0, 0.0), (0.5, 0.6), (1.0, 1.0)])])
    sent_bodies = []

    def _responder(request: httpx.Request) -> httpx.Response:
        sent_bodies.append(json.loads(request.content))
        return httpx.Response(200, json=route)

    with respx.mock:
        respx.post(f"{settings.ors_base_url}/v2/directions/cycling-regular/geojson").mock(
            side_effect=_responder
        )
        async with httpx.AsyncClient() as client:
            await routing.fetch_segment_route(
                client, (0.0, 0.0), (1.0, 1.0), "cycling-regular", via=(0.5, 0.6)
            )

    assert len(sent_bodies[0]["coordinates"]) == 3
    assert sent_bodies[0]["coordinates"][1] == [0.6, 0.5]  # via as [lng, lat]


def test_variant_offset_m_is_zero_for_first_variant_and_grows_after():
    assert routing._variant_offset_m(0, 10_000) == 0.0

    offset1 = routing._variant_offset_m(1, 10_000)
    offset2 = routing._variant_offset_m(2, 10_000)
    assert offset1 > 0
    assert offset2 < 0
    assert abs(offset2) > abs(offset1)  # later variants get a bigger detour


def test_offset_via_point_nudges_perpendicular_to_the_segment():
    start = (37.5, 127.0)
    end = (37.5, 127.01)  # a segment running due east

    via = routing._offset_via_point(start, end, 200.0)

    mid_lng = (start[1] + end[1]) / 2
    mid_lat = (start[0] + end[0]) / 2
    # Nudged mostly in latitude (perpendicular to an east-west segment).
    assert via[1] == pytest.approx(mid_lng, abs=1e-6)
    assert via[0] != pytest.approx(mid_lat, abs=1e-6)


@pytest.mark.asyncio
async def test_generate_waypoint_routes_passes_through_every_waypoint_in_order():
    def _responder(request: httpx.Request) -> httpx.Response:
        # Echo back a route that runs through exactly the requested coordinates
        # (start, optional via, end), so pass-through order can be checked.
        coords = json.loads(request.content)["coordinates"]
        path = [(lat, lng) for lng, lat in coords]
        return httpx.Response(200, json=_ors_geojson_response([(1000, 100, path)]))

    with respx.mock:
        respx.post(f"{settings.ors_base_url}/v2/directions/cycling-regular/geojson").mock(
            side_effect=_responder
        )
        routes = await routing.generate_routes(
            [(0.0, 0.0), (1.0, 1.0), (2.0, 2.0)], None, 2, "cycling-regular"
        )

    assert len(routes) == 2

    for route in routes:
        # Every generated route must start at A, pass through B, and end at C.
        assert route["coordinates"][0] == (0.0, 0.0)
        assert (1.0, 1.0) in route["coordinates"]
        assert route["coordinates"][-1] == (2.0, 2.0)
        # The shared junction point must not be duplicated.
        assert route["coordinates"].count((1.0, 1.0)) == 1

    # Variant 1 forces a via point per segment, so it must differ from
    # variant 0's plain point-to-point route.
    assert routes[0]["coordinates"] != routes[1]["coordinates"]


@pytest.mark.asyncio
async def test_fetch_segment_with_fallback_retries_with_smaller_offset_then_no_via():
    attempts = []

    def _responder(request: httpx.Request) -> httpx.Response:
        coords = json.loads(request.content)["coordinates"]
        attempts.append(len(coords))
        if len(coords) == 3:
            # Simulate ORS failing to find a routable road near the via point
            # (e.g. it landed in the sea).
            return httpx.Response(404, json={"error": {"message": "no routable point"}})
        return httpx.Response(
            200, json=_ors_geojson_response([(1000, 100, [(0.0, 0.0), (1.0, 1.0)])])
        )

    with respx.mock:
        respx.post(f"{settings.ors_base_url}/v2/directions/cycling-regular/geojson").mock(
            side_effect=_responder
        )
        async with httpx.AsyncClient() as client:
            result = await routing._fetch_segment_with_fallback(
                client, (0.0, 0.0), (1.0, 1.0), "cycling-regular", "밸런스", 500.0
            )

    # Full-offset via fails, half-offset via also fails, then it falls back
    # to the plain point-to-point request (2 coordinates) which succeeds.
    assert attempts == [3, 3, 2]
    assert result["coordinates"] == [(0.0, 0.0), (1.0, 1.0)]


@pytest.mark.asyncio
async def test_fetch_segment_with_fallback_skips_via_entirely_when_offset_is_zero():
    sent_coordinate_counts = []

    def _responder(request: httpx.Request) -> httpx.Response:
        coords = json.loads(request.content)["coordinates"]
        sent_coordinate_counts.append(len(coords))
        return httpx.Response(
            200, json=_ors_geojson_response([(1000, 100, [(0.0, 0.0), (1.0, 1.0)])])
        )

    with respx.mock:
        respx.post(f"{settings.ors_base_url}/v2/directions/cycling-regular/geojson").mock(
            side_effect=_responder
        )
        async with httpx.AsyncClient() as client:
            await routing._fetch_segment_with_fallback(
                client, (0.0, 0.0), (1.0, 1.0), "cycling-regular", "밸런스", 0.0
            )

    assert sent_coordinate_counts == [2]


@pytest.mark.asyncio
async def test_generate_waypoint_routes_only_injects_via_for_later_variants():
    sent_coordinate_counts = []

    def _responder(request: httpx.Request) -> httpx.Response:
        coords = json.loads(request.content)["coordinates"]
        sent_coordinate_counts.append(len(coords))
        path = [(lat, lng) for lng, lat in coords]
        return httpx.Response(200, json=_ors_geojson_response([(1000, 100, path)]))

    with respx.mock:
        respx.post(f"{settings.ors_base_url}/v2/directions/cycling-regular/geojson").mock(
            side_effect=_responder
        )
        await routing.generate_routes([(0.0, 0.0), (1.0, 1.0)], None, 3, "cycling-regular")

    # One segment, 3 variants -> 3 requests: the first has no via (2
    # coordinates), the rest are forced through a via point (3 coordinates).
    assert sent_coordinate_counts == [2, 3, 3]


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
