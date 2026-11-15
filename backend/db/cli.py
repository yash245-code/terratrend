"""TerraTrend Database Management CLI.

Usage:
    python -m db.cli init
    python -m db.cli migrate -m "migration description"
    python -m db.cli seed [--from DIR] [--only regions|crops|rules|economics] [--skip-invalid]
    python -m db.cli export [--to DIR]
    python -m db.cli check
    python -m db.cli backup [--out PATH]
    python -m db.cli prune-cache [--max-rows N]
    python -m db.cli precompute-grid [--limit N]
"""
from __future__ import annotations

import argparse
import logging
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import func, select

from config import Config
from db.base import get_session
from db.export import export_database
from db.models.economics import (
    BenchmarkYield,
    CropCost,
    InputRequirement,
    MandiPrice,
    Msp,
    PolicyScheme,
)
from db.models.grid import GridCell, GridCropScore
from db.models.reference import (
    AmendmentRule,
    Crop,
    CropRequirement,
    CropSoilPreference,
    District,
    State,
    TrendRule,
)
from db.repositories.economics_repo import EconomicsRepository
from db.repositories.grid_repo import GridRepository
from db.repositories.results_repo import ResultsRepository
from db.seed import seed_database

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("teratrend.db.cli")


def _get_alembic_config() -> AlembicConfig:
    backend_dir = Path(__file__).resolve().parent.parent
    ini_path = backend_dir / "alembic.ini"
    if not ini_path.exists():
        raise FileNotFoundError(f"Alembic config not found at: {ini_path}")
    cfg = AlembicConfig(str(ini_path))
    cfg.set_main_option("script_location", str(backend_dir / "migrations"))
    return cfg


def cmd_init(args: argparse.Namespace) -> int:
    """Run migrations to bring database up to head."""
    log.info("Applying database migrations (upgrade head)...")
    cfg = _get_alembic_config()
    try:
        command.upgrade(cfg, "head")
        log.info("Database successfully migrated to head revision.")
        return 0
    except Exception as exc:
        log.error("Failed to migrate database: %s", exc)
        return 1


def cmd_migrate(args: argparse.Namespace) -> int:
    """Generate a new alembic revision."""
    msg = args.message or "auto migration"
    log.info("Generating alembic revision: %s", msg)
    cfg = _get_alembic_config()
    try:
        command.revision(cfg, message=msg, autogenerate=True)
        log.info("Revision created successfully.")
        return 0
    except Exception as exc:
        log.error("Failed to generate revision: %s", exc)
        return 1


def cmd_seed(args: argparse.Namespace) -> int:
    """Import reference and economics seed JSON into the database."""
    from_dir = Path(args.from_dir).resolve() if args.from_dir else None
    log.info("Seeding database (from=%s, only=%s, skip_invalid=%s)...", from_dir, args.only, args.skip_invalid)

    try:
        with get_session() as session:
            stats = seed_database(
                session=session,
                from_dir=from_dir,
                only=args.only,
                skip_invalid=args.skip_invalid,
            )
            session.commit()

        print("\n=== Database Seeding Complete ===")
        for category, counts in stats.items():
            print(f"  {category.upper()}: {counts.get('inserted', 0)} inserted, {counts.get('updated', 0)} updated, {counts.get('rejected', 0)} rejected")
        print("=================================\n")
        return 0
    except Exception as exc:
        log.error("Seeding failed: %s", exc, exc_info=True)
        return 1


def cmd_export(args: argparse.Namespace) -> int:
    """Export reference and economics data back to JSON files."""
    to_dir = Path(args.to_dir).resolve() if args.to_dir else None
    log.info("Exporting database to JSON (target: %s)...", to_dir or "default seed dir")

    try:
        with get_session() as session:
            counts = export_database(session=session, to_dir=to_dir)

        print("\n=== Database Export Complete ===")
        for table, count in counts.items():
            print(f"  {table}: {count} exported")
        print("================================\n")
        return 0
    except Exception as exc:
        log.error("Export failed: %s", exc, exc_info=True)
        return 1


