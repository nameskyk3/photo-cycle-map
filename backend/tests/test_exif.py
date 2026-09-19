import pytest

from app.exif import extract_gps
from tests.helpers import make_jpeg_bytes


def test_extract_gps_returns_coordinates_for_northern_eastern_point():
    photo = make_jpeg_bytes(latitude=37.5665, longitude=126.9780)  # Seoul

    result = extract_gps(photo)

    assert result is not None
    latitude, longitude = result
    assert latitude == pytest.approx(37.5665, abs=1e-3)
    assert longitude == pytest.approx(126.9780, abs=1e-3)


def test_extract_gps_handles_southern_western_hemisphere():
    photo = make_jpeg_bytes(latitude=-33.8688, longitude=-70.6483)  # roughly Chile

    result = extract_gps(photo)

    assert result is not None
    latitude, longitude = result
    assert latitude == pytest.approx(-33.8688, abs=1e-3)
    assert longitude == pytest.approx(-70.6483, abs=1e-3)


def test_extract_gps_returns_none_without_gps_tags():
    photo = make_jpeg_bytes()

    assert extract_gps(photo) is None
