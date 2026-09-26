"""FastAPI uygulaması.

Açılışta kaynak veri Supabase'ten bir kez okunup bellek içi depoya alınır: veri küçük
ve statik. Pipeline'lar `DataRepository` arayüzüne bağlı olduğu için doğrudan sorgu
atan bir depo gerektiğinde değiştirilebilir.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool

from app.api import analyze, data
from app.core.config import get_settings
from app.db.models import fetch_claims, fetch_package
from app.db.repositories import InMemoryRepository
from app.db.session import connect
from app.llm.client import build_router
from app.pipelines.detection import build_detector
from app.pipelines.vision import VlmVerifier


def _load_repository() -> InMemoryRepository:
    with connect() as conn:
        return InMemoryRepository(fetch_package(conn), claims=fetch_claims(conn))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.repository = await run_in_threadpool(_load_repository)
    app.state.detector = build_detector(get_settings())
    app.state.router = build_router()
    app.state.verifier = VlmVerifier(app.state.router, get_settings().resolved_data_dir / "images")
    yield


app = FastAPI(title="Üs Koruma Karar Destek", version="0.1.0", lifespan=lifespan)
app.include_router(data.router)
app.include_router(analyze.router)

