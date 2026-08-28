const els = {
  mapboxToken: document.querySelector("#mapboxToken"),
  apiEndpoint: document.querySelector("#apiEndpoint"),
  fileTabs: [document.querySelector("#fileTab"), document.querySelector("#floatingFileTab")],
  urlTabs: [document.querySelector("#urlTab"), document.querySelector("#floatingUrlTab")],
  filePanels: [document.querySelector("#filePanel"), document.querySelector("#floatingFilePanel")],
  urlPanels: [document.querySelector("#urlPanel"), document.querySelector("#floatingUrlPanel")],
  imageFiles: [document.querySelector("#imageFile"), document.querySelector("#floatingImageFile")],
  imageUrls: [document.querySelector("#imageUrl"), document.querySelector("#floatingImageUrl")],
  fileLabels: [document.querySelector("#sideFileName"), document.querySelector("#floatingFileName")],
  previews: [
    {
      img: document.querySelector("#preview"),
      wrap: document.querySelector(".control-panel .preview-wrap"),
    },
    {
      img: document.querySelector("#floatingPreview"),
      wrap: document.querySelector(".floating-panel .preview-wrap"),
    },
  ],
  analyzeButtons: [document.querySelector("#analyzeButton"), document.querySelector("#floatingAnalyzeButton")],
  clearButtons: [document.querySelector("#clearButton"), document.querySelector("#floatingClearButton")],
  previousResultsSelect: document.querySelector("#previousResultsSelect"),
  refreshResultsButton: document.querySelector("#refreshResultsButton"),
  loadResultButton: document.querySelector("#loadResultButton"),
  finalResult: document.querySelector("#finalResult"),
  detailsToggle: document.querySelector("#detailsToggle"),
  resultBox: document.querySelector("#resultBox"),
  floatingResult: document.querySelector("#floatingResult"),
  mapStatus: document.querySelector("#mapStatus"),
  floatingMapStatus: document.querySelector("#floatingMapStatus"),
};

let map;
let marker;
let activeSource = "file";
let selectedFile = null;
let selectedImageUrl = "";
let detailsExpanded = false;
const appVersion = "20260828-history-loader";
const defaultGeolocationApiEndpoint = "http://localhost:8000/geolocate";
const maxImageBytes = 10 * 1024 * 1024;
const allowedImageExtensions = new Set(["png", "jpg", "jpeg", "webp"]);
const allowedImageTypes = new Set(["image/png", "image/jpeg", "image/webp"]);
const initialView = {
  center: [30, 15],
  zoom: 2,
  pitch: 20,
  bearing: 0,
};

els.mapboxToken.value = localStorage.getItem("mapboxToken") || "";
const savedEndpoint = localStorage.getItem("geolocationApiEndpoint") || "";
const endpointToUse = savedEndpoint.includes("/extract-clues") ? defaultGeolocationApiEndpoint : savedEndpoint || defaultGeolocationApiEndpoint;
els.apiEndpoint.value = endpointToUse;
localStorage.setItem("geolocationApiEndpoint", endpointToUse);