def cmd_check(args: argparse.Namespace) -> int:
    """Perform integrity checks, coverage matrix review, and generate DATA_GAPS.md."""
    log.info("Running database integrity and coverage checks...")
    report_lines: List[str] = [
        "# TerraTrend Database Health & Data Gaps Report",
        f"Generated at: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## 1. Table Row Counts",
    ]

    try:
        with get_session() as session:
            tables = [
                ("States", State),
                ("Districts", District),
                ("Crops", Crop),
                ("Crop Requirements", CropRequirement),
                ("Crop Soil Preferences", CropSoilPreference),
                ("Amendment Rules", AmendmentRule),
                ("Trend Rules", TrendRule),
                ("Crop Costs (CACP)", CropCost),
                ("Benchmark Yields", BenchmarkYield),
                ("MSP", Msp),
                ("Mandi Prices", MandiPrice),
                ("Input Requirements", InputRequirement),
                ("Policy Schemes", PolicyScheme),
                ("Grid Cells", GridCell),
                ("Grid Crop Scores", GridCropScore),
            ]

            counts_table = ["| Table | Count |", "| :--- | :--- |"]
            for name, model in tables:
                cnt = session.scalar(select(func.count()).select_from(model)) or 0
                counts_table.append(f"| {name} | {cnt:,} |")
            report_lines.extend(counts_table)
            report_lines.append("")

            # 2. Constraint and Integrity Validations
            report_lines.append("## 2. Integrity & Constraint Checks")
            integrity_issues: List[str] = []

            # Check trapezoid order
            bad_reqs = session.scalars(
                select(CropRequirement).where(
                    (CropRequirement.abs_min > CropRequirement.opt_min)
                    | (CropRequirement.opt_min > CropRequirement.opt_max)
                    | (CropRequirement.opt_max > CropRequirement.abs_max)
                )
            ).all()
            if bad_reqs:
                integrity_issues.append(f"Found {len(bad_reqs)} crop requirements violating trapezoid order (min <= opt_min <= opt_max <= max).")

            # Check negative yields
            bad_yields = session.scalars(
                select(BenchmarkYield).where(BenchmarkYield.yield_q_ha <= 0)
            ).all()
            if bad_yields:
                integrity_issues.append(f"Found {len(bad_yields)} benchmark yields with non-positive values.")

            if not integrity_issues:
                report_lines.append("All structural integrity and domain constraint checks passed cleanly.")
            else:
                for issue in integrity_issues:
                    report_lines.append(f"- **WARNING**: {issue}")
            report_lines.append("")

            # 3. Economics Coverage Matrix
            report_lines.append("## 3. Economics Coverage Matrix by Crop")
            econ_repo = EconomicsRepository(session)
            matrix = econ_repo.coverage_matrix()
            by_crop = matrix.get("by_crop", {})

            report_lines.append("| Crop Key | Common Name | State Costs | Benchmark Yields | MSP | Mandi Price | Input Req | Status |")
            report_lines.append("| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |")

            all_crops = session.scalars(select(Crop).order_by(Crop.key)).all()
            total_crops = len(all_crops)
            full_coverage = 0

            for c in all_crops:
                cov = by_crop.get(c.key, {})
                has_cost = cov.get("has_costs", False)
                has_yield = cov.get("has_benchmark_yield", False)
                has_msp = cov.get("has_msp", False)
                has_mandi = cov.get("has_mandi", False)
                has_inp = cov.get("has_inputs", False)

                is_complete = has_cost and has_yield and has_inp
                if is_complete:
                    full_coverage += 1
                status = "Complete" if is_complete else "Partial"

                report_lines.append(
                    f"| {c.key} | {c.name} | {'Yes' if has_cost else 'No'} | {'Yes' if has_yield else 'No'} | {'Yes' if has_msp else 'No'} | {'Yes' if has_mandi else 'No'} | {'Yes' if has_inp else 'No'} | {status} |"
                )

            report_lines.append("")
            report_lines.append(f"**Overall Coverage:** {full_coverage}/{total_crops} crops have complete economics baseline data.")
            report_lines.append("")

            # Write DATA_GAPS.md
            report_content = "\n".join(report_lines)
            gaps_path = Path(Config.BASE_DIR) / "DATA_GAPS.md"
            gaps_path.write_text(report_content, encoding="utf-8")
            log.info("Integrity check complete. Report written to %s", gaps_path)
            print(report_content)
            return 0
    except Exception as exc:
        log.error("Check failed: %s", exc, exc_info=True)
        return 1


