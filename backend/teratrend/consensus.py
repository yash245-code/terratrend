"""TeraTrend multi-dataset scientific consensus module.

Evaluates agreement across independent satellite missions and reanalysis models
on strictly overlapping observation years.
Pure scientific logic. Does NOT import Flask or any network library.
"""
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from scipy.stats import pearsonr

from config import ALPHA, DATASETS, INDICATORS, MIN_CONSENSUS_OVERLAP_YEARS
from teratrend.schemas import ConsensusResult, SourceTrend
from teratrend.trend_engine import InsufficientDataError, analyze_point, run_hamed_rao_trend

# Consensus indicator groupings
CONSENSUS_GROUPS = {
    "temperature": {
        "indicator": "air_temperature",
        "sources": ["gldas", "merra2", "airs"]
    },
    "precipitation": {
        "indicator": "rainfall",
        "sources": ["gldas", "merra2", "gpm"]
    },
    "soil_moisture": {
        "indicator": "root_moisture",
        "sources": ["gldas", "merra2"]
    },
    "evapotranspiration": {
        "indicator": "evapotranspiration",
        "sources": ["gldas", "merra2"]
    },
    "vegetation": {
        "indicator": "ndvi",
        "sources": ["modis"]
    },
    "air_quality": {
        "indicator": "no2",
        "sources": ["omi"]
    }
}


