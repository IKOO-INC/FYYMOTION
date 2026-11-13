"""
Text FX — generator animasi teks per-huruf/per-kata (Alight Motion .xml)
===========================================================================
Tool terpisah dari Teks Creator (/teks-creator), beralamat di /tools/text-fx.
Alur UI terinspirasi dari "Text FX" milik Flamo Creative
(https://universe.flamocreative.com/tools/text-fx/) — teks dipecah jadi unit
per-huruf atau per-kata, tiap unit dapat timing masuk sendiri (stagger +
jeda/posisi acak), lalu diberi warna dari palet.

PENTING — SUMBER SKEMA XML:
Setiap preset animasi di bawah ini dibangun dari 9 file .xml ASLI hasil
export Alight Motion yang diberikan langsung oleh pengguna lewat Google
Drive (folder "teks 2d"), yaitu:

    fyy-motion#blur-up.xml      -> preset "blur_up"
    fyy-motion#bounce-move.xml  -> preset "bounce_move"
    fyy-motion#random-in.xml    -> preset "random_in"
    fyy-motion#squish-up.xml    -> preset "squish_up"
    fyy-motion#stretch-half.xml -> preset "stretch_half"
    fyy-motion#up.xml           -> preset "up"
    fyymo#blur.xml              -> preset "blur"
    fyymo#elastic.xml           -> preset "elastic"
    fyymo#squish-rot.xml        -> preset "squish_rot"

Dari file-file itu terbukti (dan dipakai apa adanya) tag/atribut berikut:
``<text>``, ``<transform>``, ``<location>``, ``<scale>``, ``<rotation>``,
``<opacity>``, ``<pivot>``, ``<fillColor>``, efek
``com.alightcreative.effects.gaussianblur``, serta DUA jenis kurva easing:
``e="cubicBezier x1 y1 x2 y2"`` dan ``e="local elastic a b c d"`` (yang
kedua ini sebelumnya belum pernah terbukti di 40 preset Teks Creator —
sekarang terbukti valid dari file-file di atas, sehingga preset "Elastic",
"Squish Up/Rot", dan "Up" di bawah memakai kurva elastic ASLI, bukan lagi
bezier substitusi).

Preset "pop" memakai param dari engine 'pop' (oc01_keep_it di
alight_presets.py) yang sudah divalidasi sebelumnya. Preset "random_in_out"
adalah kombinasi "random_in" + gerak keluar yang dikomposisi ulang dari
kurva cubicBezier yang sama (dibalik arah), bukan tag baru.

Nilai offset piksel (jarak slide, besar jitter) DIHITUNG ULANG relatif
terhadap tata letak unit kita sendiri (mengikuti cara alight_presets.py
menghitung posisi per huruf) — bukan menyalin bulat-bulat angka piksel dari
file sumber (yang spesifik untuk kata "Fyymotion"). Yang dipertahankan
PERSIS dari sumber adalah: kurva easing (angka cubicBezier/elastic), kanal
transform mana yang dipakai per preset, derajat rotasi awal, dan proporsi
waktu antar-keyframe.
"""

from __future__ import annotations

import random
import time
import xml.etree.ElementTree as ET

from alight_presets import (
    ALLOWED_WEIGHTS,
    CANVAS_PRESETS,
    FONTS,
    ValidationError,
    _font_attr,
    _kf,
    _validate_hex_color,
    esc_attr,
    esc_text,
)

# --------------------------------------------------------------------------- #
# Mode timing target: per huruf atau per kata.
# --------------------------------------------------------------------------- #
TEXT_FX_MODES = {
    "character": "Per Character",
    "word": "Per Word",
}

# --------------------------------------------------------------------------- #
# Mapping warna palet ke unit (huruf/kata) ketika jumlah warna < jumlah unit.
# --------------------------------------------------------------------------- #
TEXT_FX_MAPPINGS = {
    "single": "Satu Warna",
    "cycle": "Ulang Berurutan",
    "mirror": "Bolak-balik",
}


def _cubic(x1: float, y1: float, x2: float, y2: float) -> str:
    return f"cubicBezier {x1:.7f} {y1:.7f} {x2:.7f} {y2:.7f}"