def cmd_backup(args: argparse.Namespace) -> int:
    """Perform hot backup of database."""
    db_url = Config.DATABASE_URL
    if db_url.startswith("sqlite"):
        # SQLite online backup
        db_path_str = db_url.replace("sqlite:///", "")
        source_path = Path(db_path_str).resolve()
        if not source_path.exists():
            log.error("Source SQLite database file does not exist: %s", source_path)
            return 1

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        if args.out:
            dest_path = Path(args.out).resolve()
        else:
            dest_dir = source_path.parent / "backups"
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_path = dest_dir / f"teratrend_backup_{timestamp}.db"

        log.info("Starting hot SQLite online backup from %s to %s...", source_path, dest_path)
        try:
            src = sqlite3.connect(str(source_path))
            dest = sqlite3.connect(str(dest_path))
            with dest:
                src.backup(dest, pages=250)
            src.close()
            dest.close()
            log.info("Backup successfully created at %s", dest_path)
            print(f"Backup created: {dest_path}")
            return 0
        except Exception as exc:
            log.error("SQLite backup failed: %s", exc)
            return 1
    else:
        # PostgreSQL
        print("\nPostgreSQL Database Detected.")
        print("To create a backup, run the following command:")
        print(f"  pg_dump \"{db_url}\" -F c -b -v -f teratrend_backup.dump\n")
        return 0


def cmd_prune_cache(args: argparse.Namespace) -> int:
    """Prune least-recently-hit assessment cache rows."""
    max_rows = args.max_rows or Config.CACHE_MAX_ROWS
    log.info("Pruning assessment cache to max %d rows...", max_rows)
    try:
        with get_session() as session:
            repo = ResultsRepository(session)
            removed = repo.prune(max_rows=max_rows)
            session.commit()
        log.info("Pruned %d stale cache entries.", removed)
        print(f"Pruned {removed} entries.")
        return 0
    except Exception as exc:
        log.error("Pruning cache failed: %s", exc)
        return 1


