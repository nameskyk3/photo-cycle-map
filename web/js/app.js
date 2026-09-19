const state = {
  photos: [], // { id, name, lat, lng, hasLocation, takenAt, thumbUrl }
  map: null,
  overlays: [],
  polylines: [],
  draggingId: null,
};

const ROUTE_COLORS = ["#e6194b", "#3cb44b", "#4363d8", "#f58231"];

const statusEl = document.getElementById("status-message");
const generateBtn = document.getElementById("generate-btn");
const photoInput = document.getElementById("photo-input");
const distanceField = document.getElementById("distance-field");
const distanceInput = document.getElementById("distance-input");
const multiPhotoNote = document.getElementById("multi-photo-note");
const photoListEl = document.getElementById("photo-list");
const routeListEl = document.getElementById("route-list");

let nextId = 1;

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

function locatedPhotos() {
  return state.photos.filter((p) => p.hasLocation);
}

function clearMapOverlays() {
  state.overlays.forEach((overlay) => overlay.setMap(null));
  state.overlays = [];
}

function clearRoutes() {
  state.polylines.forEach((line) => line.setMap(null));
  state.polylines = [];
  routeListEl.innerHTML = "";
}

function updateMapMarkers() {
  clearMapOverlays();

  const located = locatedPhotos();
  located.forEach((photo, index) => {
    const position = new kakao.maps.LatLng(photo.lat, photo.lng);
    const content = document.createElement("div");
    content.className = "waypoint-badge";
    content.textContent = String(index + 1);

    const overlay = new kakao.maps.CustomOverlay({
      position,
      content,
      yAnchor: 0.5,
      xAnchor: 0.5,
    });
    overlay.setMap(state.map);
    state.overlays.push(overlay);
  });

  if (located.length > 0) {
    const last = located[located.length - 1];
    state.map.setCenter(new kakao.maps.LatLng(last.lat, last.lng));
    state.map.setLevel(located.length > 1 ? 8 : 6);
  }
}

function updateControlsVisibility() {
  const count = locatedPhotos().length;
  // 사진이 없을 때만 비활성화한다. 1장이면 순환 경로 거리로, 여러 장이면
  // "최소 목표 거리"(부족하면 채우고, 이미 더 길면 무시)로 쓰인다.
  distanceInput.disabled = count === 0;
  distanceField.classList.toggle("field--disabled", count === 0);
  multiPhotoNote.hidden = count <= 1;
  generateBtn.disabled = count === 0;
}

async function uploadPhotoAndGetLocation(file) {
  const formData = new FormData();
  formData.append("photo", file);

  const response = await fetch(`${window.APP_CONFIG.API_BASE}/api/photo/location`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) throw new Error(`${file.name}: 서버 오류가 발생했습니다.`);
  return response.json();
}

async function handlePhotoInputChange() {
  const files = Array.from(photoInput.files);
  if (files.length === 0) return;

  photoInput.value = ""; // allow re-selecting the same file later
  clearRoutes();
  setStatus(`사진 ${files.length}장에서 위치 정보를 확인하는 중...`);
  generateBtn.disabled = true;

  const newEntries = [];
  for (const file of files) {
    try {
      const data = await uploadPhotoAndGetLocation(file);
      newEntries.push({
        id: nextId++,
        name: file.name,
        lat: data.latitude,
        lng: data.longitude,
        hasLocation: data.has_location,
        takenAt: data.taken_at,
        thumbUrl: URL.createObjectURL(file),
      });
    } catch (error) {
      newEntries.push({
        id: nextId++,
        name: file.name,
        hasLocation: false,
        takenAt: null,
        thumbUrl: URL.createObjectURL(file),
        error: error.message,
      });
    }
  }

  // Sort just the newly added batch by capture time (undated photos last),
  // then append after whatever the user already has (so a manual reorder
  // of earlier photos isn't disturbed by adding more later).
  newEntries.sort((a, b) => {
    if (a.takenAt && b.takenAt) return a.takenAt.localeCompare(b.takenAt);
    if (a.takenAt) return -1;
    if (b.takenAt) return 1;
    return 0;
  });

  state.photos.push(...newEntries);

  const withoutLocation = newEntries.filter((p) => !p.hasLocation).length;
  if (withoutLocation > 0) {
    setStatus(
      `${newEntries.length}장 중 ${withoutLocation}장은 위치 정보(GPS)가 없어 경로 생성에서 제외됩니다.`,
      withoutLocation === newEntries.length,
    );
  } else {
    setStatus(`사진 ${newEntries.length}장의 위치를 확인했습니다.`);
  }

  renderPhotoList();
  updateMapMarkers();
  updateControlsVisibility();
}

