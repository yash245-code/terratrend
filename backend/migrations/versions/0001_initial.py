"""0001_initial: TerraTrend core database schema.

Revision ID: 0001_initial
Revises: 
Create Date: 2026-11-14 22:15:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. States
    op.create_table(
        "states",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("is_union_territory", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_states")),
        sa.UniqueConstraint("code", name=op.f("uq_states_code")),
    )

    # 2. Districts
    op.create_table(
        "districts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("state_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("lgd_code", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["state_id"], ["states.id"], name=op.f("fk_districts_state_id_states"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_districts")),
        sa.UniqueConstraint("state_id", "name", name="uq_districts_state_id_name"),
    )

    # 3. Crops
    op.create_table(
        "crops",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("local_name", sa.String(length=100), nullable=True),
        sa.Column("group", sa.String(length=50), nullable=False),
        sa.Column("seasons", sa.JSON(), nullable=False),
        sa.Column("cycle_days", sa.Integer(), nullable=False),
        sa.Column("water_demand", sa.String(length=20), nullable=False),
        sa.Column("base_yield_cv", sa.Float(), nullable=False),
        sa.Column("salinity_ece_max", sa.Float(), nullable=False),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("source", sa.String(length=255), nullable=False),
        sa.Column("verification_status", sa.String(length=50), nullable=False, server_default="verified"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_crops")),
        sa.UniqueConstraint("key", name=op.f("uq_crops_key")),
    )

    # 4. Crop Requirements
    op.create_table(
        "crop_requirements",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("crop_id", sa.Integer(), nullable=False),
        sa.Column("factor", sa.String(length=50), nullable=False),
        sa.Column("season", sa.String(length=20), nullable=True),
        sa.Column("abs_min", sa.Float(), nullable=False),
        sa.Column("opt_min", sa.Float(), nullable=False),
        sa.Column("opt_max", sa.Float(), nullable=False),
        sa.Column("abs_max", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("abs_min <= opt_min AND opt_min <= opt_max AND opt_max <= abs_max", name="ck_crop_requirements_trapezoid_order"),
        sa.ForeignKeyConstraint(["crop_id"], ["crops.id"], name=op.f("fk_crop_requirements_crop_id_crops"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_crop_requirements")),
        sa.UniqueConstraint("crop_id", "factor", "season", name="uq_crop_requirements_crop_factor_season"),
    )

    # 5. Crop Soil Preferences
    op.create_table(
        "crop_soil_preferences",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("crop_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("class_name", sa.String(length=50), nullable=False),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["crop_id"], ["crops.id"], name=op.f("fk_crop_soil_preferences_crop_id_crops"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_crop_soil_preferences")),
    )

    # 6. Amendment Rules
    op.create_table(
        "amendment_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("factor", sa.String(length=50), nullable=False),
        sa.Column("operator", sa.String(length=20), nullable=False),
        sa.Column("threshold_low", sa.Float(), nullable=False),
        sa.Column("threshold_high", sa.Float(), nullable=True),
        sa.Column("issue", sa.String(length=255), nullable=False),
        sa.Column("actions", sa.JSON(), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_amendment_rules")),
        sa.UniqueConstraint("key", name=op.f("uq_amendment_rules_key")),
    )

    # 7. Trend Rules
    op.create_table(
        "trend_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("indicator", sa.String(length=50), nullable=False),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("crops", sa.JSON(), nullable=False),
        sa.Column("avoid", sa.JSON(), nullable=False),
        sa.Column("practices", sa.JSON(), nullable=False),
        sa.Column("confidence_note", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trend_rules")),
        sa.UniqueConstraint("indicator", "direction", name="uq_trend_rules_indicator_direction"),
    )

    # 8. Crop Costs
    op.create_table(
        "crop_costs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("crop_id", sa.Integer(), nullable=False),
        sa.Column("state_id", sa.Integer(), nullable=True),
        sa.Column("reference_year", sa.String(length=20), nullable=False),
        sa.Column("cost_a2", sa.Float(), nullable=False),
        sa.Column("cost_a2_fl", sa.Float(), nullable=False),
        sa.Column("cost_c2", sa.Float(), nullable=False),
        sa.Column("components", sa.JSON(), nullable=False),
        sa.Column("yield_reference_q_ha", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("verification_status", sa.String(length=50), nullable=False, server_default="verified"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["crop_id"], ["crops.id"], name=op.f("fk_crop_costs_crop_id_crops"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["state_id"], ["states.id"], name=op.f("fk_crop_costs_state_id_states"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_crop_costs")),
        sa.UniqueConstraint("crop_id", "state_id", "reference_year", name="uq_crop_costs_crop_state_year"),
    )

    # 9. Benchmark Yields
    op.create_table(
        "benchmark_yields",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("crop_id", sa.Integer(), nullable=False),
        sa.Column("state_id", sa.Integer(), nullable=True),
        sa.Column("district_id", sa.Integer(), nullable=True),
        sa.Column("yield_q_ha", sa.Float(), nullable=False),
        sa.Column("period_start", sa.Integer(), nullable=True),
        sa.Column("period_end", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("verification_status", sa.String(length=50), nullable=False, server_default="verified"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("yield_q_ha > 0", name="ck_benchmark_yields_positive"),
        sa.ForeignKeyConstraint(["crop_id"], ["crops.id"], name=op.f("fk_benchmark_yields_crop_id_crops"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["district_id"], ["districts.id"], name=op.f("fk_benchmark_yields_district_id_districts"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["state_id"], ["states.id"], name=op.f("fk_benchmark_yields_state_id_states"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_benchmark_yields")),
    )

    # 10. MSP
    op.create_table(
        "msp",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("crop_id", sa.Integer(), nullable=False),
        sa.Column("marketing_year", sa.String(length=20), nullable=False),
        sa.Column("msp_per_q", sa.Float(), nullable=False),
        sa.Column("is_frp", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("source", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("verification_status", sa.String(length=50), nullable=False, server_default="verified"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["crop_id"], ["crops.id"], name=op.f("fk_msp_crop_id_crops"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_msp")),
        sa.UniqueConstraint("crop_id", "marketing_year", name="uq_msp_crop_marketing_year"),
    )

    # 11. Mandi Prices
    op.create_table(
        "mandi_prices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("crop_id", sa.Integer(), nullable=False),
        sa.Column("state_id", sa.Integer(), nullable=False),
        sa.Column("as_of", sa.String(length=20), nullable=False),
        sa.Column("trailing_avg_modal_per_q", sa.Float(), nullable=False),
        sa.Column("yoy_change_pct", sa.Float(), nullable=False),
        sa.Column("price_cv", sa.Float(), nullable=False),
        sa.Column("seasonal_index", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("verification_status", sa.String(length=50), nullable=False, server_default="verified"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["crop_id"], ["crops.id"], name=op.f("fk_mandi_prices_crop_id_crops"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["state_id"], ["states.id"], name=op.f("fk_mandi_prices_state_id_states"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mandi_prices")),
        sa.UniqueConstraint("crop_id", "state_id", "as_of", name="uq_mandi_prices_crop_state_as_of"),
    )

    # 12. Input Requirements
    op.create_table(
        "input_requirements",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("crop_id", sa.Integer(), nullable=False),
        sa.Column("seed_rate_kg_ha", sa.Float(), nullable=False),
        sa.Column("npk_kg_ha", sa.JSON(), nullable=False),
        sa.Column("irrigation_count", sa.Integer(), nullable=False),
        sa.Column("season_water_mm", sa.Float(), nullable=False),
        sa.Column("man_days_ha", sa.Float(), nullable=False),
        sa.Column("sprays", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("verification_status", sa.String(length=50), nullable=False, server_default="verified"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["crop_id"], ["crops.id"], name=op.f("fk_input_requirements_crop_id_crops"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_input_requirements")),
        sa.UniqueConstraint("crop_id", name="uq_input_requirements_crop_id"),
    )

    # 13. Policy Schemes
    op.create_table(
        "policy_schemes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("as_of", sa.String(length=50), nullable=False),
        sa.Column("source", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("verify_before_use", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("verification_status", sa.String(length=50), nullable=False, server_default="verified"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_policy_schemes")),
        sa.UniqueConstraint("key", name=op.f("uq_policy_schemes_key")),
    )

    # 14. Dataset Provenance
    op.create_table(
        "dataset_provenance",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dataset_key", sa.String(length=50), nullable=False),
        sa.Column("short_names", sa.JSON(), nullable=False),
        sa.Column("versions", sa.JSON(), nullable=False),
        sa.Column("doi", sa.String(length=255), nullable=True),
        sa.Column("concept_ids", sa.JSON(), nullable=False),
        sa.Column("provider", sa.String(length=255), nullable=False),
        sa.Column("citation", sa.Text(), nullable=False),
        sa.Column("cmr_extent_start", sa.String(length=50), nullable=True),
        sa.Column("cmr_extent_end", sa.String(length=50), nullable=True),
        sa.Column("used_extent_start", sa.String(length=50), nullable=True),
        sa.Column("used_extent_end", sa.String(length=50), nullable=True),
        sa.Column("granule_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("access_date", sa.String(length=50), nullable=True),
        sa.Column("backend", sa.String(length=50), nullable=False, server_default="offline"),
        sa.Column("variables", sa.JSON(), nullable=False),
        sa.Column("regrid_method", sa.String(length=50), nullable=False),
        sa.Column("cube_path", sa.String(length=500), nullable=True),
        sa.Column("cube_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dataset_provenance")),
        sa.UniqueConstraint("dataset_key", "cube_sha256", name="uq_dataset_provenance_key_sha256"),
    )

    # 15. Boundary Provenance
    op.create_table(
        "boundary_provenance",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("source", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("license", sa.String(length=100), nullable=False),
        sa.Column("retrieved_at", sa.String(length=50), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_boundary_provenance")),
        sa.UniqueConstraint("name", name=op.f("uq_boundary_provenance_name")),
    )

    # 16. Pipeline Runs
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("command", sa.String(length=100), nullable=False),
        sa.Column("dataset_key", sa.String(length=50), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="running"),
        sa.Column("stats", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pipeline_runs")),
    )

    # 17. Assessments Cache
    op.create_table(
        "assessments_cache",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("cell_lat", sa.Float(), nullable=False),
        sa.Column("cell_lon", sa.Float(), nullable=False),
        sa.Column("state_id", sa.Integer(), nullable=True),
        sa.Column("district_id", sa.Integer(), nullable=True),
        sa.Column("crop_key", sa.String(length=50), nullable=True),
        sa.Column("season", sa.String(length=20), nullable=False),
        sa.Column("irrigation", sa.String(length=20), nullable=False),
        sa.Column("options_hash", sa.String(length=64), nullable=False),
        sa.Column("data_version", sa.String(length=64), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_hit_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessments_cache")),
        sa.UniqueConstraint("cache_key", name=op.f("uq_assessments_cache_cache_key")),
    )
    op.create_index("ix_assessments_cache_data_version", "assessments_cache", ["data_version"])
    op.create_index("ix_assessments_cache_last_hit_at", "assessments_cache", ["last_hit_at"])

    # 18. Geocode Cache
    op.create_table(
        "geocode_cache",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("query_norm", sa.String(length=255), nullable=False),
        sa.Column("results", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_geocode_cache")),
        sa.UniqueConstraint("query_norm", name=op.f("uq_geocode_cache_query_norm")),
    )

    # 19. Clients
    op.create_table(
        "clients",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clients")),
    )

    # 20. Saved Locations
    op.create_table(
        "saved_locations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("client_id", sa.String(length=36), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], name=op.f("fk_saved_locations_client_id_clients"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_saved_locations")),
    )
    op.create_index("ix_saved_locations_client_id", "saved_locations", ["client_id"])

    # 21. Saved Scenarios
    op.create_table(
        "saved_scenarios",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("client_id", sa.String(length=36), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=True),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("crop_key", sa.String(length=50), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("data_version", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], name=op.f("fk_saved_scenarios_client_id_clients"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["saved_locations.id"], name=op.f("fk_saved_scenarios_location_id_saved_locations"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_saved_scenarios")),
    )
    op.create_index("ix_saved_scenarios_client_id", "saved_scenarios", ["client_id"])

    # 22. Grid Cells
    op.create_table(
        "grid_cells",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cell_lat", sa.Float(), nullable=False),
        sa.Column("cell_lon", sa.Float(), nullable=False),
        sa.Column("state_id", sa.Integer(), nullable=True),
        sa.Column("district_id", sa.Integer(), nullable=True),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column("temperature_score", sa.Float(), nullable=False),
        sa.Column("moisture_score", sa.Float(), nullable=False),
        sa.Column("soil_ph_score", sa.Float(), nullable=False),
        sa.Column("soil_quality_score", sa.Float(), nullable=False),
        sa.Column("climate_score", sa.Float(), nullable=False),
        sa.Column("data_version", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["state_id"], ["states.id"], name=op.f("fk_grid_cells_state_id_states"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grid_cells")),
        sa.UniqueConstraint("cell_lat", "cell_lon", "data_version", name="uq_grid_cells_coords_version"),
    )
    op.create_index("ix_grid_cells_version", "grid_cells", ["data_version"])
    op.create_index("ix_grid_cells_state", "grid_cells", ["state_id"])

    # 23. Grid Crop Scores
    op.create_table(
        "grid_crop_scores",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cell_id", sa.Integer(), nullable=False),
        sa.Column("crop_key", sa.String(length=50), nullable=False),
        sa.Column("suitability_score", sa.Float(), nullable=False),
        sa.Column("roi_pct", sa.Float(), nullable=True),
        sa.Column("probability_of_loss_pct", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["cell_id"], ["grid_cells.id"], name=op.f("fk_grid_crop_scores_cell_id_grid_cells"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grid_crop_scores")),
        sa.UniqueConstraint("cell_id", "crop_key", name="uq_grid_crop_scores_cell_crop"),
    )
    op.create_index("ix_grid_crop_scores_crop_score", "grid_crop_scores", ["crop_key", "suitability_score"])


def downgrade() -> None:
    op.drop_table("grid_crop_scores")
    op.drop_table("grid_cells")
    op.drop_table("saved_scenarios")
    op.drop_table("saved_locations")
    op.drop_table("clients")
    op.drop_table("geocode_cache")
    op.drop_table("assessments_cache")
    op.drop_table("pipeline_runs")
    op.drop_table("boundary_provenance")
    op.drop_table("dataset_provenance")
    op.drop_table("policy_schemes")
    op.drop_table("input_requirements")
    op.drop_table("mandi_prices")
    op.drop_table("msp")
    op.drop_table("benchmark_yields")
    op.drop_table("crop_costs")
    op.drop_table("trend_rules")
    op.drop_table("amendment_rules")
    op.drop_table("crop_soil_preferences")
    op.drop_table("crop_requirements")
    op.drop_table("crops")
    op.drop_table("districts")
    op.drop_table("states")
