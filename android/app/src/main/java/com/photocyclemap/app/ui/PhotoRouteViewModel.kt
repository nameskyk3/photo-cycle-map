package com.photocyclemap.app.ui

import android.app.Application
import android.net.Uri
import androidx.core.content.FileProvider
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.photocyclemap.app.network.ApiClient
import com.photocyclemap.app.network.RouteDto
import com.photocyclemap.app.network.RouteRequest
import com.photocyclemap.app.network.WaypointDto
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import java.io.File
import java.util.concurrent.atomic.AtomicLong

data class LatLngState(val lat: Double, val lng: Double)

data class PhotoEntry(
    val id: Long,
    val uri: Uri,
    val name: String,
    val hasLocation: Boolean,
    val lat: Double? = null,
    val lng: Double? = null,
    val takenAt: String? = null,
    val error: String? = null,
)

data class UiState(
    val isLoading: Boolean = false,
    val statusMessage: String = "",
    val isError: Boolean = false,
    val photos: List<PhotoEntry> = emptyList(),
    val routes: List<RouteDto> = emptyList(),
) {
    val locatedPhotos: List<PhotoEntry>
        get() = photos.filter { it.hasLocation && it.lat != null && it.lng != null }
}

class PhotoRouteViewModel(application: Application) : AndroidViewModel(application) {

    private val _uiState = MutableStateFlow(UiState())
    val uiState: StateFlow<UiState> = _uiState

    private val nextId = AtomicLong(1)

    /** 사진 여러 장(1장도 가능)을 업로드해서 각각의 위치를 확인하고 목록 끝에 추가한다. */
    fun onPhotosSelected(uris: List<Uri>) {
        if (uris.isEmpty()) return

        viewModelScope.launch {
            _uiState.update {
                it.copy(
                    isLoading = true,
                    isError = false,
                    statusMessage = "사진 ${uris.size}장에서 위치 정보를 확인하는 중...",
                    routes = emptyList(),
                )
            }

            val newEntries = uris.map { uri -> uploadAndDescribe(uri) }

            // 새로 추가된 사진들만 촬영 시간 기준으로 정렬한 뒤, 기존 목록 뒤에 이어붙인다
            // (이미 순서를 직접 조정해둔 사진들은 건드리지 않는다).
            val sortedNew = newEntries.sortedWith(compareBy(nullsLast()) { it.takenAt })

            val withoutLocation = sortedNew.count { !it.hasLocation }
            val message = if (withoutLocation > 0) {
                "${sortedNew.size}장 중 ${withoutLocation}장은 위치 정보(GPS)가 없어 경로 생성에서 제외됩니다."
            } else {
                "사진 ${sortedNew.size}장의 위치를 확인했습니다."
            }

            _uiState.update {
                it.copy(
                    isLoading = false,
                    isError = withoutLocation == sortedNew.size,
                    statusMessage = message,
                    photos = it.photos + sortedNew,
                )
            }
        }
    }

    private suspend fun uploadAndDescribe(uri: Uri): PhotoEntry {
        val id = nextId.getAndIncrement()
        val context = getApplication<Application>()
        val name = uri.lastPathSegment ?: "photo_$id.jpg"

        return try {
            val tempFile = File.createTempFile("upload", ".jpg", context.cacheDir)
            context.contentResolver.openInputStream(uri)?.use { input ->
                tempFile.outputStream().use { output -> input.copyTo(output) }
            }

            val requestBody = tempFile.asRequestBody("image/*".toMediaTypeOrNull())
            val part = MultipartBody.Part.createFormData("photo", tempFile.name, requestBody)
            val response = ApiClient.service.getPhotoLocation(part)
            tempFile.delete()

            val latitude = response.latitude
            val longitude = response.longitude
            if (response.has_location && latitude != null && longitude != null) {
                PhotoEntry(
                    id = id,
                    uri = uri,
                    name = name,
                    hasLocation = true,
                    lat = latitude,
                    lng = longitude,
                    takenAt = response.taken_at,
                )
            } else {
                PhotoEntry(
                    id = id,
                    uri = uri,
                    name = name,
                    hasLocation = false,
                    error = "위치 정보(GPS) 없음",
                )
            }
        } catch (e: Exception) {
            PhotoEntry(
                id = id,
                uri = uri,
                name = name,
                hasLocation = false,
                error = e.message ?: "업로드 실패",
            )
        }
    }

    fun removePhoto(id: Long) {
        _uiState.update { it.copy(photos = it.photos.filterNot { p -> p.id == id }, routes = emptyList()) }
    }

    fun movePhoto(id: Long, offset: Int) {
        _uiState.update { state ->
            val photos = state.photos.toMutableList()
            val index = photos.indexOfFirst { it.id == id }
            val target = index + offset
            if (index == -1 || target !in photos.indices) return@update state
            val item = photos.removeAt(index)
            photos.add(target, item)
            state.copy(photos = photos, routes = emptyList())
        }
    }

    fun generateRoutes(distanceKm: Double?) {
        val located = _uiState.value.locatedPhotos
        if (located.isEmpty()) return
        if (located.size == 1 && distanceKm == null) {
            _uiState.update { it.copy(isError = true, statusMessage = "원하는 경로 거리를 입력해주세요.") }
            return
        }

        viewModelScope.launch {
            _uiState.update {
                it.copy(
                    isLoading = true,
                    isError = false,
                    statusMessage = "자전거 경로 4개를 생성하는 중... (몇 초 걸릴 수 있어요)",
                    routes = emptyList(),
                )
            }

            try {
                val waypoints = located.map { WaypointDto(latitude = it.lat!!, longitude = it.lng!!) }
                val response = ApiClient.service.generateRoutes(
                    RouteRequest(
                        waypoints = waypoints,
                        distance_km = if (located.size == 1) distanceKm else null,
                    )
                )
                _uiState.update {
                    it.copy(
                        isLoading = false,
                        statusMessage = "경로 ${response.routes.size}개를 생성했습니다.",
                        routes = response.routes,
                    )
                }
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(isLoading = false, isError = true, statusMessage = e.message ?: "경로 생성에 실패했습니다.")
                }
            }
        }
    }

    /** GPX를 캐시 디렉터리에 내려받고, 다른 앱(예: 자전거 앱)과 공유할 수 있는 content:// Uri를 돌려준다. */
    fun downloadAndShareGpx(route: RouteDto, onReady: (Uri) -> Unit, onError: (String) -> Unit) {
        viewModelScope.launch {
            try {
                val body = ApiClient.service.downloadGpx(route.id)
                val context = getApplication<Application>()
                val gpxDir = File(context.cacheDir, "gpx").apply { mkdirs() }
                val file = File(gpxDir, "${route.id}.gpx")
                body.byteStream().use { input ->
                    file.outputStream().use { output -> input.copyTo(output) }
                }
                val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
                onReady(uri)
            } catch (e: Exception) {
                onError(e.message ?: "GPX 다운로드에 실패했습니다.")
            }
        }
    }
}
