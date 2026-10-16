"""Database wiring. The DB hostname is visible only on the Compose network."""

import os

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, sessionmaker


def database_url() -> URL:
    password = os.environ.get("DB_PASSWORD")
    if not password:
        raise RuntimeError("DB_PASSWORD is required")

    return URL.create(
        drivername="postgresql+psycopg",
        username=os.environ.get("DB_USER", "magicvvu_admin"),
        password=password,
        host=os.environ.get("DB_HOST", "db"),
        port=int(os.environ.get("DB_PORT", "5432")),
        database=os.environ.get("DB_NAME", "magicvvu"),
    )


engine = create_engine(
    database_url(),
    pool_size=2,
    max_overflow=0,
    pool_timeout=5,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 5},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass
