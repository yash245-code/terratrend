"""TeraTrend system configuration and registries.

Geospatial agricultural decision-support web app for India.
NASA Space Apps Challenge 2026.
"""
from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

# Base paths
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
BOUNDARIES_DIR = DATA_DIR / "boundaries"
CROPS_DIR = DATA_DIR / "crops"
RULES_DIR = DATA_DIR / "rules"
ECONOMICS_DIR = DATA_DIR / "economics"
SEED_DIR = DATA_DIR / "seed"
SEED_CROPS_DIR = SEED_DIR / "crops"
SEED_RULES_DIR = SEED_DIR / "rules"
SEED_ECONOMICS_DIR = SEED_DIR / "economics"

# Scientific core constants
ALPHA = 0.05
ANNUAL_FREQ = "YE"
MIN_YEARS_FOR_TREND = 10
TREND_PER_YEARS = 10
MIN_CONSENSUS_OVERLAP_YEARS = 10
MAX_LAND_FALLBACK_KM = 30.0

# Geographic domain for India (6.0°N–38.0°N, 68.0°E–98.0°E)
GRID_RESOLUTION = 0.25
BBOX_INDIA = (68.0, 6.0, 98.0, 38.0)  # min_lon, min_lat, max_lon, max_lat
INDIA_STATES_GEOJSON = BOUNDARIES_DIR / "india_states.geojson"
INDIA_DISTRICTS_GEOJSON = BOUNDARIES_DIR / "india_districts.geojson"
INDIA_GRID_NC = PROCESSED_DIR / "india_grid.nc"
PROVENANCE_JSON = PROCESSED_DIR / "provenance.json"

# Scoring parameters (starting agronomic values to be reviewed by agronomists)
BASELINE_YEARS = 10
OUTLOOK_YEARS = 10

RATING_GOOD_THRESHOLD = 70.0
RATING_MODERATE_THRESHOLD = 40.0
POOR_SCORE_CAP = 69.0

FACTOR_WEIGHTS = {
    "temperature": 0.20,
    "moisture": 0.25,
    "soil_ph": 0.15,
    "soil_quality": 0.20,
    "climate": 0.20,
}

# General agronomic trapezoids: (abs_min, opt_min, opt_max, abs_max)
TRAPEZOIDS = {
    "temperature": (8.0, 17.0, 29.0, 36.0),       # Annual mean temp °C
    "rainfall": (250.0, 600.0, 1500.0, 3000.0),    # Annual rainfall mm
    "root_wetness": (0.10, 0.35, 0.80, 1.0),       # Fraction 0-1
    "soil_ph": (4.5, 6.0, 7.5, 9.0),               # Topsoil pH
    "soil_oc": (0.10, 0.80, 4.0, 12.0),            # Organic carbon %
    "soil_cec": (3.0, 10.0, 40.0, 80.0),           # CEC cmol/kg
    "growing_months": (2.0, 4.0, 8.0, 12.0),       # Favorable months count
}

# Soil quality component weights
SOIL_QUALITY_WEIGHTS = {
    "organic_carbon": 0.25,
    "texture": 0.20,
    "cec": 0.15,
    "drainage": 0.15,
    "salinity": 0.15,
    "sodicity": 0.10,
}

# Texture quality scores (0-100)
TEXTURE_SCORES = {
    "loam": 100.0,
    "silt_loam": 95.0,
    "clay_loam": 90.0,
    "sandy_clay_loam": 85.0,
    "sandy_loam": 80.0,
    "silty_clay_loam": 80.0,
    "clay": 65.0,
    "silty_clay": 65.0,
    "loamy_sand": 55.0,
    "sand": 35.0,
    "heavy_clay": 50.0,
    "deep_black_clay": 85.0,
}

# Drainage quality scores (0-100)
DRAINAGE_SCORES = {
    "well": 100.0,
    "moderately_well": 90.0,
    "somewhat_excessively": 75.0,
    "imperfectly": 60.0,
    "excessively": 50.0,
    "poorly": 40.0,
    "very_poorly": 25.0,
}

# Climate factor weights
CLIMATE_WEIGHTS = {
    "growing_months": 0.30,
    "rainfall_reliability": 0.25,
    "thermal_stress": 0.20,
    "vegetation_productivity": 0.25,
}

