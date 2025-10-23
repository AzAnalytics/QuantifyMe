# app/persistence/db.py
# -*- coding: utf-8 -*-
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager
import os

DB_URL = os.getenv("DB_URL", "sqlite:///quantifyme.db")

engine = create_engine(DB_URL, echo=False, future=True)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,  # important pour éviter DetachedInstanceError
    future=True,
)

@contextmanager
def get_session():
    """Contexte gérant automatiquement commit/rollback."""
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()

def init_db(Base, drop_and_recreate=False):
    """Crée les tables (et les recrée si demandé)."""
    if drop_and_recreate:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
