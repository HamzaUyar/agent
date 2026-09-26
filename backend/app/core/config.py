"""Ayarlar (pydantic-settings); değerler `.env` dosyasından okunur."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    supabase_url: str = ""
    supabase_service_role_key: SecretStr = SecretStr("")
    database_url: SecretStr = SecretStr("")
    storage_bucket: str = "drone-images"
    """Drone görüntülerinin Supabase Storage bucket'ı."""

    anthropic_api_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")
    glm_api_key: SecretStr = SecretStr("")
    glm_api_base: str = "https://berriailitellm-databasev1826rc3-production-d691.up.railway.app/v1"
    """Organizatörlerin gateway'i (görev tanımı s4)."""
    glm_max_concurrent: int = 4
    glm_requests_per_minute: int = 60
    glm_tokens_per_minute: int = 500_000
    glm_budget_usd: float = 15.0
    glm_price_input_per_mtok: float = 0.0
    """Harcama tahmini için fiyat (USD / 1M token); 0 ise bütçe sınırı devreye girmez."""
    glm_price_output_per_mtok: float = 0.0
    evren_api_key: SecretStr = SecretStr("")
    evren_api_base: str = "https://evren-llmapi.ssyz.org.tr/v1"

    data_dir: Path = Path("../../stage2")
    data_source: Literal["supabase", "package"] = "supabase"
    """package: veri `data_dir`'den, iddialar `claims_path`'ten; kayıtlar bellekte (çevrimdışı)."""
    claims_path: str = ""
    """Ayrıştırılmış iddiaların JSON'u (`scripts/export_claims.py`); `data_source=package` için."""
    use_inference: Literal["DEMO", "REAL"] = "DEMO"
    """DEMO: tespitler modelin önceden alınmış çıktısından (Supabase `model_detections` ya da
    `detections_csv_path`); REAL: görüntü EVREN'deki modele gönderilir."""
    detections_csv_path: str = "../../stage2/detections_all.csv"
    """DEMO + `data_source=package`: modelin çıktısı (image_id, cls, score, x, y, w, h)."""
    detections_source: str = "detections_all.csv"
    """DEMO + `data_source=supabase`: `model_detections.source` değeri."""
    evren_model_api_key: SecretStr = SecretStr("")
    """EVREN model platformu anahtarı (tespit modeli); LLM anahtarından ayrı."""
    evren_detector_model: str = "u84f118304558/d2-y26l-v2-60ep-mixup01"
    """Ekibin EVREN'deki tespit modeli (`sahip/slug`)."""
    detector_imgsz: int | None = None
    """EVREN modelinin çıkarım boyutu; boşsa `EVREN_IMAGE_SIZE`."""

    @property
    def resolved_data_dir(self) -> Path:
        """`data_dir`, backend klasörüne göre çözümlenmiş hali."""
        return _resolve(self.data_dir)

    @property
    def resolved_claims_path(self) -> Path | None:
        return _resolve(Path(self.claims_path)) if self.claims_path else None

    @property
    def resolved_detections_csv_path(self) -> Path:
        return _resolve(Path(self.detections_csv_path))


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else (BACKEND_DIR / path).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
