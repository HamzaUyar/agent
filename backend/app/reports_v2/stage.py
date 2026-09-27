"""Rapor doğrulamanın değerlendirme akışına bağlandığı yer (`stages.evaluate_reports`).

Bir görüntü için: ilgili raporlar seçilir → kanıt dosyası ve bağlam (kod) → tek LLM kararı →
kurallarla çapraz kontrol → politika (kod). Genelleme testinde tek LLM, ifadesi değişmiş
raporlarda 35 yalanın 34'ünü ve 15 tehlikeli güvencenin hepsini yakaladı; kurallar ise
ayrıştırıcıya bağımlı olduğu için 23'te kaldı. Bu yüzden karar LLM'in, kurallar ikinci görüş.

Politika (ADR-0002'nin sıkılaştırılmış hali):
- Rapor risk seviyesini değiştirmez; yalnızca bayrak ve gerekçe üretir.
- Kimlik iddiası (dost, ikmal, bize bağlı, devriye) "tutarlı" sayılamaz; en fazla doğrulanamaz.
- Kural kesin bir çelişki bulduğu hâlde LLM çelişki demediyse (ya da tersi) rapor operatöre
  "incelenmeli" diye gösterilir.
"""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path
from typing import Any

from app.data_package import to_minutes
from app.db.repositories import DataRepository
from app.llm.client import LLMRouter
from app.pipelines.detection import Detector
from app.pipelines.geo import in_footprint
from app.reports_v2 import agents, context, rules
from app.reports_v2 import evidence as ev
from app.reports_v2.verdict import ReportVerdict
from app.schemas.api import Certainty, Verdict
from app.schemas.claims import ClaimRecord
from app.schemas.domain import DataPackage, GeoPoint, ImageMeta

logger = logging.getLogger(__name__)

WINDOW_MIN = 120
IDENTITY = ("dost", "ikmal", "bize bagli", "devriye", "tatbikat")
DAY = (time(0, 0), time(23, 59))


@dataclass(frozen=True)
class ClaimEvaluation:
    """Bir iddianın bu görüntüdeki sonucu: temaslara not düşmek için gereken kadarı."""

    record: ClaimRecord
    track_id: str | None
    verdict: Verdict
    certainty: Certainty
    reasoning: str


@dataclass(frozen=True)
class VerifiedReport:
    record: ClaimRecord
    final: ReportVerdict
    rule: ReportVerdict
    llm: ReportVerdict | None
    track_id: str | None
    needs_review: bool
    model: str | None = None


