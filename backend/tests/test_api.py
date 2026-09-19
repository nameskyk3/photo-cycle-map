import httpx
import respx
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from tests.helpers import make_jpeg_bytes


client = TestClient(app)


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_photo_location_with_gps():
    photo = make_jpeg_bytes(latitude=37.5665, longitude=126.9780)

    response = client.post(
        "/api/photo/location",
        files={"photo": ("seoul.jpg", photo, "image/jpeg")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["has_location"] is True
    assert abs(body["latitude"] - 37.5665) < 1e-3
    assert abs(body["longitude"] - 126.9780) < 1e-3


def test_photo_location_without_gps():
    photo = make_jpeg_bytes()

    response = client.post(
        "/api/photo/location",
        files={"photo": ("no-gps.jpg", photo, "image/jpeg")},
    )

    assert response.status_code == 200
    assert response.json() == {"has_location": False, "latitude": None, "longitude": None}


def test_routes_end_to_end_with_mocked_routing_provider(monkeypatch):
    monkeypatch.setattr(settings, "ors_api_key", "test-key")

    ors_response = {
        "features": [
            {
                "geometry": {"coordinates": [[126.978, 37.5665], [126.98, 37.57]]},
                "properties": {"summary": {"distance": 10000, "duration": 1800}},
            }
        ]
    }

    with respx.mock:
        respx.post(f"{settings.ors_base_url}/v2/directions/cycling-regular/geojson").mock(
            return_value=httpx.Response(200, json=ors_response)
        )

        response = client.post(
            "/api/routes",
            json={
                "latitude": 37.5665,
                "longitude": 126.9780,
                "distance_km": 10,
                "count": 4,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body["routes"]) == 4

    first_route = body["routes"][0]
    gpx_response = client.get(first_route["gpx_url"])
    assert gpx_response.status_code == 200
    assert b"<gpx" in gpx_response.content


def test_gpx_download_404_for_unknown_route():
    response = client.get("/api/routes/does-not-exist/gpx")
    assert response.status_code == 404
