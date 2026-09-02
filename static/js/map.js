(function () {
  "use strict";

  const AUSTIN_CENTER = [30.2711, -97.7437];

  const GROUP_COLORS = {
    "Basketball": "#C9502F",
    "Tennis": "#2F5D3A",
    "Soccer / Fields": "#3E7CB1",
    "Dog Parks": "#8A5A44",
    "Skate Parks": "#7A4FA3",
    "Disc Golf": "#C98A2B",
    "Golf": "#4F7942",
    "Track & Trails": "#B5891C",
    "Swimming": "#2C8C99",
    "Playgrounds": "#D6738B",
    "Parks": "#2F5D3A",
    "Sports Clubs": "#5B6559",
    "Stadiums": "#A6303E",
    "Volleyball": "#C9A227",
    "Pickleball": "#8FA83E",
    "Other": "#5B6559",
  };

  function colorFor(group) {
    return GROUP_COLORS[group] || GROUP_COLORS["Other"];
  }

  const map = L.map("map", { zoomControl: true }).setView(AUSTIN_CENTER, 13);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors | data &copy; <a href="https://overturemaps.org">Overture Maps Foundation</a>',
    subdomains: "abc",
    maxZoom: 19,
  }).addTo(map);

  let dataLayer = L.geoJSON(null, {
    pointToLayer: (feature, latlng) => {
      const group = feature.properties.group;
      return L.circleMarker(latlng, {
        radius: 7,
        fillColor: colorFor(group),
        color: "#1B2B1E",
        weight: 1,
        fillOpacity: 0.9,
      });
    },
    style: (feature) => ({
      color: colorFor(feature.properties.group),
      weight: 1.5,
      fillOpacity: 0.15,
    }),
    onEachFeature: (feature, layer) => {
      layer.bindPopup(`<div class="spot-popup">${buildSpotHtml(feature.properties)}</div>`);
    },
  }).addTo(map);

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str == null ? "" : str;
    return div.innerHTML;
  }
  function escapeAttr(str) {
    return escapeHtml(str).replace(/"/g, "&quot;");
  }

  // Shared by the Leaflet popup and the list-view cards.
  function buildSpotHtml(p) {
    const limitedNote = p.details_limited
      ? '<p class="limited-note">Limited details available for this spot.</p>'
      : "";
    const address = p.address ? `<p>${escapeHtml(p.address)}</p>` : "";
    const phone = p.phone ? `<p>${escapeHtml(p.phone)}</p>` : "";
    const website = p.website
      ? `<p><a href="${escapeAttr(p.website)}" target="_blank" rel="noopener">Website ↗</a></p>`
      : "";
    return `<h3>${escapeHtml(p.name)}</h3>
      <p class="category">${escapeHtml(p.group)}</p>
      ${address}${phone}${website}${limitedNote}`;
  }

  // --- State ---
  let activeGroup = "All";
  let userLocation = null; // {lat, lon}
  let radiusMiles = 2;

  const resultCountEl = document.getElementById("result-count");
  const locateStatusEl = document.getElementById("locate-status");
  const locateBtn = document.getElementById("locate-btn");
  const radiusRow = document.getElementById("radius-row");
  const radiusInput = document.getElementById("radius-input");
  const clearLocateBtn = document.getElementById("clear-locate-btn");
  const searchForm = document.getElementById("search-form");
  const searchInput = document.getElementById("search-input");
  const searchStatusEl = document.getElementById("search-status");
  const providerRow = document.getElementById("provider-row");
  const providerSelect = document.getElementById("provider-select");
  let searchQuery = null;

  // Populate the provider picker from whichever AI keys are configured on
  // the server; "Keyword search (no AI)" is always included. Only show the
  // picker at all if there's an actual AI option to choose alongside it.
  fetch("/api/llm-providers.json")
    .then((r) => r.json())
    .then((options) => {
      providerSelect.innerHTML = "";
      options.forEach((opt) => {
        const el = document.createElement("option");
        el.value = opt.id;
        el.textContent = opt.label;
        providerSelect.appendChild(el);
      });
      providerRow.hidden = options.length <= 1;
    })
    .catch(() => {
      providerRow.hidden = true;
    });

  const viewToggle = document.getElementById("view-toggle");
  const mapEl = document.getElementById("map");
  const listViewEl = document.getElementById("list-view");
  let viewMode = "map";

  function setViewMode(mode) {
    if (mode === viewMode) return;
    viewMode = mode;
    viewToggle.querySelectorAll(".view-btn").forEach((b) => b.classList.toggle("active", b.dataset.view === mode));
    if (mode === "map") {
      listViewEl.hidden = true;
      mapEl.hidden = false;
      map.invalidateSize();
    } else {
      mapEl.hidden = true;
      listViewEl.hidden = false;
    }
  }

  viewToggle.addEventListener("click", (e) => {
    const btn = e.target.closest(".view-btn[data-view]");
    if (btn) setViewMode(btn.dataset.view);
  });

  function focusFeatureOnMap(feature) {
    setViewMode("map");
    const layer = dataLayer.getLayers().find((l) => l.feature === feature);
    if (!layer) return;
    const center = layer.getLatLng ? layer.getLatLng() : layer.getBounds().getCenter();
    map.setView(center, 16);
    layer.openPopup();
  }

  function renderList(geojson, emptyMessage) {
    listViewEl.innerHTML = "";
    if (!geojson.features.length) {
      const empty = document.createElement("p");
      empty.className = "list-empty";
      empty.textContent = emptyMessage;
      listViewEl.appendChild(empty);
      return;
    }
    geojson.features.forEach((feature) => {
      const card = document.createElement("div");
      card.className = "spot-card";
      card.innerHTML = buildSpotHtml(feature.properties);
      card.addEventListener("click", () => focusFeatureOnMap(feature));
      listViewEl.appendChild(card);
    });
  }

  function buildFilterSwatches() {
    document.querySelectorAll(".filter-btn[data-group]").forEach((btn) => {
      const group = btn.dataset.group;
      if (group === "All") return;
      const swatch = document.createElement("span");
      swatch.className = "swatch";
      swatch.style.background = colorFor(group);
      btn.prepend(swatch);
    });
  }
  buildFilterSwatches();

  function renderResult(geojson, emptyMessage) {
    dataLayer.clearLayers();
    dataLayer.addData(geojson);
    renderList(geojson, emptyMessage);
    const count = geojson.features.length;
    resultCountEl.textContent =
      count === 0 ? emptyMessage : `${count} spot${count === 1 ? "" : "s"} shown`;
  }

  function fetchAndRender() {
    if (searchQuery) {
      fetchSearch();
      return;
    }
    const params = new URLSearchParams();
    if (activeGroup && activeGroup !== "All") params.set("group", activeGroup);
    if (userLocation) {
      params.set("lat", userLocation.lat);
      params.set("lon", userLocation.lon);
      params.set("radius", radiusMiles);
    }

    resultCountEl.textContent = "Loading spots…";

    fetch("/api/places?" + params.toString())
      .then((r) => r.json())
      .then((geojson) => renderResult(geojson, "No spots match. Try a different filter or a wider radius."))
      .catch(() => {
        resultCountEl.textContent = "Couldn't load spots. Try refreshing.";
      });
  }

  function fetchSearch() {
    resultCountEl.textContent = "Loading spots…";
    searchStatusEl.textContent = "Searching…";
    searchStatusEl.classList.remove("search-error");

    const params = new URLSearchParams({ q: searchQuery });
    if (providerSelect.value) params.set("provider", providerSelect.value);

    fetch("/api/search?" + params.toString())
      .then((r) => r.json())
      .then((data) => {
        if (data.error) {
          searchStatusEl.textContent = data.error;
          searchStatusEl.classList.add("search-error");
          resultCountEl.textContent = "";
          return;
        }

        renderResult(data, "No spots match that search. Try rephrasing.");

        if (data.notice) {
          searchStatusEl.textContent = data.notice;
        } else if (data.mode === "keyword") {
          searchStatusEl.textContent = "Matched by keyword (no AI provider selected).";
        } else if (data.interpreted) {
          const { groups, landmark, radius } = data.interpreted;
          const groupsText = groups && groups.length ? groups.join(", ") : "all activities";
          const nearText = landmark ? ` near ${landmark} (${radius} mi)` : "";
          searchStatusEl.textContent = `Understood as: ${groupsText}${nearText}`;
          if (landmark && data.features.length) {
            map.setView(dataLayer.getBounds().getCenter(), 14);
          }
        }
      })
      .catch(() => {
        resultCountEl.textContent = "";
        searchStatusEl.textContent = "Couldn't run that search. Try refreshing.";
        searchStatusEl.classList.add("search-error");
      });
  }

  function exitSearch() {
    if (!searchQuery) return;
    searchQuery = null;
    searchInput.value = "";
    searchStatusEl.textContent = "";
    searchStatusEl.classList.remove("search-error");
  }

  // --- Search ---
  searchForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const value = searchInput.value.trim();
    if (!value) return;
    document.querySelectorAll(".filter-btn[data-group]").forEach((b) => b.classList.remove("active"));
    searchQuery = value;
    fetchAndRender();
  });

  // --- Filter buttons ---
  document.querySelectorAll(".filter-btn[data-group]").forEach((btn) => {
    btn.addEventListener("click", () => {
      exitSearch();
      document.querySelectorAll(".filter-btn[data-group]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      activeGroup = btn.dataset.group;
      fetchAndRender();
    });
  });

  // --- Geolocation ---
  locateBtn.addEventListener("click", () => {
    if (!navigator.geolocation) {
      locateStatusEl.textContent = "Geolocation isn't available in this browser.";
      return;
    }
    exitSearch();
    locateStatusEl.textContent = "Finding your location…";
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        userLocation = { lat: pos.coords.latitude, lon: pos.coords.longitude };
        radiusMiles = parseFloat(radiusInput.value);
        locateBtn.classList.add("active");
        locateBtn.textContent = "Location set";
        radiusRow.hidden = false;
        locateStatusEl.textContent = "";
        map.setView([userLocation.lat, userLocation.lon], 14);
        fetchAndRender();
      },
      () => {
        locateStatusEl.textContent = "Couldn't get your location. Check browser permissions.";
      }
    );
  });

  radiusInput.addEventListener("change", () => {
    radiusMiles = parseFloat(radiusInput.value);
    if (userLocation) fetchAndRender();
  });

  clearLocateBtn.addEventListener("click", () => {
    userLocation = null;
    radiusRow.hidden = true;
    locateBtn.classList.remove("active");
    locateBtn.textContent = "Use my location";
    locateStatusEl.textContent = "";
    map.setView(AUSTIN_CENTER, 13);
    fetchAndRender();
  });

  // Initial load
  fetchAndRender();
})();
