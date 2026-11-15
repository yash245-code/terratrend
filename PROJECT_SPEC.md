# TerraTrend: Master Feature List, Architecture & Roadmap Specification
**NASA Space Apps Challenge 2026 — "Be An Earth System Trend Detective!"**

---

## Part 1: Feature List & Architectural Alignment

### A. What the User Sees (Core Product)
- **Location Input**: Map click, lat/lon manual entry, or place-name / district search. Strict validation against the official Government of India (Survey of India) boundary polygon, covering all 28 States and 8 Union Territories (including Andaman & Nicobar, Lakshadweep, Jammu & Kashmir, and Ladakh).
- **Region Lookup**: Automatic reverse spatial resolution to State/UT and District; instant HTTP 422 `OUT_OF_INDIA` rejection for coordinates outside sovereign territory.
- **5-Factor Land Report Card**:
  1. *Temperature* (GLDAS 2m, MERRA-2, AIRS)
  2. *Moisture* (GLDAS root-zone 0–100cm, MERRA-2 wetness)
  3. *Soil pH* (HWSD v2.0 topsoil)
  4. *Soil Quality* (HWSD organic carbon, CEC, drainage/texture)
  5. *Climate Stability* (GPM IMERG / GLDAS precipitation CV and heat anomaly)
  - Each factor displays: **GOOD / MODERATE / POOR** rating, 0–100 continuous score, measured value, agronomic ideal range, plain-language explanation, and confidence level (`high`, `medium`, `low`).
- **Overall Verdict**:
  - Continuous weighted score across factors.
  - **Liebig's Weak-Link Capping Rule**: If any single factor is rated **POOR** ($< 70$), the overall composite score is capped at **69.0**, and limiting factors are explicitly named.
- **Trend & 10-Year Outlook**: Verified long-term trajectory (*Improving*, *Stable*, or *Worsening*) based strictly on statistically significant trends ($p < 0.05$).
- **Crop Suitability Ranking**:
  - Ranked suitabilities for 24 Indian field crops across seasons (*Kharif*, *Rabi*, *Zaid*, and *Annual*) and regimes (*Rainfed* vs. *Irrigated*).
  - Explicit flagging of misfits / unfavorable crops.
  - Automated detection of the single **"Balanced Pick"** combining agronomic score and high ROI.
- **Comprehensive Crop Economics (CACP Standard)**:
  - Expected yield (quintals/ha), Gross revenue, Cultivation cost ($A_2+FL$ and $C_2$).
  - Net Profit/Loss, ROI (%), Benefit-Cost Ratio (BCR), Break-Even Yield, Break-Even Price, Margin of Safety (%), Return per day, and 10-Year ROI Outlook.
- **Risk Analysis**:
  - Probability of loss ($\Pr(\text{Net Return} < 0)$).
  - Deterministic 5,000-draw lognormal Monte Carlo risk bands ($P_{10}$ worst-case, $P_{50}$ median, $P_{90}$ best-case).
  - Sensitivity tornado table ($\pm 10\%$ shifts in yield, market price, and input cost).
- **Interactive Scenario Sandbox**:
  - Real-time simulation sliders for farm area (ha/acres), land tenure (*Owned* vs. *Leased*), yield override, mandi price override, and cost inflation multiplier.
- **Industry & Institutional Factors**:
  - Mandi modal prices, seasonality, and best selling months.
  - Input costs and labour breakdown.
  - Irrigation requirement gap and historical drought-year frequency.
  - Minimum Support Price (MSP) floor protection, PMFBY crop insurance premiums, and institutional credit scheme integration.
  - Post-harvest storage and transit losses ($\lambda_{\text{loss}}$).
- **Targeted Improvement Actions**:
  - Agronomic soil amendments and physical practices (agricultural lime, gypsum, organic mulching, drip irrigation, biochar), accompanied by the mandatory disclaimer: *"Confirm with a certified soil test before applying amendments."*
- **Trend-Based Adaptation Advice**:
  - Strict $p < 0.05$ significance gate preventing hasty crop shifts; platform advises *"keep your rotation"* unless a multi-decadal shift is scientifically proven.

---

