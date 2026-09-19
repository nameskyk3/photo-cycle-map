import gpxpy

from app.gpx import build_gpx


def test_build_gpx_produces_parseable_track_with_all_points():
    coordinates = [(37.5665, 126.9780), (37.5700, 126.9800), (37.5665, 126.9780)]

    xml = build_gpx("test-route", coordinates)
    parsed = gpxpy.parse(xml)

    assert len(parsed.tracks) == 1
    points = parsed.tracks[0].segments[0].points
    assert [(p.latitude, p.longitude) for p in points] == coordinates
