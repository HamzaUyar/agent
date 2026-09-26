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

    anthropic_api_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")
    glm_api_key: SecretStr = SecretStr("")
    glm_api_base: str = "https://berriailitellm-databasev1826rc3-production-d691.up.railway.app/v1"
    """Organizatörlerin gateway'i (görev tanımı s4)."""
    glm_max_concurrent: int = 4
    glm_requests_per_minute: int = 60
    glm_budget_usd: float = 15.0
    glm_price_input_per_mtok: float = 0.0
    """Harcama tahmini için fiyat (USD / 1M token); 0 ise bütçe sınırı devreye girmez."""
    glm_price_output_per_mtok: float = 0.0
    evren_api_key: SecretStr = SecretStr("")
    evren_api_base: str = "https://evren-llmapi.ssyz.org.tr/v1"

    data_dir: Path = Path("../../stage2")
    detector_mode: Literal["mock", "evren", "model"] = "mock"
    detector_weights_path: str = ""
    evren_model_api_key: SecretStr = SecretStr("")
    """EVREN model platformu anahtarı (tespit modeli); LLM anahtarından ayrı."""
    evren_detector_model: str = "u84f118304558/d2-y26l-v2-60ep-mixup01"
    """Ekibin EVREN'deki tespit modeli (`sahip/slug`)."""
    detector_mock_path: str = ""
    """Sahte tespitlerin JSON dosyası (ör. sentetik `detections.json`); boşsa yerleşik örnek."""
    detector_imgsz: int | None = None
    """Modelin çıkarım boyutu; boşsa Ultralytics'in varsayılanı."""

    @property
    def resolved_data_dir(self) -> Path:
        """`data_dir`, backend klasörüne göre çözümlenmiş hali."""
        return _resolve(self.data_dir)

    @property
    def resolved_weights_path(self) -> Path | None:
        """Model ağırlıkları, backend klasörüne göre çözümlenmiş; tanımlı değilse `None`."""
        return _resolve(Path(self.detector_weights_path)) if self.detector_weights_path else None

    @property
    def resolved_mock_path(self) -> Path | None:
        """Sahte tespit dosyası, backend klasörüne göre çözümlenmiş; tanımlı değilse `None`."""
        return _resolve(Path(self.detector_mock_path)) if self.detector_mock_path else None


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else (BACKEND_DIR / path).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
