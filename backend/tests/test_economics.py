"""Test suite for agricultural enterprise economics, CACP cost accounting, Monte Carlo risk, and scenarios."""
import pytest
from teratrend.economics import (
    compute_economics, interpolate_yield_factor, rank_by_economics,
    run_monte_carlo_risk, select_balanced_crop
)
from teratrend.schemas import CropScore, Region


def test_yield_factor_interpolation():
    """Verify piecewise linear yield factor curve anchors:
    0 -> 0.40, 40 -> 0.75, 70 -> 1.00, 100 -> 1.20
    """
    assert interpolate_yield_factor(0.0) == pytest.approx(0.40)
    assert interpolate_yield_factor(40.0) == pytest.approx(0.75)
    assert interpolate_yield_factor(70.0) == pytest.approx(1.00)
    assert interpolate_yield_factor(100.0) == pytest.approx(1.20)

    # Midpoints
    assert interpolate_yield_factor(20.0) == pytest.approx(0.40 + 0.5 * (0.75 - 0.40))
    assert interpolate_yield_factor(55.0) == pytest.approx(0.75 + 0.5 * (1.00 - 0.75))


def test_economics_calculation_known_inputs():
    """Verify revenue, costs, net return, ROI, BCR, break-even yield and price."""
    reg = Region(state="Punjab", is_union_territory=False)
    rep = compute_economics(
        crop="wheat",
        region=reg,
        suitability_now=70.0,  # Score 70 -> yield factor 1.00
        options={"area_ha": 2.0, "tenure": "owned", "cost_basis": "a2_fl", "price_basis": "market"}
    )

    assert rep.available is True
    # At suitability 70, expected yield = benchmark yield
    bench = rep.yield_data["benchmark_q_ha"]
    expected_yield = rep.yield_data["expected_q_ha"]
    assert expected_yield == pytest.approx(bench)

    # Revenue = expected_yield * price
    price = rep.price_data["chosen_price_per_q"]
    gross_rev = rep.returns_data["gross_revenue_per_ha"]["chosen"]
    assert gross_rev == pytest.approx(expected_yield * price)

    # Net return over A2+FL = gross_revenue - a2_fl_cost
    a2_fl = rep.costs_data["a2_fl_per_ha"]
    net_return = rep.returns_data["net_return_per_ha"]["chosen"]
    assert net_return == pytest.approx(gross_rev - a2_fl)

    # ROI % = net_return / cost * 100
    roi = rep.returns_data["roi_pct"]["chosen"]
    assert roi == pytest.approx((net_return / a2_fl) * 100.0, abs=0.5)

    # BCR = gross_revenue / cost
    assert rep.returns_data["benefit_cost_ratio"] == pytest.approx(gross_rev / a2_fl, abs=0.05)

    # Break-even yield = cost / price
    assert rep.returns_data["break_even_yield_q_ha"] == pytest.approx(a2_fl / price, abs=0.1)

    # Break-even price = cost / expected_yield
    assert rep.returns_data["break_even_price_per_q"] == pytest.approx(a2_fl / expected_yield, abs=1.0)

    # Totals for 2 ha area
    totals = rep.totals_for_area
    assert totals["area_ha"] == 2.0
    assert totals["total_production_quintals"] == pytest.approx(expected_yield * 2.0)
    assert totals["total_net_return_inr"] == pytest.approx(net_return * 2.0)


def test_user_overrides_win():
    """Verify user overrides for yield and price supersede defaults and are echoed back."""
    reg = Region(state="Punjab", is_union_territory=False)
    rep = compute_economics(
        crop="wheat",
        region=reg,
        suitability_now=50.0,
        options={
            "yield_override_q_ha": 60.0,
            "price_override_per_q": 3000.0,
            "cost_multiplier": 1.10
        }
    )

    assert rep.yield_data["expected_q_ha"] == 60.0
    assert rep.price_data["chosen_price_per_q"] == 3000.0
    assert rep.returns_data["gross_revenue_per_ha"]["chosen"] == pytest.approx(60.0 * 3000.0)


def test_monte_carlo_deterministic():
    """Verify Monte Carlo risk produces identical results for identical inputs and seeds."""
    p_loss1, p10_1, p50_1, p90_1, _ = run_monte_carlo_risk(
        expected_yield=35.0, yield_cv=0.15, chosen_price=2300.0, price_cv=0.10, chosen_cost=40000.0, seed_key=42
    )
    p_loss2, p10_2, p50_2, p90_2, _ = run_monte_carlo_risk(
        expected_yield=35.0, yield_cv=0.15, chosen_price=2300.0, price_cv=0.10, chosen_cost=40000.0, seed_key=42
    )
    assert p_loss1 == p_loss2
    assert p10_1 == p10_2
    assert p50_1 == p50_2
    assert p90_1 == p90_2

    # Higher price volatility should increase probability of loss
    p_loss_high_cv, _, _, _, _ = run_monte_carlo_risk(
        expected_yield=35.0, yield_cv=0.15, chosen_price=2300.0, price_cv=0.40, chosen_cost=40000.0, seed_key=42
    )
    assert p_loss_high_cv > p_loss1


def test_state_to_national_fallback_flags():
    """Verify fallback from unrepresented state to All-India average with explicit flags."""
    # State without surveyed wheat (e.g. Kerala)
    reg_kerala = Region(state="Kerala", is_union_territory=False)
    rep = compute_economics(crop="wheat", region=reg_kerala, suitability_now=60.0)

    assert rep.available is True
    assert rep.data_quality["benchmark_level"] == "national"
    assert rep.data_quality["cost_level"] == "national"
    assert any("All-India" in w for w in rep.warnings)


def test_balanced_pick_selection():
    """Verify balanced pick selects highest suitability crop with positive ROI and P(loss) < 30%."""
    scored = [
        CropScore("rice", "Rice", "Dhan", "cereals", 88.0, "GOOD", "none", "kharif", "Good"),
        CropScore("wheat", "Wheat", "Gehun", "cereals", 82.0, "GOOD", "none", "rabi", "Good")
    ]
    reg = Region(state="Punjab", is_union_territory=False)
    reports = {
        "rice": compute_economics("rice", reg, 88.0),
        "wheat": compute_economics("wheat", reg, 82.0)
    }

    pick = select_balanced_crop(scored, reports)
    assert pick is not None
    assert pick["roi_pct"] > 0
    assert pick["probability_of_loss_pct"] < 30.0
