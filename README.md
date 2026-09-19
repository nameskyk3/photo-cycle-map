# Photo Cycle Map

사진(안드로이드/PC)을 올리면 사진의 EXIF GPS 위치를 읽어 카카오맵에 표시하고, 자전거 경로 4개를
생성해 GPX 파일로 내려받을 수 있는 프로젝트입니다.

- **사진 1장**: 그 위치를 시작/도착점으로 하는, 원하는 거리(km)의 순환 경로 4개
- **사진 2장 이상**: 사진들의 위치를 순서대로(기본은 촬영 시각순, 직접 순서 조정 가능) 모두 지나는
  경로 4개. 원하는 거리(km)를 함께 입력하면 "최소 목표 거리"로 취급합니다 — 사진들을 잇는 실제
  경로가 이미 그보다 길면 입력값은 무시하고, 짧으면 마지막 사진 위치에서 부족한 만큼 순환 구간을
  추가해 채웁니다.

## 구성

```
photo-cycle-map/
├── backend/   # FastAPI 서버 (Android/Web 공통) - EXIF 추출, 경로 생성, GPX 제공
├── web/       # PC 브라우저용 정적 웹앱 (카카오맵 JS SDK)
└── android/   # 안드로이드 앱 (Kotlin + Jetpack Compose, 카카오맵 SDK for Android)
```

### 동작 흐름

1. 사진을 업로드한다 (여러 장 가능). 웹은 파일 선택창에서 여러 장 선택, 안드로이드는 갤러리에서 다중 선택.
2. 백엔드가 각 사진의 EXIF GPS 태그를 읽어 위도/경도(및 촬영 시각)를 반환한다. (GPS 정보가 없는 사진은 목록에는 남지만 경로 생성에서 제외)
3. 사진이 여러 장이면 기본적으로 촬영 시각순으로 정렬되고, 화면에서 순서를 직접 조정할 수 있다.
4. 각 위치를 카카오맵에 마커로 표시한다.
5. "경로 4개 생성"을 누르면 [OpenRouteService](https://openrouteservice.org/)를 이용해 경로를 만든다.
   - 사진 1장: 원하는 거리(km)만큼의 순환(라운드트립) 경로를 서로 다른 시드로 4번 요청.
   - 사진 2장 이상: 연속된 두 사진 사이 구간마다 대안 경로를 구해서, 경로마다 다른 대안을 조합해
     모든 사진 위치를 순서대로 지나는 전체 경로 4개를 만든다. 거리를 입력했고 그 경로가 입력값보다
     짧으면, 마지막 사진 위치에서 부족한 거리만큼 순환 구간을 추가로 붙인다.
   (카카오맵 자체에는 자전거 경로 자동 생성 API가 없어 별도 라우팅 엔진을 사용합니다.)
6. 각 경로를 지도에 다른 색 폴리라인으로 표시하고, GPX 파일로 내려받거나 다른 자전거 앱과 공유할 수 있다.

## 필요한 API 키

| 키 | 용도 | 발급처 |
|---|---|---|
| 카카오 JavaScript 키 | 웹앱 지도 표시 | [Kakao Developers](https://developers.kakao.com) > 내 애플리케이션 > 앱 키 |
| 카카오 네이티브 앱 키 | 안드로이드 앱 지도 표시 | 위와 동일 (플랫폼에 안드로이드 패키지명 + 키 해시 등록 필요) |
| OpenRouteService API 키 | 자전거 경로 생성 (백엔드에서만 사용, 무료) | [openrouteservice.org/dev](https://openrouteservice.org/dev/#/signup) |

카카오 디벨로퍼스 콘솔에서 웹은 "플랫폼 > Web"에 서빙 도메인을, 안드로이드는 "플랫폼 > Android"에
패키지명(`com.photocyclemap.app`)과 키 해시를 등록해야 지도가 정상적으로 뜹니다.

## 백엔드 실행

**Windows**: `backend\run.bat`을 더블클릭(또는 실행)하면 가상환경 생성 → 의존성 설치 → `.env` 생성(최초 1회, 메모장으로 자동으로 열어줌) →
서버 실행까지 한 번에 됩니다. 이후에는 그냥 다시 실행하면 서버만 뜹니다.

**macOS/Linux**: `./backend/run.sh` (최초 1회 `chmod +x backend/run.sh` 필요)

수동으로 하려면:

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

- `POST /api/photo/location` — multipart 필드 `photo`로 이미지 업로드 → `{has_location, latitude, longitude, taken_at}`
- `POST /api/routes` — `{waypoints: [{latitude, longitude}, ...], distance_km?, count}` → 경로 목록
  (각 경로에 좌표/거리/시간/GPX 다운로드 URL). `waypoints`가 1개면 `distance_km` 필수(순환 경로 거리).
  2개 이상이면 선택 사항이며 "최소 목표 거리"로 쓰입니다 (실제 경로가 더 길면 무시, 짧으면 순환
  구간을 추가해 채움).
- `GET /api/routes/{id}/gpx` — 생성된 경로의 GPX 파일 다운로드

## 웹앱 실행

**Windows**: `web\run.bat` 더블클릭 — 최초 1회 `config.js`를 만들어 메모장으로 열어주고, 이후 정적 서버(5500 포트)를 띄웁니다.

수동으로 하려면:

```bash
cp web/js/config.example.js web/js/config.js   # KAKAO_JS_KEY, API_BASE 채우기
cd web
python3 -m http.server 5500
```

브라우저에서 `http://localhost:5500` 접속. 백엔드가 다른 포트(8000)에서 실행 중이어야 합니다.

### 백엔드 + 웹 한 번에 켜기 (Windows)

저장소 루트의 `dev.bat`을 더블클릭하면 backend/web 서버가 각각 별도 콘솔 창으로 함께 실행됩니다.

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
