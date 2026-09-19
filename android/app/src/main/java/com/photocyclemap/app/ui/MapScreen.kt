package com.photocyclemap.app.ui

import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import com.kakao.vectormap.KakaoMap
import com.kakao.vectormap.KakaoMapReadyCallback
import com.kakao.vectormap.LatLng
import com.kakao.vectormap.MapLifeCycleCallback
import com.kakao.vectormap.MapView
import com.kakao.vectormap.camera.CameraUpdateFactory
import com.kakao.vectormap.label.LabelOptions
import com.kakao.vectormap.route.RouteLineOptions
import com.kakao.vectormap.route.RouteLineSegment
import com.kakao.vectormap.route.RouteLineStyle
import com.kakao.vectormap.route.RouteLineStyles
import com.photocyclemap.app.network.RouteDto

// NOTE: 카카오맵 SDK for Android v2(com.kakao.vectormap)의 실제 API 시그니처는
// SDK 버전에 따라 조금씩 달라질 수 있습니다. 빌드 전에 최신 공식 문서와 대조해 확인하세요:
// https://apis.map.kakao.com/android_v2/
private val ROUTE_COLORS = listOf(0xFFE6194B.toInt(), 0xFF3CB44B.toInt(), 0xFF4363D8.toInt(), 0xFFF58231.toInt())

@Composable
fun MapScreen(
    modifier: Modifier = Modifier,
    location: LatLngState?,
    routes: List<RouteDto>,
) {
    var kakaoMap by remember { mutableStateOf<KakaoMap?>(null) }

    AndroidView(
        modifier = modifier.fillMaxSize(),
        factory = { context ->
            MapView(context).apply {
                start(
                    object : MapLifeCycleCallback() {
                        override fun onMapDestroy() {
                            kakaoMap = null
                        }

                        override fun onMapError(error: Exception) {
                            kakaoMap = null
                        }
                    },
                    object : KakaoMapReadyCallback() {
                        override fun onMapReady(map: KakaoMap) {
                            kakaoMap = map
                        }
                    },
                )
            }
        },
        update = {
            val map = kakaoMap ?: return@AndroidView
            renderOnMap(map, location, routes)
        },
    )
}

private fun renderOnMap(map: KakaoMap, location: LatLngState?, routes: List<RouteDto>) {
    map.labelManager?.layer?.removeAll()
    map.routeLineManager?.layer?.removeAll()

    if (location != null) {
        val position = LatLng.from(location.lat, location.lng)
        map.labelManager?.layer?.addLabel(LabelOptions.from(position))
        map.moveCamera(CameraUpdateFactory.newCenterPosition(position, 14))
    }

    routes.forEachIndexed { index, route ->
        val color = ROUTE_COLORS[index % ROUTE_COLORS.size]
        val points = route.coordinates.map { pair -> LatLng.from(pair[0], pair[1]) }
        if (points.size < 2) return@forEachIndexed

        val style = RouteLineStyles.from(RouteLineStyle.from(12f, color))
        val segment = RouteLineSegment.from(points, style)
        map.routeLineManager?.layer?.addRouteLine(RouteLineOptions.from(segment))
    }
}