function removePhoto(id) {
  state.photos = state.photos.filter((p) => p.id !== id);
  clearRoutes();
  renderPhotoList();
  updateMapMarkers();
  updateControlsVisibility();
}

function reorderPhotos(draggedId, targetId) {
  if (draggedId === targetId) return;
  const fromIndex = state.photos.findIndex((p) => p.id === draggedId);
  const toIndex = state.photos.findIndex((p) => p.id === targetId);
  if (fromIndex === -1 || toIndex === -1) return;

  const [moved] = state.photos.splice(fromIndex, 1);
  state.photos.splice(toIndex, 0, moved);

  clearRoutes();
  renderPhotoList();
  updateMapMarkers();
}

function renderPhotoList() {
  photoListEl.innerHTML = "";
  let order = 0;

  state.photos.forEach((photo) => {
    if (photo.hasLocation) order += 1;

    const card = document.createElement("div");
    card.className = "photo-card" + (photo.hasLocation ? "" : " photo-card--no-location");
    card.draggable = true;
    card.dataset.id = String(photo.id);

    card.addEventListener("dragstart", (e) => {
      state.draggingId = photo.id;
      e.dataTransfer.effectAllowed = "move";
    });
    card.addEventListener("dragover", (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
    });
    card.addEventListener("drop", (e) => {
      e.preventDefault();
      if (state.draggingId !== null) reorderPhotos(state.draggingId, photo.id);
      state.draggingId = null;
    });

    const handle = document.createElement("span");
    handle.className = "drag-handle";
    handle.textContent = "⠿";

    const thumb = document.createElement("img");
    thumb.className = "thumb";
    thumb.src = photo.thumbUrl;
    thumb.alt = photo.name;

    const info = document.createElement("div");
    info.className = "photo-info";
    if (photo.hasLocation) {
      info.innerHTML = `<strong>${order}. ${photo.name}</strong><span>${photo.lat.toFixed(5)}, ${photo.lng.toFixed(5)}</span>`;
    } else {
      info.innerHTML = `<strong>${photo.name}</strong><span class="error">${photo.error || "위치 정보(GPS) 없음 — 경로에서 제외됨"}</span>`;
    }

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "remove-btn";
    removeBtn.textContent = "삭제";
    removeBtn.addEventListener("click", () => removePhoto(photo.id));

    card.append(handle, thumb, info, removeBtn);
    photoListEl.appendChild(card);
  });
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

async function handleGenerateRoutes() {
  const located = locatedPhotos();
  if (located.length === 0) return;

  const waypoints = located.map((p) => ({ latitude: p.lat, longitude: p.lng }));
  const isSingle = located.length === 1;

  const distanceKm = Number(distanceInput.value);
  if (isSingle && (!distanceKm || distanceKm <= 0)) {
    setStatus("올바른 거리를 입력해주세요.", true);
    return;
  }

  clearRoutes();
  setStatus("자전거 경로 4개를 생성하는 중... (몇 초 걸릴 수 있어요)");
  generateBtn.disabled = true;

  try {
    const body = { waypoints, count: 4 };
    // 여러 장일 때는 거리를 "최소 목표"로만 보낸다 - 비워두거나 0이면 순수 최단 경로만 생성.
    if (distanceKm > 0) body.distance_km = distanceKm;

    const response = await fetch(`${window.APP_CONFIG.API_BASE}/api/routes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
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

  updateControlsVisibility();
  photoInput.addEventListener("change", handlePhotoInputChange);
  generateBtn.addEventListener("click", handleGenerateRoutes);
}

main();