function formatResult(value) {
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function finalPayload(value) {
  return value?.final || value;
}

function finalLocation(value) {
  const final = finalPayload(value);
  return final?.location || value?.location || null;
}

function formatFinalResult(value) {
  if (typeof value === "string") {
    return escapeHtml(value);
  }

  const final = finalPayload(value);
  const location = finalLocation(value);
  if (!final || (!location && !final.reasoning)) {
    return "Result received, but no final geolocation payload was returned.";
  }

  if (!location) {
    return `
      <p class="final-result-title">Final Geolocation</p>
      <div class="final-result-grid">
        <div><span>Status:</span> Manual review needed</div>
        <div><span>Confidence:</span> ${escapeHtml(final.confidence ?? value?.confidence ?? 0)}</div>
      </div>
      <div class="final-result-reasoning">${escapeHtml(final.reasoning || "No defensible coordinates returned.")}</div>
    `;
  }

  const latitude = Number(location.latitude ?? location.lat);
  const longitude = Number(location.longitude ?? location.lng ?? location.lon);
  const label = location.name || location.city || location.region || location.country || "Predicted location";
  const confidence = final.confidence ?? value?.confidence ?? null;
  const review = final.needs_manual_review ? "Manual review needed" : "Ready";

  return `
    <p class="final-result-title">${escapeHtml(label)}</p>
    <div class="final-result-grid">
      <div><span>Latitude:</span> ${Number.isFinite(latitude) ? latitude.toFixed(6) : "Unavailable"}</div>
      <div><span>Longitude:</span> ${Number.isFinite(longitude) ? longitude.toFixed(6) : "Unavailable"}</div>
      <div><span>Confidence:</span> ${confidence == null ? "Unavailable" : escapeHtml(confidence)}</div>
      <div><span>Status:</span> ${escapeHtml(review)}</div>
      <div><span>Region:</span> ${escapeHtml([location.city, location.region, location.country].filter(Boolean).join(", ") || "Unavailable")}</div>
    </div>
    <div class="final-result-reasoning">${escapeHtml(final.reasoning || "No reasoning returned.")}</div>
  `;
}

function formatApiErrorDetail(detail) {
  if (!detail) {
    return "";
  }

  if (typeof detail === "string") {
    return detail;
  }

  return JSON.stringify(detail, null, 2);
}

function buildRequestError(response, data) {
  const detail = formatApiErrorDetail(data?.detail);
  const message = data?.message || data?.error || detail || response.statusText || "Unknown API error";
  return `Request failed with ${response.status}\n\n${message}`;
}

function backendBaseUrl() {
  try {
    return new URL(els.apiEndpoint.value.trim() || defaultGeolocationApiEndpoint).origin;
  } catch {
    return new URL(defaultGeolocationApiEndpoint).origin;
  }
}

function formatRunTimestamp(runId) {
  const match = String(runId || "").match(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z_/);
  if (!match) {
    return runId || "Unknown run";
  }

  const [, year, month, day, hour, minute, second] = match;
  return `${year}-${month}-${day} ${hour}:${minute}:${second} UTC`;
}

function resultOptionLabel(item) {
  const location = item.location;
  const name = location?.name || location?.city || location?.region || location?.country || "No location";
  const confidence = item.confidence == null ? "n/a" : item.confidence;
  return `${formatRunTimestamp(item.run_id)} - ${name} - ${confidence}`;
}

function formatFloatingResult(value) {
  if (typeof value === "string") {
    return value.split("\n").find(Boolean) || "Ready.";
  }

  const final = finalPayload(value);
  const finalLoc = finalLocation(value);
  if (finalLoc) {
    const label = finalLoc.name || finalLoc.city || finalLoc.region || finalLoc.country || "Predicted location";
    const latitude = Number(finalLoc.latitude ?? finalLoc.lat);
    const longitude = Number(finalLoc.longitude ?? finalLoc.lng ?? finalLoc.lon);
    if (Number.isFinite(latitude) && Number.isFinite(longitude)) {
      return `${label}: ${latitude.toFixed(5)}, ${longitude.toFixed(5)}`;
    }
  }

  if (final?.reasoning) {
    return final.needs_manual_review ? "Manual review needed." : "Final result received.";
  }

  const clueResult = value?.clues?.clues || value?.clues;
  if (clueResult?.search_queries || clueResult?.visible_text) {
    const textCount = clueResult.visible_text?.length || 0;
    const queryCount = clueResult.search_queries?.length || 0;
    return `Clues extracted: ${textCount} text items, ${queryCount} search queries.`;
  }

  const location = value?.location || value?.coordinates || value;
  const label = location?.city || location?.address || value?.reasoning || "Result received.";
  const latitude = Number(location?.latitude ?? location?.lat);
  const longitude = Number(location?.longitude ?? location?.lng ?? location?.lon);

  if (Number.isFinite(latitude) && Number.isFinite(longitude)) {
    return `${label}: ${latitude.toFixed(5)}, ${longitude.toFixed(5)}`;
  }

  return "Result received.";
}

function setResult(value) {
  detailsExpanded = false;
  els.finalResult.innerHTML = formatFinalResult(value);
  els.resultBox.textContent = formatResult(value);
  els.resultBox.hidden = true;
  els.detailsToggle.hidden = typeof value === "string";
  els.detailsToggle.textContent = "More details";
  els.floatingResult.textContent = formatFloatingResult(value);
}

function setMapStatus(value) {
  els.mapStatus.textContent = value;
  els.floatingMapStatus.textContent = value;
}

function getFileExtension(path) {
  return String(path || "").split(".").pop()?.toLowerCase() || "";
}

// Image input validation: keeps uploaded files within supported formats and size.
function validateImageFile(file) {
  if (!file) {
    throw new Error("Choose an image file first.");
  }

  const extension = getFileExtension(file.name);
  if (!allowedImageExtensions.has(extension)) {
    throw new Error("File must be a PNG, JPG, JPEG, or WebP image.");
  }

  if (file.type && !allowedImageTypes.has(file.type)) {
    throw new Error("File type must be PNG, JPG, JPEG, or WebP.");
  }

  if (file.size > maxImageBytes) {
    throw new Error("Image file must be 10 MB or smaller.");
  }
}

// Image URL validation: accepts remote images without allowing unsupported URL paths.
function validateImageUrl(value) {
  if (!value) {
    throw new Error("Enter an image URL first.");
  }

  let url;
  try {
    url = new URL(value);
  } catch {
    throw new Error("Enter a valid image URL.");
  }

  if (!["http:", "https:"].includes(url.protocol)) {
    throw new Error("Image URL must start with http:// or https://.");
  }

  const extension = getFileExtension(url.pathname);
  if (!allowedImageExtensions.has(extension)) {
    throw new Error("Image URL path must end in .png, .jpg, .jpeg, or .webp.");
  }

  return url.toString();
}

// UI sync: keeps side-panel controls and floating controls on one shared state.
function setButtonsDisabled(disabled) {
  els.analyzeButtons.forEach((button) => {
    button.disabled = disabled;
  });
}

function setFileLabels(label) {
  els.fileLabels.forEach((fileLabel) => {
    fileLabel.textContent = label;
  });
}

function clearPreviews() {
  els.previews.forEach(({ img, wrap }) => {
    img.removeAttribute("src");
    wrap.classList.remove("has-image");
  });
}

function showFilePreviews(file) {
  els.previews.forEach(({ img, wrap }) => {
    const url = URL.createObjectURL(file);
    img.src = url;
    img.onload = () => URL.revokeObjectURL(url);
    wrap.classList.add("has-image");
  });
}

function showUrlPreviews(url) {
  els.previews.forEach(({ img, wrap }) => {
    img.src = url;
    wrap.classList.add("has-image");
  });
}

function syncUrlInputs(value, sourceInput) {
  selectedImageUrl = value;
  els.imageUrls.forEach((input) => {
    if (input !== sourceInput) {
      input.value = value;
    }
  });
}

function clearFileInputs(sourceInput) {
  els.imageFiles.forEach((input) => {
    if (input !== sourceInput) {
      input.value = "";
    }
  });
}

// Map setup: owns Mapbox style, globe projection, controls, and load/error status.
function initMap() {
  const token = els.mapboxToken.value.trim();
  localStorage.setItem("mapboxToken", token);

  if (!token) {
    setMapStatus("Token needed");
    setResult(`Add your Mapbox public token to initialize the globe.\n\nApp version: ${appVersion}`);
    return;
  }

  if (map) {
    map.remove();
  }

  mapboxgl.accessToken = token;
  map = new mapboxgl.Map({
    container: "map",
    style: "mapbox://styles/renceboey/cmt6tk6rx006q01skha9ndkbs",
    projection: "globe",
    center: initialView.center,
    zoom: initialView.zoom,
    pitch: initialView.pitch,
    bearing: initialView.bearing,
  });

  map.addControl(new mapboxgl.NavigationControl({ visualizePitch: true }), "top-right");
  map.addControl(new mapboxgl.FullscreenControl(), "top-right");

  map.on("style.load", () => {
    map.setFog({});
    setResult(`Loaded ${map.getStyle()?.sprite ? "Mapbox style" : "style"}.\n\nApp version: ${appVersion}`);
    setMapStatus("Globe ready");
  });

  map.on("idle", () => {
    const layerCount = map.getStyle()?.layers?.length || 0;
    if (layerCount > 0) {
      setMapStatus("Basemap ready");
    }
  });

  map.on("error", (event) => {
    setMapStatus("Map error");
    const message = event?.error?.message || "Mapbox failed to load.";
    setResult(
      `${message}\n\nIf the globe renders but has no countries or labels, check that your Mapbox public token has access to Mapbox styles and vector tiles.`
    );
  });
}

// Source switching: toggles File/URL tabs across both the side and floating UI.
function setActiveSource(source) {
  activeSource = source;
  els.fileTabs.forEach((button) => button.classList.toggle("active", source === "file"));
  els.urlTabs.forEach((button) => button.classList.toggle("active", source === "url"));
  els.filePanels.forEach((panel) => panel.classList.toggle("hidden", source !== "file"));
  els.urlPanels.forEach((panel) => panel.classList.toggle("hidden", source !== "url"));
}

// Shared file handler: either file picker updates one selected file used by both UIs.
function updatePreviewFromFile(event) {
  const sourceInput = event.currentTarget;
  const file = sourceInput.files?.[0];
  if (!file) return;

  try {
    validateImageFile(file);
    selectedFile = file;
    clearFileInputs(sourceInput);
    setActiveSource("file");
    setFileLabels(file.name);
    showFilePreviews(file);
    setResult(`Selected ${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB).`);
  } catch (error) {
    selectedFile = null;
    sourceInput.value = "";
    clearFileInputs(sourceInput);
    setFileLabels("Choose an image");
    clearPreviews();
    setResult(error instanceof Error ? error.message : "Invalid image file.");
  }
}

// Shared URL handler: URL text is mirrored because text inputs can be safely synchronized.
function updatePreviewFromUrl(event) {
  const sourceInput = event.currentTarget;
  const url = sourceInput.value.trim();
  syncUrlInputs(url, sourceInput);
  setActiveSource("url");

  if (!url) {
    clearPreviews();
    return;
  }

  try {
    showUrlPreviews(validateImageUrl(url));
  } catch {
    clearPreviews();
  }
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      resolve(result.includes(",") ? result.split(",")[1] : result);
    };
    reader.onerror = () => reject(reader.error || new Error("Could not read file"));
    reader.readAsDataURL(file);
  });
}

