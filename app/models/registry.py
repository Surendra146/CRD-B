from sqlalchemy.engine import Engine

from app.database.connection import Base

from . import tables


def create_tables(bind: Engine) -> None:
    Base.metadata.create_all(bind=bind)
