from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str | None = None):
    database_url = url or get_settings().database_url
    kwargs = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, future=True, pool_pre_ping=True, connect_args=kwargs)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(target_engine=engine) -> None:
    from app import models  # noqa: F401
    from app import domain  # noqa: F401

    Base.metadata.create_all(bind=target_engine)
    if target_engine.dialect.name == 'postgresql':
        from app.ingestion import install_search

        with Session(target_engine) as migration_session:
            install_search(migration_session)
            migration_session.commit()


def get_session() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session


def session_dependency(target_engine):
    """Build a request dependency whose sessions use the supplied engine."""
    factory = sessionmaker(bind=target_engine, autoflush=False, expire_on_commit=False)

    def dependency() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    return dependency