function normalizeCoordinates(response) {
  const location = response?.location || response?.geolocation?.estimatedLocation || response?.coordinates || response;
  const latitude = Number(location?.latitude ?? location?.lat);
  const longitude = Number(location?.longitude ?? location?.lng ?? location?.lon);

  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
    throw new Error("The geolocation response did not include numeric latitude/longitude.");
  }

  return {
    latitude,
    longitude,
    label: location?.address || location?.city || response?.reasoning || "Predicted location",
    confidence: response?.confidence ?? location?.confidence ?? null,
    raw: response,
  };
}

function tryNormalizeCoordinates(response) {
  try {
    return normalizeCoordinates(response);
  } catch {
    return null;
  }
}

// Map result rendering: owns marker creation, popup content, and camera fly-to.
function pinCoordinates(result) {
  if (!map) {
    throw new Error("Initialize the Mapbox globe first.");
  }

  const { longitude, latitude, label, confidence } = result;
  const popupHtml = `
    <strong>${label}</strong><br>
    ${latitude.toFixed(6)}, ${longitude.toFixed(6)}
    ${confidence == null ? "" : `<br>Confidence: ${confidence}`}
  `;

  if (!marker) {
    const markerEl = document.createElement("div");
    markerEl.className = "coordinate-marker";
    marker = new mapboxgl.Marker({ element: markerEl }).setPopup(new mapboxgl.Popup({ offset: 18 }));
  }

  marker.setLngLat([longitude, latitude]).setPopup(new mapboxgl.Popup({ offset: 18 }).setHTML(popupHtml)).addTo(map);
  marker.togglePopup();

  map.flyTo({
    center: [longitude, latitude],
    zoom: 13.5,
    pitch: 55,
    bearing: 18,
    duration: 1800,
    essential: true,
  });
}

