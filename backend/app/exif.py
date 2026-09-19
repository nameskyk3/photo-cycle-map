import io
from datetime import datetime

from PIL import Image
from PIL.ExifTags import GPSTAGS

GPS_IFD_TAG = 0x8825
EXIF_IFD_TAG = 0x8769
DATE_TIME_ORIGINAL_TAG = 36867
DATE_TIME_TAG = 306


def _to_degrees(value: tuple[float, float, float]) -> float:
    degrees, minutes, seconds = value
    return float(degrees) + float(minutes) / 60.0 + float(seconds) / 3600.0


def extract_gps(image_bytes: bytes) -> tuple[float, float] | None:
    """Return (latitude, longitude) from a photo's EXIF GPS tags, or None if absent."""
    image = Image.open(io.BytesIO(image_bytes))
    exif = image.getexif()
    if not exif:
        return None

    gps_ifd = exif.get_ifd(GPS_IFD_TAG)
    if not gps_ifd:
        return None

    gps = {GPSTAGS.get(tag_id, tag_id): value for tag_id, value in gps_ifd.items()}

    lat = gps.get("GPSLatitude")
    lat_ref = gps.get("GPSLatitudeRef")
    lon = gps.get("GPSLongitude")
    lon_ref = gps.get("GPSLongitudeRef")
    if not lat or not lon or not lat_ref or not lon_ref:
        return None

    latitude = _to_degrees(lat)
    if lat_ref != "N":
        latitude = -latitude

    longitude = _to_degrees(lon)
    if lon_ref != "E":
        longitude = -longitude

    return latitude, longitude


def extract_taken_at(image_bytes: bytes) -> str | None:
    """Return the photo's EXIF capture time as an ISO 8601 string, or None if absent.

    Used to default-sort multiple uploaded photos into the order they were taken.
    """
    image = Image.open(io.BytesIO(image_bytes))
    exif = image.getexif()
    if not exif:
        return None

    raw_value = exif.get(DATE_TIME_TAG)

    exif_ifd = exif.get_ifd(EXIF_IFD_TAG)
    if exif_ifd and DATE_TIME_ORIGINAL_TAG in exif_ifd:
        raw_value = exif_ifd[DATE_TIME_ORIGINAL_TAG]

    if not raw_value:
        return None

    try:
        return datetime.strptime(raw_value, "%Y:%m:%d %H:%M:%S").isoformat()
    except ValueError:
        return None
