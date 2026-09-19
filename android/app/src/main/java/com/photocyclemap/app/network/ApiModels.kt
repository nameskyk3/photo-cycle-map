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

/** 업힐(오르막 선호) / 밸런스(오르막+평지 혼합) / 평지(오르막 회피). */
enum class ClimbPreference(val apiValue: String) {
    UPHILL("업힐"),
    BALANCE("밸런스"),
    FLAT("평지"),
}

data class RouteRequest(
    val waypoints: List<WaypointDto>,
    // 사진이 1장이면 필수(순환 경로 거리). 2장 이상이면 "최소 목표 거리"로 쓰이며 생략 가능하다.
    val distance_km: Double? = null,
    val count: Int = 4,
    val climb_preference: String = ClimbPreference.BALANCE.apiValue,
)

data class RouteDto(
    val id: String,
    val distance_m: Double,
    val duration_s: Double,
    val ascent_m: Double?,
    val descent_m: Double?,
    val coordinates: List<List<Double>>, // [lat, lng] pairs, in path order
    val gpx_url: String,
)

data class RouteListResponse(
    val routes: List<RouteDto>,
)
