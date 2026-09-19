import gpxpy
import gpxpy.gpx


def build_gpx(
    name: str,
    coordinates: list[tuple[float, float]],
    elevations: list[float | None] | None = None,
) -> str:
    """Build a GPX document (as XML text) from a list of (lat, lng) points,
    optionally with per-point elevation (meters) for a proper climb profile."""
    gpx = gpxpy.gpx.GPX()

    track = gpxpy.gpx.GPXTrack(name=name)
    gpx.tracks.append(track)

    segment = gpxpy.gpx.GPXTrackSegment()
    track.segments.append(segment)

    for index, (latitude, longitude) in enumerate(coordinates):
        elevation = elevations[index] if elevations and index < len(elevations) else None
        segment.points.append(gpxpy.gpx.GPXTrackPoint(latitude, longitude, elevation=elevation))

    return gpx.to_xml()