def consensus_for_group(
    store: Any,
    lat: float,
    lon: float,
    group: str
) -> ConsensusResult:
    """Evaluate multi-dataset consensus across available sources for a group on overlapping years."""
    if group not in CONSENSUS_GROUPS:
        raise KeyError(f"Unknown consensus group '{group}'. Valid: {list(CONSENSUS_GROUPS.keys())}")

    group_def = CONSENSUS_GROUPS[group]
    indicator = group_def["indicator"]
    candidate_sources = group_def["sources"]

    # 1. Collect annual series for available sources
    available_series: Dict[str, pd.Series] = {}
    sources_excluded: List[Dict[str, str]] = []

    for src in candidate_sources:
        if not store.has_dataset(src):
            sources_excluded.append({"source": src, "reason": "Dataset not loaded in store"})
            continue

        try:
            tr = analyze_point(store, lat, lon, indicator, source=src)
            # Reconstruct series from tr.annual_values
            years = [entry["year"] for entry in tr.annual_values]
            vals = [entry["value"] for entry in tr.annual_values]
            s = pd.Series(vals, index=years, name=src)
            available_series[src] = s
        except InsufficientDataError as e:
            sources_excluded.append({"source": src, "reason": str(e.message)})
        except Exception as e:
            sources_excluded.append({"source": src, "reason": str(e)})

    # If no sources available
    if not available_series:
        return ConsensusResult(
            group=group,
            consensus_level="NO_DATA",
            sources_used=[],
            sources_excluded=sources_excluded,
            overlap_years=0,
            direction="no_trend",
            individual_trends={},
            pairwise_correlations={},
            summary="No valid satellite or reanalysis sources available for this group."
        )

    # If only 1 source available
    if len(available_series) == 1:
        src = list(available_series.keys())[0]
        s = available_series[src]
        tr = run_hamed_rao_trend(np.array(s.index), s.values, indicator_name=indicator, source_name=src)
        ind_trend = {
            src: SourceTrend(
                dataset=src,
                p_value=tr.p_value,
                significant=tr.significant,
                direction=tr.direction,
                sens_slope_per_decade=tr.sens_slope_per_decade,
                standardized_change=tr.standardized_change
            )
        }
        return ConsensusResult(
            group=group,
            consensus_level="SINGLE_SOURCE",
            sources_used=[src],
            sources_excluded=sources_excluded,
            overlap_years=len(s),
            direction=tr.direction,
            individual_trends=ind_trend,
            pairwise_correlations={},
            summary=f"Only single source ({src}) loaded; cross-dataset verification not possible."
        )

    # 2. Find strictly overlapping years across all available sources
    overlap_years_set = set(list(available_series.values())[0].index)
    for s in list(available_series.values())[1:]:
        overlap_years_set = overlap_years_set.intersection(set(s.index))

    sorted_overlap = sorted(list(overlap_years_set))
    if len(sorted_overlap) < MIN_CONSENSUS_OVERLAP_YEARS:
        # Fall back to pairwise or report insufficient overlap
        sources_excluded.append({
            "source": "multi_source",
            "reason": f"Overlapping years ({len(sorted_overlap)}) less than minimum required {MIN_CONSENSUS_OVERLAP_YEARS}"
        })
        src = list(available_series.keys())[0]
        s = available_series[src]
        tr = run_hamed_rao_trend(np.array(s.index), s.values, indicator_name=indicator, source_name=src)
        return ConsensusResult(
            group=group,
            consensus_level="SINGLE_SOURCE",
            sources_used=[src],
            sources_excluded=sources_excluded,
            overlap_years=len(s),
            direction=tr.direction,
            individual_trends={
                src: SourceTrend(
                    dataset=src,
                    p_value=tr.p_value,
                    significant=tr.significant,
                    direction=tr.direction,
                    sens_slope_per_decade=tr.sens_slope_per_decade,
                    standardized_change=tr.standardized_change
                )
            },
            pairwise_correlations={},
            summary=f"Insufficient multi-source temporal overlap ({len(sorted_overlap)} years). Evaluated primary source {src} individually."
        )

    # 3. Restrict each series to the overlapping years and run trend tests
    individual_trends: Dict[str, SourceTrend] = {}
    aligned_arrays: Dict[str, np.ndarray] = {}
    years_arr = np.array(sorted_overlap, dtype=int)

    for src, s in available_series.items():
        aligned_vals = s.loc[sorted_overlap].values.astype(float)
        aligned_arrays[src] = aligned_vals
        tr = run_hamed_rao_trend(years_arr, aligned_vals, indicator_name=indicator, source_name=src)
        individual_trends[src] = SourceTrend(
            dataset=src,
            p_value=tr.p_value,
            significant=tr.significant,
            direction=tr.direction,
            sens_slope_per_decade=tr.sens_slope_per_decade,
            standardized_change=tr.standardized_change
        )

    # 4. Compute pairwise Pearson correlations of annual anomalies
    pairwise_correlations: Dict[str, float] = {}
    src_list = list(aligned_arrays.keys())
    for i in range(len(src_list)):
        for j in range(i + 1, len(src_list)):
            s1, s2 = src_list[i], src_list[j]
            v1 = aligned_arrays[s1] - np.mean(aligned_arrays[s1])
            v2 = aligned_arrays[s2] - np.mean(aligned_arrays[s2])
            if np.std(v1) > 1e-6 and np.std(v2) > 1e-6:
                r, _ = pearsonr(v1, v2)
                pairwise_correlations[f"{s1}_vs_{s2}"] = round(float(r), 3)

    # 5. Evaluate consensus level
    # Directions of significant sources
    sig_trends = [st for st in individual_trends.values() if st.significant]
    all_directions = [st.direction for st in individual_trends.values()]
    all_slopes = [st.sens_slope_per_decade for st in individual_trends.values()]

    # Check for CONFLICTING: significant trends in opposite directions
    has_sig_inc = any(st.direction == "increasing" for st in sig_trends)
    has_sig_dec = any(st.direction == "decreasing" for st in sig_trends)

    if has_sig_inc and has_sig_dec:
        consensus_level = "CONFLICTING"
        overall_direction = "conflicting"
        summary = "Independent datasets show statistically significant opposite trend directions."
    elif len(sig_trends) >= 2 and len({st.direction for st in sig_trends}) == 1:
        consensus_level = "STRONG"
        overall_direction = sig_trends[0].direction
        summary = f"Strong consensus: {len(sig_trends)} datasets confirm a significant {overall_direction} trend."
    elif len(sig_trends) == 1:
        consensus_level = "MODERATE"
        overall_direction = sig_trends[0].direction
        summary = f"Moderate consensus: 1 dataset shows significant {overall_direction} trend, others directionally consistent."
    elif all(d == all_directions[0] for d in all_directions) and all_directions[0] != "no_trend":
        consensus_level = "MODERATE"
        overall_direction = all_directions[0]
        summary = f"Consistent direction ({overall_direction}) across all datasets, though below statistical significance threshold."
    else:
        consensus_level = "WEAK"
        overall_direction = "no_trend"
        summary = "No statistically significant multi-dataset consensus detected."

    # 6. Check vegetation confirmation if group is moisture or precipitation
    vegetation_confirms = None
    if group in ["moisture", "precipitation", "soil_moisture"] and overall_direction == "decreasing":
        if store.has_dataset("modis"):
            try:
                modis_tr = analyze_point(store, lat, lon, "ndvi", source="modis")
                if modis_tr.significant and modis_tr.direction == "decreasing":
                    vegetation_confirms = True
                else:
                    vegetation_confirms = False
            except Exception:
                vegetation_confirms = None

    return ConsensusResult(
        group=group,
        consensus_level=consensus_level,
        sources_used=list(individual_trends.keys()),
        sources_excluded=sources_excluded,
        overlap_years=len(sorted_overlap),
        direction=overall_direction,
        individual_trends=individual_trends,
        pairwise_correlations=pairwise_correlations,
        vegetation_confirms=vegetation_confirms,
        summary=summary
    )