@dataclass
class ReportVerifier:
    """Veri depo ve detektörden bir kez okunur; LLM cevapları önbellekte tutulur."""

    repo: DataRepository
    detector: Detector
    router: LLMRouter | None
    images_dir: Path
    cache_path: Path | None = None
    store: agents.VerdictCache | None = None
    """Verilirse (Supabase) önbellek ve kayıt burası; yoksa `cache_path` dosyası ya da bellek."""
    _data: ev.Data | None = field(default=None, init=False, repr=False)
    _cache: agents.VerdictCache | None = field(default=None, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def data(self) -> ev.Data:
        with self._lock:
            if self._data is None:
                images = self.repo.list_images()
                package = DataPackage(
                    base=self.repo.base(),
                    zones=self.repo.zones(),
                    images=images,
                    track_points=self.repo.track_points_between(*DAY),
                    reports=self.repo.reports_between(DAY[1]),
                )
                detections = {img.image_id: self._detect(img) for img in images}
                self._data = ev.Data(package, detections, self.images_dir)
            return self._data

    def _detect(self, img: ImageMeta) -> list[dict[str, Any]]:
        """Başka karelerin tipleri bağlam içindir; dosyası ya da tespiti olmayan kare atlanır."""
        try:
            found = self.detector.detect(img)
        except Exception:
            return []
        return [
            {
                "label": d.label.value,
                "confidence": d.confidence,
                "x": d.x,
                "y": d.y,
                "w": d.w,
                "h": d.h,
            }
            for d in found
        ]

    def cache(self) -> agents.VerdictCache:
        if self._cache is None:
            self._cache = self.store or agents.Cache(self.cache_path)
        return self._cache

    def _dossier(self, rid: int, rec: ClaimRecord) -> dict[str, Any]:
        """Kanıt dosyası ayrıştırılmış iddiadan: konum ve bölge iddianın, metin raporun."""
        c = rec.claim
        m = ev.COORD.search(rec.report.text)
        point = (
            GeoPoint(c.lat, c.lon)
            if c.location_type == "coordinate" and c.lat is not None and c.lon is not None
            else None
        )
        d = ev.dossier_for(
            self.data(),
            rid=rid,
            text=rec.report.text,
            minute=to_minutes(rec.report.time),
            official=rec.report.source.value == "official",
            point=point,
            decimals=len(m.group(2)) if m else None,
            zone=c.zone if c.location_type == "zone" else None,
        )
        return context.add_context(self.data(), d)

    def relevant(
        self, image: ImageMeta, zone: str, now: time, claims: list[ClaimRecord]
    ) -> list[ClaimRecord]:
        """Bu görüntüyü ilgilendiren iddialar: noktası karede olan koordinatlılar, görüntünün
        bölgesini anan bölge iddiaları (çekimden önceki 120 dk) ve konumsuz duyuruların en
        sonuncusu."""
        start = to_minutes(now) - WINDOW_MIN
        latest_general: dict[str, ClaimRecord] = {}
        out: list[ClaimRecord] = []
        for rec in claims:
            if rec.report.time > now:
                continue
            c = rec.claim
            in_window = to_minutes(rec.report.time) >= start
            if c.location_type == "coordinate" and c.lat is not None and c.lon is not None:
                if in_window and in_footprint(image, GeoPoint(c.lat, c.lon)):
                    out.append(rec)
            elif c.location_type == "zone":
                if in_window and c.zone == zone:
                    out.append(rec)
            else:
                prev = latest_general.get(rec.report.text)
                if prev is None or rec.report.time >= prev.report.time:
                    latest_general[rec.report.text] = rec
        return out + list(latest_general.values())

    def verify(
        self, image: ImageMeta, zone: str, now: time, claims: list[ClaimRecord]
    ) -> list[VerifiedReport]:
        """İlgili iddiaları doğrular; LLM çağrıları paralel gider (gateway sınırı 4)."""
        relevant = self.relevant(image, zone, now, claims)

        def judge(rec: ClaimRecord) -> _Judged:
            dossier = self._dossier(rec.claim_id, rec)
            rule = rules.judge(dossier, rec.claim)
            llm: ReportVerdict | None = None
            model: str | None = None
            key: str | None = None
            if self.router is not None:
                try:
                    compact = ev.compact(dossier)
                    llm, models, key = agents.single_llm(self.router, self.cache(), compact)
                    model = models[0] if models else None
                except Exception:
                    llm = None
            return _Judged(rule, llm, _linked_track(dossier), model, key, dossier)

        with ThreadPoolExecutor(max_workers=4) as pool:
            done = list(pool.map(judge, relevant))
        results: list[VerifiedReport] = []
        for rec, j in zip(relevant, done, strict=True):
            final, review = combine(j.rule, j.llm, rec.report.text)
            results.append(VerifiedReport(rec, final, j.rule, j.llm, j.track, review, j.model))
            self._record(rec, image, j, final, review)
        return results

    def _record(
        self, rec: ClaimRecord, image: ImageMeta, j: "_Judged", final: ReportVerdict, review: bool
    ) -> None:
        """Depo kayıt destekliyorsa (Supabase) kural kararını ve nihai sonucu yazar."""
        annotate = getattr(self.cache(), "annotate", None)
        if annotate is None or j.key is None:
            return
        located = rec.claim.location_type == "coordinate"
        try:
            annotate(
                j.key,
                claim_id=rec.claim_id,
                image_id=image.image_id if located else None,
                final=final.model_dump(),
                rule_verdict=j.rule.verdict,
                needs_review=review,
                dossier=j.dossier,
            )
        except Exception:
            logger.warning(
                "rapor doğrulama kaydı yazılamadı (iddia %s)", rec.claim_id, exc_info=True
            )


@dataclass(frozen=True)
class _Judged:
    rule: ReportVerdict
    llm: ReportVerdict | None
    track: str | None
    model: str | None
    key: str | None
    dossier: dict[str, Any]


def _linked_track(dossier: dict[str, Any]) -> str | None:
    bind = 15.0 if dossier.get("koordinat_ondalik", 0) >= 5 else 35.0
    for c in dossier.get("noktadaki_temaslar_cekim_aninda") or []:
        if c["noktaya_uzaklik_m"] <= bind:
            return c["iz"] if str(c["iz"]).startswith("T") else None
    return None


def combine(
    rule: ReportVerdict, llm: ReportVerdict | None, text: str
) -> tuple[ReportVerdict, bool]:
    """Karar LLM'in (yoksa kuralın); ikisi çelişki konusunda ayrışırsa operatör incelemesi.
    Politika kodla uygulanır."""
    final = llm or rule
    review = False
    if llm is not None:
        rule_says = rule.verdict == "contradicts"
        llm_says = llm.verdict in ("contradicts", "partial")
        review = rule_says != llm_says
        flags = list(dict.fromkeys([*llm.context_flags, *rule.context_flags]))
        final = llm.model_copy(
            update={
                "context_flags": flags,
                "dangerous_reassurance": llm.dangerous_reassurance or rule.dangerous_reassurance,
            }
        )
    if any(k in text.lower() for k in IDENTITY) and final.verdict == "consistent":
        final = final.model_copy(
            update={
                "verdict": "unverifiable",
                "reasoning": final.reasoning + " Kimlik doğrulanamaz.",
            }
        )
    if final.harm == "lowers_risk" and final.verdict == "contradicts":
        final = final.model_copy(update={"dangerous_reassurance": True})
    return final, review
