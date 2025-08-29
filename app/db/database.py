from __future__ import annotations
import os
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, declarative_base

Base = declarative_base()

# Lazily created, module-global singletons
_ENGINE = None
_SESSION_FACTORY: Optional[sessionmaker] = None

def get_engine():
    """Create the Engine on first use; reuse thereafter."""
    global _ENGINE
    if _ENGINE is None:
        url = os.getenv("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL is not set")
        # future=True enables SQLAlchemy 2.0 style;
        # pool_pre_ping helps recover broken connections.
        _ENGINE = create_engine(url, pool_pre_ping=True, future=True)
    return _ENGINE

def get_session_factory() -> sessionmaker:
    """Create the sessionmaker on first use; reuse thereafter."""
    global _SESSION_FACTORY
    if _SESSION_FACTORY is None:
        _SESSION_FACTORY = sessionmaker(
            bind=get_engine(),
            autocommit=False,
            autoflush=False,
            future=True,
        )
    return _SESSION_FACTORY

def SessionLocal() -> Session:
    """Return a new Session each call (FastAPI dependency will call this)."""
    return get_session_factory()()

@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Optional helper for scripts/jobs."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close()
