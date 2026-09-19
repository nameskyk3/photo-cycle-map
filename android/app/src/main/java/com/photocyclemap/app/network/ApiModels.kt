package com.photocyclemap.app.network

data class LocationResponse(
    val has_location: Boolean,
    val latitude: Double?,
    val longitude: Double?,
)

data class RouteRequest(
    val latitude: Double,
    val longitude: Double,
    val distance_km: Double,
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