### B. Scientific & Data Layer
- **Six NASA Earth Observation Datasets**:
  1. *NASA GLDAS 2.1 NOAH* (0.25°, 2005–present): 2m temperature, rainfall, root moisture, evapotranspiration.
  2. *NASA MERRA-2* (0.5° × 0.625°): Temperature, root wetness, precipitation, atmospheric parameters.
  3. *NASA GPM IMERG Final Run V07* (0.1°): Multi-satellite precipitation accumulation.
  4. *NASA MODIS Terra/Aqua MOD13C2/MYD13C2* (0.05°): NDVI vegetation vigor and EVI canopy health.
  5. *NASA AIRS/Aqua* (1.0°): Atmospheric thermal infrared validation layer.
  6. *NASA Aura OMI OMNO2d* (0.25°): Tropospheric $\text{NO}_2$ column density.
  - *Plus HWSD v2.0 Global Soil Grid* via NASA ORNL DAAC: Soil pH, reference bulk density, organic carbon, drainage, and CEC.
- **Statistical Trend Forensics**:
  - **Hamed-Rao (1998) Modified Mann-Kendall**: Computes the empirical rank autocorrelation $\rho_S(i)$ across all significant lags ($|\rho_S(i)| > 1.96/\sqrt{n}$) to scale the test statistic variance $\text{Var}^*(S)$, preventing up to 40% false positives from monsoon persistence.
  - **Theil-Sen Robust Median Slope**: Breakdown point of 29.3%, impervious to cloud outliers and sensor recalibrations.
  - Kendall's rank correlation $\tau$, standard $Z$-score, percentage change, and standardized change ($\Delta\sigma$).
- **Cross-Dataset Consensus**:
  - Hierarchy: `STRONG` (all sources agree in direction and significance), `MODERATE` (majority agree), `WEAK` (magnitude divergence), `CONFLICTING` (directional contradiction), and `SINGLE_SOURCE`.
  - Consensus directly modulates the reported confidence level.
- **Vegetation Confirmation**:
  - Hydro-climatic drying trends are checked against co-located MODIS NDVI trajectories to confirm biological stress.
- **Data Engineering**:
  - Common 0.25° sovereign grid extent (6.0°N–38.0°N, 68.0°E–98.0°E).
  - Island and coastal fallback logic: 30 km spatial nearest-neighbor search for land-surface models on coastal enclaves while directly retaining unmasked atmospheric fields.
  - SHA-256 hash checksums, DAAC URIs, and persistent DOIs in provenance metadata.
- **Economic Data Layer**:
  - CACP Comprehensive Scheme for Studying Cost of Cultivation (CSCoC).
  - Directorate of Economics & Statistics (DES) historical benchmark yields.
  - Agmarknet mandi modal prices, seasonal arrival indices, and statutory MSP notifications.

---

### C. Engineering Architecture
- **Monolithic In-Memory Architecture**: Single-server Python Flask application loading pre-indexed boundary polygons, CACP datasets, and NetCDF raster cubes directly into RAM for sub-50ms queries.
- **RESTful API**:
  - `POST /api/assess`: Complete land report card and default crop economics.
  - `GET /api/assess`: URL parameter query support.
  - `POST /api/economics`: Real-time farm financial and scenario calculation.
  - `GET /api/region`: Reverse spatial boundary resolution.
  - `GET /api/soil`: Dedicated HWSD soil parameters.
  - `GET /api/crops`: Complete catalog of 24 crops with agro-climatic requirements.
  - `GET /api/analyze`: Single-indicator Hamed-Rao time-series evaluation.
  - `GET /api/consensus`: Cross-sensor consensus for indicator groups.
  - `GET /api/geocode`: District name geocoder.
  - `GET /api/health`: CubeStore and spatial engine health diagnostics.
  - `GET /api/datasets` & `GET /api/provenance`: Data lineage, hashes, and DAAC citations.
- **Graceful Degradation**: Missing optional layers downgrade confidence rather than failing requests.
- **Offline Test Suite**: 100% pass rate across 70 tests verifying math, spatial containment, economics, and edge cases.

---

