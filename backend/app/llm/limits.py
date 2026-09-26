"""Organizatör gateway'inin takım limitleri (görev tanımı s4, s10).

Aynı anda en fazla 4 istek, dakikada 60 istek ve toplam 15 USD bütçe. Limitler süreç
geneli tutulur: FastAPI thread havuzundaki bütün değerlendirmeler ve süresi dolup arka
planda biten çağrılar da aynı sayaçlara girer.
"""

import logging
import threading
import time
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager

logger = logging.getLogger(__name__)

WINDOW_S = 60.0


class BudgetExceededError(RuntimeError):
    """Tahmini harcama bütçeye ulaştı; gateway'e yeni istek gönderilmez."""


class GatewayLimits:
    """Eşzamanlılık, dakikalık istek ve bütçe sınırı.

    Harcama, cevaplardaki token sayılarından ve verilen fiyatlardan tahmin edilir; fiyat
    verilmezse (0) yalnızca token sayılır, bütçe sınırı devreye girmez. Gerçek harcama
    gateway'in `/key/info` uç noktasındadır.
    """

    def __init__(
        self,
        *,
        max_concurrent: int = 4,
        per_minute: int = 60,
        budget_usd: float | None = None,
        price_input_per_mtok: float = 0.0,
        price_output_per_mtok: float = 0.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._slots = threading.BoundedSemaphore(max_concurrent)
        self._per_minute = per_minute
        self._starts: deque[float] = deque()
        self._lock = threading.Lock()
        self._budget_usd = budget_usd
        self._prices = (price_input_per_mtok, price_output_per_mtok)
        self._clock = clock
        self._sleep = sleep
        self.input_tokens = 0
        self.output_tokens = 0

    @property
    def spent_usd(self) -> float:
        price_in, price_out = self._prices
        return (self.input_tokens * price_in + self.output_tokens * price_out) / 1_000_000

    def record_usage(self, input_tokens: int, output_tokens: int) -> None:
        with self._lock:
            self.input_tokens += input_tokens
            self.output_tokens += output_tokens
        logger.info(
            "gateway kullanımı: %d girdi, %d çıktı token (tahmini %.3f USD)",
            self.input_tokens,
            self.output_tokens,
            self.spent_usd,
        )

    @contextmanager
    def slot(self) -> Iterator[None]:
        """Bir istek için yer ayırır: bütçe, eşzamanlılık ve dakikalık sınır."""
        if self._budget_usd is not None and self.spent_usd >= self._budget_usd:
            raise BudgetExceededError(
                f"tahmini harcama {self.spent_usd:.2f} USD, bütçe {self._budget_usd:.2f} USD"
            )
        with self._slots:
            self._wait_for_rate()
            yield

    def _wait_for_rate(self) -> None:
        while True:
            with self._lock:
                now = self._clock()
                while self._starts and now - self._starts[0] >= WINDOW_S:
                    self._starts.popleft()
                if len(self._starts) < self._per_minute:
                    self._starts.append(now)
                    return
                wait = WINDOW_S - (now - self._starts[0])
            logger.info("dakikalık istek sınırı: %.1f sn bekleniyor", wait)
            self._sleep(wait)
