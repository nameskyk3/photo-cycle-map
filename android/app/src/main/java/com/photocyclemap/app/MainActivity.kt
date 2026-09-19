package com.photocyclemap.app

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.photocyclemap.app.network.RouteDto
import com.photocyclemap.app.ui.LatLngState
import com.photocyclemap.app.ui.MapScreen
import com.photocyclemap.app.ui.PhotoEntry
import com.photocyclemap.app.ui.PhotoRouteViewModel

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    PhotoCycleMapScreen()
                }
            }
        }
    }
}

@Composable
fun PhotoCycleMapScreen(viewModel: PhotoRouteViewModel = viewModel()) {
    val uiState by viewModel.uiState.collectAsState()
    var distanceKm by remember { mutableStateOf("10") }
    val context = LocalContext.current

    val pickPhotosLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.PickMultipleVisualMedia(),
    ) { uris -> viewModel.onPhotosSelected(uris) }

    val locatedCount = uiState.locatedPhotos.size

    Scaffold { padding: PaddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                text = "사진 위치 → 자전거 경로",
                style = MaterialTheme.typography.headlineSmall,
            )

            Button(onClick = {
                pickPhotosLauncher.launch(
                    PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)
                )
            }) {
                Text("1. 사진 선택 (여러 장 가능)")
            }

            if (uiState.photos.isNotEmpty()) {
                PhotoOrderList(photos = uiState.photos, viewModel = viewModel)
            }

            if (locatedCount > 0) {
                OutlinedTextField(
                    value = distanceKm,
                    onValueChange = { distanceKm = it },
                    label = { Text("2. 원하는 경로 거리 (km)") },
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            if (locatedCount > 1) {
                Text(
                    text = "사진 ${locatedCount}장의 위치를 순서대로 잇는 경로가 만들어집니다. " +
                        "그 경로가 입력한 거리보다 짧으면 부족한 만큼 순환 구간을 추가하고, " +
                        "이미 더 길면 입력한 거리는 무시합니다.",
                    style = MaterialTheme.typography.bodySmall,
                )
            }

            Button(
                onClick = { viewModel.generateRoutes(distanceKm.toDoubleOrNull()) },
                enabled = locatedCount > 0 && !uiState.isLoading,
            ) {
                Text("경로 4개 생성")
            }

            if (uiState.statusMessage.isNotBlank()) {
                Text(
                    text = uiState.statusMessage,
                    color = if (uiState.isError) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurface,
                )
            }

            MapScreen(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(320.dp),
                waypoints = uiState.locatedPhotos.map { LatLngState(it.lat!!, it.lng!!) },
                routes = uiState.routes,
            )

            LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(uiState.routes) { route ->
                    RouteCard(route = route) {
                        viewModel.downloadAndShareGpx(
                            route = route,
                            onReady = { uri -> shareGpx(context, uri) },
                            onError = { },
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun PhotoOrderList(photos: List<PhotoEntry>, viewModel: PhotoRouteViewModel) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        var order = 0
        photos.forEachIndexed { index, photo ->
            if (photo.hasLocation) order++
            Card(modifier = Modifier.fillMaxWidth()) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(8.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    val label = if (photo.hasLocation) "$order. ${photo.name}" else "${photo.name} (${photo.error})"
                    Text(text = label, style = MaterialTheme.typography.bodySmall)

                    Row {
                        TextButton(onClick = { viewModel.movePhoto(photo.id, -1) }, enabled = index > 0) {
                            Text("▲")
                        }
                        TextButton(onClick = { viewModel.movePhoto(photo.id, 1) }, enabled = index < photos.lastIndex) {
                            Text("▼")
                        }
                        TextButton(onClick = { viewModel.removePhoto(photo.id) }) {
                            Text("삭제")
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun RouteCard(route: RouteDto, onShareGpx: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            val km = route.distance_m / 1000.0
            val minutes = (route.duration_s / 60.0).toInt()
            Text(text = "%.1f km · 약 %d분".format(km, minutes))
            Button(onClick = onShareGpx) {
                Text("GPX 공유")
            }
        }
    }
}

private fun shareGpx(context: Context, uri: Uri) {
    val intent = Intent(Intent.ACTION_SEND).apply {
        type = "application/gpx+xml"
        putExtra(Intent.EXTRA_STREAM, uri)
        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }
    context.startActivity(Intent.createChooser(intent, "GPX 파일 공유"))
}
