import gpxpy
import gpxpy.gpx


def build_gpx(name: str, coordinates: list[tuple[float, float]]) -> str:
    """Build a GPX document (as XML text) from a list of (lat, lng) points."""
    gpx = gpxpy.gpx.GPX()

    track = gpxpy.gpx.GPXTrack(name=name)
    gpx.tracks.append(track)

    segment = gpxpy.gpx.GPXTrackSegment()
    track.segments.append(segment)

    for latitude, longitude in coordinates:
        segment.points.append(gpxpy.gpx.GPXTrackPoint(latitude, longitude))

    return gpx.to_xml()