def _elastic(a: float, b: float, c: float, d: float) -> str:
    # Sintaks "local elastic a b c d" terbukti ASLI pada file sumber
    # fyy-motion#up.xml / #squish-up.xml / fyymo#elastic.xml / #squish-rot.xml
    # / #bounce-move.xml — dipakai apa adanya, bukan tag baru.
    return f"local elastic {a:.7f} {b:.7f} {c:.7f} {d:.7f}"


# --------------------------------------------------------------------------- #
# Katalog preset animasi. Tiap style punya engine_id yang dipakai
# build_text_fx_xml() untuk memilih rangkaian channel transform yang tepat
# (lihat docstring modul untuk sumber file per preset).
# --------------------------------------------------------------------------- #
TEXT_FX_STYLES = {
    "pop": {
        "name": "Pop",
        "description": "Setiap unit membesar dari nol ke ukuran penuh. Sumber: engine 'pop' (preset oc01_keep_it, alight_presets.py).",
        "icon": "fa-solid fa-circle-up",
        "engine": "pop",
    },
    "blur": {
        "name": "Blur",
        "description": "Muncul di tempat sambil buram (gaussian blur) hilang dan fade in. Sumber asli: fyymo#blur.xml.",
        "icon": "fa-solid fa-eye",
        "engine": "blur",
    },
    "blur_up": {
        "name": "Blur Up",
        "description": "Meluncur naik sambil buram hilang dan fade in. Sumber asli: fyy-motion#blur-up.xml.",
        "icon": "fa-solid fa-wind",
        "engine": "blur_up",
    },
    "bounce_move": {
        "name": "Bounce Move",
        "description": "Meluncur horizontal sambil memantul (squash Y elastis). Sumber asli: fyy-motion#bounce-move.xml.",
        "icon": "fa-solid fa-arrows-left-right",
        "engine": "bounce_move",
    },
    "random_in": {
        "name": "Random In",
        "description": "Tiap unit terbang masuk dari posisi acak (seed-able) lalu mendarat presisi. Sumber asli: fyy-motion#random-in.xml.",
        "icon": "fa-solid fa-shuffle",
        "engine": "random_in",
        "supports_random": True,
    },
    "random_in_out": {
        "name": "Random In & Out",
        "description": "Sama seperti 'Random In', tapi tiap unit juga terbang keluar lagi sebelum layer berakhir (komposisi ulang dari kurva yang sama).",
        "icon": "fa-solid fa-shuffle",
        "engine": "random_in_out",
        "supports_random": True,
    },
    "squish_up": {
        "name": "Squish Up",
        "description": "Meluncur naik + membesar + berputar lalu fade in, dengan kurva pegas (elastic) asli. Sumber asli: fyy-motion#squish-up.xml.",
        "icon": "fa-solid fa-arrow-up",
        "engine": "squish_up",
    },
    "up": {
        "name": "Up",
        "description": "Versi lebih ringkas dari Squish Up (jarak lebih pendek, tanpa fade terpisah). Sumber asli: fyy-motion#up.xml.",
        "icon": "fa-solid fa-chevron-up",
        "engine": "up",
    },
    "elastic": {
        "name": "Elastic",
        "description": "Meluncur dari samping + membesar + berputar dengan kurva pegas (elastic) asli. Sumber asli: fyymo#elastic.xml.",
        "icon": "fa-solid fa-bolt-lightning",
        "engine": "elastic",
    },
    "squish_rot": {
        "name": "Squish Rot",
        "description": "Meluncur naik + membesar + berputar lebih jauh, lalu fade in, kurva pegas (elastic) asli. Sumber asli: fyymo#squish-rot.xml.",
        "icon": "fa-solid fa-arrows-rotate",
        "engine": "squish_rot",
    },
    "stretch_half": {
        "name": "Stretch Half",
        "description": "Meluncur masuk lalu memantul/stretch dua kali dan menghilang sendiri di akhir — animasi satu paket lengkap. Sumber asli: fyy-motion#stretch-half.xml.",
        "icon": "fa-solid fa-arrows-up-down",
        "engine": "stretch_half",
    },
}

