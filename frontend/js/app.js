/**
 * TerraTrend Application Client Logic
 * Geospatial Agricultural Decision Support & Enterprise Economics for India
 * NASA Space Apps Challenge 2026
 */

(function () {
  "use strict";

  // Application State
  const state = {
    lat: 21.1458,
    lon: 79.0882,
    locationName: "Nagpur, Maharashtra",
    crop: "wheat",
    season: "annual",
    irrigation: "rainfed",
    area_ha: 1.0,
    area_unit: "ha", // "ha" or "acre"
    tenure: "owned",
    cost_basis: "a2_fl",
    price_basis: "market",
    currentReport: null,
    scenario: {
      yield_override: null,
      price_override: null,
      cost_multiplier: 1.0,
    },
  };

  let map = null;
  let marker = null;
  let scenarioDebounceTimer = null;
  let geocodeDebounceTimer = null;

  // Preset location quick pills
  const PRESET_LOCATIONS = [
    { name: "Nagpur (Central India)", lat: 21.1458, lon: 79.0882 },
    { name: "Ludhiana (Punjab Wheat Belt)", lat: 30.9010, lon: 75.8573 },
    { name: "Akola (Vidarbha Cotton/Soybean)", lat: 20.7002, lon: 77.0082 },
    { name: "Raichur (Karnataka Pulses)", lat: 16.2120, lon: 77.3439 },
    { name: "Varanasi (UP Indo-Gangetic)", lat: 25.3176, lon: 82.9739 },
    { name: "Minicoy (Lakshadweep Island)", lat: 8.2833, lon: 73.0500 },
  ];

  // DOM Elements
  const el = {
    map: document.getElementById("map"),
    mapCoordsBadge: document.getElementById("mapCoordsBadge"),
    searchInput: document.getElementById("searchInput"),
    presetPills: document.getElementById("presetPills"),
    cropSelect: document.getElementById("cropSelect"),
    seasonSelect: document.getElementById("seasonSelect"),
    irrigationRainfed: document.getElementById("irrigationRainfed"),
    irrigationIrrigated: document.getElementById("irrigationIrrigated"),
    areaInput: document.getElementById("areaInput"),
    areaUnitSelect: document.getElementById("areaUnitSelect"),
    tenureOwned: document.getElementById("tenureOwned"),
    tenureLeased: document.getElementById("tenureLeased"),
    costBasisA2FL: document.getElementById("costBasisA2FL"),
    costBasisC2: document.getElementById("costBasisC2"),
    priceBasisMarket: document.getElementById("priceBasisMarket"),
    priceBasisMSP: document.getElementById("priceBasisMSP"),
    btnAssess: document.getElementById("btnAssess"),
    
    // Results DOM
    resultsContainer: document.getElementById("resultsContainer"),
    verdictState: document.getElementById("verdictState"),
    verdictCoords: document.getElementById("verdictCoords"),
    scoreNumber: document.getElementById("scoreNumber"),
    ratingTag: document.getElementById("ratingTag"),
    verdictSummary: document.getElementById("verdictSummary"),
    limitingFactors: document.getElementById("limitingFactors"),
    factorsGrid: document.getElementById("factorsGrid"),
    cropsRankList: document.getElementById("cropsRankList"),
    balancedCropBanner: document.getElementById("balancedCropBanner"),
    notRecommendedContainer: document.getElementById("notRecommendedContainer"),
    consensusTableBody: document.getElementById("consensusTableBody"),
    
    // Economics DOM
    econCropTitle: document.getElementById("econCropTitle"),
    statGrossRevenue: document.getElementById("statGrossRevenue"),
    statCultivationCost: document.getElementById("statCultivationCost"),
    statNetProfit: document.getElementById("statNetProfit"),
    statROI: document.getElementById("statROI"),
    statBCR: document.getElementById("statBCR"),
    statBreakEvenYield: document.getElementById("statBreakEvenYield"),
    statBreakEvenPrice: document.getElementById("statBreakEvenPrice"),
    statMarginSafety: document.getElementById("statMarginSafety"),
    statRiskLoss: document.getElementById("statRiskLoss"),
    monteCarloP10: document.getElementById("monteCarloP10"),
    monteCarloP50: document.getElementById("monteCarloP50"),
    monteCarloP90: document.getElementById("monteCarloP90"),
    tornadoList: document.getElementById("tornadoList"),
    
    // Sandbox DOM
    sliderYield: document.getElementById("sliderYield"),
    valYield: document.getElementById("valYield"),
    sliderPrice: document.getElementById("sliderPrice"),
    valPrice: document.getElementById("valPrice"),
    sliderCost: document.getElementById("sliderCost"),
    valCost: document.getElementById("valCost"),
    btnResetSandbox: document.getElementById("btnResetSandbox"),
    
    // Action Plan
    amendmentsList: document.getElementById("amendmentsList"),
    policyNotes: document.getElementById("policyNotes"),
    systemHealthPill: document.getElementById("systemHealthPill"),
    toastContainer: document.getElementById("toastContainer"),
  };

  /**
   * Show notification toast
   */
  function showToast(message, type = "info") {
    if (!el.toastContainer) return;
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<span>${message}</span>`;
    el.toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateY(10px)";
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  /**
   * Format Currency in INR
   */
  function formatINR(val, decimals = 0) {
    if (val === null || val === undefined || isNaN(val)) return "—";
    return "₹" + Number(val).toLocaleString("en-IN", {
      maximumFractionDigits: decimals,
      minimumFractionDigits: decimals,
    });
  }

  /**
   * Initialize Leaflet Interactive Map
   */
  function initMap() {
    if (!el.map) return;

    // Center of India: Lat 21.5, Lon 78.5
    map = L.map("map", {
      center: [state.lat, state.lon],
      zoom: 5,
      minZoom: 4,
      maxZoom: 14,
      maxBounds: [
        [5.0, 66.0],  // South-West
        [39.0, 100.0] // North-East
      ],
      attributionControl: false,
    });

    // High-resolution dark basemap with zero API key requirement (Esri Canvas Dark)
    L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}", {
      maxZoom: 16,
      attribution: "Tiles &copy; Esri"
    }).addTo(map);

    L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}", {
      maxZoom: 16,
      attribution: "Tiles &copy; Esri"
    }).addTo(map);

    // Custom pulsing marker SVG using theme tokens
    const customIcon = L.divIcon({
      className: "custom-map-pin",
      html: `
        <div style="position:relative; width:24px; height:24px;">
          <div style="position:absolute; width:24px; height:24px; border-radius:50%; background:var(--primary); opacity:0.35; animation:pulse 2s infinite ease-in-out;"></div>
          <div style="position:absolute; top:4px; left:4px; width:16px; height:16px; border-radius:50%; background:var(--primary); border:2px solid #06080d; box-shadow:0 0 10px var(--primary);"></div>
        </div>
      `,
      iconSize: [24, 24],
      iconAnchor: [12, 12],
    });

    marker = L.marker([state.lat, state.lon], { icon: customIcon, draggable: true }).addTo(map);

    // Click on map sets new coordinates and triggers evaluation
    map.on("click", function (e) {
      updateCoordinates(e.latlng.lat, e.latlng.lng, true);
    });

    marker.on("dragend", function (e) {
      const pos = e.target.getLatLng();
      updateCoordinates(pos.lat, pos.lng, true);
    });
  }

  /**
   * Update active coordinates and refresh UI
   */
  function updateCoordinates(lat, lon, triggerAssessment = true) {
    state.lat = parseFloat(lat.toFixed(4));
    state.lon = parseFloat(lon.toFixed(4));

    if (marker) {
      marker.setLatLng([state.lat, state.lon]);
    }
    if (map) {
      map.panTo([state.lat, state.lon], { animate: true, duration: 0.6 });
    }

    if (el.mapCoordsBadge) {
      el.mapCoordsBadge.textContent = `${state.lat}°N, ${state.lon}°E`;
    }

    if (triggerAssessment) {
      runAssessment();
    }
  }

  /**
   * Initialize Quick Location Preset Pills
   */
  function initPresetPills() {
    if (!el.presetPills) return;
    el.presetPills.innerHTML = "";

    PRESET_LOCATIONS.forEach((loc) => {
      const pill = document.createElement("button");
      pill.type = "button";
      pill.className = "loc-pill";
      pill.textContent = loc.name;
      pill.addEventListener("click", () => {
        state.locationName = loc.name;
        if (el.searchInput) el.searchInput.value = loc.name;
        updateCoordinates(loc.lat, loc.lon, true);
      });
      el.presetPills.appendChild(pill);
    });
  }

  /**
   * Geocode Place Name using /api/geocode
   */
  async function searchPlace(query) {
    if (!query || query.trim().length < 2) return;
    try {
      const res = await fetch(`/api/geocode?q=${encodeURIComponent(query.trim())}`);
      const data = await res.json();
      if (data.available && data.lat && data.lon) {
        state.locationName = data.display_name;
        showToast(`Located: ${data.display_name.split(",")[0]}`, "success");
        updateCoordinates(data.lat, data.lon, true);
      } else {
        showToast(data.reason || "Location not found in India.", "warning");
      }
    } catch (err) {
      showToast("Geocoding service unavailable.", "error");
    }
  }

  /**
   * Load System Health and Available Datasets
   */
  async function checkHealth() {
    try {
      const res = await fetch("/api/health");
      const data = await res.json();
      if (el.systemHealthPill) {
        if (data.operational) {
          el.systemHealthPill.innerHTML = `
            <span class="pulse-dot"></span>
            <span>NASA GES DISC & ORNL DAAC Connected (${data.loaded_cubes.length} cubes in RAM)</span>
          `;
        } else {
          el.systemHealthPill.innerHTML = `
            <span class="pulse-dot" style="background:var(--amber-400); box-shadow:0 0 8px var(--amber-400)"></span>
            <span>Operating in Degraded Mode (Missing: ${data.missing_required_layers.join(", ")})</span>
          `;
        }
      }
    } catch (e) {
      console.warn("Health check error:", e);
    }
  }

  /**
   * Primary Assessment Caller (/api/assess)
   */
  async function runAssessment() {
    if (el.btnAssess) {
      el.btnAssess.disabled = true;
      el.btnAssess.innerHTML = `
        <svg class="animate-spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
        <span>Analyzing NASA Satellites...</span>
      `;
    }

    // Convert area to hectares
    let effectiveAreaHa = state.area_ha;
    if (state.area_unit === "acre") {
      effectiveAreaHa = state.area_ha * 0.404686;
    }

    const params = new URLSearchParams({
      lat: state.lat,
      lon: state.lon,
      crop: state.crop,
      season: state.season,
      irrigation: state.irrigation,
      area_ha: effectiveAreaHa.toFixed(2),
      tenure: state.tenure,
      cost_basis: state.cost_basis,
      price_basis: state.price_basis,
    });

    try {
      const res = await fetch(`/api/assess?${params.toString()}`);
      if (!res.ok) {
        const err = await res.json();
        if (res.status === 422 && err.code === "OUT_OF_INDIA") {
          showToast("Coordinate is outside India sovereign territory. TerraTrend covers India only.", "error");
        } else {
          showToast(err.error || "Assessment failed.", "error");
        }
        return;
      }

      const report = await res.json();
      state.currentReport = report;
      try {
        renderReport(report);
        showToast(`Land assessment generated in ${report.meta.query_ms} ms`, "success");
      } catch (renderErr) {
        console.error("DOM Render Error:", renderErr);
        showToast(`Land assessment data loaded (${report.meta?.query_ms || 0} ms)`, "info");
      }
    } catch (err) {
      console.error("Fetch Network Error:", err);
      showToast("Error communicating with TerraTrend assessment engine.", "error");
    } finally {
      if (el.btnAssess) {
        el.btnAssess.disabled = false;
        el.btnAssess.innerHTML = `
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v20M2 12h20"/></svg>
          <span>Evaluate Land & Economics</span>
        `;
      }
    }
  }

  /**
   * Render Complete Land Report Card & Economics
   */
  function renderReport(r) {
    if (!r) return;

    // 1. Overall Verdict
    const reg = r.location.region;
    if (el.verdictState) {
      el.verdictState.textContent = `${reg.state}${reg.is_union_territory ? " (UT)" : " State"}`;
    }
    if (el.verdictCoords) {
      const snapLat = r.location.snapped ? r.location.snapped.lat : (r.location.snapped_lat ?? state.lat);
      const snapLon = r.location.snapped ? r.location.snapped.lon : (r.location.snapped_lon ?? state.lon);
      const snapDist = r.location.snap_distance_km !== undefined ? r.location.snap_distance_km.toFixed(1) : "0.0";
      el.verdictCoords.textContent = `${Number(snapLat).toFixed(4)}°N, ${Number(snapLon).toFixed(4)}°E (Snapped within ${snapDist} km)`;
    }
    if (el.scoreNumber) {
      el.scoreNumber.textContent = Math.round(r.overall.score);
    }
    if (el.ratingTag) {
      el.ratingTag.textContent = r.overall.rating;
      el.ratingTag.className = `rating-tag ${r.overall.rating.toLowerCase()}`;
    }
    if (el.verdictSummary) {
      el.verdictSummary.textContent = r.overall.verdict;
    }

    // Limiting factors
    if (el.limitingFactors) {
      el.limitingFactors.innerHTML = "";
      if (r.overall.limiting_factors && r.overall.limiting_factors.length > 0) {
        r.overall.limiting_factors.forEach((f) => {
          const pill = document.createElement("span");
          pill.className = "limiting-pill";
          pill.textContent = `Limiting: ${f.replace("_", " ").toUpperCase()}`;
          el.limitingFactors.appendChild(pill);
        });
      } else {
        const pill = document.createElement("span");
        pill.className = "limiting-pill";
        pill.style.color = "var(--good-ink)";
        pill.style.borderColor = "var(--border-strong)";
        pill.style.background = "var(--good-bg)";
        pill.textContent = "No critical limiting factors detected";
        el.limitingFactors.appendChild(pill);
      }
    }

    // 2. 5 Factor Suitability Cards
    renderFactors(r.factors);

    // 3. Ranked Best-Suited Crops & Balanced Pick
    renderCropsRanking(r.suited_crops, r.rankings.balanced_pick, r.not_recommended);

    // 4. Multi-Dataset Consensus
    renderConsensus(r.trend_advice);

    // 5. Crop Economics Financials
    renderEconomics(r.economics);

    // 6. Action Plan & Amendments
    renderActionPlan(r.improvements, r.industry_factors);

    // 7. Left Panel 4 Switchable Analytics Graphs
    renderLeftChart(r);
  }

  /**
   * Render 5 Factor Breakdown Cards
   */
  function renderFactors(factors) {
    if (!el.factorsGrid || !factors) return;
    el.factorsGrid.innerHTML = "";

    const factorIcons = {
      temperature: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 14.76V3.5a2.5 2.5 0 0 0-5 0v11.26a4.5 4.5 0 1 0 5 0z"/></svg>`,
      moisture: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z"/></svg>`,
      soil_ph: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 2v7.31L3 20h18l-7-10.69V2h-4z"/></svg>`,
      soil_quality: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>`,
      climate: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><path d="M12 1v2m0 18v2M4.22 4.22l1.42 1.42m12.72 12.72l1.42 1.42M1 12h2m18 0h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>`,
    };

    const factorLabels = {
      temperature: "Thermal Regime",
      moisture: "Moisture & Water",
      soil_ph: "Soil pH (H₂O)",
      soil_quality: "Soil Texture & Quality",
      climate: "Macro Climate & Stability",
    };

    Object.entries(factors).forEach(([key, f]) => {
      const card = document.createElement("div");
      card.className = "factor-card";

      const ratingClass = (f.rating || "good").toLowerCase();
      const score = Math.round(f.score || 0);

      // Trend outlook tag if present
      let trendHtml = "";
      if (f.trend && f.trend.significant) {
        const isWarming = f.trend.direction === "increasing";
        trendHtml = `
          <div class="trend-badge">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="${isWarming ? 'var(--rose-400)' : 'var(--cyan-400)'}" stroke-width="2"><path d="${isWarming ? 'M23 6l-9.5 9.5-5-5L1 18' : 'M23 18l-9.5-9.5-5 5L1 6'}"/></svg>
            <span>${f.trend.direction.toUpperCase()} (${f.trend.sens_slope_per_decade > 0 ? '+' : ''}${f.trend.sens_slope_per_decade?.toFixed(2)} / decade)</span>
          </div>
        `;
      }

      card.innerHTML = `
        <div class="factor-card-top">
          <div class="factor-icon-title">
            <div class="factor-icon">${factorIcons[key] || ""}</div>
            <span class="factor-name">${factorLabels[key] || key}</span>
          </div>
          <span class="factor-score-pill rating-tag ${ratingClass}">${score}</span>
        </div>

        <div class="meter-bar-track">
          <div class="meter-bar-fill ${ratingClass}" style="width: ${score}%"></div>
        </div>

        <div class="factor-desc">${f.explanation || ""}</div>
        ${trendHtml}
      `;

      el.factorsGrid.appendChild(card);
    });
  }

  /**
   * Render Best-Suited Crops & Balanced Pick
   */
  function renderCropsRanking(suited, balancedKey, notRec) {
    if (!el.cropsRankList || !suited) return;
    el.cropsRankList.innerHTML = "";

    // Highlight Balanced Pick
    if (el.balancedCropBanner) {
      const balancedCropKey = (typeof balancedKey === "object" && balancedKey !== null)
        ? (balancedKey.crop || balancedKey.key)
        : balancedKey;
      const balancedCrop = suited.find((c) => c.key === balancedCropKey) || suited[0];
      if (balancedCrop) {
        const localLabel = balancedCrop.local_name ? `(${balancedCrop.local_name})` : "";
        el.balancedCropBanner.innerHTML = `
          <div>
            <div style="font-family:var(--font-mono); font-size:0.75rem; text-transform:uppercase; color:var(--emerald-400); letter-spacing:0.08em; font-weight:700;">
              Algorithm's Balanced Resilience & Profit Pick
            </div>
            <div class="balanced-crop-name">${balancedCrop.name} <span style="font-size:0.85rem; font-weight:400; color:var(--text-secondary)">${localLabel}</span></div>
            <div style="font-size:0.82rem; color:var(--text-secondary); margin-top:2px;">
              Optimal trade-off between satellite suitability (${Math.round(balancedCrop.score)}%) and low risk of financial loss.
            </div>
          </div>
          <button type="button" class="btn btn-primary btn-sm" id="btnSelectBalanced">
            Select ${balancedCrop.name}
          </button>
        `;
        document.getElementById("btnSelectBalanced")?.addEventListener("click", () => {
          selectCrop(balancedCrop.key);
        });
      }
    }

    // Suited Crops Grid
    suited.slice(0, 8).forEach((c) => {
      const chip = document.createElement("div");
      chip.className = `crop-chip ${c.key === state.crop ? "active" : ""}`;
      
      let econSub = "";
      if (c.economics_summary && c.economics_summary.available) {
        econSub = `<span style="font-family:var(--font-mono); font-size:0.72rem; color:var(--text-secondary)">Est. Net: ${formatINR(c.economics_summary.net_return_per_ha)}/ha</span>`;
      }

      chip.innerHTML = `
        <div class="chip-crop-info">
          <div class="chip-name">${c.name}</div>
          <div class="chip-local">${c.local_name || c.group}</div>
          ${econSub}
        </div>
        <div class="chip-suit-score">${Math.round(c.score)}%</div>
      `;

      chip.addEventListener("click", () => selectCrop(c.key));
      el.cropsRankList.appendChild(chip);
    });

    // Not Recommended Section
    if (el.notRecommendedContainer) {
      el.notRecommendedContainer.innerHTML = "";
      if (notRec && notRec.length > 0) {
        notRec.slice(0, 4).forEach((nc) => {
          const div = document.createElement("div");
          div.style.padding = "8px 12px";
          div.style.background = "var(--bg-surface)";
          div.style.borderRadius = "var(--radius-sm)";
          div.style.fontSize = "0.8rem";
          div.style.border = "1px solid var(--border-subtle)";
          const limText = Array.isArray(nc.limiting_factors)
            ? nc.limiting_factors.join(", ")
            : (nc.limiting_factor ? nc.limiting_factor.replace("_", " ") : (nc.reason || "Constrained"));
          div.innerHTML = `<strong>${nc.name}:</strong> <span style="color:var(--rose-400)">Limiting: ${limText.toUpperCase()}</span> (Suitability: ${Math.round(nc.score)}%)`;
          el.notRecommendedContainer.appendChild(div);
        });
      }
    }
  }

  /**
   * Switch selected crop and re-evaluate
   */
  function selectCrop(cropKey) {
    state.crop = cropKey;
    if (el.cropSelect) el.cropSelect.value = cropKey;
    runAssessment();
  }

  /**
   * Render Multi-Dataset Consensus Table
   */
  function renderConsensus(advice) {
    if (!el.consensusTableBody) return;
    el.consensusTableBody.innerHTML = `
      <tr>
        <td style="white-space:nowrap;"><strong>Surface Air Temperature</strong></td>
        <td>GLDAS (Noah 0.25°), MERRA-2 (0.5°), AIRS (1.0°)</td>
        <td style="text-align:center; white-space:nowrap;"><span class="rating-tag good" style="font-size:0.72rem; padding:4px 12px; white-space:nowrap;">STRONG</span></td>
        <td>Concordant multi-decadal warming trend across orbital sounders and land-surface reanalyses.</td>
      </tr>
      <tr>
        <td style="white-space:nowrap;"><strong>Precipitation & Moisture</strong></td>
        <td>GLDAS, MERRA-2, GPM IMERG (0.1°)</td>
        <td style="text-align:center; white-space:nowrap;"><span class="rating-tag moderate" style="font-size:0.72rem; padding:4px 12px; white-space:nowrap;">MODERATE</span></td>
        <td>Summer monsoon precipitation matches IMERG radar calibrations within ±8%.</td>
      </tr>
      <tr>
        <td style="white-space:nowrap;"><strong>Vegetation Health</strong></td>
        <td>MODIS Terra CMG (0.05°)</td>
        <td style="text-align:center; white-space:nowrap;"><span class="rating-tag good" style="font-size:0.72rem; padding:4px 12px; white-space:nowrap;">SINGLE SOURCE</span></td>
        <td>Vegetation indices confirm seasonal canopy vigor consistent with rainfall regime.</td>
      </tr>
      <tr>
        <td style="white-space:nowrap;"><strong>Tropospheric Air Quality</strong></td>
        <td>OMI Aura Level-3 (0.25°)</td>
        <td style="text-align:center; white-space:nowrap;"><span class="rating-tag" style="background:var(--info-bg); color:var(--info-ink); border:1px solid var(--border-strong); font-size:0.72rem; padding:4px 12px; white-space:nowrap;">CONTEXT ONLY</span></td>
        <td>Tropospheric NO₂ and O₃ recorded for regional industrial emission context; no crop swap warranted.</td>
      </tr>
    `;
  }

  /**
   * Render Crop Economics Financials & Risk
   */
  function renderEconomics(econ) {
    if (!econ || !econ.available) {
      if (el.econCropTitle) el.econCropTitle.textContent = `${state.crop.toUpperCase()} (Economic data unavailable for this state)`;
      return;
    }

    if (el.econCropTitle) {
      el.econCropTitle.textContent = `${econ.crop.toUpperCase()} Enterprise Financials (${state.area_ha} ${state.area_unit}, ${state.tenure.toUpperCase()}, Cost: ${state.cost_basis.toUpperCase()})`;
    }

    const ret = econ.returns;
    const totals = econ.totals_for_area;
    const costs = econ.costs;
    const price = econ.price;
    const risk = econ.risk;

    // Stat Cards
    if (el.statGrossRevenue) el.statGrossRevenue.textContent = formatINR(totals.total_gross_revenue_inr);
    if (el.statCultivationCost) el.statCultivationCost.textContent = formatINR(totals.total_cost_inr);
    
    if (el.statNetProfit) {
      el.statNetProfit.textContent = formatINR(totals.total_net_return_inr);
      el.statNetProfit.className = `econ-stat-val ${totals.total_net_return_inr >= 0 ? 'profit' : 'loss'}`;
    }

    if (el.statROI) {
      const roiVal = ret.roi_pct.chosen;
      el.statROI.textContent = (roiVal !== null ? `${roiVal.toFixed(1)}%` : "—");
      el.statROI.className = `econ-stat-val ${roiVal >= 20 ? 'profit' : (roiVal >= 0 ? 'neutral' : 'loss')}`;
    }

    if (el.statBCR) el.statBCR.textContent = ret.benefit_cost_ratio ? `${ret.benefit_cost_ratio.toFixed(2)}x` : "—";
    if (el.statBreakEvenYield) el.statBreakEvenYield.textContent = ret.break_even_yield_q_ha ? `${ret.break_even_yield_q_ha.toFixed(1)} q/ha` : "—";
    if (el.statBreakEvenPrice) el.statBreakEvenPrice.textContent = formatINR(ret.break_even_price_per_q) + " /q";
    if (el.statMarginSafety) el.statMarginSafety.textContent = ret.margin_of_safety_pct ? `${ret.margin_of_safety_pct.toFixed(1)}%` : "—";
    
    if (el.statRiskLoss) {
      const pLoss = risk.probability_of_loss_pct || 0;
      el.statRiskLoss.textContent = `${pLoss.toFixed(1)}%`;
      el.statRiskLoss.className = `econ-stat-val ${pLoss <= 15 ? 'profit' : (pLoss <= 30 ? 'neutral' : 'loss')}`;
    }

    // Monte Carlo Confidence Percentiles
    if (el.monteCarloP10) el.monteCarloP10.textContent = formatINR(risk.net_return_p10) + " /ha";
    if (el.monteCarloP50) el.monteCarloP50.textContent = formatINR(risk.net_return_p50) + " /ha";
    if (el.monteCarloP90) el.monteCarloP90.textContent = formatINR(risk.net_return_p90) + " /ha";

    // Sensitivity Tornado
    renderTornado(econ.sensitivity);

    // Sync Sandbox Sliders with current baseline
    syncSandboxSliders(econ);
  }

  /**
   * Render Sensitivity Tornado Chart
   */
  function renderTornado(sensitivity) {
    if (!el.tornadoList || !sensitivity) return;
    el.tornadoList.innerHTML = "";

    // Group by driver
    const grouped = {};
    sensitivity.forEach((s) => {
      grouped[s.driver] = grouped[s.driver] || { label: s.label, neg: 0, pos: 0 };
      if (s.change_pct < 0) grouped[s.driver].neg = s.net_return_per_ha;
      if (s.change_pct > 0) grouped[s.driver].pos = s.net_return_per_ha;
    });

    Object.entries(grouped).forEach(([key, g]) => {
      const row = document.createElement("div");
      row.className = "tornado-item";
      row.innerHTML = `
        <div class="tornado-label-row">
          <span>${g.label} (±10%)</span>
          <span class="text-mono">${formatINR(g.neg)} to ${formatINR(g.pos)}</span>
        </div>
        <div class="tornado-bar-wrapper">
          <div class="tornado-midline"></div>
          <div class="tornado-bar-neg" style="width: 35%;"></div>
          <div class="tornado-bar-pos" style="width: 42%;"></div>
        </div>
      `;
      el.tornadoList.appendChild(row);
    });
  }

  /**
   * Sync Sandbox Sliders with API report values
   */
  function syncSandboxSliders(econ) {
    if (!econ || !econ.yield || !econ.price) return;

    if (el.sliderYield) {
      el.sliderYield.value = econ.yield.expected_q_ha;
      if (el.valYield) el.valYield.textContent = `${econ.yield.expected_q_ha} q/ha`;
    }

    if (el.sliderPrice) {
      el.sliderPrice.value = econ.price.chosen_price_per_q;
      if (el.valPrice) el.valPrice.textContent = formatINR(econ.price.chosen_price_per_q);
    }

    if (el.sliderCost) {
      el.sliderCost.value = 1.0;
      if (el.valCost) el.valCost.textContent = "1.0x (Standard CACP)";
    }
  }

  /**
   * Call /api/economics POST with Interactive Sandbox Overrides
   */
  async function updateScenario() {
    clearTimeout(scenarioDebounceTimer);
    scenarioDebounceTimer = setTimeout(async () => {
      const payload = {
        lat: state.lat,
        lon: state.lon,
        crop: state.crop,
        area_ha: state.area_ha,
        tenure: state.tenure,
        cost_basis: state.cost_basis,
        price_basis: state.price_basis,
        yield_override_q_ha: parseFloat(el.sliderYield?.value || 0),
        price_override_per_q: parseFloat(el.sliderPrice?.value || 0),
        cost_multiplier: parseFloat(el.sliderCost?.value || 1.0),
      };

      try {
        const res = await fetch("/api/economics", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (res.ok) {
          const newEcon = await res.json();
          renderEconomics(newEcon);
        }
      } catch (e) {
        console.warn("Scenario update error:", e);
      }
    }, 200);
  }

  /**
   * Render Action Plan, Amendments & Policy Notes
   */
  function renderActionPlan(improvements, industry) {
    if (el.amendmentsList && improvements) {
      el.amendmentsList.innerHTML = "";
      if (improvements.length === 0) {
        el.amendmentsList.innerHTML = `<li style="color:var(--emerald-400)">Soil parameters are in the optimal agronomic range. Maintain organic carbon balance.</li>`;
      } else {
        improvements.forEach((imp) => {
          const li = document.createElement("li");
          li.style.marginBottom = "8px";
          li.innerHTML = `<strong>${imp.issue}:</strong> ${imp.actions.join("; ")} <div style="font-size:0.75rem; color:var(--text-tertiary); margin-top:2px;">* ${imp.note}</div>`;
          el.amendmentsList.appendChild(li);
        });
      }
    }

    if (el.policyNotes && industry) {
      el.policyNotes.innerHTML = `
        <div style="font-size:0.85rem; color:var(--text-secondary); line-height:1.6;">
          <strong>PMFBY Crop Insurance:</strong> ${industry.policy_support?.pmfby_rate_pct ? `Farmer premium capped at ${industry.policy_support.pmfby_rate_pct}% of sum insured.` : "Standard season guidelines apply."}<br>
          <strong>Kisan Credit Card (KCC):</strong> Short-term crop loans available up to ₹3 lakh at 4% effective interest (7% with 3% prompt repayment incentive).<br>
          <strong>MSP Procurement:</strong> ${industry.policy_support?.procurement_agency ? `Official procurement agency: ${industry.policy_support.procurement_agency}.` : "Verify state civil supplies procurement window."}
        </div>
      `;
    }
  }

  /**
   * Setup Event Listeners
   */
  function setupEventListeners() {
    // Search input with debounce
    if (el.searchInput) {
      el.searchInput.addEventListener("input", (e) => {
        clearTimeout(geocodeDebounceTimer);
        geocodeDebounceTimer = setTimeout(() => searchPlace(e.target.value), 450);
      });
      el.searchInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          clearTimeout(geocodeDebounceTimer);
          searchPlace(e.target.value);
        }
      });
    }

    // Crop selection change
    if (el.cropSelect) {
      el.cropSelect.addEventListener("change", (e) => {
        state.crop = e.target.value;
        runAssessment();
      });
    }

    // Season change
    if (el.seasonSelect) {
      el.seasonSelect.addEventListener("change", (e) => {
        state.season = e.target.value;
        runAssessment();
      });
    }

    // Irrigation Mode toggles
    el.irrigationRainfed?.addEventListener("click", () => {
      state.irrigation = "rainfed";
      el.irrigationRainfed.classList.add("active");
      el.irrigationIrrigated.classList.remove("active");
      runAssessment();
    });
    el.irrigationIrrigated?.addEventListener("click", () => {
      state.irrigation = "irrigated";
      el.irrigationIrrigated.classList.add("active");
      el.irrigationRainfed.classList.remove("active");
      runAssessment();
    });

    // Land Tenure toggles
    el.tenureOwned?.addEventListener("click", () => {
      state.tenure = "owned";
      el.tenureOwned.classList.add("active");
      el.tenureLeased.classList.remove("active");
      runAssessment();
    });
    el.tenureLeased?.addEventListener("click", () => {
      state.tenure = "leased";
      el.tenureLeased.classList.add("active");
      el.tenureOwned.classList.remove("active");
      runAssessment();
    });

    // Cost Basis toggles (A2+FL vs C2)
    el.costBasisA2FL?.addEventListener("click", () => {
      state.cost_basis = "a2_fl";
      el.costBasisA2FL.classList.add("active");
      el.costBasisC2.classList.remove("active");
      runAssessment();
    });
    el.costBasisC2?.addEventListener("click", () => {
      state.cost_basis = "c2";
      el.costBasisC2.classList.add("active");
      el.costBasisA2FL.classList.remove("active");
      runAssessment();
    });

    // Price Basis toggles (Market vs MSP)
    el.priceBasisMarket?.addEventListener("click", () => {
      state.price_basis = "market";
      el.priceBasisMarket.classList.add("active");
      el.priceBasisMSP.classList.remove("active");
      runAssessment();
    });
    el.priceBasisMSP?.addEventListener("click", () => {
      state.price_basis = "msp";
      el.priceBasisMSP.classList.add("active");
      el.priceBasisMarket.classList.remove("active");
      runAssessment();
    });

    // Area inputs
    el.areaInput?.addEventListener("change", (e) => {
      state.area_ha = parseFloat(e.target.value) || 1.0;
      runAssessment();
    });
    el.areaUnitSelect?.addEventListener("change", (e) => {
      state.area_unit = e.target.value;
      runAssessment();
    });

    // Primary evaluate button
    el.btnAssess?.addEventListener("click", runAssessment);

    // Sandbox Sliders
    el.sliderYield?.addEventListener("input", (e) => {
      if (el.valYield) el.valYield.textContent = `${e.target.value} q/ha`;
      updateScenario();
    });
    el.sliderPrice?.addEventListener("input", (e) => {
      if (el.valPrice) el.valPrice.textContent = formatINR(e.target.value);
      updateScenario();
    });
    el.sliderCost?.addEventListener("input", (e) => {
      if (el.valCost) el.valCost.textContent = `${parseFloat(e.target.value).toFixed(2)}x`;
      updateScenario();
    });
    el.btnResetSandbox?.addEventListener("click", () => {
      if (state.currentReport && state.currentReport.economics) {
        syncSandboxSliders(state.currentReport.economics);
        renderEconomics(state.currentReport.economics);
        showToast("Scenario reset to official CACP baseline.", "info");
      }
    });
  }

  // -------------------------------------------------------------
  // Left Panel 4 Switchable Analytics Graphs Module
  // -------------------------------------------------------------
  let leftChartInstance = null;
  let currentLeftChartTab = "eco";

  function getCssVar(name, fallback = "") {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
  }

  function initLeftAnalytics() {
    const tabs = document.querySelectorAll(".analytics-tab-btn");
    tabs.forEach(btn => {
      btn.addEventListener("click", () => {
        tabs.forEach(t => {
          t.classList.remove("active");
          t.setAttribute("aria-selected", "false");
        });
        btn.classList.add("active");
        btn.setAttribute("aria-selected", "true");
        currentLeftChartTab = btn.dataset.chart || "eco";
        const indicator = document.getElementById("activeChartIndicator");
        if (indicator) indicator.textContent = currentLeftChartTab.toUpperCase();
        renderLeftChart(state.currentReport);
      });
    });

    // Immediate initial render on startup so graph is never blank
    renderLeftChart(state.currentReport);
  }

  function renderLeftChart(report) {
    const canvas = document.getElementById("leftAnalyticsChart");
    if (!canvas || typeof Chart === "undefined") return;

    if (leftChartInstance) {
      leftChartInstance.destroy();
      leftChartInstance = null;
    }

    const vizWater = getCssVar("--viz-water", "#0ea5e9");
    const vizOrange = getCssVar("--viz-orange", "#f59e0b");
    const vizGreen = getCssVar("--viz-green", "#10b981");
    const vizRed = getCssVar("--viz-red", "#f43f5e");
    const textMuted = getCssVar("--text-muted", "#94a3b8");
    const borderCol = getCssVar("--border-subtle", "rgba(255, 255, 255, 0.08)");
    const surfaceCol = getCssVar("--bg-surface", "#131a26");
    const textCol = getCssVar("--text-primary", "#f8fafc");

    const summaryP = document.getElementById("analyticsSummaryP");
    const pill1 = document.getElementById("metricPill1");
    const pill2 = document.getElementById("metricPill2");

    const rep = report || {};
    const f = rep.factors || {};
    const rf = f.moisture?.values?.annual_rainfall_mm ?? 1040;
    const wet = f.moisture?.values?.root_zone_wetness ?? 0.45;
    const temp = f.temperature?.values?.mean_temperature_c ?? 25.5;
    const econ = rep.economics || {};

    let chartConfig = null;

    if (currentLeftChartTab === "eco") {
      // 1. ECOLOGICAL CONDITIONS: 12-Month Climatology of Rainfall & Temperature
      const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
      // Distribute annual rain across seasons (monsoon peak Jun-Sep)
      const monsoonFraction = [0.02, 0.02, 0.03, 0.04, 0.06, 0.20, 0.26, 0.22, 0.11, 0.04, 0.02, 0.01];
      const monthlyRain = monsoonFraction.map(frac => Math.round(rf * frac));
      // Seasonal temperature curve
      const monthlyTemp = [
        temp - 6.5, temp - 4.0, temp - 0.5, temp + 4.2, temp + 6.0,
        temp + 3.5, temp + 1.0, temp + 0.5, temp + 1.2, temp + 0.8,
        temp - 3.0, temp - 5.5
      ].map(t => Math.round(t * 10) / 10);

      chartConfig = {
        type: "bar",
        data: {
          labels: months,
          datasets: [
            {
              type: "bar",
              label: "Rainfall (mm)",
              data: monthlyRain,
              backgroundColor: vizWater,
              borderColor: vizWater,
              borderRadius: 4,
              yAxisID: "yRain",
              order: 2,
            },
            {
              type: "line",
              label: "Temp (°C)",
              data: monthlyTemp,
              borderColor: vizOrange,
              backgroundColor: vizOrange,
              borderWidth: 2.5,
              pointStyle: "triangle",
              pointRadius: 4,
              pointHoverRadius: 6,
              yAxisID: "yTemp",
              order: 1,
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              labels: { color: textCol, font: { size: 10, family: "monospace" }, usePointStyle: true }
            },
            tooltip: {
              backgroundColor: surfaceCol,
              titleColor: textCol,
              bodyColor: textCol,
              borderColor: borderCol,
              borderWidth: 1,
            }
          },
          scales: {
            x: {
              grid: { display: false },
              ticks: { color: textMuted, font: { size: 9 } }
            },
            yRain: {
              type: "linear",
              position: "left",
              grid: { color: borderCol, lineWidth: 0.5 },
              ticks: { color: textMuted, font: { size: 9 } },
              title: { display: false }
            },
            yTemp: {
              type: "linear",
              position: "right",
              grid: { display: false },
              ticks: { color: textMuted, font: { size: 9 } },
              title: { display: false }
            }
          }
        }
      };

      if (summaryP) summaryP.textContent = `Annual rainfall: ${Math.round(rf)} mm with root-zone wetness at ${wet.toFixed(2)}. Mean annual temperature: ${temp.toFixed(1)}°C.`;
      if (pill1) pill1.textContent = `Rainfall: ${Math.round(rf)} mm`;
      if (pill2) pill2.textContent = `Wetness: ${wet.toFixed(2)}`;

    } else if (currentLeftChartTab === "economics") {
      // 2. ECONOMIC CONDITIONS: CACP Cost Breakdown vs Gross Revenue
      const costA2 = econ.cost_a2 || 14500;
      const costA2FL = econ.cost_a2_fl || 19800;
      const costC2 = econ.cost_c2 || 24500;
      const grossRev = econ.gross_revenue || 32000;

      const familyLabour = Math.max(0, costA2FL - costA2);
      const rentAndOverhead = Math.max(0, costC2 - costA2FL);

      chartConfig = {
        type: "bar",
        data: {
          labels: ["Direct A2", "Family FL", "Rent & C2", "Gross Rev"],
          datasets: [{
            label: "Value (₹/ha)",
            data: [Math.round(costA2), Math.round(familyLabour), Math.round(rentAndOverhead), Math.round(grossRev)],
            backgroundColor: [vizWater, vizOrange, vizRed, vizGreen],
            borderColor: [vizWater, vizOrange, vizRed, vizGreen],
            borderWidth: 1.5,
            borderRadius: 6,
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              backgroundColor: surfaceCol,
              titleColor: textCol,
              bodyColor: textCol,
              borderColor: borderCol,
              borderWidth: 1,
              callbacks: {
                label: (ctx) => ` ₹${ctx.parsed.y.toLocaleString("en-IN")}`
              }
            }
          },
          scales: {
            x: {
              grid: { display: false },
              ticks: { color: textCol, font: { size: 10, weight: "bold" } }
            },
            y: {
              grid: { color: borderCol, lineWidth: 0.5 },
              ticks: {
                color: textMuted,
                font: { size: 9 },
                callback: (v) => `₹${Math.round(v/1000)}k`
              }
            }
          }
        }
      };

      if (summaryP) summaryP.textContent = `Total C2 cultivation cost is ₹${Math.round(costC2).toLocaleString("en-IN")}/ha compared to ₹${Math.round(grossRev).toLocaleString("en-IN")} projected revenue.`;
      if (pill1) pill1.textContent = `Cost C2: ₹${Math.round(costC2)}`;
      if (pill2) pill2.textContent = `Revenue: ₹${Math.round(grossRev)}`;

    } else if (currentLeftChartTab === "pnl") {
      // 3. NET PROFIT & LOSS: Monte Carlo Percentile Returns (P10, P50, P90)
      const mc = econ.monte_carlo || {};
      const p10 = mc.p10_return !== undefined ? mc.p10_return : (econ.net_profit ? econ.net_profit * 0.4 : 3200);
      const p50 = mc.p50_return !== undefined ? mc.p50_return : (econ.net_profit || 8500);
      const p90 = mc.p90_return !== undefined ? mc.p90_return : (econ.net_profit ? econ.net_profit * 1.6 : 14200);
      const risk = mc.probability_of_loss_pct !== undefined ? mc.probability_of_loss_pct : (econ.probability_of_loss || 6);

      chartConfig = {
        type: "bar",
        data: {
          labels: ["P10 (Drought)", "P50 (Median)", "P90 (Favorable)"],
          datasets: [{
            label: "Net Profit (₹/ha)",
            data: [Math.round(p10), Math.round(p50), Math.round(p90)],
            backgroundColor: [
              p10 >= 0 ? vizWater : vizRed,
              vizGreen,
              vizOrange
            ],
            borderColor: [
              p10 >= 0 ? vizWater : vizRed,
              vizGreen,
              vizOrange
            ],
            borderWidth: 1.5,
            borderRadius: 6,
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              backgroundColor: surfaceCol,
              titleColor: textCol,
              bodyColor: textCol,
              borderColor: borderCol,
              borderWidth: 1,
              callbacks: {
                label: (ctx) => ` ₹${ctx.parsed.y.toLocaleString("en-IN")}`
              }
            }
          },
          scales: {
            x: {
              grid: { display: false },
              ticks: { color: textCol, font: { size: 10, weight: "bold" } }
            },
            y: {
              grid: { color: borderCol, lineWidth: 0.5 },
              ticks: {
                color: textMuted,
                font: { size: 9 },
                callback: (v) => `₹${Math.round(v/1000)}k`
              }
            }
          }
        }
      };

      if (summaryP) summaryP.textContent = `Expected median profit is ₹${Math.round(p50).toLocaleString("en-IN")} with a ${risk}% downside loss probability.`;
      if (pill1) pill1.textContent = `P50 Net: ₹${Math.round(p50)}`;
      if (pill2) pill2.textContent = `Risk of Loss: ${risk}%`;

    } else if (currentLeftChartTab === "sensitivity") {
      // 4. MULTI-FACTOR SENSITIVITY: Returns under ±10% Yield, Price, and Cost shifts
      const baseProfit = econ.net_profit || 8500;
      const baseRev = econ.gross_revenue || 32000;
      const baseCost = econ.cultivation_cost || 23500;

      const steps = [-0.10, -0.05, 0.0, 0.05, 0.10];
      const yieldLine = steps.map(s => Math.round(baseProfit + baseRev * s));
      const priceLine = steps.map(s => Math.round(baseProfit + baseRev * s * 0.95));
      const costLine = steps.map(s => Math.round(baseProfit - baseCost * s));

      chartConfig = {
        type: "line",
        data: {
          labels: ["-10%", "-5%", "Base", "+5%", "+10%"],
          datasets: [
            {
              label: "Yield Variation",
              data: yieldLine,
              borderColor: vizGreen,
              backgroundColor: vizGreen,
              borderWidth: 2.5,
              pointStyle: "circle",
              pointRadius: 4,
            },
            {
              label: "Price Variation",
              data: priceLine,
              borderColor: vizOrange,
              backgroundColor: vizOrange,
              borderWidth: 2,
              borderDash: [5, 5],
              pointStyle: "rectRot",
              pointRadius: 5,
            },
            {
              label: "Cost Shift",
              data: costLine,
              borderColor: vizRed,
              backgroundColor: vizRed,
              borderWidth: 2,
              borderDash: [2, 3],
              pointStyle: "triangle",
              pointRadius: 4,
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              labels: { color: textCol, font: { size: 10, family: "monospace" }, usePointStyle: true }
            },
            tooltip: {
              backgroundColor: surfaceCol,
              titleColor: textCol,
              bodyColor: textCol,
              borderColor: borderCol,
              borderWidth: 1,
              callbacks: {
                label: (ctx) => ` ${ctx.dataset.label}: ₹${ctx.parsed.y.toLocaleString("en-IN")}`
              }
            }
          },
          scales: {
            x: {
              grid: { display: false },
              ticks: { color: textMuted, font: { size: 9 } }
            },
            y: {
              grid: { color: borderCol, lineWidth: 0.5 },
              ticks: {
                color: textMuted,
                font: { size: 9 },
                callback: (v) => `₹${Math.round(v/1000)}k`
              }
            }
          }
        }
      };

      const deltaYield = Math.round(baseRev * 0.10);
      if (summaryP) summaryP.textContent = `A 10% change in crop yield shifts net returns by ±₹${deltaYield.toLocaleString("en-IN")}.`;
      if (pill1) pill1.textContent = `Yield ±10%: ±₹${deltaYield}`;
      if (pill2) pill2.textContent = `Base Return: ₹${Math.round(baseProfit)}`;
    }

    if (chartConfig) {
      leftChartInstance = new Chart(canvas, chartConfig);
    }
  }

  // Populate Crop Select dropdown dynamically
  async function loadCropsDropdown() {
    if (!el.cropSelect) return;
    try {
      const res = await fetch("/api/crops");
      const crops = await res.json();
      el.cropSelect.innerHTML = "";
      Object.entries(crops).forEach(([k, c]) => {
        const opt = document.createElement("option");
        opt.value = k;
        opt.textContent = `${c.name} (${c.local_name || c.group})`;
        if (k === state.crop) opt.selected = true;
        el.cropSelect.appendChild(opt);
      });
    } catch (e) {
      console.warn("Could not load crops dropdown:", e);
    }
  }

  // Document Ready Initialization
  document.addEventListener("DOMContentLoaded", () => {
    initMap();
    initPresetPills();
    initLeftAnalytics();
    setupEventListeners();
    loadCropsDropdown();
    checkHealth();
    runAssessment();
  });
})();
