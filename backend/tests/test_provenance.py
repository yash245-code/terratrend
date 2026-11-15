"""Tests for pipeline provenance tracking and schema validation.
"""
import json
import pytest
from pathlib import Path
from backend.pipeline.provenance import (
    compute_file_sha256,
    fetch_cmr_collection_metadata,
    record_dataset_provenance,
    build_provenance_report,
    load_provenance
)


def test_provenance_hashing_and_report(tmp_path):
    prov_path = tmp_path / "provenance.json"

    # Test file hashing on a dummy file
    dummy_file = tmp_path / "test.nc"
    dummy_file.write_text("dummy netcdf binary content")
    sha256 = compute_file_sha256(dummy_file)
    assert len(sha256) == 64
    assert isinstance(sha256, str)

    # Test record_dataset_provenance
    rec = record_dataset_provenance("gldas", dummy_file, granule_count=12)
    assert rec["dataset_key"] == "gldas"
    assert rec["sha256"] == sha256
    assert rec["granule_count"] == 12
    assert "access_date_utc" in rec

    # Test build_provenance_report
    report = build_provenance_report(output_path=prov_path)
    assert prov_path.exists()
    assert report["project"] == "TeraTrend (NASA Space Apps Challenge 2026)"
    assert "datasets" in report
    assert "libraries" in report
    assert "xarray" in report["libraries"]

    # Test load_provenance
    loaded = load_provenance(prov_path)
    assert loaded is not None
    assert loaded["spatial_domain"]["common_grid_resolution"] == 0.25


def test_provenance_offline_cmr_degradation():
    meta = fetch_cmr_collection_metadata("GLDAS_NOAH025_M", "2.1")
    assert isinstance(meta, dict)
    assert "version_id" in meta