# Economics parameters
YIELD_FACTOR_CURVE = {
    0.0: 0.40,
    40.0: 0.75,
    70.0: 1.00,
    100.0: 1.20,
}
DEFAULT_COST_BASIS = "a2_fl"
DEFAULT_PRICE_BASIS = "market"
MC_DRAWS = 5000
PRICE_CV_BY_GROUP = {
    "cereals": 0.10,
    "pulses": 0.15,
    "oilseeds": 0.15,
    "fibre": 0.15,
    "commercial": 0.10,
    "vegetables": 0.40,
}
DEFAULT_PRICE_CV = 0.15
DEFAULT_COST_CV = 0.05
YIELD_PRICE_CORRELATION = -0.20

# Environment / Feature toggles
ENABLE_SOILGRIDS_LIVE = os.getenv("ENABLE_SOILGRIDS_LIVE", "false").lower() == "true"
GEOCODER_USER_AGENT = os.getenv("GEOCODER_USER_AGENT", "TeraTrend-App/1.0 (contact@teratrend.org)")
DATA_GOV_IN_API_KEY = os.getenv("DATA_GOV_IN_API_KEY", "")
DOWNLOAD_BACKEND = os.getenv("DOWNLOAD_BACKEND", "auto")

# ---------------------------------------------------------
# DATASET REGISTRY
# ---------------------------------------------------------
DATASETS = {
    "gldas": {
        "key": "gldas",
        "label": "GLDAS Noah L4 Monthly 0.25°",
        "provider": "NASA GES DISC",
        "collection": "GLDAS_NOAH025_M",
        "version": "2.1",
        "concept_id": "C1342986036-GES_DISC",
        "doi": "10.5067/9VO19KM6ZTR3",
        "cube_path": PROCESSED_DIR / "gldas_cube.nc",
        "native_res": 0.25,
        "regrid_method": "native_gldas",
        "required": True,
        "static": False,
        "land_masked": True,
        "min_valid_months": 12,
        "annual_method": "standard",
        "variables": {
            "SoilMoi0_10cm_inst": {"name": "surface_moisture", "unit": "kg/m^2", "scale": 1.0, "fill": -9999.0},
            "SoilMoi10_40cm_inst": {"name": "root_moisture_l2", "unit": "kg/m^2", "scale": 1.0, "fill": -9999.0},
            "SoilMoi40_100cm_inst": {"name": "root_moisture_l3", "unit": "kg/m^2", "scale": 1.0, "fill": -9999.0},
            "Tair_f_inst": {"name": "air_temperature", "unit": "K", "scale": 1.0, "fill": -9999.0},
            "Rainf_f_tavg": {"name": "rainfall_flux", "unit": "kg/m^2/s", "scale": 1.0, "fill": -9999.0},
            "Evap_tavg": {"name": "evapotranspiration_flux", "unit": "kg/m^2/s", "scale": 1.0, "fill": -9999.0},
        }
    },
    "merra2": {
        "key": "merra2",
        "label": "MERRA-2 Monthly Atmospheric & Land Assimilation",
        "provider": "NASA GES DISC / GMAO",
        "collection": "M2TMNXSLV / M2TMNXFLX / M2TMNXLND",
        "version": "5.12.4",
        "concept_ids": ["C1276812859-GES_DISC", "C1276812868-GES_DISC", "C1276812856-GES_DISC"],
        "doi": "10.5067/0J5VGDOSB07B",
        "cube_path": PROCESSED_DIR / "merra2_cube.nc",
        "native_res": 0.5,
        "regrid_method": "bilinear_interp",
        "required": False,
        "static": False,
        "land_masked": False,  # Atmospheric variables cover coasts/islands directly
        "min_valid_months": 12,
        "annual_method": "standard",
        "variables": {
            "T2M": {"name": "air_temperature", "unit": "K", "scale": 1.0, "fill": 1e15},
            "PRECTOTCORR": {"name": "rainfall_flux", "unit": "kg/m^2/s", "scale": 1.0, "fill": 1e15},
            "EVAP": {"name": "evapotranspiration_flux", "unit": "kg/m^2/s", "scale": 1.0, "fill": 1e15},
            "GWETROOT": {"name": "root_wetness", "unit": "fraction", "scale": 1.0, "fill": 1e15},
            "GWETTOP": {"name": "surface_wetness", "unit": "fraction", "scale": 1.0, "fill": 1e15},
        }
    },
    "gpm": {
        "key": "gpm",
        "label": "GPM IMERG Final Monthly Precipitation v07",
        "provider": "NASA GES DISC",
        "collection": "GPM_3IMERGM",
        "version": "07",
        "concept_id": "C2723754851-GES_DISC",
        "doi": "10.5067/GPM/IMERG/3B-MONTH/07",
        "cube_path": PROCESSED_DIR / "gpm_cube.nc",
        "native_res": 0.10,
        "regrid_method": "bilinear_interp",
        "required": False,
        "static": False,
        "land_masked": False,
        "min_valid_months": 12,
        "annual_method": "standard",
        "variables": {
            "precipitation": {"name": "rainfall_rate", "unit": "mm/hr", "scale": 1.0, "fill": -9999.9}
        }
    },
    "modis": {
        "key": "modis",
        "label": "MODIS/Terra Vegetation Indices Monthly CMG 0.05°",
        "provider": "NASA LP DAAC",
        "collection": "MOD13C2",
        "version": "061",
        "concept_id": "C2565788914-LPCLOUD",
        "doi": "10.5067/MODIS/MOD13C2.061",
        "cube_path": PROCESSED_DIR / "modis_cube.nc",
        "native_res": 0.05,
        "regrid_method": "area_mean_coarsen_5x",
        "required": False,
        "static": False,
        "land_masked": True,
        "min_valid_months": 12,
        "annual_method": "standard",
        "variables": {
            "NDVI": {"name": "ndvi", "unit": "unitless", "scale": 0.0001, "fill": -3000},
            "EVI": {"name": "evi", "unit": "unitless", "scale": 0.0001, "fill": -3000},
            "pixel_reliability": {"name": "pixel_reliability", "unit": "flag", "scale": 1.0, "fill": -1}
        }
    },
    "airs": {
        "key": "airs",
        "label": "AIRS Level 3 Monthly Surface Temperature & Humidity",
        "provider": "NASA GES DISC",
        "collection": "AIRS3STM",
        "version": "7.0",
        "concept_id": "C1701805662-GES_DISC",
        "doi": "10.5067/AIRS/AIRS3STM.007",
        "cube_path": PROCESSED_DIR / "airs_cube.nc",
        "native_res": 1.0,
        "regrid_method": "bilinear_interp",
        "required": False,
        "static": False,
        "land_masked": False,
        "min_valid_months": 12,
        "annual_method": "standard",
        "variables": {
            "SurfAirTemp_A": {"name": "surf_air_temp_asc", "unit": "K", "scale": 1.0, "fill": -9999.0},
            "SurfAirTemp_D": {"name": "surf_air_temp_desc", "unit": "K", "scale": 1.0, "fill": -9999.0},
            "SurfRelHum_A": {"name": "surf_rel_hum_asc", "unit": "%", "scale": 1.0, "fill": -9999.0},
            "SurfRelHum_D": {"name": "surf_rel_hum_desc", "unit": "%", "scale": 1.0, "fill": -9999.0},
        }
    },
    "omi": {
        "key": "omi",
        "label": "OMI Level 3 Daily Tropospheric NO2 & Total Ozone",
        "provider": "NASA GES DISC",
        "collection": "OMNO2d / OMTO3d",
        "version": "003",
        "concept_ids": ["C1266136111-GES_DISC", "C1266136070-GES_DISC"],
        "doi": "10.5067/Aura/OMI/DATA3007",
        "cube_path": PROCESSED_DIR / "omi_cube.nc",
        "native_res": 0.25,
        "regrid_method": "daily_to_monthly_accumulator",
        "required": False,
        "static": False,
        "land_masked": False,
        "min_valid_months": 9,
        "annual_method": "anomaly",
        "variables": {
            "ColumnAmountNO2TropCloudScreened": {"name": "no2", "unit": "1e15 molec/cm^2", "scale": 1e-15, "fill": -1.26765e30},
            "ColumnAmountO3": {"name": "ozone", "unit": "DU", "scale": 1.0, "fill": -1.26765e30}
        }
    },
    "hwsd": {
        "key": "hwsd",
        "label": "Harmonized World Soil Database v1.2 (Regridded NetCDF)",
        "provider": "NASA ORNL DAAC / FAO / IIASA",
        "collection": "HWSD_1247",
        "version": "1.2",
        "concept_id": "C2216863856-ORNL_CLOUD",
        "doi": "10.3334/ORNLDAAC/1247",
        "cube_path": PROCESSED_DIR / "hwsd_cube.nc",
        "native_res": 0.05,
        "regrid_method": "area_mean_for_continuous_modal_for_categorical",
        "required": True,
        "static": True,
        "land_masked": True,
        "min_valid_months": 1,
        "annual_method": "standard",
        "variables": {
            "T_PH_H2O": {"name": "soil_ph_top", "unit": "pH", "scale": 1.0, "fill": -9.0},
            "S_PH_H2O": {"name": "soil_ph_sub", "unit": "pH", "scale": 1.0, "fill": -9.0},
            "T_OC": {"name": "soil_organic_carbon", "unit": "% weight", "scale": 1.0, "fill": -9.0},
            "T_CEC_SOIL": {"name": "soil_cec", "unit": "cmol/kg", "scale": 1.0, "fill": -9.0},
            "T_SAND": {"name": "soil_sand", "unit": "%", "scale": 1.0, "fill": -9.0},
            "T_SILT": {"name": "soil_silt", "unit": "%", "scale": 1.0, "fill": -9.0},
            "T_CLAY": {"name": "soil_clay", "unit": "%", "scale": 1.0, "fill": -9.0},
            "T_GRAVEL": {"name": "soil_gravel", "unit": "%", "scale": 1.0, "fill": -9.0},
            "T_ECE": {"name": "soil_salinity", "unit": "dS/m", "scale": 1.0, "fill": -9.0},
            "T_ESP": {"name": "soil_sodicity", "unit": "%", "scale": 1.0, "fill": -9.0},
            "DRAINAGE": {"name": "soil_drainage", "unit": "class_code", "scale": 1.0, "fill": -9.0},
            "USDA_TEXTURE": {"name": "soil_texture", "unit": "class_code", "scale": 1.0, "fill": -9.0},
        }
    }
}

