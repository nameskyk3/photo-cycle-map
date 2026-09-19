import io

import piexif
from PIL import Image


def _deg_to_dms_rational(value: float) -> list[tuple[int, int]]:
    value = abs(value)
    degrees = int(value)
    minutes_float = (value - degrees) * 60
    minutes = int(minutes_float)
    seconds = round((minutes_float - minutes) * 60 * 100)
    return [(degrees, 1), (minutes, 1), (seconds, 100)]


def make_jpeg_bytes(latitude: float | None = None, longitude: float | None = None) -> bytes:
    """Build an in-memory JPEG, optionally with GPS EXIF tags set."""
    image = Image.new("RGB", (8, 8), color="red")
    buffer = io.BytesIO()

    exif_bytes = b""
    if latitude is not None and longitude is not None:
        gps_ifd = {
            piexif.GPSIFD.GPSLatitudeRef: "N" if latitude >= 0 else "S",
            piexif.GPSIFD.GPSLatitude: _deg_to_dms_rational(latitude),
            piexif.GPSIFD.GPSLongitudeRef: "E" if longitude >= 0 else "W",
            piexif.GPSIFD.GPSLongitude: _deg_to_dms_rational(longitude),
        }
        exif_bytes = piexif.dump({"GPS": gps_ifd})

    if exif_bytes:
        image.save(buffer, format="jpeg", exif=exif_bytes)
    else:
        image.save(buffer, format="jpeg")

    return buffer.getvalue()
