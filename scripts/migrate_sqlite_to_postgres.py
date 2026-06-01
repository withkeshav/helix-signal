#!/usr/bin/env python3
"""
Copy Helix-Signal data from SQLite to PostgreSQL/Timescale without data loss.

Prerequisites:
  - Target Postgres is up and empty (or use --skip-existing for idempotent re-run)
  - HELIX_USE_ALEMBIC=true on target so schema exists

Environment:
  SQLITE_SOURCE_URL   e.g. sqlite:////data/helix.db
  DATABASE_URL        e.g. postgresql+psycopg2://helix:helix@postgres:5432/helix

Usage:
  python scripts/migrate_sqlite_to_postgres.py --backup /data/helix.db
  python scripts/migrate_sqlite_to_postgres.py --verify-only
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# Run from repo root or backend/
ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker

from database import (
    AssetChainSnapshot,
    AssetTrendSnapshot,
    ChainTrendSnapshot,
    ForecastPoint,
    ForecastRun,
    OsintArticle,
    SignalEvent,
    SourceStatus,
)

MODELS_IN_ORDER = [
    SourceStatus,
    AssetChainSnapshot,
    AssetTrendSnapshot,
    ChainTrendSnapshot,
    ForecastRun,
    ForecastPoint,
    SignalEvent,
    OsintArticle,
]


def _row_dict(obj) -> dict:
    return {attr.key: getattr(obj, attr.key) for attr in inspect(obj).mapper.column_attrs}


def _backup_sqlite_file(sqlite_url: str, backup_dir: Path) -> Path:
    if not sqlite_url.startswith("sqlite:///"):
        raise SystemExit("Backup only supported for sqlite:/// URLs")
    src = Path(sqlite_url.replace("sqlite:///", "", 1))
    if not src.is_file():
        raise SystemExit(f"SQLite file not found: {src}")
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = backup_dir / f"helix_pre_postgres_{stamp}.db"
    shutil.copy2(src, dest)
    print(f"OK: backup written to {dest}")
    return dest


def _count(session: Session, model) -> int:
    return session.query(model).count()


def _copy_table(src: Session, dst: Session, model, *, skip_existing: bool) -> tuple[int, int]:
    rows = src.query(model).all()
    inserted = 0
    skipped = 0
    for row in rows:
        data = _row_dict(row)
        if skip_existing:
            existing = dst.get(model, data.get("id"))
            if existing is not None:
                skipped += 1
                continue
        dst.merge(model(**data))
        inserted += 1
    dst.commit()
    return inserted, skipped


def _verify_counts(src: Session, dst: Session) -> bool:
    ok = True
    for model in MODELS_IN_ORDER:
        sc = _count(src, model)
        dc = _count(dst, model)
        name = model.__tablename__
        if sc != dc:
            print(f"MISMATCH {name}: sqlite={sc} postgres={dc}")
            ok = False
        else:
            print(f"OK {name}: {sc} rows")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate Helix-Signal SQLite → PostgreSQL")
    parser.add_argument("--backup", metavar="SQLITE_PATH", help="Copy SQLite file before migrate")
    parser.add_argument("--backup-dir", default="/data/backups", help="Backup directory on server")
    parser.add_argument("--verify-only", action="store_true", help="Compare row counts only")
    parser.add_argument("--skip-existing", action="store_true", help="Skip rows already present by id")
    parser.add_argument("--no-alembic", action="store_true", help="Skip alembic upgrade on target")
    args = parser.parse_args()

    sqlite_url = os.environ.get("SQLITE_SOURCE_URL", "sqlite:///data/helix.db")
    pg_url = os.environ.get("DATABASE_URL", "")
    if not pg_url.startswith("postgresql"):
        print("ERROR: DATABASE_URL must be a postgresql URL", file=sys.stderr)
        return 1

    if args.backup:
        sqlite_url = f"sqlite:///{Path(args.backup).resolve().as_posix()}"
        _backup_sqlite_file(sqlite_url, Path(args.backup_dir))

    src_engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})
    dst_engine = create_engine(pg_url)

    Src = sessionmaker(bind=src_engine)
    Dst = sessionmaker(bind=dst_engine)

    if args.verify_only:
        with Src() as src, Dst() as dst:
            return 0 if _verify_counts(src, dst) else 2

    os.environ["DATABASE_URL"] = pg_url
    os.environ["HELIX_USE_ALEMBIC"] = "true"
    if not args.no_alembic:
        import importlib
        import database

        importlib.reload(database)
        database.upgrade_db()
        print("OK: alembic upgrade head on target")

    with Src() as src, Dst() as dst:
        for model in MODELS_IN_ORDER:
            ins, skip = _copy_table(src, dst, model, skip_existing=args.skip_existing)
            print(f"Copied {model.__tablename__}: inserted={ins} skipped={skip}")

        if not _verify_counts(src, dst):
            print("ERROR: row count verification failed — do not cut over", file=sys.stderr)
            return 2

    print("OK: migration complete — safe to point DATABASE_URL at Postgres and restart backend")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