def cmd_precompute_grid(args: argparse.Namespace) -> int:
    """Optionally precompute scores for India territorial grid."""
    from db.repositories.grid_repo import GridRepository
    from teratrend.cube_store import get_store
    from teratrend.services.assessment_service import AssessmentService
    from teratrend.services.reference_cache import get_reference_cache

    log.info("Grid precompute invoked (limit=%s)...", args.limit)
    grid_file = Config.DATA_DIR / "processed" / "india_grid.nc"
    if not grid_file.exists():
        log.warning("No india_grid.nc found at %s. Grid precompute requires processed NetCDF grid.", grid_file)
        print(f"Grid precomputation skipped: {grid_file} does not exist.")
        return 0

    store = get_store()
    store.load_all()
    ref_cache = get_reference_cache()
    service = AssessmentService(store)
    data_version = f"{getattr(store, 'data_version', Config.CODE_VERSION)}_{ref_cache.reference_version}"

    import xarray as xr
    grid_ds = xr.open_dataset(grid_file)
    lats = grid_ds["lat"].values
    lons = grid_ds["lon"].values
    mask = grid_ds["india_mask"].values.astype(bool)

    limit = args.limit or 200
    cells_data: List[Dict[str, Any]] = []

    # Clear existing grid cells
    try:
        with get_session() as s:
            s.query(GridCropScore).delete()
            s.query(GridCell).delete()
            s.commit()
    except Exception as exc:
        log.debug("Cleanup note: %s", exc)

    count = 0
    # Step through grid with step 3 (0.75° resolution) to cover all states quickly
    for i in range(0, len(lats), 3):
        for j in range(0, len(lons), 3):
            if not mask[i, j]:
                continue
            lat = float(lats[i])
            lon = float(lons[j])
            try:
                res = service.assess_location(lat, lon)
                state_id = None
                district_id = None
                if res.get("location", {}).get("region", {}).get("state"):
                    st_name = res["location"]["region"]["state"]
                    st_obj = ref_cache.regions.get("state_map", {}).get(st_name)
                    if st_obj:
                        state_id = getattr(st_obj, "id", None) or (st_obj.get("id") if isinstance(st_obj, dict) else None)

                crop_scores = []
                for sc in res.get("suited_crops", [])[:5]:
                    e_sum = sc.get("economics_summary") or {}
                    crop_scores.append({
                        "crop_key": sc.get("key", sc.get("crop")),
                        "suitability_score": sc.get("score", sc.get("suitability_score", 0.0)),
                        "roi_pct": e_sum.get("roi_pct"),
                        "probability_of_loss_pct": e_sum.get("probability_of_loss_pct"),
                    })

                cells_data.append({
                    "cell_lat": lat,
                    "cell_lon": lon,
                    "state_id": state_id,
                    "district_id": district_id,
                    "overall_score": res["overall"]["score"],
                    "temperature_score": res["factors"]["temperature"]["score"],
                    "moisture_score": res["factors"]["moisture"]["score"],
                    "soil_ph_score": res["factors"]["soil_ph"]["score"],
                    "soil_quality_score": res["factors"]["soil_quality"]["score"],
                    "climate_score": res["factors"]["climate"]["score"],
                    "data_version": data_version,
                    "crop_scores": crop_scores,
                })
                count += 1
                if count >= limit:
                    break
            except Exception as e:
                log.debug("Skipping cell (%f, %f): %s", lat, lon, e)
        if count >= limit:
            break

    with get_session() as s:
        repo = GridRepository(s)
        inserted = repo.bulk_insert_cells_and_scores(cells_data)
        s.commit()

    log.info("Precomputed and stored %d grid cells and their crop scores.", inserted)
    print(f"Precomputation completed: {inserted} grid cells stored.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="TerraTrend Database Management CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # init
    subparsers.add_parser("init", help="Run migrations to upgrade database to head")

    # migrate
    migrate_p = subparsers.add_parser("migrate", help="Generate an alembic migration revision")
    migrate_p.add_argument("-m", "--message", help="Migration description", default=None)

    # seed
    seed_p = subparsers.add_parser("seed", help="Import reference and economics seed JSON")
    seed_p.add_argument("--from-dir", "--from", dest="from_dir", help="Path to seed data folder", default=None)
    seed_p.add_argument("--only", choices=["regions", "crops", "rules", "economics"], help="Seed single category")
    seed_p.add_argument("--skip-invalid", action="store_true", help="Log and skip invalid records rather than aborting")

    # export
    export_p = subparsers.add_parser("export", help="Export DB reference data back to JSON")
    export_p.add_argument("--to-dir", "--to", dest="to_dir", help="Target output folder", default=None)

    # check
    subparsers.add_parser("check", help="Run integrity and coverage checks, writing DATA_GAPS.md")

    # backup
    backup_p = subparsers.add_parser("backup", help="Perform database backup")
    backup_p.add_argument("--out", help="Output file path", default=None)

    # prune-cache
    prune_p = subparsers.add_parser("prune-cache", help="Prune least-recently-used cache rows")
    prune_p.add_argument("--max-rows", type=int, default=None, help="Maximum number of rows to keep")

    # precompute-grid
    pre_p = subparsers.add_parser("precompute-grid", help="Precompute land suitability grid scores")
    pre_p.add_argument("--limit", type=int, default=None, help="Limit number of cells to process")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    cmd_map = {
        "init": cmd_init,
        "migrate": cmd_migrate,
        "seed": cmd_seed,
        "export": cmd_export,
        "check": cmd_check,
        "backup": cmd_backup,
        "prune-cache": cmd_prune_cache,
        "precompute-grid": cmd_precompute_grid,
    }

    exit_code = cmd_map[args.command](args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