// API orchestration: builds one request payload from shared UI state and pins the response.
async function analyzeImage() {
  const endpoint = els.apiEndpoint.value.trim();
  localStorage.setItem("geolocationApiEndpoint", endpoint);

  if (!endpoint) {
    setResult(`Add a geolocation API endpoint. For the LangGraph geolocation flow, use ${defaultGeolocationApiEndpoint}.`);
    return;
  }

  setButtonsDisabled(true);
  setResult("Analyzing image...");

  try {
    const payload = {};

    if (activeSource === "file") {
      validateImageFile(selectedFile);
      payload.image_b64 = await fileToBase64(selectedFile);
      payload.filename = selectedFile.name;
    } else {
      payload.image_url = validateImageUrl(selectedImageUrl.trim());
    }

    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(buildRequestError(response, data));
    }

    const coordinates = tryNormalizeCoordinates(data);
    if (coordinates) {
      pinCoordinates(coordinates);
    }
    setResult(data);
    refreshPreviousResults({ silent: true });
  } catch (error) {
    setResult(error instanceof Error ? error.message : "Analysis failed.");
  } finally {
    setButtonsDisabled(false);
  }
}

async function refreshPreviousResults(options = {}) {
  const { silent = false } = options;
  els.refreshResultsButton.disabled = true;
  els.loadResultButton.disabled = true;

  try {
    const response = await fetch(`${backendBaseUrl()}/agent-results?limit=50`);
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(buildRequestError(response, data));
    }

    const results = data?.results || [];
    els.previousResultsSelect.innerHTML = "";

    if (!results.length) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "No previous results found";
      els.previousResultsSelect.append(option);
      return;
    }

    for (const item of results) {
      const option = document.createElement("option");
      option.value = item.run_id;
      option.textContent = resultOptionLabel(item);
      els.previousResultsSelect.append(option);
    }
  } catch (error) {
    els.previousResultsSelect.innerHTML = "";
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "Could not load previous results";
    els.previousResultsSelect.append(option);
    if (!silent) {
      setResult(error instanceof Error ? error.message : "Could not load previous results.");
    }
  } finally {
    els.refreshResultsButton.disabled = false;
    els.loadResultButton.disabled = !els.previousResultsSelect.value;
  }
}

