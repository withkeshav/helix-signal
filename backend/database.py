import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import DateTime, Float, Integer, String, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def _default_database_url() -> str:
    db_path = Path(__file__).resolve().parent / "helix.db"
    return f"sqlite:///{db_path.as_posix()}"


DATABASE_URL = os.getenv("DATABASE_URL", _default_database_url())

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class ChainData(Base):
    __tablename__ = "chain_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    chain_name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    usdt_supply: Mapped[float] = mapped_column(Float, default=0.0)
    usdt_supply_prev_day: Mapped[float | None] = mapped_column(Float, nullable=True)
    usdt_supply_prev_week: Mapped[float | None] = mapped_column(Float, nullable=True)
    usdt_supply_prev_month: Mapped[float | None] = mapped_column(Float, nullable=True)
    tvl: Mapped[float | None] = mapped_column(Float, nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class SourceStatus(Base):
    __tablename__ = "source_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source_name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="unknown")
    last_attempted_fetch: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_successful_fetch: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_chain_data_columns()


def _ensure_chain_data_columns() -> None:
    if not DATABASE_URL.startswith("sqlite"):
        return

    expected = {
        "usdt_supply_prev_day": "FLOAT",
        "usdt_supply_prev_week": "FLOAT",
        "usdt_supply_prev_month": "FLOAT",
    }
    with engine.begin() as conn:
        existing_columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(chain_data)")).fetchall()
            if len(row) > 1
        }
        for column_name, column_type in expected.items():
            if column_name not in existing_columns:
                conn.execute(text(f"ALTER TABLE chain_data ADD COLUMN {column_name} {column_type}"))