ALLOWED_ALIGN_FX = {"left", "center", "right"}

CANVAS_IDS = CANVAS_PRESETS  # reuse katalog kanvas yang sama dengan Teks Creator


def list_text_fx_styles() -> list:
    """Daftar preset animasi untuk ditampilkan sebagai kartu/grid di UI."""
    out = []
    for style_id, style in TEXT_FX_STYLES.items():
        out.append({
            "id": style_id,
            "name": style["name"],
            "description": style["description"],
            "icon": style["icon"],
            "supports_random": style.get("supports_random", False),
        })
    return out


def _wrap_width_for_unit(text_unit: str, font_size: int) -> int:
    return max(160, int(len(text_unit) * font_size * 0.78) + 60)


def _validate_colors(raw) -> list:
    if not raw:
        return ["111111"]
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        raise ValidationError("Palet warna harus berupa daftar warna.")
    colors = [_validate_hex_color(c) for c in raw[:6]]
    if not colors:
        raise ValidationError("Palet warna tidak boleh kosong.")
    return colors


def _pick_color(colors: list, idx: int, n: int, mapping: str) -> str:
    if len(colors) == 1 or mapping == "single":
        return colors[0]
    if mapping == "mirror" and len(colors) > 1:
        period = (len(colors) - 1) * 2
        pos = idx % period if period else 0
        if pos >= len(colors):
            pos = period - pos
        return colors[pos]
    # default: cycle
    return colors[idx % len(colors)]


def _validate_text_fx_payload(payload: dict) -> dict:
    text = str(payload.get("text") or "").strip()
    text = text.replace("\r", "").replace("\n", " ")
    text = " ".join(text.split())
    if not text:
        raise ValidationError("Teks tidak boleh kosong.")
    if len(text) > 60:
        raise ValidationError("Teks terlalu panjang (maksimal 60 karakter untuk Text FX).")

    mode = str(payload.get("mode") or "character").strip().lower()
    if mode not in TEXT_FX_MODES:
        raise ValidationError("Mode tidak dikenali. Pilih Per Character atau Per Word.")

    style_id = str(payload.get("style_id") or "").strip()
    if style_id not in TEXT_FX_STYLES:
        raise ValidationError("Preset animasi tidak dikenali. Pilih salah satu kartu preset.")
    style = TEXT_FX_STYLES[style_id]

    if mode == "character":
        units = [ch for ch in text if ch != " "]
        if len(units) > 28:
            raise ValidationError("Untuk mode Per Character, maksimal 28 huruf (spasi tidak dihitung).")
    else:
        units = [w for w in text.split(" ") if w]
        if len(units) > 10:
            raise ValidationError("Untuk mode Per Word, maksimal 10 kata.")
    if not units:
        raise ValidationError("Teks tidak menghasilkan unit animasi (huruf/kata) apa pun.")

    try:
        font_size = int(float(payload.get("font_size", 72)))
    except (TypeError, ValueError) as exc:
        raise ValidationError("Ukuran teks harus berupa angka.") from exc
    if not (10 <= font_size <= 260):
        raise ValidationError("Ukuran teks harus di antara 10 dan 260.")

    font_id = str(payload.get("font_id") or "inter").strip()
    if font_id not in FONTS:
        raise ValidationError("Font tidak dikenali.")

    try:
        weight = int(payload.get("font_weight", 700))
    except (TypeError, ValueError) as exc:
        raise ValidationError("Berat font (weight) harus angka.") from exc
    if weight not in ALLOWED_WEIGHTS:
        raise ValidationError("Berat font harus salah satu dari: " + ", ".join(map(str, sorted(ALLOWED_WEIGHTS))))

    colors = _validate_colors(payload.get("colors"))
    mapping = str(payload.get("color_mapping") or "cycle").strip().lower()
    if mapping not in TEXT_FX_MAPPINGS:
        raise ValidationError("Mapping warna tidak dikenali.")

    canvas_id = str(payload.get("canvas_id") or "portrait").strip()
    if canvas_id not in CANVAS_PRESETS:
        raise ValidationError("Ukuran kanvas tidak dikenali.")
    canvas = CANVAS_PRESETS[canvas_id]

    try:
        stagger_ms = int(float(payload.get("stagger_ms", 90)))
    except (TypeError, ValueError) as exc:
        raise ValidationError("Stagger harus berupa angka (ms).") from exc
    if not (0 <= stagger_ms <= 500):
        raise ValidationError("Stagger harus di antara 0 dan 500 ms.")

    try:
        random_pct = int(float(payload.get("random_pct", 60 if style.get("supports_random") else 0)))
    except (TypeError, ValueError) as exc:
        raise ValidationError("Random (%) harus berupa angka.") from exc
    if not (0 <= random_pct <= 100):
        raise ValidationError("Random (%) harus di antara 0 dan 100.")

    try:
        seed = int(payload.get("seed", 0) or 0)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Seed harus berupa angka bulat.") from exc

    try:
        layer_duration_ms = int(float(payload.get("layer_duration_ms", 1200)))
    except (TypeError, ValueError) as exc:
        raise ValidationError("Layer duration harus berupa angka (ms).") from exc
    if not (300 <= layer_duration_ms <= 8000):
        raise ValidationError("Layer duration harus di antara 300 ms dan 8000 ms.")

    extend_to_end = bool(payload.get("extend_to_end", True))

    return {
        "text": text,
        "mode": mode,
        "units": units,
        "style_id": style_id,
        "style": style,
        "font_size": font_size,
        "font_id": font_id,
        "font_family": FONTS[font_id]["family"],
        "weight": weight,
        "colors": colors,
        "color_mapping": mapping,
        "canvas_id": canvas_id,
        "canvas": canvas,
        "stagger_ms": stagger_ms,
        "random_pct": random_pct,
        "seed": seed,
        "layer_duration_ms": layer_duration_ms,
        "extend_to_end": extend_to_end,
    }


