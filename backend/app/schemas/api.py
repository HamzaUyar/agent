"""API modelleri. Yapılandırılmış Brief, arayüzün ve kayıtların ortak sözleşmesidir."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.domain import CargoState, RiskLevel, Trend, VehicleColor

ContactKind = Literal["matched", "unregistered", "missed"]
"""matched: Tespit + Track · unregistered: kayıt dışı temas · missed: kaçırılmış temas."""
Certainty = Literal["certain", "likely", "weak", "unverified"]


class LatLon(BaseModel):
    lat: float
    lon: float


class TrackCandidate(BaseModel):
    track_id: str
    distance_m: float


class StopFinding(BaseModel):
    """Duraklama: saat (SS:DD), süre, yer ve bölge."""

    start: str
    end: str
    minutes: int
    location: LatLon
    zone: str
    distance_to_base_m: float


class MotionFinding(BaseModel):
    distance_to_base_m: float
    distance_to_base_30min_ago_m: float | None
    trend: Trend
    route: list[LatLon] = Field(default_factory=list)
    total_distance_m: float
    avg_speed_mps: float
    recent_speed_mps: float
    heading_deg: float | None
    stops: list[StopFinding] = Field(default_factory=list)
    zones_passed: list[str] = Field(default_factory=list)
    # Çekim anında süren duraklamanın süresi (dk); duraklamada değilse yok.
    current_stop_minutes: int | None
    # Süren duraklama bilinen ilk noktadan beri sürüyor: gerçek süre en az bu kadar.
    stop_open_ended: bool


class LabelObservation(BaseModel):
    image_id: str
    label: str


class VisualFinding(BaseModel):
    """VLM'in bir tespit kutusunda gördükleri; bilemediği özellik boş kalır."""

    is_vehicle: bool
    color: VehicleColor | None
    cargo: CargoState | None
    model: str
    """Cevabı veren model (`sağlayıcı/model`)."""


class ContactFinding(BaseModel):
    """Temas: bir Tespit ve/veya onu çekim anında karşılayan Track."""

    kind: ContactKind
    label: str | None
    """Bu karedeki tespit sınıfı; kaçırılmış temasta yok."""
    effective_label: str | None
    """Riskte kullanılan sınıf: önceki karelerle çelişki varsa daha riskli olan."""
    confidence: float | None
    bbox: tuple[float, float, float, float] | None
    location: LatLon
    is_weak: bool = False
    is_ambiguous: bool = False
    position_estimated: bool = False
    type_conflict: bool = False
    verified_friend: bool = False
    """Resmi ve bütün özellikleri doğrulanmış dostluk iddiası (ADR-0002)."""
    observed_labels: list[LabelObservation] = Field(default_factory=list)
    distance_to_base_m: float
    track_id: str | None = None
    match_distance_m: float | None = None
    second_candidate: TrackCandidate | None = None
    motion: MotionFinding | None = None
    visual: VisualFinding | None = None
    """Görsel doğrulama; yalnızca gerektiğinde (zayıf tespit, renk ya da yük iddiası) yapılır."""
    base_level: RiskLevel
    final_level: RiskLevel
    level_reasons: list[str] = Field(default_factory=list)
    adjustment_reason: str | None = None
    """LLM'in kabul edilen ±1 kademe ayarının gerekçesi."""
    adjustment_rejected: str | None = None
    """LLM'in reddedilen önerisi ve red sebebi."""
    certainty: Certainty


Verdict = Literal["consistent", "contradicts", "unverifiable", "irrelevant"]
Effect = Literal["raises", "lowers", "none"]
TimeCheck = Literal["ok", "mismatch", "unknown"]


class ReportFinding(BaseModel):
    """Rapor kararı: bir iddianın bu değerlendirmedeki sonucu ve riske etkisi."""

    claim_id: int
    report_time: str
    source: str
    text: str
    claim_type: str
    track_id: str | None
    verdict: Verdict
    certainty: Certainty
    effect: Effect
    # Bağlanan temasın rapor saatindeki konumu iddiayla uyuşuyor mu.
    time_check: TimeCheck
    reasoning: str


class Brief(BaseModel):
    image_id: str
    zone: str
    capture_time: str
    risk_level: RiskLevel
    recommended_action: str
    is_fallback: bool
    fallback_reason: str | None = None
    model: str | None = None
    """Brief'i yazan model (`sağlayıcı/model`); otomatik özette yok."""
    contacts: list[ContactFinding]
    report_findings: list[ReportFinding] = Field(default_factory=list)
    text: str
    sources: list[str]


class StepEvent(BaseModel):
    """Değerlendirme adımı; arayüze SSE ile akar ve kaydedilir."""

    step_no: int
    name: str
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)


class ImageSummary(BaseModel):
    image_id: str
    zone: str
    capture_time: str
    last_risk_level: RiskLevel | None = None


class EvaluationRequest(BaseModel):
    image_id: str
    recompute: bool = False
    """True ise önbellekteki sonuç yerine yeni değerlendirme başlatılır."""


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class EvaluationRecord(BaseModel):
    """Kayıtlı bir değerlendirme: bütün adımları ve brief'i."""

    run_id: str
    image_id: str
    status: Literal["running", "done", "failed"]
    steps: list[StepEvent]
    brief: Brief | None
    error: str | None
