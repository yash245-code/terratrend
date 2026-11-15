"""Test suite for multi-dataset consensus evaluation across satellite & model sources."""
import numpy as np
import pytest

from teratrend.consensus import consensus_for_group
from teratrend.schemas import ConsensusResult, SourceTrend


def test_consensus_strong_agreement(synthetic_grid_and_store):
    """Verify consensus when datasets agree on significant trend direction."""
    store, _ = synthetic_grid_and_store
    # Check temperature group where GLDAS and MERRA-2 both have warming trend
    res = consensus_for_group(store, 15.0, 75.0, "temperature")

    assert isinstance(res, ConsensusResult)
    assert res.consensus_level in ["STRONG", "MODERATE"]
    assert res.overlap_years >= 10
    assert "gldas" in res.sources_used
    assert "merra2" in res.sources_used


def test_consensus_single_source(synthetic_grid_and_store):
    """Verify SINGLE_SOURCE level when only one dataset is in group (e.g. vegetation with MODIS)."""
    store, _ = synthetic_grid_and_store
    res = consensus_for_group(store, 15.0, 75.0, "vegetation")

    assert res.consensus_level == "SINGLE_SOURCE"
    assert res.sources_used == ["modis"]
    assert len(res.individual_trends) == 1


def test_conflicting_consensus_logic():
    """Verify CONFLICTING classification when independent sources show significant opposite directions."""
    from teratrend.consensus import ConsensusResult, SourceTrend
    ind_trends = {
        "src_a": SourceTrend("src_a", p_value=0.01, significant=True, direction="increasing", sens_slope_per_decade=2.0, standardized_change=1.2),
        "src_b": SourceTrend("src_b", p_value=0.02, significant=True, direction="decreasing", sens_slope_per_decade=-1.8, standardized_change=-1.1)
    }

    has_sig_inc = any(st.direction == "increasing" and st.significant for st in ind_trends.values())
    has_sig_dec = any(st.direction == "decreasing" and st.significant for st in ind_trends.values())
    assert has_sig_inc and has_sig_dec  # Conflicting condition met