def _loc_kf_list(kfs) -> list:
    """kfs: list of (t, x, y, easing|None) -> baris <kf> untuk <location>."""
    return [_kf(t, f"{x:.6f},{y:.6f},0.000000", e) for (t, x, y, e) in kfs]


def _scale_kf_list(kfs) -> list:
    """kfs: list of (t, sx, sy, easing|None) -> baris <kf> untuk <scale>."""
    return [_kf(t, f"{sx:.6f},{sy:.6f}", e) for (t, sx, sy, e) in kfs]


def _scalar_kf_list(kfs) -> list:
    """kfs: list of (t, value, easing|None) -> baris <kf> untuk rotation/opacity/blur."""
    return [_kf(t, f"{v:.6f}", e) for (t, v, e) in kfs]


def _build_unit_xml(engine: str, lx: float, cy: float, rnd: random.Random,
                     random_pct: int, font_size: int, own_dur_s: float) -> tuple[list, list]:
    """Kembalikan (transform_lines, effect_lines) untuk satu unit, sesuai engine."""
    transform_lines = []
    effect_lines = []

    if engine == "pop":
        pop_s = max(0.22, min(0.9, own_dur_s * 0.5))
        transform_lines.append(f'      <location value="{lx:.6f},{cy:.6f},0.000000" />')
        transform_lines.append("      <scale>")
        transform_lines += _scale_kf_list([
            (0.0, 0.0, 0.0, None),
            (pop_s, 1.0, 1.0, _cubic(0.25, 0.25, 0.20753138, 1.0)),
        ])
        transform_lines.append("      </scale>")

    elif engine == "blur":
        transform_lines.append(f'      <location value="{lx:.6f},{cy:.6f},0.000000" />')
        transform_lines.append("      <opacity>")
        transform_lines += _scalar_kf_list([(0.0, 0.0, None), (0.086, 1.0, None)])
        transform_lines.append("      </opacity>")
        effect_lines = [
            '      <effect id="com.alightcreative.effects.gaussianblur" locallyApplied="true">',
            '        <property name="strength" type="float">',
            _kf(0.0, "0.150000"),
            _kf(0.067, "0.000000"),
            "        </property>",
            "      </effect>",
        ]

    elif engine == "blur_up":
        offset_y = 177.0
        transform_lines.append("      <location>")
        transform_lines += _loc_kf_list([
            (0.0, lx, cy + offset_y, None),
            (0.11475, lx, cy, _cubic(0.0, 0.0, 0.16407079, 1.0)),
        ])
        transform_lines.append("      </location>")
        transform_lines.append("      <opacity>")
        transform_lines += _scalar_kf_list([(0.0, 0.0, None), (0.03998, 1.0, None)])
        transform_lines.append("      </opacity>")
        effect_lines = [
            '      <effect id="com.alightcreative.effects.gaussianblur" locallyApplied="true">',
            '        <property name="strength" type="float">',
            _kf(0.0, "0.060000"),
            _kf(0.092204, "0.000000"),
            "        </property>",
            "      </effect>",
        ]

    elif engine == "bounce_move":
        offset_x = 140.0
        transform_lines.append("      <location>")
        transform_lines += _loc_kf_list([
            (0.0, lx + offset_x, cy, None),
            (0.16675, lx, cy, _cubic(0.0, 0.20526315, 0.0014749262, 1.0)),
        ])
        transform_lines.append("      </location>")
        transform_lines.append("      <scale>")
        transform_lines += _scale_kf_list([
            (0.0, 1.0, 0.0, None),
            (0.175412, 1.0, 1.0, _elastic(0.33554572, 1.0, 0.16192983, 0.60833335)),
        ])
        transform_lines.append("      </scale>")
        transform_lines.append("      <opacity>")
        transform_lines += _scalar_kf_list([(0.0, 0.0, None), (0.073, 1.0, None)])
        transform_lines.append("      </opacity>")

    elif engine in ("random_in", "random_in_out"):
        max_jitter = font_size * 2.2 * (random_pct / 100.0)
        jx = rnd.uniform(-1.0, 1.0) * max_jitter
        jy = rnd.uniform(-1.0, 1.0) * max_jitter
        transform_lines.append("      <location>")
        transform_lines += _loc_kf_list([
            (0.0, lx + jx, cy + jy, None),
            (0.060969, lx + jx * 0.03, cy + jy * 0.03, _cubic(0.42, 0.0, 0.15227138, 1.0)),
            (0.125, lx, cy, _cubic(0.67330384, 0.015789473, 0.32669616, 1.0)),
        ])
        if engine == "random_in_out" and own_dur_s > 0.25:
            jx2 = rnd.uniform(-1.0, 1.0) * max_jitter
            jy2 = rnd.uniform(-1.0, 1.0) * max_jitter
            out_small_s = max(0.125, own_dur_s - 0.0641)
            transform_lines += _loc_kf_list([
                (out_small_s, lx + jx2 * 0.03, cy + jy2 * 0.03, _cubic(0.67330384, 0.015789473, 0.32669616, 1.0)),
                (own_dur_s, lx + jx2, cy + jy2, _cubic(0.42, 0.0, 0.15227138, 1.0)),
            ])
        transform_lines.append("      </location>")
        transform_lines.append("      <opacity>")
        opacity_kfs = [(0.0, 0.0, None), (0.03186, 1.0, None)]
        if engine == "random_in_out" and own_dur_s > 0.25:
            opacity_kfs += [(max(0.125, own_dur_s - 0.0641), 1.0, None), (own_dur_s, 0.0, None)]
        transform_lines += _scalar_kf_list(opacity_kfs)
        transform_lines.append("      </opacity>")

    elif engine in ("squish_up", "up", "elastic", "squish_rot"):
        cfg = {
            "squish_up": dict(axis="y", offset=230.0, loc_e=_elastic(0.5, 1.0, 0.0, 0.4063158),
                               loc_t=0.1625, scale_e=_elastic(0.5, 1.0, 0.0, 1.0), scale_t=0.198401,
                               rot_start=-46.097561, rot_e=_elastic(0.5, 1.0, 0.0, 0.65368426), rot_t=0.2125,
                               opacity=True),
            "up": dict(axis="y", offset=100.0, loc_e=_elastic(0.5, 1.0, 0.0, 0.4063158),
                       loc_t=0.1625, scale_e=_elastic(0.5, 1.0, 0.0, 1.0), scale_t=0.198401,
                       rot_start=-46.097561, rot_e=_elastic(0.5, 1.0, 0.0, 0.65368426), rot_t=0.2125,
                       opacity=False),
            "elastic": dict(axis="x", offset=123.0, loc_e=_elastic(0.5, 1.0, 0.0, 0.30324566),
                            loc_t=0.1625, scale_e=_elastic(0.3960177, 1.0, 0.0, 0.44754386), scale_t=0.144178,
                            rot_start=28.536585, rot_e=_elastic(0.44321534, 1.0, 0.06710528, 0.7114035), rot_t=0.16675,
                            opacity=False),
            "squish_rot": dict(axis="y", offset=218.0, loc_e=_elastic(0.5, 1.0, 0.0, 0.4063158),
                                loc_t=0.1625, scale_e=_elastic(0.5, 1.0, 0.0, 1.0), scale_t=0.198401,
                                rot_start=51.585365, rot_e=_elastic(0.5, 1.0, 0.0, 0.65368426), rot_t=0.2125,
                                opacity=True),
        }[engine]
        if cfg["axis"] == "y":
            start_x, start_y = lx, cy + cfg["offset"]
        else:
            start_x, start_y = lx + cfg["offset"], cy
        transform_lines.append("      <location>")
        transform_lines += _loc_kf_list([
            (0.0, start_x, start_y, None),
            (cfg["loc_t"], lx, cy, cfg["loc_e"]),
        ])
        transform_lines.append("      </location>")
        transform_lines.append("      <scale>")
        transform_lines += _scale_kf_list([
            (0.0, 0.0, 0.0, None),
            (cfg["scale_t"], 1.0, 1.0, cfg["scale_e"]),
        ])
        transform_lines.append("      </scale>")
        transform_lines.append("      <rotation>")
        transform_lines += _scalar_kf_list([
            (0.0, cfg["rot_start"], None),
            (cfg["rot_t"], 0.0, cfg["rot_e"]),
        ])
        transform_lines.append("      </rotation>")
        if cfg["opacity"]:
            transform_lines.append("      <opacity>")
            transform_lines += _scalar_kf_list([(0.046, 0.0, None), (0.0835, 1.0, None)])
            transform_lines.append("      </opacity>")

    elif engine == "stretch_half":
        offset_x = 217.0
        transform_lines.append("      <location>")
        transform_lines += _loc_kf_list([
            (0.0, lx + offset_x, cy, None),
            (0.11475, lx, cy, _cubic(0.0, 0.0, 0.16407079, 1.0)),
        ])
        transform_lines.append("      </location>")
        transform_lines.append("      <scale>")
        transform_lines += _scale_kf_list([
            (0.0, 1.0, 0.0, None),
            (0.04175, 1.0, 2.098188, _cubic(0.33997053, 0.8105263, 0.32227138, 1.0)),
            (0.175412, 1.0, 1.0, _cubic(0.8860767, 0.0, 0.22306783, 1.0)),
            (0.36475, 1.0, 1.0, None),
            (0.383558, 1.0, 0.892857, _cubic(0.42, 0.0, 0.58, 1.0)),
            (0.446027, 1.0, 1.882440, _cubic(0.43952802, 0.0, 0.0, 1.0)),
            (0.489750, 1.0, 0.000016, _cubic(1.0, 0.0, 0.75, 0.75)),
        ])
        transform_lines.append("      </scale>")
        transform_lines.append("      <opacity>")
        transform_lines += _scalar_kf_list([(0.0, 0.0, None), (0.0105, 1.0, None)])
        transform_lines.append("      </opacity>")

    else:  # pragma: no cover - safety net
        transform_lines.append(f'      <location value="{lx:.6f},{cy:.6f},0.000000" />')

    return transform_lines, effect_lines


