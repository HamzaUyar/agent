"""Bütün yaklaşımların ortak çıktısı: bir raporun doğrulama kararı."""

from typing import Literal, get_args

from pydantic import BaseModel, Field

VerdictLabel = Literal["consistent", "partial", "contradicts", "unverifiable", "irrelevant"]
Harm = Literal["lowers_risk", "raises_risk", "none"]
CheckStatus = Literal["match", "mismatch", "unverified", "not_claimed"]
ContextFlag = Literal[
    "olası örtü hikâyesi",
    "telsiz kopukluğu + ağır araç hareketi",
    "gece ihbarı bölgesinden kalkış",
]
CONTEXT_FLAGS: tuple[str, ...] = get_args(ContextFlag)


def normalize_flags(flags: object) -> list[str]:
    """LLM'in yazdığı bayrakları sabit listeye indirger: geçerli bayrağı içeren metin o bayrak
    sayılır, diğerleri atılır (açıklama gerekçede kalır). Önbellekteki eski cevaplar için de."""
    out: list[str] = []
    for flag in flags if isinstance(flags, list) else []:
        text = str(flag).strip().lower()
        match = next((f for f in CONTEXT_FLAGS if f in text or text.startswith(f)), None)
        if match and match not in out:
            out.append(match)
    return out


class Check(BaseModel):
    attribute: str = Field(
        description="konum, varlık, tip, sayı, hareket, süre, renk, yük, kimlik, bölge"
    )
    status: CheckStatus
    evidence: str = Field(description="Kanıt dosyasından kısa dayanak (sayılarla)")


class ReportVerdict(BaseModel):
    verdict: VerdictLabel
    harm: Harm = Field(
        description="Rapor inanılırsa riski düşürür mü (lowers_risk: 'olağan', 'dost', "
        "'uzaklaşıyor', 'ağır araç yok' gibi) yükseltir mi (raises_risk: ağır araç, kalabalık, "
        "tehdit), yoksa etkisiz mi"
    )
    dangerous_reassurance: bool = Field(
        description="Rapor riski düşüren bir şey söylüyor ama kanıt aksini gösteriyor (ör. üsse "
        "yaklaşan araca 'olağan' demek)"
    )
    checks: list[Check]
    context_flags: list[ContextFlag] = Field(
        default_factory=list,
        description="Bağlam bayrakları: 'olası örtü hikâyesi', 'telsiz kopukluğu + ağır araç "
        "hareketi', 'gece ihbarı bölgesinden kalkış'; yoksa boş",
    )
    reasoning: str = Field(description="Operatör için 1-2 cümle Türkçe gerekçe")
