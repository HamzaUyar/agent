"""Değerlendirme ve sohbet kayıtlarının deposu: Supabase ya da bellek içi.

Bellek içi depo veritabanısız (çevrimdışı) demo içindir: kayıtlar süreç kapanınca kaybolur,
önbellek süreç boyunca çalışır.
"""

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Protocol

from app.agent.chat import ChatStore, InMemoryChatStore
from app.agent.runner import InMemoryRunStore, RunStore
from app.db.models import ChatRecorder, RunRecorder
from app.db.session import connect


class Stores(Protocol):
    def open(self) -> AbstractContextManager[tuple[RunStore, ChatStore]]: ...


class DatabaseStores:
    """Her istek için yeni bir Supabase bağlantısı."""

    @contextmanager
    def open(self) -> Iterator[tuple[RunStore, ChatStore]]:
        with connect() as conn:
            yield RunRecorder(conn), ChatRecorder(conn)


class MemoryStores:
    def __init__(self) -> None:
        self._runs = InMemoryRunStore()
        self._chats = InMemoryChatStore()

    @contextmanager
    def open(self) -> Iterator[tuple[RunStore, ChatStore]]:
        yield self._runs, self._chats
