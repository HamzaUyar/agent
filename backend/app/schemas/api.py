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


class RoutePoint(LatLon):
    time: str | None = None
    """Kayıt saati (SS:DD); bu alandan önce kaydedilmiş brief'lerde yok."""


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
    distance_to_base_60min_ago_m: float | None
    trend: Trend
    route: list[RoutePoint] = Field(default_factory=list)
    """Çekim anına kadarki kayıtlı noktalar, zamana göre sıralı (ADR-0001)."""
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
    # Kaydın tamamında üsse en yakın ve en uzak mesafe (m).
    base_distance_min_m: float
    base_distance_max_m: float
    # Kaydın kapsadığı alan: birbirine en uzak iki noktanın arası (m).
    extent_m: float


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


AttentionReason = Literal[
    "yaklasma",
    "dolasma",
    "uzun_duraklama",
    "tehdit_uyarisi",
    "rapor_celiskisi",
    "kacirilmis_temas",
    "kayit_disi",
    "dikkat_gerekmiyor",
]
"""Karar LLM'inin bir temas için seçebileceği dikkat nedenleri; her biri kodla doğrulanır."""


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
    level_basis: list[AttentionReason] = Field(default_factory=list)
    """Kuralların seviyede zaten saydığı dikkat nedenleri; LLM bunlarla yükseltemez."""
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


class AttentionFinding(BaseModel):
    """Karar LLM'inin bir dikkat maddesi ve kodun onu veriyle doğrulamasının sonucu."""

    contact: str
    """Temas etiketi: track kimliği ya da kayıt dışı temas için `kayit_disi_N`."""
    track_id: str | None
    reason: AttentionReason
    basis: list[int | str]
    """Dayanılan bulgu alanları ve rapor iddialarının kimlikleri."""
    level_proposal: RiskLevel | None = None
    accepted: bool
    """Neden veriyle doğrulandı."""
    level_accepted: bool | None = None
    """Seviye önerisi kabul edildi mi; öneri yoksa ya da seviyeyi değiştirmiyorsa `None`."""
    rejection: str | None = None
    """Nedenin ya da seviye önerisinin reddedilme sebebi."""
    text: str | None = None
    """Doğrulanmış nedenin kodla yazılmış açıklaması (sayılar bulgu alanlarından)."""


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
    attention: list[AttentionFinding] = Field(default_factory=list)
    """Karar LLM'inin dikkat maddeleri ve doğrulamaları; otomatik özette boş."""
    summary: str | None = None
    """LLM'in kısa özeti; sayı, kimlik, bölge adı ya da İngilizce terim içeriyorsa atılır."""
    summary_rejected: str | None = None
    """Özet atıldıysa sebebi."""


class StepEvent(BaseModel):
    """Değerlendirme adımı; arayüze SSE ile akar ve kaydedilir."""

    step_no: int
    name: str
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)


Pair = tuple[float, float]
"""[lat, lon]; veri paketindeki sıra."""


class BaseInfo(BaseModel):
    name: str
    lat: float
    lon: float


class ZoneInfo(BaseModel):
    name: str
    center: Pair


class ZonesResponse(BaseModel):
    """Üs ve bölgeler, `zones.json` biçiminde. Bölgelerin sınırı yok, yalnızca merkezi var."""

    base: BaseInfo
    zones: list[ZoneInfo]


class CornerCoordinates(BaseModel):
    top_left: Pair
    top_right: Pair
    bottom_left: Pair
    bottom_right: Pair


class ImageDetail(BaseModel):
    """Görüntünün `image_meta.json` kaydı; karenin merkezi ve bölgesiyle."""

    image_id: str
    width_px: int
    height_px: int
    capture_time: str
    corner_coordinates: CornerCoordinates
    center: Pair
    zone: str


class ImageSummary(BaseModel):
    image_id: str
    zone: str
    capture_time: str
    last_risk_level: RiskLevel | None = None


class ContactLevel(BaseModel):
    """Kayıtlı bir değerlendirmedeki temasın seviye özeti. Brief'in yalnızca bu alanları
    okunur; eski kod sürümlerinin kayıtları da (sonradan eklenen hareket alanları olmadan)
    buna uyar."""

    track_id: str | None
    final_level: RiskLevel
    kind: ContactKind
    label: str | None = None
    effective_label: str | None = None


class TrackOverview(BaseModel):
    """Bir track'in bütün kaydı ve bittiği görüntünün son değerlendirmesindeki yeri.

    Her track bir görüntünün çekim anında o görüntünün karesinde biter (kaydı o görüntünün
    son iki saatidir). Seviye ve sınıf o görüntünün son tamamlanmış değerlendirmesindeki
    temastan okunur; yeniden hesaplanmaz. Değerlendirme yoksa `None`.
    """

    track_id: str
    start: str
    end: str
    points: list[RoutePoint]
    image_id: str | None = None
    """Track'in bittiği görüntü: çekim anı track'in son kaydı ve son konum karede."""
    level: RiskLevel | None = None
    label: str | None = None
    """Temasın (riskte sayılan) sınıfı; tespit yoksa (kaçırılmış temas) `None`."""
    kind: ContactKind | None = None


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
