"""Test suite for industry drivers, effective rainfall (USDA-SCS), and policy blocks."""
import pytest
from teratrend.industry import build_industry_factors, compute_usda_effective_rainfall
from teratrend.schemas import EconomicsReport


def test_usda_scs_effective_rainfall_formula():
    """Verify USDA-SCS monthly effective rainfall formula on both branches:
    Branch 1: P <= 250 mm -> Peff = P * (125 - 0.2*P) / 125
    Branch 2: P > 250 mm  -> Peff = 125 + 0.1*P
    """
    # Test Branch 1: P = 100 mm -> Peff = 100 * (125 - 20) / 125 = 100 * 105 / 125 = 84 mm
    m_rf_branch1 = {1: 100.0}
    total_rf1, peff1 = compute_usda_effective_rainfall(m_rf_branch1, season="annual")
    assert peff1 == pytest.approx(84.0)

    # Test Branch 2: P = 300 mm -> Peff = 125 + 0.1 * 300 = 125 + 30 = 155 mm
    m_rf_branch2 = {1: 300.0}
    total_rf2, peff2 = compute_usda_effective_rainfall(m_rf_branch2, season="annual")
    assert peff2 == pytest.approx(155.0)


def test_industry_factors_structure_and_policy_flags():
    """Verify structured industry factors block carries policy as_of and verify_before_use."""
    mock_econ = EconomicsReport(
        available=True,
        crop="wheat",
        currency="INR",
        area_ha=1.0,
        tenure="owned",
        cost_basis="a2_fl",
        price_basis="market",
        costs_data={"components": {"human_labour_hired": 5000, "human_labour_family": 4000}},
        returns_data={"net_return_per_ha": {"chosen": 25000}, "roi_pct": {"chosen": 35.0}}
    )

    factors = build_industry_factors(
        crop="wheat",
        state="Punjab",
        econ_report=mock_econ
    )

    # Market block
    assert "msp_available" in factors.market
    assert "best_selling_months" in factors.market

    # Water block
    assert "effective_rainfall_usda_scs_mm" in factors.water
    assert "suggested_irrigation_events" in factors.water

    # Policy support flags
    pmfby = factors.policy_support.get("pmfby_scheme", {})
    assert pmfby.get("verify_before_use") is True
    assert "as_of" in pmfby
