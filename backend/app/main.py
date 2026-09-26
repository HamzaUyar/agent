"""FastAPI uygulaması.

Açılışta kaynak veri bir kez okunup bellek içi depoya alınır: veri küçük ve statik.
Varsayılan kaynak Supabase'tir; `DATA_SOURCE=package` ile veri paketi ve iddia dosyası
diskten okunur, kayıtlar bellekte tutulur (ağsız demo). Pipeline'lar `DataRepository`
arayüzüne bağlı olduğu için doğrudan sorgu atan bir depo gerektiğinde değiştirilebilir.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool

from app.api import analyze, data
from app.api.stores import DatabaseStores, MemoryStores, Stores
from app.core.config import Settings, get_settings
from app.data_package import load_claims, read_package
from app.db.models import fetch_claims, fetch_package
from app.db.repositories import InMemoryRepository
from app.db.session import connect
from app.llm.client import build_router
from app.pipelines.detection import build_detector
from app.pipelines.vision import VlmVerifier
from app.storage import build_storage


def _load_repository(settings: Settings) -> InMemoryRepository:
    if settings.data_source == "package":
        claims_path = settings.resolved_claims_path
        if claims_path is None or not claims_path.is_file():
            raise ValueError(
                "DATA_SOURCE=package için CLAIMS_PATH tanımlı olmalı (scripts/export_claims.py)"
            )
        return InMemoryRepository(
            read_package(settings.resolved_data_dir), claims=load_claims(claims_path)
        )
    with connect() as conn:
        return InMemoryRepository(fetch_package(conn), claims=fetch_claims(conn))


def _stores(settings: Settings) -> Stores:
    return MemoryStores() if settings.data_source == "package" else DatabaseStores()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.repository = await run_in_threadpool(_load_repository, settings)
    app.state.stores = _stores(settings)
    app.state.detector = build_detector(settings)
    app.state.router = build_router(check_budget=True)
    app.state.verifier = VlmVerifier(
        app.state.router,
        settings.resolved_data_dir / "images",
        storage=build_storage(settings),
    )
    yield


app = FastAPI(title="Üs Koruma Karar Destek", version="0.1.0", lifespan=lifespan)
app.include_router(data.router)
app.include_router(analyze.router)
