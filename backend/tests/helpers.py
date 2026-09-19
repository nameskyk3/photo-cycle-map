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


def make_jpeg_bytes(
    latitude: float | None = None,
    longitude: float | None = None,
    taken_at: str | None = None,
) -> bytes:
    """Build an in-memory JPEG, optionally with GPS/DateTimeOriginal EXIF tags set.

    `taken_at`, if given, must be in EXIF format: "YYYY:MM:DD HH:MM:SS".
    """
    image = Image.new("RGB", (8, 8), color="red")
    buffer = io.BytesIO()

    exif_dict: dict = {"GPS": {}, "Exif": {}}
    has_exif = False

    if latitude is not None and longitude is not None:
        exif_dict["GPS"] = {
            piexif.GPSIFD.GPSLatitudeRef: "N" if latitude >= 0 else "S",
            piexif.GPSIFD.GPSLatitude: _deg_to_dms_rational(latitude),
            piexif.GPSIFD.GPSLongitudeRef: "E" if longitude >= 0 else "W",
            piexif.GPSIFD.GPSLongitude: _deg_to_dms_rational(longitude),
        }
        has_exif = True

    if taken_at is not None:
        exif_dict["Exif"] = {piexif.ExifIFD.DateTimeOriginal: taken_at}
        has_exif = True

    exif_bytes = piexif.dump(exif_dict) if has_exif else b""

    if exif_bytes:
        image.save(buffer, format="jpeg", exif=exif_bytes)
    else:
        image.save(buffer, format="jpeg")

    return buffer.getvalue()
