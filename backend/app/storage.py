"""In-memory store for generated routes, keyed by route id.

A real deployment would put this in Redis/a DB; for this app a single
process's memory is enough since routes are short-lived (generated, then
downloaded as GPX shortly after).
"""

from collections import OrderedDict

_MAX_ROUTES = 500

_routes: "OrderedDict[str, str]" = OrderedDict()  # route_id -> gpx xml


def save_gpx(route_id: str, gpx_xml: str) -> None:
    _routes[route_id] = gpx_xml
    while len(_routes) > _MAX_ROUTES:
        _routes.popitem(last=False)


def get_gpx(route_id: str) -> str | None:
    return _routes.get(route_id)
