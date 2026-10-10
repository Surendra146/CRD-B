from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config.settings import get_settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    future=True,
)

control_engine = create_engine(get_settings().control_database_url, pool_pre_ping=True, pool_size=5, max_overflow=10)
ControlSessionLocal = sessionmaker(bind=control_engine, autoflush=False, autocommit=False, future=True)


def get_control_db():
    # Trusted identity/provider/platform paths only; never use for tenant CRM queries.
    with ControlSessionLocal() as db:
        yield db


from app.database import tenancy  # Register transaction-local scope listener.

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_all() -> None:
    from app.models import create_tables

    create_tables(bind=engine)