# ---------------------------------------------------------
# INDICATORS REGISTRY
# ---------------------------------------------------------
INDICATORS = {
    "root_moisture": {
        "key": "root_moisture",
        "label": "Root-Zone Soil Moisture",
        "unit": "kg/m^2",
        "group": "moisture",
        "aggregation": "mean",
        "primary_source": "gldas",
        "sources": [
            {"dataset": "gldas", "raw_var": "SoilMoi10_40cm_inst", "conversion": "gldas_root_moisture"},
            {"dataset": "merra2", "raw_var": "GWETROOT", "conversion": "none"}
        ]
    },
    "surface_moisture": {
        "key": "surface_moisture",
        "label": "Surface Soil Moisture",
        "unit": "kg/m^2",
        "group": "moisture",
        "aggregation": "mean",
        "primary_source": "gldas",
        "sources": [
            {"dataset": "gldas", "raw_var": "SoilMoi0_10cm_inst", "conversion": "none"},
            {"dataset": "merra2", "raw_var": "GWETTOP", "conversion": "none"}
        ]
    },
    "air_temperature": {
        "key": "air_temperature",
        "label": "2m Air Temperature",
        "unit": "degC",
        "group": "temperature",
        "aggregation": "mean",
        "primary_source": "gldas",
        "sources": [
            {"dataset": "gldas", "raw_var": "Tair_f_inst", "conversion": "kelvin_to_celsius"},
            {"dataset": "merra2", "raw_var": "T2M", "conversion": "kelvin_to_celsius"},
            {"dataset": "airs", "raw_var": "SurfAirTemp", "conversion": "kelvin_to_celsius"}
        ]
    },
    "rainfall": {
        "key": "rainfall",
        "label": "Annual Total Rainfall",
        "unit": "mm/year",
        "group": "moisture",
        "aggregation": "sum",
        "primary_source": "gldas",
        "sources": [
            {"dataset": "gldas", "raw_var": "Rainf_f_tavg", "conversion": "flux_to_mm_month"},
            {"dataset": "merra2", "raw_var": "PRECTOTCORR", "conversion": "flux_to_mm_month"},
            {"dataset": "gpm", "raw_var": "precipitation", "conversion": "mm_per_hour_to_mm_month"}
        ]
    },
    "evapotranspiration": {
        "key": "evapotranspiration",
        "label": "Annual Evapotranspiration",
        "unit": "mm/year",
        "group": "moisture",
        "aggregation": "sum",
        "primary_source": "gldas",
        "sources": [
            {"dataset": "gldas", "raw_var": "Evap_tavg", "conversion": "flux_to_mm_month"},
            {"dataset": "merra2", "raw_var": "EVAP", "conversion": "flux_to_mm_month"}
        ]
    },
    "ndvi": {
        "key": "ndvi",
        "label": "Normalized Difference Vegetation Index",
        "unit": "unitless",
        "group": "vegetation",
        "aggregation": "mean",
        "primary_source": "modis",
        "sources": [
            {"dataset": "modis", "raw_var": "NDVI", "conversion": "modis_scale"}
        ]
    },
    "evi": {
        "key": "evi",
        "label": "Enhanced Vegetation Index",
        "unit": "unitless",
        "group": "vegetation",
        "aggregation": "mean",
        "primary_source": "modis",
        "sources": [
            {"dataset": "modis", "raw_var": "EVI", "conversion": "modis_scale"}
        ]
    },
    "surface_humidity": {
        "key": "surface_humidity",
        "label": "Surface Relative Humidity",
        "unit": "%",
        "group": "climate",
        "aggregation": "mean",
        "primary_source": "airs",
        "sources": [
            {"dataset": "airs", "raw_var": "SurfRelHum", "conversion": "none"}
        ]
    },
    "no2": {
        "key": "no2",
        "label": "Tropospheric NO2 Column",
        "unit": "1e15 molec/cm^2",
        "group": "air_quality",
        "aggregation": "mean",
        "primary_source": "omi",
        "sources": [
            {"dataset": "omi", "raw_var": "ColumnAmountNO2TropCloudScreened", "conversion": "none"}
        ]
    },
    "ozone": {
        "key": "ozone",
        "label": "Total Column Ozone",
        "unit": "DU",
        "group": "air_quality",
        "aggregation": "mean",
        "primary_source": "omi",
        "sources": [
            {"dataset": "omi", "raw_var": "ColumnAmountO3", "conversion": "none"}
        ]
    },

    # Static Soil Indicators
    "soil_ph_top": {
        "key": "soil_ph_top",
        "label": "Topsoil pH (H2O)",
        "unit": "pH",
        "group": "soil_ph",
        "aggregation": "mean",
        "primary_source": "hwsd",
        "sources": [{"dataset": "hwsd", "raw_var": "T_PH_H2O", "conversion": "none"}]
    },
    "soil_ph_sub": {
        "key": "soil_ph_sub",
        "label": "Subsoil pH (H2O)",
        "unit": "pH",
        "group": "soil_ph",
        "aggregation": "mean",
        "primary_source": "hwsd",
        "sources": [{"dataset": "hwsd", "raw_var": "S_PH_H2O", "conversion": "none"}]
    },
    "soil_organic_carbon": {
        "key": "soil_organic_carbon",
        "label": "Soil Organic Carbon",
        "unit": "% weight",
        "group": "soil_quality",
        "aggregation": "mean",
        "primary_source": "hwsd",
        "sources": [{"dataset": "hwsd", "raw_var": "T_OC", "conversion": "none"}]
    },
    "soil_cec": {
        "key": "soil_cec",
        "label": "Cation Exchange Capacity",
        "unit": "cmol/kg",
        "group": "soil_quality",
        "aggregation": "mean",
        "primary_source": "hwsd",
        "sources": [{"dataset": "hwsd", "raw_var": "T_CEC_SOIL", "conversion": "none"}]
    },
    "soil_texture": {
        "key": "soil_texture",
        "label": "USDA Soil Texture Class",
        "unit": "class",
        "group": "soil_quality",
        "aggregation": "modal",
        "primary_source": "hwsd",
        "sources": [{"dataset": "hwsd", "raw_var": "USDA_TEXTURE", "conversion": "texture_code_to_name"}]
    },
    "soil_sand": {
        "key": "soil_sand",
        "label": "Sand Fraction",
        "unit": "%",
        "group": "soil_quality",
        "aggregation": "mean",
        "primary_source": "hwsd",
        "sources": [{"dataset": "hwsd", "raw_var": "T_SAND", "conversion": "none"}]
    },
    "soil_silt": {
        "key": "soil_silt",
        "label": "Silt Fraction",
        "unit": "%",
        "group": "soil_quality",
        "aggregation": "mean",
        "primary_source": "hwsd",
        "sources": [{"dataset": "hwsd", "raw_var": "T_SILT", "conversion": "none"}]
    },
    "soil_clay": {
        "key": "soil_clay",
        "label": "Clay Fraction",
        "unit": "%",
        "group": "soil_quality",
        "aggregation": "mean",
        "primary_source": "hwsd",
        "sources": [{"dataset": "hwsd", "raw_var": "T_CLAY", "conversion": "none"}]
    },
    "soil_drainage": {
        "key": "soil_drainage",
        "label": "Soil Drainage Class",
        "unit": "class",
        "group": "soil_quality",
        "aggregation": "modal",
        "primary_source": "hwsd",
        "sources": [{"dataset": "hwsd", "raw_var": "DRAINAGE", "conversion": "drainage_code_to_name"}]
    },
    "soil_salinity": {
        "key": "soil_salinity",
        "label": "Soil Salinity (ECe)",
        "unit": "dS/m",
        "group": "soil_quality",
        "aggregation": "mean",
        "primary_source": "hwsd",
        "sources": [{"dataset": "hwsd", "raw_var": "T_ECE", "conversion": "none"}]
    },
    "soil_sodicity": {
        "key": "soil_sodicity",
        "label": "Exchangeable Sodium Percentage (ESP)",
        "unit": "%",
        "group": "soil_quality",
        "aggregation": "mean",
        "primary_source": "hwsd",
        "sources": [{"dataset": "hwsd", "raw_var": "T_ESP", "conversion": "none"}]
    },
    "soil_gravel": {
        "key": "soil_gravel",
        "label": "Gravel Content",
        "unit": "%",
        "group": "soil_quality",
        "aggregation": "mean",
        "primary_source": "hwsd",
        "sources": [{"dataset": "hwsd", "raw_var": "T_GRAVEL", "conversion": "none"}]
    }
}

# ---------------------------------------------------------
# FLASK & DATABASE CONFIGURATION
# ---------------------------------------------------------
class Config:
    """Base Flask & database configuration."""
    SECRET_KEY = os.getenv("SECRET_KEY", "teratrend-nasa-space-apps-secret-key-2026")
    DEBUG = os.getenv("FLASK_DEBUG", "0") == "1"
    TESTING = False
    JSON_SORT_KEYS = False
    DATASETS = DATASETS
    INDICATORS = INDICATORS

    # Paths
    BASE_DIR = BASE_DIR
    DATA_DIR = DATA_DIR
    SEED_DIR = SEED_DIR
    BOUNDARIES_DIR = BOUNDARIES_DIR
    PROCESSED_DIR = PROCESSED_DIR

    # Database Configuration
    DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'teratrend.db'}")
    AUTO_CREATE_DB = os.getenv("AUTO_CREATE_DB", "false").lower() in ("true", "1", "yes")
    ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

    # Caching
    CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").lower() in ("true", "1", "yes")
    CACHE_MAX_ROWS = int(os.getenv("CACHE_MAX_ROWS", "100000"))
    REQUEST_LOGGING = os.getenv("REQUEST_LOGGING", "false").lower() in ("true", "1", "yes")

    # Saved Items
    ENABLE_SAVED_ITEMS = os.getenv("ENABLE_SAVED_ITEMS", "true").lower() in ("true", "1", "yes")
    SAVED_LOCATION_LIMIT = int(os.getenv("SAVED_LOCATION_LIMIT", "50"))
    SAVED_SCENARIO_LIMIT = int(os.getenv("SAVED_SCENARIO_LIMIT", "100"))
    COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() in ("true", "1", "yes")

    # Application Versioning & Precomputed Grid
    CODE_VERSION = os.getenv("CODE_VERSION", "1.0.0")
    ENABLE_GRID_PRECOMPUTE = os.getenv("ENABLE_GRID_PRECOMPUTE", "false").lower() in ("true", "1", "yes")
