package com.photocyclemap.app.network

data class LocationResponse(
    val has_location: Boolean,
    val latitude: Double?,
    val longitude: Double?,
    val taken_at: String?,
)

data class WaypointDto(
    val latitude: Double,
    val longitude: Double,
)

data class RouteRequest(
    val waypoints: List<WaypointDto>,
    // 사진이 1장(순환 경로)일 때만 필요. 2장 이상이면 null로 보낸다.
    val distance_km: Double? = null,
    val count: Int = 4,
)

data class RouteDto(
    val id: String,
    val distance_m: Double,
    val duration_s: Double,
    val coordinates: List<List<Double>>, // [lat, lng] pairs, in path order
    val gpx_url: String,
)

data class RouteListResponse(
    val routes: List<RouteDto>,
)
