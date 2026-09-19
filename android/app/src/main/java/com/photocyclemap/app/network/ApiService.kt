package com.photocyclemap.app.network

import okhttp3.MultipartBody
import okhttp3.ResponseBody
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part
import retrofit2.http.Path
import retrofit2.http.Streaming

interface ApiService {

    @Multipart
    @POST("api/photo/location")
    suspend fun getPhotoLocation(@Part photo: MultipartBody.Part): LocationResponse

    @POST("api/routes")
    suspend fun generateRoutes(@Body request: RouteRequest): RouteListResponse

    @Streaming
    @GET("api/routes/{routeId}/gpx")
    suspend fun downloadGpx(@Path("routeId") routeId: String): ResponseBody
}
