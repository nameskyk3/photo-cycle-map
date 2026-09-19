import httpx
import pytest
import respx

from app import routing
from app.config import settings


def _ors_geojson_response(distance_m: float, duration_s: float, coords: list[tuple[float, float]]) -> dict:
    # ORS returns [lng, lat] pairs.
    return {
        "features": [
            {
                "geometry": {"coordinates": [[lng, lat] for lat, lng in coords]},
                "properties": {"summary": {"distance": distance_m, "duration": duration_s}},
            }
        ]
    }


@pytest.fixture(autouse=True)
def _ors_key(monkeypatch):
    monkeypatch.setattr(settings, "ors_api_key", "test-key")


@pytest.mark.asyncio
async def test_fetch_round_trip_parses_geojson_response():
    route = _ors_geojson_response(10_000, 1800, [(37.5, 127.0), (37.6, 127.1)])

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
async def test_generate_routes_requests_one_route_per_count_with_distinct_seeds():
    route = _ors_geojson_response(10_000, 1800, [(37.5, 127.0)])
    seeds_used = []

    def _responder(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content)
        seeds_used.append(body["options"]["round_trip"]["seed"])
        return httpx.Response(200, json=route)

    with respx.mock:
        respx.post(f"{settings.ors_base_url}/v2/directions/cycling-regular/geojson").mock(
            side_effect=_responder
        )
        routes = await routing.generate_routes(37.5, 127.0, 10.0, 4, "cycling-regular")

    assert len(routes) == 4
    assert len(set(seeds_used)) == 4  # every request used a different seed


@pytest.mark.asyncio
async def test_generate_routes_requires_api_key(monkeypatch):
    monkeypatch.setattr(settings, "ors_api_key", "")

    with pytest.raises(routing.RoutingError):
        await routing.generate_routes(37.5, 127.0, 10.0, 4, "cycling-regular")
