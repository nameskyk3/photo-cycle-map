const state = {
  location: null, // { lat, lng }
  map: null,
  marker: null,
  polylines: [],
};

const ROUTE_COLORS = ["#e6194b", "#3cb44b", "#4363d8", "#f58231"];

const statusEl = document.getElementById("status-message");
const generateBtn = document.getElementById("generate-btn");
const photoInput = document.getElementById("photo-input");
const distanceInput = document.getElementById("distance-input");
const routeListEl = document.getElementById("route-list");

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.classList.toggle("error", isError);
}

function loadKakaoSdk() {
  return new Promise((resolve, reject) => {
    if (!window.APP_CONFIG || !window.APP_CONFIG.KAKAO_JS_KEY) {
      reject(new Error("config.js에 KAKAO_JS_KEY를 설정해주세요."));
      return;
    }
    const script = document.createElement("script");
    script.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${window.APP_CONFIG.KAKAO_JS_KEY}&autoload=false&libraries=services`;
    script.onload = () => window.kakao.maps.load(resolve);
    script.onerror = () => reject(new Error("카카오맵 SDK를 불러오지 못했습니다."));
    document.head.appendChild(script);
  });
}

function initMap() {
  const container = document.getElementById("map");
  state.map = new kakao.maps.Map(container, {
    center: new kakao.maps.LatLng(37.5665, 126.978),
    level: 6,
  });
}

function showLocation(lat, lng) {
  const position = new kakao.maps.LatLng(lat, lng);
  if (state.marker) {
    state.marker.setMap(null);
  }
  state.marker = new kakao.maps.Marker({ position, map: state.map });
  state.map.setCenter(position);
  state.map.setLevel(6);
}

function clearRoutes() {
  state.polylines.forEach((line) => line.setMap(null));
  state.polylines = [];
  routeListEl.innerHTML = "";
}

function drawRoute(route, color) {
  const path = route.coordinates.map(([lat, lng]) => new kakao.maps.LatLng(lat, lng));
  const polyline = new kakao.maps.Polyline({
    path,
    strokeWeight: 5,
    strokeColor: color,
    strokeOpacity: 0.8,
    strokeStyle: "solid",
  });
  polyline.setMap(state.map);
  state.polylines.push(polyline);
}

function renderRouteCard(route, index, color) {
  const card = document.createElement("div");
  card.className = "route-card";

  const km = (route.distance_m / 1000).toFixed(1);
  const minutes = Math.round(route.duration_s / 60);

  const swatch = document.createElement("span");
  swatch.className = "swatch";
  swatch.style.background = color;

  const info = document.createElement("div");
  info.className = "route-info";
  info.innerHTML = `<strong>경로 ${index + 1}</strong><span>${km} km · 약 ${minutes}분</span>`;

  const link = document.createElement("a");
  link.href = `${window.APP_CONFIG.API_BASE}${route.gpx_url}`;
  link.textContent = "GPX 다운로드";
  link.setAttribute("download", "");

  card.append(swatch, info, link);
  routeListEl.appendChild(card);
}

async function handlePhotoChange() {
  const file = photoInput.files[0];
  if (!file) return;

  generateBtn.disabled = true;
  clearRoutes();
  setStatus("사진에서 위치 정보를 확인하는 중...");

  const formData = new FormData();
  formData.append("photo", file);

  try {
    const response = await fetch(`${window.APP_CONFIG.API_BASE}/api/photo/location`, {
      method: "POST",
      body: formData,
    });
    if (!response.ok) throw new Error("서버 오류가 발생했습니다.");
    const data = await response.json();

    if (!data.has_location) {
      state.location = null;
      setStatus("이 사진에는 위치 정보(GPS)가 없습니다. 다른 사진을 선택해주세요.", true);
      return;
    }

    state.location = { lat: data.latitude, lng: data.longitude };
    showLocation(data.latitude, data.longitude);
    setStatus(`위치를 찾았습니다: ${data.latitude.toFixed(5)}, ${data.longitude.toFixed(5)}`);
    generateBtn.disabled = false;
  } catch (error) {
    setStatus(error.message, true);
  }
}

async function handleGenerateRoutes() {
  if (!state.location) return;

  const distanceKm = Number(distanceInput.value);
  if (!distanceKm || distanceKm <= 0) {
    setStatus("올바른 거리를 입력해주세요.", true);
    return;
  }

  clearRoutes();
  setStatus("자전거 경로 4개를 생성하는 중... (몇 초 걸릴 수 있어요)");
  generateBtn.disabled = true;

  try {
    const response = await fetch(`${window.APP_CONFIG.API_BASE}/api/routes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        latitude: state.location.lat,
        longitude: state.location.lng,
        distance_km: distanceKm,
        count: 4,
      }),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || "경로 생성에 실패했습니다.");
    }

    const data = await response.json();
    data.routes.forEach((route, index) => {
      const color = ROUTE_COLORS[index % ROUTE_COLORS.length];
      drawRoute(route, color);
      renderRouteCard(route, index, color);
    });
    setStatus(`경로 ${data.routes.length}개를 생성했습니다.`);
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    generateBtn.disabled = false;
  }
}

async function main() {
  try {
    await loadKakaoSdk();
    initMap();
  } catch (error) {
    setStatus(error.message, true);
    return;
  }

  photoInput.addEventListener("change", handlePhotoChange);
  generateBtn.addEventListener("click", handleGenerateRoutes);
}

main();
