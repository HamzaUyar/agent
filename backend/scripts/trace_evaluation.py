"""Bir görüntünün değerlendirmesini canlı izler: her kolun çıktısı ve LLM/VLM logları.

Değerlendirme adımları geldikçe kol kol basılır (Kol A tespit ve konum, Kol B1 çekim anı
konumları, eşleşme, Kol B2 hareket ve temel seviye, Kol C raporlar, risk, LLM kararı,
brief). LLM ve VLM çağrıları zaman damgalı log olarak araya düşer. `--image-out` ile
görüntünün üzerine kutular, track'ler ve seviyeler çizilir.

Sentetik paket Supabase'te yüklüyken:
    DATA_DIR=synthetic/package python -m scripts.trace_evaluation img_002724 \\
        --detections synthetic/detections.json --image-out iz.png
"""

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any, TextIO

from PIL import Image, ImageDraw, ImageFont

from app.agent.service import BRIEF_STEP, EvaluationService
from app.data_package import TRACK_STEP_MINUTES, find_image_file, format_hhmm, from_minutes
from app.data_package import to_minutes as minutes_of
from app.pipelines.geo import distance_m, in_footprint
from app.pipelines.motion import positions_at
from app.schemas.api import Brief
from app.schemas.domain import ImageMeta
from scripts.common import add_source_args, build_service, images_dir

LEVEL_TR = {"low": "DÜŞÜK", "medium": "ORTA", "high": "YÜKSEK", "critical": "KRİTİK"}
KIND_TR = {"matched": "eşleşmiş", "unregistered": "kayıt dışı", "missed": "kaçırılmış"}
TREND_TR = {
    "approaching": "yaklaşıyor",
    "receding": "uzaklaşıyor",
    "stationary": "yerinde",
    "passing": "geçiyor",
    "unknown": "belirsiz",
}
# Türkçe karakterli etiketler için yazı tipleri (macOS, Linux); hiçbiri yoksa ASCII'ye çevrilir.
FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)
_ASCII = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
LEVEL_RGB = {
    "low": (46, 160, 67),
    "medium": (219, 171, 9),
    "high": (230, 110, 20),
    "critical": (215, 38, 38),
}


class Tracer:
    def __init__(self, out: TextIO) -> None:
        self.out = out
        self.started = time.monotonic()

    def section(self, title: str) -> None:
        elapsed = time.monotonic() - self.started
        self.out.write(f"\n━━ {title} {'━' * max(3, 70 - len(title))} {elapsed:5.1f} sn\n")
        self.out.flush()

    def line(self, text: str = "") -> None:
        self.out.write(f"  {text}\n")
        self.out.flush()


def _km(meters: float) -> str:
    return f"{meters / 1000:.2f} km"


def trace_b1(t: Tracer, service: EvaluationService, image: ImageMeta) -> None:
    """Kol B1: çekim anında sahadaki bütün track'lerin konumu (eşleşmenin girdisi)."""
    now = image.capture_time
    since = from_minutes(minutes_of(now) - 2 * TRACK_STEP_MINUTES)
    positions = positions_at(service.repository.track_points_between(since, now), now)
    center = image.corners.center
    ranked = sorted(positions, key=lambda p: distance_m(p.location, center))
    inside = [p for p in positions if in_footprint(image, p.location)]
    t.section("KOL B1 · Çekim anı konumları")
    t.line(
        f"{format_hhmm(now)} itibarıyla sahada {len(positions)} track; "
        f"{len(inside)} tanesi karenin içinde"
    )
    t.line("Kare merkezine en yakınlar:")
    for p in ranked[: max(len(inside), 5)]:
        tag = "karede" if in_footprint(image, p.location) else "dışarıda"
        est = " · kestirildi" if p.estimated else ""
        t.line(
            f"  {p.track_id}  {p.location.lat:.5f}, {p.location.lon:.5f}  "
            f"merkeze {distance_m(p.location, center):6.0f} m  {tag}{est}"
        )


def _print_event(t: Tracer, name: str, data: dict[str, Any], state: dict[str, Any]) -> None:
    if name == "goruntu":
        t.section("1 · Görüntü meta verisi (image_meta.json)")
        t.line(f"{data['image_id']} · {data['zone']} · çekim anı {data['capture_time']}")
        tl = data["corners"][0]
        t.line(f"sol üst köşe {tl['lat']:.6f}, {tl['lon']:.6f}")
    elif name == "tespit":
        t.section("KOL A · Tespit")
        state["detections"] = data["detections"]
        for i, d in enumerate(data["detections"], 1):
            x, y, w, h = d["bbox"]
            weak = "  ZAYIF" if d["weak"] else ""
            t.line(
                f"#{i:<2} {d['label']:<5} güven {d['confidence']:.2f}  "
                f"kutu ({x:.0f}, {y:.0f}, {w:.0f}, {h:.0f}){weak}"
            )
        if data["ignored"]:
            t.line(f"{data['ignored']} kutu güven < 0,25 olduğu için yok sayıldı")
    elif name == "konum":
        t.section("KOL A · Konum (piksel → koordinat)")
        for i, (d, loc) in enumerate(zip(state["detections"], data["locations"], strict=True), 1):
            x, y, w, h = d["bbox"]
            t.line(
                f"#{i:<2} merkez ({x + w / 2:.0f}, {y + h / 2:.0f}) px → "
                f"{loc['lat']:.5f}, {loc['lon']:.5f}"
            )
        state["on_konum"]()
    elif name == "eslesme":
        t.section("BİRLEŞİM 1 · Eşleşme (Kol A konumu ↔ Kol B1 konumu, eşik 15 m)")
        index = {tuple(d["bbox"]): str(i) for i, d in enumerate(state["detections"], 1)}
        for m in data["matches"]:
            ref = index.get(tuple(m["bbox"]), "?")
            if m["track_id"] is None:
                t.line(f"#{ref:<2} → track yok  (kayıt dışı temas)")
                continue
            second = m["second"]
            extra = (
                f" · ikinci aday {second['track_id']} {second['distance_m']:.0f} m"
                if second
                else ""
            )
            amb = " · BELİRSİZ" if m["ambiguous"] else ""
            t.line(f"#{ref:<2} → {m['track_id']}  {m['distance_m']:.1f} m{extra}{amb}")
        for tid in data["visually_rejected"]:
            t.line(f"VLM 'araç değil' dedi → zayıf kutu düştü, {tid} kaçırılmış sayılacak")
        for tid in data["missed"]:
            t.line(f"{tid} karede ama tespit yok → kaçırılmış temas")
        if data["estimated_positions"]:
            t.line("Kestirilen konumlar: " + ", ".join(data["estimated_positions"]))
    elif name == "hareket":
        t.section("KOL B2 · Hareket analizi (son 120 dk)")
        for tid, mo in data["motions"].items():
            heading = (
                f"yön {mo['heading_deg']:.0f}°" if mo["heading_deg"] is not None else "yön yok"
            )
            then = mo["distance_to_base_30min_ago_m"]
            change = f" (30 dk önce {_km(then)})" if then is not None else ""
            t.line(
                f"{tid}: {TREND_TR[mo['trend']]}, üsse {_km(mo['distance_to_base_m'])}{change}, "
                f"son 10 dk {mo['recent_speed_mps']:.1f} m/s, {heading}"
            )
            for st in mo["stops"]:
                t.line(
                    f"     duraklama {st['start']}–{st['end']} ({st['minutes']} dk), "
                    f"üsse {_km(st['distance_to_base_m'])}"
                )
        t.section("BİRLEŞİM 2 · Temel seviye (tip, mesafe: Kol A · eğilim, duraklama: Kol B)")
        for c in data["contacts"]:
            who = c["track_id"] or "kayıt dışı"
            trend = TREND_TR[c["trend"]] if c["trend"] else "hareket kaydı yok"
            t.line(
                f"{who:<10} {KIND_TR[c['kind']]:<10} tip {c['label'] or '?':<5} "
                f"{_km(c['distance_to_base_m'])}  {trend:<11} → {LEVEL_TR[c['base_level']]:<7} "
                f"({'; '.join(c['reasons'])}) · {c['certainty']}"
            )
    elif name == "raporlar":
        t.section("KOL C · Raporlar (iddia, aracın rapor saatindeki konumuyla)")
        if not data["findings"]:
            t.line("İlgili rapor yok")
        for f in data["findings"]:
            source = "resmi" if f["source"] == "official" else "üçüncü taraf"
            t.line(f'{f["report_time"]} {source}: "{f["text"][:80]}"')
            t.line(
                f"     tür {f['claim_type']} · track {f['track_id'] or '-'} · karar {f['verdict']} "
                f"· etki {f['effect']} · {f['certainty']}"
            )
            t.line(f"     gerekçe: {f['reasoning']}")
        for v in data.get("visual_checks", []):
            t.line(f"VLM kutu {v['bbox']}: {v}")
    elif name == "risk":
        t.section("RİSK · Rapor etkileri uygulandıktan sonra")
        for c in data["contacts"]:
            change = (
                f"{LEVEL_TR[c['base_level']]} → {LEVEL_TR[c['final_level']]}"
                if c["base_level"] != c["final_level"]
                else LEVEL_TR[c["final_level"]]
            )
            t.line(f"{c['track_id'] or 'kayıt dışı':<10} {change}")
        t.line(f"Görüntü seviyesi (en yüksek temas): {LEVEL_TR[data['level']]}")
    elif name == "karar":
        t.section("KARAR · LLM (±1 kademe, kod doğrular)")
        if data["model"] is None:
            t.line(f"Otomatik özet: {data['fallback_reason']}")
        else:
            t.line(f"Model: {data['model']}")
        changed = [
            c for c in data["contacts"] if c["adjustment_reason"] or c["adjustment_rejected"]
        ]
        if not changed and data["model"]:
            t.line("LLM seviyelere dokunmadı")
        for c in changed:
            if c["adjustment_reason"]:
                t.line(
                    f"KABUL {c['track_id']}: → {LEVEL_TR[c['final_level']]} · "
                    f"{c['adjustment_reason']}"
                )
            if c["adjustment_rejected"]:
                t.line(f"RED   {c['track_id']}: {c['adjustment_rejected']}")