async function loadPreviousResult() {
  const runId = els.previousResultsSelect.value;
  if (!runId) {
    setResult("Choose a previous result first.");
    return;
  }

  els.loadResultButton.disabled = true;
  try {
    const response = await fetch(`${backendBaseUrl()}/agent-results/${encodeURIComponent(runId)}`);
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(buildRequestError(response, data));
    }

    const coordinates = tryNormalizeCoordinates(data);
    if (coordinates) {
      pinCoordinates(coordinates);
    }
    setResult(data);
  } catch (error) {
    setResult(error instanceof Error ? error.message : "Could not load previous result.");
  } finally {
    els.loadResultButton.disabled = !els.previousResultsSelect.value;
  }
}

// Reset control: clears the active marker and returns the globe to its initial view.
function clearPin() {
  if (marker) {
    marker.remove();
    marker = null;
  }

  if (map) {
    map.flyTo({
      ...initialView,
      duration: 1400,
      essential: true,
    });
  }

  setResult("Pin cleared. Map reset.");
}

els.mapboxToken.addEventListener("change", initMap);
els.apiEndpoint.addEventListener("change", () => {
  localStorage.setItem("geolocationApiEndpoint", els.apiEndpoint.value.trim());
});
els.detailsToggle.addEventListener("click", () => {
  detailsExpanded = !detailsExpanded;
  els.resultBox.hidden = !detailsExpanded;
  els.detailsToggle.textContent = detailsExpanded ? "Hide details" : "More details";
});
els.refreshResultsButton.addEventListener("click", () => refreshPreviousResults());
els.loadResultButton.addEventListener("click", loadPreviousResult);
els.previousResultsSelect.addEventListener("change", () => {
  els.loadResultButton.disabled = !els.previousResultsSelect.value;
});
els.fileTabs.forEach((button) => button.addEventListener("click", () => setActiveSource("file")));
els.urlTabs.forEach((button) => button.addEventListener("click", () => setActiveSource("url")));
els.imageFiles.forEach((input) => input.addEventListener("change", updatePreviewFromFile));
els.imageUrls.forEach((input) => input.addEventListener("input", updatePreviewFromUrl));
els.analyzeButtons.forEach((button) => button.addEventListener("click", analyzeImage));
els.clearButtons.forEach((button) => button.addEventListener("click", clearPin));

initMap();
refreshPreviousResults({ silent: true });
