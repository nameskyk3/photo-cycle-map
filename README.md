# Photo Cycle Map

사진(안드로이드/PC)을 올리면 사진의 EXIF GPS 위치를 읽어 카카오맵에 표시하고, 그 위치를 지나는
자전거 경로 4개(원하는 거리만큼)를 생성해 GPX 파일로 내려받을 수 있는 프로젝트입니다.

## 구성

```
photo-cycle-map/
├── backend/   # FastAPI 서버 (Android/Web 공통) - EXIF 추출, 경로 생성, GPX 제공
├── web/       # PC 브라우저용 정적 웹앱 (카카오맵 JS SDK)
└── android/   # 안드로이드 앱 (Kotlin + Jetpack Compose, 카카오맵 SDK for Android)
```

### 동작 흐름

1. 사진을 업로드한다 (웹: 파일 선택 / 안드로이드: 사진 선택).
2. 백엔드가 EXIF GPS 태그를 읽어 위도/경도를 반환한다. (GPS 정보가 없는 사진은 처리 불가)
3. 해당 위치를 카카오맵에 마커로 표시한다.
4. 사용자가 원하는 거리(예: 10km)를 입력하면, 백엔드가 [OpenRouteService](https://openrouteservice.org/)의
   자전거 라운드트립(순환 경로) API를 서로 다른 시드로 4번 호출해 서로 다른 경로 4개를 생성한다.
   (카카오맵 자체에는 자전거 경로 자동 생성 API가 없어 별도 라우팅 엔진을 사용합니다.)
5. 각 경로를 지도에 다른 색 폴리라인으로 표시하고, GPX 파일로 내려받거나 다른 자전거 앱과 공유할 수 있다.

## 필요한 API 키

| 키 | 용도 | 발급처 |
|---|---|---|
| 카카오 JavaScript 키 | 웹앱 지도 표시 | [Kakao Developers](https://developers.kakao.com) > 내 애플리케이션 > 앱 키 |
| 카카오 네이티브 앱 키 | 안드로이드 앱 지도 표시 | 위와 동일 (플랫폼에 안드로이드 패키지명 + 키 해시 등록 필요) |
| OpenRouteService API 키 | 자전거 경로 생성 (백엔드에서만 사용, 무료) | [openrouteservice.org/dev](https://openrouteservice.org/dev/#/signup) |

카카오 디벨로퍼스 콘솔에서 웹은 "플랫폼 > Web"에 서빙 도메인을, 안드로이드는 "플랫폼 > Android"에
패키지명(`com.photocyclemap.app`)과 키 해시를 등록해야 지도가 정상적으로 뜹니다.

## 백엔드 실행

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt   # 테스트까지 필요하면 -dev, 아니면 requirements.txt
cp .env.example .env    # ORS_API_KEY 값 채우기
.venv/bin/uvicorn app.main:app --reload --port 8000
```

테스트 실행 (EXIF 추출/GPX 생성/라우팅 호출을 모두 목(mock) 데이터로 검증합니다. 실제 카카오/ORS 키 없이도 통과합니다):

```bash
cd backend
.venv/bin/pytest -v
```

### API

- `POST /api/photo/location` — multipart 필드 `photo`로 이미지 업로드 → `{has_location, latitude, longitude}`
- `POST /api/routes` — `{latitude, longitude, distance_km, count}` → 경로 목록(각 경로에 좌표/거리/시간/GPX 다운로드 URL)
- `GET /api/routes/{id}/gpx` — 생성된 경로의 GPX 파일 다운로드

## 웹앱 실행

```bash
cp web/js/config.example.js web/js/config.js   # KAKAO_JS_KEY, API_BASE 채우기
cd web
python3 -m http.server 5500
```

브라우저에서 `http://localhost:5500` 접속. 백엔드가 다른 포트(8000)에서 실행 중이어야 합니다.

## 안드로이드 앱

`android/` 는 Gradle 프로젝트입니다. **이 개발 환경에는 Android SDK가 설치되어 있지 않아 실제 빌드/실행 검증은
하지 못했습니다.** Android Studio(또는 Android SDK가 설치된 환경)에서 아래 순서로 열어 확인해주세요.

```bash
cd android
cp local.properties.example local.properties   # KAKAO_NATIVE_APP_KEY, API_BASE_URL 채우기
```

Android Studio로 `android/` 폴더를 열면 SDK 경로가 `local.properties`에 자동으로 추가됩니다.
`com.kakao.maps.open:android` (카카오맵 SDK v2) API는 버전에 따라 세부 시그니처가 바뀔 수 있으니,
`app/src/main/java/com/photocyclemap/app/ui/MapScreen.kt`를 최신 [카카오맵 SDK 공식 문서](https://apis.map.kakao.com/android_v2/)와
대조해서 확인해주세요.

주요 파일:

- `MainActivity.kt` — 사진 선택, 거리 입력, 경로 생성 버튼, 경로 목록 UI (Compose)
- `ui/PhotoRouteViewModel.kt` — 사진 업로드/위치 조회/경로 생성/GPX 다운로드 로직
- `ui/MapScreen.kt` — 카카오맵에 마커 + 경로 폴리라인 표시
- `network/` — Retrofit 기반 백엔드 API 클라이언트

## 알려진 제한 사항

- 이 세션 환경에는 Android SDK가 없어 안드로이드 앱은 코드 리뷰 수준으로만 작성되었고 실제 컴파일/실행 검증을
  하지 못했습니다. 백엔드(pytest)와 웹 프론트(문법 검사)는 검증했습니다.
- 백엔드는 생성된 경로를 프로세스 메모리에만 보관합니다(재시작하면 사라짐). 운영 배포 시에는 Redis 등으로
  교체하는 것을 권장합니다.
- OpenRouteService 무료 티어는 호출 빈도 제한이 있습니다. 트래픽이 늘어나면 유료 플랜 또는 다른 라우팅
  엔진(OSRM 자체 호스팅 등)으로 교체를 고려하세요.