### D. User Interface & Experience
- **Navigation Structure**:
  - `Home` (`/`): High-impact mission landing page with real-time metrics and 3-pillar feature showcase.
  - `Decision Engine` (`/decision`): Farm parameters, Leaflet map, 5-factor meters, best-suited crops, CACP financial KPI cards, Monte Carlo distributions, and scenario sandbox.
  - `Trend Explorer` (`/explorer`): Fullscreen GIS inspector with High-DPI Canvas time series and Sen's slope overlays.
  - `Methodology & Science` (`/methodology`): Comprehensive editorial documentation covering mathematical derivations and economic definitions.
- **Design System**:
  - Clean, high-contrast obsidian canvas (`#060709`, `#0a0d12`, `#0f141d`) with razor-sharp borders (`rgba(255, 255, 255, 0.08)` to `0.16`).
  - **JetBrains Mono** typography throughout all headings, metrics, tables, and controls.
  - CartoDB dark basemap bounded strictly to India's sovereign territory.

---

## Part 2: Roadmap & Improvement Areas (Living Backlog)

### 1. Accuracy & Validation (Highest Priority)
- [ ] **District Yield Back-Testing**: Compare computed suitability scores against empirical DES district yields (e.g., Akola cotton, Ludhiana wheat, Burdwan rice) to fit a calibrated score-to-yield regression.
- [ ] **IMD Climate Cross-Validation**: Compare GLDAS and MERRA-2 gridded rainfall/temperature against Indian Meteorological Department (IMD) 0.25° gridded observations.
- [ ] **User Soil Test Override**: Allow users to input their certified Soil Health Card parameters (tested pH, organic carbon, NPK) to supersede coarse 1 km HWSD values.
- [ ] **SMAP Observational Integration**: Incorporate NASA SMAP L3/L4 radiometer-measured soil moisture alongside modeled GLDAS Noah.

### 2. Science Depth
- [ ] **Daily Extremes & Agrometeorology**: Ingest daily data to detect heat waves (>40°C during grain filling), dry spells (>14 consecutive days during monsoon), and frost dates.
- [ ] **Aridity & Evapotranspiration Indices**: Compute Penman-Monteith potential evapotranspiration (PET), UNEP Aridity Index, and Standardized Precipitation Evapotranspiration Index (SPEI).
- [ ] **Growing Degree Days (GDD)**: Base-temperature accumulation curves per crop.
- [ ] **Pettitt & Buishand Breakpoint Tests**: Detect sudden shifts vs. monotonic gradual trends.

### 3. Economics Depth
- [ ] **Multi-Season Crop Rotations**: Model annual rotation economics (e.g., Paddy-Wheat in Punjab, Cotton-Gram in Vidarbha, Soya-Wheat in Malwa).
- [ ] **Live Mandi Integration & Nearest-Market Finder**: Real-time Agmarknet mandi scraping with distance-based transport cost deduction.
- [ ] **Horticulture & Cash Crops**: Expand from 24 field crops to fruits (mango, banana, citrus) and spices (chilli, turmeric).
- [ ] **Cash-Flow Timelines**: Month-by-month cash outflows (sowing, weeding, harvesting) and inflow timing.

### 4. User Experience & Accessibility
- [ ] **Multilingual Support (Hindi & Regional)**: Localization in Hindi, Marathi, Punjabi, Telugu, and Tamil.
- [ ] **Low-Bandwidth Farmer Mode**: Ultra-lightweight card view with large vernacular text and high-contrast color indicators.
- [ ] **WhatsApp / PDF Shareable Export**: One-click generation of a branded PDF land report card.
- [ ] **Plot Boundary KML/GeoJSON Upload**: Allow farmers to draw or upload their survey number plot boundaries.

### 5. Product & Scalability
- [ ] **Precomputed Territorial Grid Raster**: Pre-evaluate all ~8,000 Indian 0.25° grid cells to enable instantaneous zero-compute responses.
- [ ] **Extension-Worker Batch Mode**: Multi-point assessment tool for Krishi Vigyan Kendras (KVKs) and FPOs.
- [ ] **SMS / WhatsApp Climate Alerts**: Proactive notification when a tracked farm cell registers a statistically significant drying or warming trend.
