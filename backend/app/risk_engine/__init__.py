"""Zaman boyutlu risk motoru.

Her iz, ilk noktasından itibaren her gözlem adımında yalnız o ana kadarki noktalarla
değerlendirilir (ADR-0001). Katmanlar:
  features  nedensel hareket özellikleri
  rules     seviye tablosu (giriş ve çıkış) ve etiketler
  state     durum makinesi: yayınlanan seviye, iniş beklemesi, bildirimler
  priority  0-100 öncelik skoru (seviyeyi değiştirmez)
  summary   olay kayıtları ve görüntü özeti
Parametreler `app/core/risk_engine.toml`.
"""

from app.risk_engine.config import EngineConfig, default_config, load_config
from app.risk_engine.features import Point, to_local
from app.risk_engine.rules import LEVEL_NAMES, RULE_TEXT, unregistered_level
from app.risk_engine.state import Notice, Step, TrackRisk, run_track

__all__ = [
    "LEVEL_NAMES",
    "RULE_TEXT",
    "EngineConfig",
    "Notice",
    "Point",
    "Step",
    "TrackRisk",
    "default_config",
    "load_config",
    "run_track",
    "to_local",
    "unregistered_level",
]
