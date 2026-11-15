"""Tests for in-memory ReferenceDataCache."""
from __future__ import annotations

import pytest
from teratrend.services.reference_cache import ReferenceDataCache, get_reference_cache


def test_reference_data_cache_initialization_and_snapshot():
    """Verify ReferenceDataCache loads from database, sets version, and hydrates RAM."""
    cache = ReferenceDataCache()
    cache.load(fail_fast=True)

    assert cache.counts["crops"] == 20
    assert cache.counts["states"] == 36
    assert cache.reference_version is not None
    assert len(cache.reference_version) == 16

    snap = cache.snapshot()
    assert snap["status"] == "ready"
    assert snap["counts"]["crops"] == 20
    assert snap["reference_version"] == cache.reference_version


def test_reference_data_cache_reload():
    """Verify reload hot-refreshes data in place."""
    cache = get_reference_cache()
    old_version = cache.reference_version
    cache.reload()
    assert cache.reference_version is not None
    assert cache.counts["crops"] == 20
