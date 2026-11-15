"""TeraTrend land management and soil amendment recommendations.

Rule-driven actionable soil health and agronomic practices.
Pure agronomic logic. Does NOT import Flask or any network library.
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import RULES_DIR
from teratrend.schemas import Improvement

_AMENDMENTS_RULES_CACHE: Optional[List[Dict[str, Any]]] = None


def set_amendment_rules(rules: List[Dict[str, Any]]) -> None:
    """Explicitly inject amendment rules from repository or cache."""
    global _AMENDMENTS_RULES_CACHE
    _AMENDMENTS_RULES_CACHE = list(rules)


def load_amendment_rules(path: Optional[Path] = None, force_reload: bool = False) -> List[Dict[str, Any]]:
    """Load amendment rule definitions from JSON."""
    global _AMENDMENTS_RULES_CACHE
    if not force_reload and _AMENDMENTS_RULES_CACHE is not None:
        return _AMENDMENTS_RULES_CACHE

    target_path = path or (RULES_DIR / "amendments.json")
    if not target_path.exists():
        raise FileNotFoundError(f"Amendments rules file missing: {target_path}")

    with open(target_path, "r", encoding="utf-8") as f:
        _AMENDMENTS_RULES_CACHE = json.load(f)

    return _AMENDMENTS_RULES_CACHE


def evaluate_condition(cond: Dict[str, Any], context: Dict[str, Any]) -> bool:
    """Evaluate a condition dictionary against feature context."""
    field_name = cond.get("field")
    op = cond.get("op")
    target_val = cond.get("val")

    if field_name not in context:
        return False

    val = context[field_name]
    if val is None:
        return False

    try:
        fval = float(val)
        ftarget = float(target_val)
    except (ValueError, TypeError):
        return False

    if op == "<":
        return fval < ftarget
    elif op == "<=":
        return fval <= ftarget
    elif op == ">":
        return fval > ftarget
    elif op == ">=":
        return fval >= ftarget
    elif op == "==":
        return fval == ftarget
    return False


def generate_amendments(
    location_features: Dict[str, Any],
    rules_path: Optional[Path] = None,
    rules_data: Optional[List[Dict[str, Any]]] = None,
) -> List[Improvement]:
    """Generate triggered land improvement and amendment practices based on soil & climate features.
    
    Adheres strictly to the safety rule: never prescribe numeric doses; always instruct
    the user to verify with a local soil test and professional agronomist.
    """
    rules = rules_data if rules_data is not None else load_amendment_rules(rules_path)
    improvements: List[Improvement] = []

    for rule in rules:
        cond = rule.get("condition", {})
        if evaluate_condition(cond, location_features):
            improvements.append(
                Improvement(
                    factor=rule.get("factor", "general"),
                    issue=rule.get("issue", ""),
                    actions=list(rule.get("actions", [])),
                    note=rule.get("note", "Confirm with a local soil test and an agronomist before applying amendments.")
                )
            )

    return improvements
