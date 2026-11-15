"""Test suite for soil amendment triggers and agronomic safety notes."""
import pytest
from teratrend.amendments import generate_amendments


def test_acidic_ph_amendment_trigger():
    """Verify acidic pH triggers liming actions without numeric doses."""
    acidic_env = {
        "soil_ph_top": 5.2,
        "soil_sodicity": 3.0,
        "soil_organic_carbon": 1.2
    }

    improvements = generate_amendments(acidic_env)
    assert len(improvements) > 0

    ph_imp = next((imp for imp in improvements if imp.factor == "soil_ph"), None)
    assert ph_imp is not None
    assert "lime" in " ".join(ph_imp.actions).lower()
    # Safety note must always be present
    assert "soil test" in ph_imp.note.lower()
    # Must not contain hardcoded dosage numbers like 'kg/ha' or 'tonnes/ha' in actionable lime instructions
    for action in ph_imp.actions:
        assert "kg/ha of lime" not in action.lower()


def test_sodic_and_low_carbon_triggers():
    """Verify sodic soil (ESP > 15) triggers gypsum/leaching, and low OC (<0.5%) triggers organic matter."""
    sodic_low_c_env = {
        "soil_ph_top": 8.4,
        "soil_sodicity": 18.0,
        "soil_organic_carbon": 0.35,
        "soil_salinity": 2.0
    }

    improvements = generate_amendments(sodic_low_c_env)
    issues = [imp.issue.lower() for imp in improvements]

    assert any("sodic" in iss for iss in issues)
    assert any("organic carbon" in iss for iss in issues)
