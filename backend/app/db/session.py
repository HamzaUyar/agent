"""Postgres (Supabase) bağlantısı."""

import psycopg

from app.core.config import Settings, get_settings


def connect(settings: Settings | None = None) -> psycopg.Connection:
    """`DATABASE_URL` ile yeni bir bağlantı açar; çağıran kapatmaktan sorumludur."""
    url = (settings or get_settings()).database_url.get_secret_value()
    if not url:
        raise RuntimeError("DATABASE_URL tanımlı değil (.env)")
    # SQLAlchemy biçimindeki sürücü önekini psycopg'nin anladığı biçime çevir.
    return psycopg.connect(url.replace("postgresql+psycopg://", "postgresql://", 1))
