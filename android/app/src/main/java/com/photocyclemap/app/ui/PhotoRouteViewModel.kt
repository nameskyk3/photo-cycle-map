package com.photocyclemap.app.ui

import android.app.Application
import android.net.Uri
import androidx.core.content.FileProvider
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.photocyclemap.app.network.ApiClient
import com.photocyclemap.app.network.RouteDto
import com.photocyclemap.app.network.RouteRequest
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import java.io.File

data class LatLngState(val lat: Double, val lng: Double)

data class UiState(
    val isLoading: Boolean = false,
    val statusMessage: String = "",
    val isError: Boolean = false,
    val location: LatLngState? = null,
    val routes: List<RouteDto> = emptyList(),
)

class PhotoRouteViewModel(application: Application) : AndroidViewModel(application) {

    private val _uiState = MutableStateFlow(UiState())
    val uiState: StateFlow<UiState> = _uiState

    fun onPhotoSelected(uri: Uri) {
        viewModelScope.launch {
            _uiState.update {
                it.copy(
                    isLoading = true,
                    isError = false,
                    statusMessage = "사진에서 위치 정보를 확인하는 중...",
                    routes = emptyList(),
                )
            }

            try {
                val context = getApplication<Application>()
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
                    _uiState.update {
                        it.copy(
                            isLoading = false,
                            statusMessage = "위치를 찾았습니다: %.5f, %.5f".format(latitude, longitude),
                            location = LatLngState(latitude, longitude),
                        )
                    }
                } else {
                    _uiState.update {
                        it.copy(
                            isLoading = false,
                            isError = true,
                            statusMessage = "이 사진에는 위치 정보(GPS)가 없습니다. 다른 사진을 선택해주세요.",
                            location = null,
                        )
                    }
                }
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(isLoading = false, isError = true, statusMessage = e.message ?: "오류가 발생했습니다.")
                }
            }
        }
    }

    fun generateRoutes(distanceKm: Double) {
        val location = _uiState.value.location ?: return

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
                val response = ApiClient.service.generateRoutes(
                    RouteRequest(latitude = location.lat, longitude = location.lng, distance_km = distanceKm)
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
