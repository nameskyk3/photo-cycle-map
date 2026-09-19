package com.photocyclemap.app

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.compose.rememberLauncherForActivityResult
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
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.photocyclemap.app.network.RouteDto
import com.photocyclemap.app.ui.MapScreen
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

    val pickPhotoLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.PickVisualMedia(),
    ) { uri ->
        uri?.let(viewModel::onPhotoSelected)
    }

    val context = androidx.compose.ui.platform.LocalContext.current

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
                pickPhotoLauncher.launch(
                    androidx.activity.result.PickVisualMediaRequest(
                        ActivityResultContracts.PickVisualMedia.ImageOnly,
                    )
                )
            }) {
                Text("1. 사진 선택")
            }

            OutlinedTextField(
                value = distanceKm,
                onValueChange = { distanceKm = it },
                label = { Text("2. 원하는 경로 거리 (km)") },
                modifier = Modifier.fillMaxWidth(),
            )

            Button(
                onClick = { distanceKm.toDoubleOrNull()?.let(viewModel::generateRoutes) },
                enabled = uiState.location != null && !uiState.isLoading,
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
                location = uiState.location,
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

private fun shareGpx(context: android.content.Context, uri: android.net.Uri) {
    val intent = Intent(Intent.ACTION_SEND).apply {
        type = "application/gpx+xml"
        putExtra(Intent.EXTRA_STREAM, uri)
        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }
    context.startActivity(Intent.createChooser(intent, "GPX 파일 공유"))
}