def build_text_fx_xml(payload: dict) -> tuple[str, str]:
    """Validasi payload, bangun XML scene Text FX (banyak <text> layer), kembalikan (xml_text, filename)."""
    data = _validate_text_fx_payload(payload)
    w, h = data["canvas"]["width"], data["canvas"]["height"]
    cx, cy = w / 2.0, h / 2.0
    style = data["style"]
    engine = style["engine"]
    font_attr = _font_attr(data["font_family"], data["weight"])
    units = data["units"]
    n = len(units)
    font_size = data["font_size"]

    char_w = max(font_size * 0.72, 24.0)
    gap_w = char_w * (1.0 if data["mode"] == "character" else 0.65)

    if data["mode"] == "character":
        unit_widths = [char_w for _ in units]
    else:
        unit_widths = [max(len(u) * char_w, char_w) for u in units]

    total_w = sum(unit_widths) + gap_w * max(0, n - 1)
    start_x = cx - total_w / 2.0

    rnd = random.Random(data["seed"])

    layers = []
    x_cursor = start_x
    max_end_ms = 0
    unit_starts = []
    for idx, unit in enumerate(units):
        start_ms = idx * data["stagger_ms"]
        unit_starts.append(start_ms)
        own_end_ms = start_ms + data["layer_duration_ms"]
        max_end_ms = max(max_end_ms, own_end_ms)

    for idx, unit in enumerate(units):
        start_ms = unit_starts[idx]
        end_ms = max_end_ms if data["extend_to_end"] else start_ms + data["layer_duration_ms"]
        own_dur_s = max(0.05, (end_ms - start_ms) / 1000.0)
        lx = x_cursor + unit_widths[idx] / 2.0
        x_cursor += unit_widths[idx] + gap_w

        color_hex = _pick_color(data["colors"], idx, n, data["color_mapping"])

        transform_lines, effect_lines = _build_unit_xml(
            engine, lx, cy, rnd, data["random_pct"], font_size, own_dur_s
        )

        wrap_w = _wrap_width_for_unit(unit, font_size)
        layer_lines = [
            f'  <text id="{101 + idx}" label="FYY Text FX unit {idx + 1}" '
            f'startTime="{start_ms}" endTime="{end_ms}" fillType="color" mediaFillMode="fill" '
            f'size="{font_size:.6f}" font="{esc_attr(font_attr)}" wrapWidth="{wrap_w}" align="center">',
            "    <transform>",
            "\n".join(transform_lines),
            "    </transform>",
            f'    <fillColor value="#ff{color_hex}" />',
        ]
        if effect_lines:
            layer_lines.append("\n".join(effect_lines))
        layer_lines.append(f"    <content>{esc_text(unit)}</content>")
        layer_lines.append("  </text>")
        layers.append("\n".join(layer_lines))

    body_xml = "\n".join(layers)
    total_ms = max_end_ms
    now_ms = int(time.time() * 1000)
    title = f"Text FX {style['name']} - {data['text'][:30]}"

    xml_text = (
        "<?xml version='1.0' encoding='UTF-8' ?><!--\n"
        "Dibuat oleh FYY MOTION Text FX (bukan diekspor dari aplikasi Alight Motion)\n"
        f"Style: {style['name']} | Mode: {TEXT_FX_MODES[data['mode']]}\n"
        "-->\r\n"
        f'<scene title="{esc_attr(title)}" width="{w}" height="{h}" exportWidth="{w}" '
        f'exportHeight="{h}" precompose="dynamicResolution" bgcolor="#00000000" '
        f'totalTime="{total_ms}" fps="30" modifiedTime="{now_ms}" '
        'amver="1002592" ffver="106" am="com.alightcreative.motion/5.0.275" '
        'amplatform="android" retime="freeze" retimeAdaptFPS="false">\r\n'
        f"{body_xml}\r\n"
        "</scene>"
    )

    try:
        ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValidationError(f"Gagal membuat XML yang valid: {exc}") from exc

    safe_style = data["style_id"].replace("_", "-")
    filename = f"fyymotion-textfx-{safe_style}-{now_ms}.xml"
    return xml_text, filename