def draw(image: ImageMeta, brief: Brief, source: Path, out: Path) -> None:
    """Kutular son seviyenin rengiyle; kaçırılmış temaslar track konumunda halka olarak."""
    with Image.open(source) as img:
        canvas = img.convert("RGB")
    pen = ImageDraw.Draw(canvas)
    font_size = max(14, canvas.width // 70)
    font_path = next((f for f in FONT_CANDIDATES if Path(f).is_file()), None)
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont = (
        ImageFont.truetype(font_path, font_size)
        if font_path
        else ImageFont.load_default(size=font_size)
    )
    c = image.corners

    def to_px(lat: float, lon: float) -> tuple[float, float]:
        x = (lon - c.top_left.lon) / (c.top_right.lon - c.top_left.lon) * image.width_px
        y = (c.top_left.lat - lat) / (c.top_left.lat - c.bottom_left.lat) * image.height_px
        return x, y

    width = max(2, canvas.width // 400)
    for contact in brief.contacts:
        color = LEVEL_RGB[contact.final_level]
        label = f"{contact.track_id or 'kayıt dışı'} {LEVEL_TR[contact.final_level]}"
        if contact.bbox:
            x, y, w, h = contact.bbox
            pen.rectangle((x, y, x + w, y + h), outline=color, width=width)
            anchor = (x, max(0, y - font_size - 4))
        else:
            px, py = to_px(contact.location.lat, contact.location.lon)
            r = max(12, canvas.width // 60)
            pen.ellipse((px - r, py - r, px + r, py + r), outline=color, width=width)
            anchor = (px + r + 2, py - r)
            label += " (kaçırılmış)"
        if font_path is None:
            label = label.translate(_ASCII)
        # Etiket görüntünün dışına taşmasın.
        text_w = pen.textlength(label, font=font)
        ax = min(max(0.0, anchor[0]), canvas.width - text_w - 4)
        ay = min(max(0.0, anchor[1]), canvas.height - font_size - 4)
        pen.text((ax, ay), label, fill=color, font=font, stroke_width=2, stroke_fill=(0, 0, 0))
    canvas.save(out)


def trace(
    service: EvaluationService,
    image_id: str,
    out: TextIO = sys.stdout,
    *,
    images: Path | None = None,
    image_out: Path | None = None,
) -> Brief:
    t = Tracer(out)
    image = service.require_image(image_id)
    state: dict[str, Any] = {"on_konum": lambda: trace_b1(t, service, image)}
    brief: Brief | None = None
    for event in service.evaluate(image_id):
        if event.name == BRIEF_STEP:
            brief = Brief.model_validate(event.data)
            break
        _print_event(t, event.name, event.data, state)
    if brief is None:
        raise RuntimeError("Değerlendirme brief üretmeden bitti")
    t.section("BRIEF")
    for text_line in brief.text.splitlines():
        t.line(text_line)
    if image_out is not None and images is not None:
        source = find_image_file(images, image_id)
        if source is None:
            t.line(f"(görüntü dosyası yok, çizim atlandı: {images})")
        else:
            draw(image, brief, source, image_out)
            t.line(f"Çizim: {image_out}")
    return brief


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("image_id")
    add_source_args(parser)
    parser.add_argument("--image-out", type=Path, help="Kutuları ve seviyeleri çizip kaydet")
    parser.add_argument("--verbose", action="store_true", help="HTTP isteklerini de logla")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="  │ %(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    for noisy in ("httpx", "httpcore", "openai", "anthropic"):
        logging.getLogger(noisy).setLevel(logging.INFO if args.verbose else logging.WARNING)

    service = build_service(args)
    trace(service, args.image_id, images=images_dir(args), image_out=args.image_out)


if __name__ == "__main__":
    main()
