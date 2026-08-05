"""Engine and session factories. Components pass the URL in — this lib reads no env."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def create_db_engine(url: str, *, echo: bool = False) -> Engine:
    return create_engine(url, echo=echo, pool_pre_ping=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
