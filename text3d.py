"""
3D Text — generator animasi teks 3D (extrude/flip/long-shadow) untuk Alight Motion (.xml)
===========================================================================
Tool terpisah dari Teks Creator & Text FX, beralamat di /tools/3d-text.
Alur & param form terinspirasi dari "3D Text Animate" milik Flamo Creative
(https://universe.flamocreative.com/tools/3d-text/).

PENTING — SUMBER KEBENARAN SKEMA XML:
Ketujuh preset di bawah ini dibangun HANYA dari tag/atribut/efek yang
benar-benar terbukti ada di 7 file .xml ASLI hasil export Alight Motion
yang diberikan pengguna lewat Google Drive (folder "teks 3d"):

    fyymotion-academy#flip.xml        -> preset "flip"        (Flip 3D)
    fyymotion-academy#right.xml       -> preset "right"       (Right)
    fyymotion-academy#popup.xml       -> preset "popup"       (Popup Rotate Extrude)
    fyymotion-academy#longshadow.xml  -> preset "longshadow"  (Long Shadow)
    fyymotion-academy#offset.xml      -> preset "offset_blank"    (Offset Kosongan)
    fyymotion-academy#orange.xml      -> preset "offset_orange"   (Offset Orange Style)
    fyymotion-academy#greenfire.xml   -> preset "offset_greenfire"(Offset Green Fire)

Dari file-file itu terbukti dipakai (dan dipakai apa adanya) efek:
``com.alightcreative.effects.flip3``, ``com.alightcreative.effects.extrude``,
``com.alightcreative.effects.longshadow2``, ``com.alightcreative.effects.offset``,
``com.alightcreative.effects.smoothedges``, ``com.alightcreative.effects.gaussianblur``,
``com.alightcreative.gradientoverlay2``, ``com.alightcreative.contourgrad``,
``com.alightcreative.solidcolor``, ``com.alightcreative.effects.lift``,
``com.alightcreative.effects.findedges``, ``com.alightcreative.replacecolor``,
``com.alightcreative.effects.chromakey``, ``com.alightcreative.effects.halftonedots``,
``com.alightcreative.internal.smoothbevel``, ``com.alightcreative.effects.wavewarp2``,
``com.alightcreative.effects.fractalwarp4``, ``com.alightcreative.effects.wipe2``,
``com.alightcreative.effects.stretchsegment``, ``<border>``, ``<path-stroke>``,
``<nullobj>``, ``<shape s=".rect">``, serta dua jenis kurva easing:
``e="cubicBezier x1 y1 x2 y2"`` dan ``e="local elastic a b c d"`` — semuanya
dipakai apa adanya dengan nilai numerik yang sama persis dengan sample asli.

PENYEDERHANAAN STRUKTURAL (ditandai eksplisit, mengikuti preseden yang sama
dipakai untuk 10 preset kategori "Apple" di alight_presets.py): sample asli
"flip" & "longshadow" membungkus layer teks dalam beberapa level
``<embedScene>``/``<nullobj>`` bersarang untuk kebutuhan tata-letak proyek asli
penggunanya. Untuk generator ini, pembungkus bersarang itu DISEDERHANAKAN
jadi satu level ``<nullobj>`` + (untuk "flip"/"longshadow") satu
``<shape s=".rect">`` latar sebagai pengganti bingkai — supaya layout bisa
dihitung ulang untuk teks apa pun (panjang/isi berbeda dari sample), TANPA
mengubah satupun tag efek, properti, atau nilai kurva yang terbukti asli.
Posisi X/Y tiap huruf juga DIHITUNG ULANG (bukan dipakai mentah dari sample,
karena sample dibuat untuk kata "Fyymotion Academy" secara spesifik) memakai
rumus spacing yang sama dengan Text FX (alight_presets.py / text_fx.py).

Kurva (Layer Graph Controller): hanya preset "right" & "popup" yang kurva
pergerakan utamanya satu cubicBezier tunggal (terbukti dari sample) sehingga
boleh diedit penggunanya; preset lain memakai kombinasi cubicBezier + local
elastic multi-tahap (persis sample) sehingga kurvanya dikunci, sama seperti
aturan di text_fx.py.
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET

from alight_presets import (
    ALLOWED_WEIGHTS,
    CANVAS_PRESETS,
    CURVES,
    FONTS,
    ValidationError,
    _font_attr,
    _kf,
    _validate_hex_color,
    am_xml_header,
    esc_attr,
    esc_text,
)

TEXT3D_MODES = {
    "character": "Per Character",
    "word": "Per Word",
}


def _cubic(x1: float, y1: float, x2: float, y2: float) -> str:
    return f"cubicBezier {x1:.7f} {y1:.7f} {x2:.7f} {y2:.7f}"


def _elastic(a: float, b: float, c: float, d: float) -> str:
    return f"local elastic {a:.7f} {b:.7f} {c:.7f} {d:.7f}"


def _loc_kf(kfs) -> list:
    return [_kf(t, f"{x:.6f},{y:.6f},0.000000", e) for (t, x, y, e) in kfs]


def _scale_kf(kfs) -> list:
    return [_kf(t, f"{sx:.6f},{sy:.6f}", e) for (t, sx, sy, e) in kfs]


def _scalar_kf(kfs) -> list:
    return [_kf(t, f"{v:.6f}", e) for (t, v, e) in kfs]


def _vec2_kf(kfs) -> list:
    return [_kf(t, f"{x:.6f},{y:.6f}", e) for (t, x, y, e) in kfs]


def _vec3_kf(kfs) -> list:
    return [_kf(t, f"{x:.6f},{y:.6f},{z:.6f}", e) for (t, x, y, z, e) in kfs]


# --------------------------------------------------------------------------- #
# Katalog 7 preset — role warna & default persis sample, kurva hanya untuk
# "right"/"popup" (satu cubicBezier utama).
# --------------------------------------------------------------------------- #
TEXT3D_STYLES = {
    "flip": {
        "name": "Flip 3D",
        "description": "Tiap huruf membalik 360° (sumbu Y) dari arah luar lalu mendarat dengan kilatan warna & long-shadow ganda. Sumber: fyymotion-academy#flip.xml.",
        "icon": "fa-solid fa-cube",
        "engine": "flip",
        "supports_curve_edit": False,
        "default_curve": None,
        "color_roles": [
            {"key": "base", "label": "Text / Base", "default": "#FFFFFF"},
            {"key": "face", "label": "Face (kilatan)", "default": "#FEA800"},
            {"key": "extrude_a", "label": "Extrude A", "default": "#FF9300"},
            {"key": "extrude_b", "label": "Extrude B", "default": "#FF8C00"},
            {"key": "border", "label": "Border", "default": "#AC2D2A"},
        ],
        "default_canvas": "square",
    },
    "right": {
        "name": "Right",
        "description": "Huruf meluncur masuk dengan extrude 3D berputar (efek extrude + rotate) dan gradasi warna pada permukaannya. Sumber: fyymotion-academy#right.xml.",
        "icon": "fa-solid fa-angles-right",
        "engine": "right",
        "supports_curve_edit": True,
        "default_curve": {"x1": 0.0, "y1": 0.0, "x2": 0.13457225, "y2": 1.0},
        "color_roles": [
            {"key": "base", "label": "Text / Base", "default": "#FFFFFF"},
            {"key": "face", "label": "Face (gradasi)", "default": "#FFC3B2"},
            {"key": "border", "label": "Border", "default": "#DE5044"},
            {"key": "extrude", "label": "Extrude", "default": "#7E170E"},
        ],
        "default_canvas": "square",
    },
    "popup": {
        "name": "Popup Rotate Extrude",
        "description": "Huruf pop-up membesar dari nol sambil extrude-nya berputar lalu berhenti tegak. Sumber: fyymotion-academy#popup.xml.",
        "icon": "fa-solid fa-arrow-up-from-bracket",
        "engine": "popup",
        "supports_curve_edit": True,
        "default_curve": {"x1": 0.0, "y1": 0.0, "x2": 0.13457225, "y2": 1.0},
        "color_roles": [
            {"key": "base", "label": "Text / Base", "default": "#FFFFFF"},
            {"key": "face", "label": "Face (gradasi)", "default": "#FFC3B2"},
            {"key": "border", "label": "Border", "default": "#DE5044"},
            {"key": "extrude", "label": "Extrude", "default": "#7E170E"},
        ],
        "default_canvas": "square",
    },
    "longshadow": {
        "name": "Long Shadow",
        "description": "Huruf melompat masuk satu-satu dengan long-shadow yang memanjang &  mengecil saat mendarat, plus outline tipis. Sumber: fyymotion-academy#longshadow.xml.",
        "icon": "fa-solid fa-shoe-prints",
        "engine": "longshadow",
        "supports_curve_edit": False,
        "default_curve": None,
        "color_roles": [
            {"key": "base", "label": "Text / Base", "default": "#FFFFFF"},
            {"key": "shadow", "label": "Long Shadow", "default": "#013C95"},
            {"key": "border", "label": "Border bingkai", "default": "#007AFF"},
            {"key": "outline", "label": "Outline huruf", "default": "#80D2F7"},
        ],
        "default_canvas": "portrait",
    },
    "offset_blank": {
        "name": "Offset Kosongan",
        "description": "Huruf 'menggulung' naik-turun lewat efek Offset — tanpa latar dekoratif (kosongan). Sumber: fyymotion-academy#offset.xml.",
        "icon": "fa-solid fa-expand",
        "engine": "offset",
        "supports_curve_edit": False,
        "default_curve": None,
        "color_roles": [
            {"key": "base", "label": "Text / Base", "default": "#FFFFFF"},
        ],
        "default_canvas": "portrait",
        "background": None,
    },
    "offset_orange": {
        "name": "Offset Orange Style",
        "description": "Sama seperti Offset Kosongan, ditambah panel latar aksen oranye (shape + efek replace-color/halftone). Sumber: fyymotion-academy#orange.xml.",
        "icon": "fa-solid fa-palette",
        "engine": "offset",
        "supports_curve_edit": False,
        "default_curve": None,
        "color_roles": [
            {"key": "base", "label": "Text / Base", "default": "#FFFFFF"},
            {"key": "accent1", "label": "Aksen 1", "default": "#FF9500"},
            {"key": "accent2", "label": "Aksen 2", "default": "#D36300"},
        ],
        "default_canvas": "portrait",
        "background": "orange",
    },
    "offset_greenfire": {
        "name": "Offset Green Fire",
        "description": "Sama seperti Offset Kosongan, ditambah panel latar api hijau (wavewarp + fractalwarp + gradient). Sumber: fyymotion-academy#greenfire.xml.",
        "icon": "fa-solid fa-fire",
        "engine": "offset",
        "supports_curve_edit": False,
        "default_curve": None,
        "color_roles": [
            {"key": "base", "label": "Text / Base", "default": "#FFFFFF"},
            {"key": "accent1", "label": "Aksen 1", "default": "#CDFF5A"},
            {"key": "accent2", "label": "Aksen 2", "default": "#F8FF00"},
        ],
        "default_canvas": "portrait",
        "background": "greenfire",
    },
}


def list_text3d_styles() -> list:
    out = []
    for style_id, style in TEXT3D_STYLES.items():
        out.append({
            "id": style_id,
            "name": style["name"],
            "description": style["description"],
            "icon": style["icon"],
            "supports_curve_edit": style.get("supports_curve_edit", False),
            "default_curve": style.get("default_curve"),
            "color_roles": style["color_roles"],
            "default_canvas": style.get("default_canvas", "square"),
        })
    return out


# --------------------------------------------------------------------------- #
# Validasi payload
# --------------------------------------------------------------------------- #
def _validate_colors_roles(raw, style: dict) -> dict:
    roles = style["color_roles"]
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for role in roles:
        key = role["key"]
        value = raw.get(key, role["default"])
        out[key] = _validate_hex_color(value, f"warna {role['label']}")
    return out


def _validate_text3d_curve(payload: dict, style: dict) -> dict | None:
    if not style.get("supports_curve_edit"):
        return None
    default = style.get("default_curve") or {"x1": 0.0, "y1": 0.0, "x2": 0.13457225, "y2": 1.0}

    curve_id = str(payload.get("curve_id") or "").strip()
    if curve_id and curve_id in CURVES:
        c = CURVES[curve_id]
        return {"x1": c["x1"], "y1": c["y1"], "x2": c["x2"], "y2": c["y2"]}

    custom = payload.get("curve") or {}
    if not custom:
        return dict(default)
    try:
        x1 = float(custom.get("x1", default["x1"]))
        y1 = float(custom.get("y1", default["y1"]))
        x2 = float(custom.get("x2", default["x2"]))
        y2 = float(custom.get("y2", default["y2"]))
    except (TypeError, ValueError) as exc:
        raise ValidationError("Nilai kurva cubic-bezier tidak valid.") from exc
    if not (0.0 <= x1 <= 1.0) or not (0.0 <= x2 <= 1.0):
        raise ValidationError("Nilai X pada kurva cubic-bezier harus di antara 0 dan 1.")
    for label, v in (("Y1", y1), ("Y2", y2)):
        if not (-3.0 <= v <= 4.0):
            raise ValidationError(f"Nilai {label} pada kurva di luar batas wajar (-3 s.d. 4).")
    return {"x1": x1, "y1": y1, "x2": x2, "y2": y2}


def _validate_text3d_payload(payload: dict) -> dict:
    text = str(payload.get("text") or "").strip()
    text = text.replace("\r", "")
    lines = [" ".join(ln.split()) for ln in text.split("\n")]
    lines = [ln for ln in lines if ln]
    if not lines:
        raise ValidationError("Teks tidak boleh kosong.")
    if len(lines) > 3:
        raise ValidationError("Maksimal 3 baris teks untuk 3D Text.")
    joined = " ".join(lines)
    if len(joined) > 60:
        raise ValidationError("Teks terlalu panjang (maksimal 60 karakter total).")

    mode = str(payload.get("mode") or "character").strip().lower()
    if mode not in TEXT3D_MODES:
        raise ValidationError("Mode tidak dikenali. Pilih Per Character atau Per Word.")

    style_id = str(payload.get("style_id") or "").strip()
    if style_id not in TEXT3D_STYLES:
        raise ValidationError("Preset 3D tidak dikenali. Pilih salah satu kartu preset.")
    style = TEXT3D_STYLES[style_id]

    line_units = []
    total_units = 0
    for ln in lines:
        if mode == "character":
            units = [ch for ch in ln if ch != " "]
        else:
            units = [w for w in ln.split(" ") if w]
        if not units:
            continue
        line_units.append(units)
        total_units += len(units)
    if not line_units:
        raise ValidationError("Teks tidak menghasilkan unit animasi (huruf/kata) apa pun.")
    if total_units > 24:
        raise ValidationError("Maksimal 24 unit animasi (huruf/kata digabung semua baris) untuk 3D Text.")

    try:
        font_size = int(float(payload.get("font_size", 72)))
    except (TypeError, ValueError) as exc:
        raise ValidationError("Ukuran teks harus berupa angka.") from exc
    if not (20 <= font_size <= 220):
        raise ValidationError("Ukuran teks harus di antara 20 dan 220.")

    font_id = str(payload.get("font_id") or "inter").strip()
    if font_id not in FONTS:
        raise ValidationError("Font tidak dikenali.")

    try:
        weight = int(payload.get("font_weight", 700))
    except (TypeError, ValueError) as exc:
        raise ValidationError("Berat font (weight) harus angka.") from exc
    if weight not in ALLOWED_WEIGHTS:
        raise ValidationError("Berat font harus salah satu dari: " + ", ".join(map(str, sorted(ALLOWED_WEIGHTS))))

    canvas_id = str(payload.get("canvas_id") or style.get("default_canvas", "square")).strip()
    if canvas_id not in CANVAS_PRESETS:
        raise ValidationError("Ukuran kanvas tidak dikenali.")
    canvas = CANVAS_PRESETS[canvas_id]

    try:
        spacing = float(payload.get("spacing", font_size * 1.35))
    except (TypeError, ValueError) as exc:
        raise ValidationError("Spacing harus berupa angka.") from exc
    if not (10 <= spacing <= 600):
        raise ValidationError("Spacing harus di antara 10 dan 600 px.")

    try:
        line_gap = float(payload.get("line_gap", font_size * 2.2))
    except (TypeError, ValueError) as exc:
        raise ValidationError("Line gap harus berupa angka.") from exc
    if not (10 <= line_gap <= 800):
        raise ValidationError("Line gap harus di antara 10 dan 800 px.")

    try:
        x_pos = float(payload.get("x_position", 0))
    except (TypeError, ValueError) as exc:
        raise ValidationError("X Position harus berupa angka.") from exc
    try:
        y_pos = float(payload.get("y_position", 0))
    except (TypeError, ValueError) as exc:
        raise ValidationError("Y Position harus berupa angka.") from exc
    if not (-2000 <= x_pos <= 2000) or not (-2000 <= y_pos <= 2000):
        raise ValidationError("X/Y Position harus di antara -2000 dan 2000 px.")

    try:
        extrude_pct = float(payload.get("extrude_depth", 50))
    except (TypeError, ValueError) as exc:
        raise ValidationError("Extrude/Depth harus berupa angka.") from exc
    if not (0 <= extrude_pct <= 100):
        raise ValidationError("Extrude/Depth harus di antara 0 dan 100%.")

    try:
        stagger_ms = int(float(payload.get("stagger_ms", 50)))
    except (TypeError, ValueError) as exc:
        raise ValidationError("Stagger harus berupa angka (ms).") from exc
    if not (0 <= stagger_ms <= 400):
        raise ValidationError("Stagger harus di antara 0 dan 400 ms.")

    try:
        last_start_ms = int(float(payload.get("last_start_ms", 500)))
    except (TypeError, ValueError) as exc:
        raise ValidationError("Last Start harus berupa angka (ms).") from exc
    if not (0 <= last_start_ms <= 4000):
        raise ValidationError("Last Start harus di antara 0 dan 4000 ms.")

    try:
        end_hold_ms = int(float(payload.get("end_hold_ms", 1000)))
    except (TypeError, ValueError) as exc:
        raise ValidationError("End Hold harus berupa angka (ms).") from exc
    if not (0 <= end_hold_ms <= 6000):
        raise ValidationError("End Hold harus di antara 0 dan 6000 ms.")

    border_on = bool(payload.get("border", True))
    colors = _validate_colors_roles(payload.get("colors"), style)
    curve = _validate_text3d_curve(payload, style)

    return {
        "lines": lines,
        "line_units": line_units,
        "mode": mode,
        "style_id": style_id,
        "style": style,
        "curve": curve,
        "font_size": font_size,
        "font_id": font_id,
        "font_family": FONTS[font_id]["family"],
        "weight": weight,
        "canvas_id": canvas_id,
        "canvas": canvas,
        "spacing": spacing,
        "line_gap": line_gap,
        "x_position": x_pos,
        "y_position": y_pos,
        "extrude_depth": extrude_pct,
        "stagger_ms": stagger_ms,
        "last_start_ms": last_start_ms,
        "end_hold_ms": end_hold_ms,
        "border_on": border_on,
        "colors": colors,
    }


# --------------------------------------------------------------------------- #
# Tata-letak: pusatkan tiap baris, baris ditumpuk pakai line_gap. Rumus sama
# gaya dengan text_fx.py (char_w dari font_size), bukan koordinat mentah
# sample (yang spesifik untuk kata "Fyymotion Academy").
# --------------------------------------------------------------------------- #
def _layout_units(data: dict):
    """Kembalikan list of dict {unit, lx, ly, start_ms} terurut flat (semua baris)."""
    font_size = data["font_size"]
    spacing = data["spacing"]
    mode = data["mode"]
    n_lines = len(data["line_units"])
    cy0 = data["canvas"]["height"] / 2.0 + data["y_position"]
    cx0 = data["canvas"]["width"] / 2.0 + data["x_position"]

    flat = []
    global_idx = 0
    total_units = sum(len(u) for u in data["line_units"])
    for li, units in enumerate(data["line_units"]):
        ly = cy0 + (li - (n_lines - 1) / 2.0) * data["line_gap"]
        if mode == "character":
            widths = [spacing for _ in units]
        else:
            widths = [max(len(u) * spacing * 0.62, spacing) for u in units]
        total_w = sum(widths)
        cursor = cx0 - total_w / 2.0
        for unit, uw in zip(units, widths):
            lx = cursor + uw / 2.0
            cursor += uw
            flat.append({"unit": unit, "lx": lx, "ly": ly, "idx": global_idx})
            global_idx += 1

    stagger_s = data["stagger_ms"] / 1000.0
    last_start_s = data["last_start_ms"] / 1000.0
    for item in flat:
        raw_start = item["idx"] * stagger_s
        item["start_s"] = min(raw_start, last_start_s) if total_units > 1 else 0.0
    return flat


# --------------------------------------------------------------------------- #
# Engine "flip" — flip3 + pop bounce + kilatan solidcolor + long-shadow ganda.
# Nilai kurva & pulsa efek PERSIS sample fyymotion-academy#flip.xml (hanya
# posisi huruf & offset waktu (stagger) yang dihitung ulang generik).
# --------------------------------------------------------------------------- #
def _build_flip_letter(lx: float, ly: float, start_s: float, font_size: int, colors: dict) -> tuple[list, list]:
    s = start_s
    apex_dy = -164.336761 * (font_size / 72.0)
    transform = ["      <location>"]
    transform += _loc_kf([
        (s + 0.0, lx, ly, None),
        (s + 0.132249, lx, ly + apex_dy, _cubic(0.25, 0.25, 0.15560472, 0.95789474)),
        (s + 0.455040, lx, ly, _elastic(0.5, 1.0, 0.0, 0.550614)),
    ])
    transform.append("      </location>")
    transform.append("      <scale>")
    transform += _scale_kf([
        (s + 0.077365, 1.0, 1.0, _cubic(0.0, 0.3026316, 0.0, 1.0)),
        (s + 0.0, 0.000003, 0.000003, None),
        (s + 0.137870, 1.0, 1.0, None),
        (s + 0.234624, 1.0, 0.789638, _cubic(0.5936578, 0.028947368, 1.0, 0.15789473)),
        (s + 0.521130, 1.0, 1.0, _elastic(0.45575222, 1.0, 0.16605264, 1.0)),
    ])
    transform.append("      </scale>")

    effects = []
    effects.append('    <effect id="com.alightcreative.effects.flip3" locallyApplied="true">')
    effects.append('      <property name="angle" type="float">')
    effects += _scalar_kf([(s + 0.0, 0.0, None), (s + 0.537654, -360.0, _elastic(0.5, 1.0, 0.0, 0.15482461))])
    effects.append("      </property>")
    effects.append('      <property name="axis" type="float" value="90.000000"/>')
    effects.append("    </effect>")
    effects.append('    <effect id="com.alightcreative.effects.smoothedges" locallyApplied="true"/>')
    effects.append('    <effect id="com.alightcreative.solidcolor" locallyApplied="true">')
    effects.append('      <property name="alpha" type="float">')
    effects += _scalar_kf([(s + 0.088277, 1.0, None), (s + 0.036351, 0.0, None), (s + 0.152011, 0.0, None)])
    effects.append("      </property>")
    effects.append(f'      <property name="color" type="color" value="#FF{colors["face"][1:]}"/>')
    effects.append("    </effect>")
    effects.append('    <effect id="com.alightcreative.effects.longshadow2" locallyApplied="true">')
    effects.append('      <property name="alpha" type="float" value="1.000000"/>')
    effects.append('      <property name="angle" type="float" value="90.000000"/>')
    effects.append(f'      <property name="color" type="color" value="#FF{colors["extrude_a"][1:]}"/>')
    effects.append('      <property name="size" type="float">')
    effects += _scalar_kf([
        (s + 0.071746, 0.045, None), (s + 0.031062, 0.0, None), (s + 0.082655, 0.0, None),
        (s + 0.132249, 0.0, None), (s + 0.148780, 0.045, None), (s + 0.214904, 0.0, None),
    ])
    effects.append("      </property>")
    effects.append("    </effect>")
    effects.append('    <effect id="com.alightcreative.effects.longshadow2" locallyApplied="true">')
    effects.append('      <property name="alpha" type="float" value="1.000000"/>')
    effects.append('      <property name="angle" type="float" value="270.000000"/>')
    effects.append(f'      <property name="color" type="color" value="#FF{colors["extrude_b"][1:]}"/>')
    effects.append('      <property name="size" type="float">')
    effects += _scalar_kf([(s + 0.069396, 0.0, None), (s + 0.082655, 0.045, None), (s + 0.126960, 0.0, None)])
    effects.append("      </property>")
    effects.append("    </effect>")
    return transform, effects


# --------------------------------------------------------------------------- #
# Engine "right"/"popup" — extrude 3D + gradasi + border kontur. Satu-satunya
# bagian kurva-editable: entrance utama (cubicBezier tunggal, lihat curve).
# --------------------------------------------------------------------------- #
def _build_rightpopup_letter(engine: str, lx: float, ly: float, start_s: float, font_size: int,
                              colors: dict, extrude_depth_pct: float, curve: dict) -> tuple[list, list]:
    s = start_s
    main_curve = _cubic(curve["x1"], curve["y1"], curve["x2"], curve["y2"])
    depth = 0.01 + (extrude_depth_pct / 100.0) * 0.09  # 0.01 - 0.10, proporsional ke sample (0.052 @ 50%)
    transform = ["      <location>"]
    if engine == "right":
        slide_from = lx - font_size * 3.2
        transform += _loc_kf([
            (s + 0.0, slide_from, ly, None),
            (s + 0.374529, lx, ly, main_curve),
        ])
    else:  # popup
        apex_dy = -164.336182 * (font_size / 72.0)
        transform += _loc_kf([
            (s + 0.0, lx, ly, None),
            (s + 0.177641, lx, ly + apex_dy, _cubic(0.25, 0.25, 0.15560472, 0.95789474)),
            (s + 0.611226, lx, ly, _elastic(0.5, 1.0, 0.0, 0.550614)),
        ])
    transform.append("      </location>")
    transform.append("      <scale>")
    if engine == "right":
        transform += _scale_kf([(s + 0.374529, 1.0, 1.0, _cubic(0.42, 0.0, 0.0, 1.0))])
    else:
        transform += _scale_kf([
            (s + 0.103919, 1.0, 1.0, _cubic(0.0, 0.3026316, 0.0, 1.0)),
            (s + 0.0, 0.000003, 0.000003, None),
            (s + 0.185192, 1.0, 1.0, None),
            (s + 0.315155, 1.0, 0.789638, _cubic(0.5936578, 0.028947368, 1.0, 0.15789473)),
            (s + 0.700000, 1.0, 1.0, _elastic(0.45575222, 1.0, 0.16605264, 1.0)),
        ])
    transform.append("      </scale>")
    if engine == "right":
        transform.append("      <opacity>")
        transform += _scalar_kf([(s + 0.079086, 1.0, None), (s + 0.026363, 0.0, None)])
        transform.append("      </opacity>")

    effects = []
    effects.append('    <effect id="com.alightcreative.effects.smoothedges" locallyApplied="true">')
    effects.append('      <property name="strength" type="float" value="0.080000"/>')
    effects.append("    </effect>")
    effects.append('    <effect id="com.alightcreative.gradientoverlay2" locallyApplied="true">')
    effects.append('      <property name="alpha" type="float" value="1.000000"/>')
    effects.append(f'      <property name="color1" type="color" value="#FF{colors["base"][1:]}"/>')
    effects.append(f'      <property name="color2" type="color" value="#FF{colors["face"][1:]}"/>')
    effects.append("    </effect>")
    effects.append('    <effect id="com.alightcreative.contourgrad" locallyApplied="true">')
    effects.append(f'      <property name="color1" type="color" value="#FF{colors["border"][1:]}"/>')
    effects.append(f'      <property name="color2" type="color" value="#FF{colors["border"][1:]}"/>')
    effects.append('      <property name="width" type="float" value="8.600000"/>')
    effects.append("    </effect>")
    effects.append('    <effect id="com.alightcreative.effects.smoothedges" locallyApplied="true">')
    effects.append('      <property name="maskToLayer" type="bool" value="true"/>')
    effects.append('      <property name="strength" type="float" value="0.080000"/>')
    effects.append("    </effect>")
    effects.append('    <effect id="com.alightcreative.effects.extrude" locallyApplied="true">')
    effects.append('      <property name="depth" type="float">')
    if engine == "right":
        effects += _scalar_kf([(s + 0.158174, depth * 5.2, None), (s + 0.383229, depth, None)])
    else:
        effects += _scalar_kf([(s + 0.132165, depth * 5.2, None), (s + 0.320214, depth, None)])
    effects.append("      </property>")
    effects.append('      <property name="fadeBlend" type="float" value="1.000000"/>')
    effects.append(f'      <property name="fadeColor" type="color" value="#FF{colors["extrude"][1:]}"/>')
    effects.append('      <property name="interiorBlend" type="float" value="1.000000"/>')
    effects.append(f'      <property name="interiorColor" type="color" value="#FF{colors["extrude"][1:]}"/>')
    effects.append('      <property name="rotate" type="vec3">')
    if engine == "right":
        effects += _vec3_kf([
            (s + 0.0, 0.0, 624.0, 0.0, None),
            (s + 0.400905, 0.0, -35.0, 0.0, _cubic(0.0, 0.0, 0.0, 1.0)),
            (s + 0.700000, 0.0, 0.0, 0.0, _elastic(0.5, 1.0, 0.0, 1.0)),
        ])
    else:
        effects += _vec3_kf([
            (s + 0.345390, 0.0, 0.0, 0.0, _cubic(0.42, 0.0, 0.0, 1.0)),
            (s + 0.0, 0.0, 240.0, 0.0, None),
        ])
    effects.append("      </property>")
    effects.append('      <property name="shadingType" type="int" value="0"/>')
    effects.append("    </effect>")
    if engine == "right":
        effects.append('    <effect id="com.alightcreative.effects.gaussianblur" locallyApplied="true">')
        effects.append('      <property name="strength" type="float">')
        effects += _scalar_kf([(s + 0.035325, 0.15, None), (s + 0.189903, 0.0, _cubic(0.42, 0.0, 0.1375221, 1.0))])
        effects.append("      </property>")
        effects.append("    </effect>")
    effects.append(
        f'    <path-stroke direction="centered" enabled="false" join="round" end-size="1.5">'
        f'<color value="#FF{colors["border"][1:]}"/><size value="5.000000"/></path-stroke>'
    )
    return transform, effects


# --------------------------------------------------------------------------- #
# Engine "longshadow" — hop bounce + long-shadow ganda per huruf + outline.
# --------------------------------------------------------------------------- #
def _build_longshadow_letter(lx: float, ly: float, start_s: float, font_size: int, colors: dict) -> tuple[list, list]:
    s = start_s
    sc = 1.198577
    rest_y = ly
    apex_y = ly - 57.0 * (font_size / 72.0)
    dip_y = ly + 8.39 * (font_size / 72.0)
    transform = ["      <location>"]
    transform += _loc_kf([
        (s + 0.0, lx, rest_y, None),
        (s + 0.188323, lx, apex_y, _cubic(0.42, 0.0, 0.10949851, 1.0)),
        (s + 0.414129, lx, apex_y, None),
        (s + 0.579420, lx - 3.2 * (font_size / 72.0), dip_y, _cubic(0.7057522, 0.0, 0.39159292, 1.0)),
        (s + 0.700000, lx, rest_y, _cubic(0.6202065, 0.013157895, 0.43879056, 1.0)),
    ])
    transform.append("      </location>")
    transform.append(f'      <scale value="{sc:.6f},{sc:.6f}"/>')

    effects = []
    effects.append('    <effect id="com.alightcreative.effects.longshadow2" locallyApplied="true">')
    effects.append('      <property name="alpha" type="float" value="1.000000"/>')
    effects.append('      <property name="angle" type="float" value="125.000000"/>')
    effects.append(f'      <property name="color" type="color" value="#FF{colors["shadow"][1:]}"/>')
    effects.append('      <property name="size" type="float">')
    effects += _scalar_kf([
        (s + 0.0, 0.0, None), (s + 0.188323, 0.055, _cubic(0.42, 0.0, 0.10949851, 1.0)),
        (s + 0.414129, 0.055, None), (s + 0.579420, 0.0, _cubic(0.7057522, 0.0, 0.39159292, 1.0)),
    ])
    effects.append("      </property>")
    effects.append("    </effect>")
    effects.append('    <effect id="com.alightcreative.effects.longshadow2" locallyApplied="true">')
    effects.append('      <property name="alpha" type="float" value="1.000000"/>')
    effects.append('      <property name="angle" type="float" value="309.500000"/>')
    effects.append(f'      <property name="color" type="color" value="#FF{colors["shadow"][1:]}"/>')
    effects.append('      <property name="size" type="float">')
    effects += _scalar_kf([
        (s + 0.579420, 0.009, _cubic(0.7057522, 0.0, 0.39159292, 1.0)),
        (s + 0.478462, 0.0, None), (s + 0.700000, 0.0, _cubic(0.86837757, 0.023684211, 0.3322124, 1.0)),
    ])
    effects.append("      </property>")
    effects.append("    </effect>")
    effects.append(
        f'    <path-stroke direction="centered" join="miter" end-size="1.5">'
        f'<color value="#FF{colors["outline"][1:]}"/><size value="5.000000"/></path-stroke>'
    )
    return transform, effects


# --------------------------------------------------------------------------- #
# Engine "offset" — slide-up lalu jatuh via efek Offset (vec2), identik untuk
# ketiga varian (blank/orange/greenfire); bedanya hanya shape latar opsional.
# --------------------------------------------------------------------------- #
def _build_offset_letter(lx: float, ly: float, start_s: float, font_size: int) -> tuple[list, list]:
    s = start_s
    scale = font_size / 18.0 * 0.887  # proporsi sample: size18 * scale3.547 ~ font_size 72 efektif
    transform = [f'      <location value="{lx:.6f},{ly:.6f},0.000000"/>']
    transform.append(f'      <scale value="{scale:.6f},{scale:.6f}"/>')

    effects = []
    effects.append('    <effect id="com.alightcreative.effects.offset" locallyApplied="true">')
    effects.append('      <property name="offset" type="vec2">')
    effects += _vec2_kf([
        (s + 0.284713, 0.0, -159.0, _cubic(1.0, 0.0, 0.58, 1.0)),
        (s + 0.700000, 0.0, 2001.0, _cubic(0.61469024, 0.0, 0.33516222, 1.0)),
        (s + 0.0, 0.0, 0.0, None),
    ])
    effects.append("      </property>")
    effects.append("    </effect>")
    return transform, effects


def _offset_background_shapes(bg: str, canvas: dict, colors: dict) -> list:
    """Shape dekoratif latar untuk varian 'orange'/'greenfire' (opsional).
    Semua tag/efek di sini terbukti ada di sample asli
    fyymotion-academy#orange.xml & #greenfire.xml, hanya posisi/ukuran yang
    disesuaikan ke ukuran kanvas yang dipilih pengguna."""
    if not bg:
        return []
    cx, cy = canvas["width"] / 2.0, canvas["height"] / 2.0
    size_scale = min(canvas["width"], canvas["height"]) / 160.0
    lines = []
    if bg == "orange":
        lines += [
            f'<shape id="45" tag="+accent" label="base 2" startTime="0" endTime="999999" fillType="color" s=".rect">',
            f'  <transform><location value="{cx:.6f},{cy:.6f},0.000000"/><scale value="{size_scale:.6f},{size_scale:.6f}"/></transform>',
            f'  <fillColor value="#FF6FFA42"/>',
            '  <effect id="com.alightcreative.effects.lift" locallyApplied="true"/>',
            '  <effect id="com.alightcreative.effects.findedges" locallyApplied="true">',
            '    <property name="smoothing" type="float" value="1.620000"/>',
            "  </effect>",
            '  <effect id="com.alightcreative.replacecolor" locallyApplied="true">',
            f'    <property name="newcolor" type="color" value="#FF{colors["accent1"][1:]}"/>',
            '    <property name="oldcolor" type="color" value="#FFFFFFFF"/>',
            "  </effect>",
            '  <effect id="com.alightcreative.effects.longshadow2" locallyApplied="true">',
            '    <property name="alpha" type="float" value="1.000000"/>',
            '    <property name="size" type="float" value="0.010000"/>',
            "  </effect>",
            '  <path-stroke direction="centered" end-size="1.5"/>',
            "</shape>",
            f'<shape id="46" tag="+accent" label="base 2 Copy" startTime="0" endTime="999999" fillType="color" s=".rect">',
            f'  <transform><location value="{cx:.6f},{cy:.6f},0.000000"/><scale value="{size_scale:.6f},{size_scale:.6f}"/></transform>',
            f'  <fillColor value="#FF6FFA42"/>',
            '  <effect id="com.alightcreative.effects.lift" locallyApplied="true"/>',
            '  <effect id="com.alightcreative.effects.chromakey" locallyApplied="true">',
            '    <property name="keyColor" type="color" value="#FF0D0E15"/>',
            "  </effect>",
            '  <effect id="com.alightcreative.gradientoverlay2" locallyApplied="true">',
            '    <property name="alpha" type="float" value="1.000000"/>',
            '    <property name="angle" type="float" value="180.000000"/>',
            '    <property name="color1" type="color" value="#FF0D0E15"/>',
            '    <property name="color2" type="color" value="#FFF2E6DA"/>',
            '    <property name="offset" type="vec2" value="-45.000000,21.000000"/>',
            '    <property name="scale" type="float" value="0.100000"/>',
            "  </effect>",
            '  <effect id="com.alightcreative.effects.halftonedots" locallyApplied="true">',
            '    <property name="amount" type="float" value="149.300003"/>',
            '    <property name="angle" type="float" value="0.000000"/>',
            '    <property name="strength" type="float" value="0.300000"/>',
            "  </effect>",
            '  <effect id="com.alightcreative.effects.chromakey" locallyApplied="true">',
            '    <property name="keyColor" type="color" value="#FFFFEEDD"/>',
            "  </effect>",
            '  <effect id="com.alightcreative.solidcolor" locallyApplied="true">',
            f'    <property name="color" type="color" value="#FF{colors["accent2"][1:]}"/>',
            "  </effect>",
            '  <path-stroke direction="centered" end-size="1.5"/>',
            "</shape>",
        ]
    elif bg == "greenfire":
        lines += [
            f'<shape id="45" tag="+accent" label="fire" startTime="0" endTime="999999" fillType="color" s=".rect">',
            f'  <transform><location value="{cx:.6f},{cy:.6f},0.000000"/><scale value="{size_scale:.6f},{size_scale:.6f}"/></transform>',
            f'  <fillColor value="#FF{colors["accent1"][1:]}"/>',
            '  <effect id="com.alightcreative.effects.wipe2" locallyApplied="true">',
            '    <property name="angle" type="float" value="90.000000"/>',
            '    <property name="end" type="float" value="0.583000"/>',
            "  </effect>",
            '  <effect id="com.alightcreative.effects.smoothedges" locallyApplied="true">',
            '    <property name="strength" type="float" value="0.090000"/>',
            "  </effect>",
            '  <effect id="com.alightcreative.effects.stretchsegment" locallyApplied="true">',
            '    <property name="angle" type="float" value="89.000000"/>',
            '    <property name="offset" type="float" value="-87.000000"/>',
            '    <property name="smooth" type="float" value="1.000000"/>',
            '    <property name="stretch" type="float" value="4.000000"/>',
            "  </effect>",
            '  <effect id="com.alightcreative.effects.wavewarp2" locallyApplied="true">',
            '    <property name="a1d" type="float" value="143.000000"/>',
            '    <property name="m1" type="float" value="147.100006"/>',
            '    <property name="m2" type="float" value="0.300000"/>',
            '    <property name="phase" type="float">',
            '      <kf t="0.000000" v="0.000000"/>',
            '      <kf t="0.992613" v="3.340000"/>',
            "    </property>",
            "  </effect>",
            '  <effect id="com.alightcreative.effects.wavewarp2" locallyApplied="true">',
            '    <property name="a1d" type="float" value="90.000000"/>',
            '    <property name="m1" type="float" value="203.900009"/>',
            '    <property name="m2" type="float" value="0.500000"/>',
            '    <property name="phase" type="float">',
            '      <kf t="0.000000" v="0.000000"/>',
            '      <kf t="0.992613" v="3.340000"/>',
            "    </property>",
            "  </effect>",
            '  <effect id="com.alightcreative.effects.fractalwarp4" locallyApplied="true">',
            '    <property name="intensity" type="float" value="0.660000"/>',
            '    <property name="mag" type="float" value="-0.060000"/>',
            '    <property name="octaves" type="float" value="5.000000"/>',
            '    <property name="scale" type="float" value="3.900000"/>',
            "  </effect>",
            '  <effect id="com.alightcreative.solidcolor" locallyApplied="true">',
            f'    <property name="color" type="color" value="#FF{colors["accent1"][1:]}"/>',
            "  </effect>",
            '  <effect id="com.alightcreative.gradientoverlay2" locallyApplied="true">',
            '    <property name="alpha" type="float" value="1.000000"/>',
            f'    <property name="color1" type="color" value="#FF{colors["accent2"][1:]}"/>',
            f'    <property name="color2" type="color" value="#FF{colors["accent1"][1:]}"/>',
            '    <property name="offset" type="vec2" value="0.000000,-41.000000"/>',
            '    <property name="scale" type="float" value="0.140000"/>',
            "  </effect>",
            '  <effect id="com.alightcreative.effects.smoothedges" locallyApplied="true">',
            '    <property name="strength" type="float" value="0.060000"/>',
            "  </effect>",
            '  <effect id="com.alightcreative.gradientoverlay2" locallyApplied="true">',
            f'    <property name="color2" type="color" value="#FF{colors["accent1"][1:]}"/>',
            '    <property name="offset" type="vec2" value="0.000000,-43.000000"/>',
            '    <property name="scale" type="float" value="0.100000"/>',
            "  </effect>",
            '  <effect id="com.alightcreative.effects.gaussianblur" locallyApplied="true"/>',
            "</shape>",
        ]
    return lines


# --------------------------------------------------------------------------- #
# Builder utama
# --------------------------------------------------------------------------- #
def build_text3d_xml(payload: dict) -> tuple[str, str]:
    """Validasi payload, bangun XML scene 3D Text, kembalikan (xml_text, filename)."""
    data = _validate_text3d_payload(payload)
    style = data["style"]
    engine = style["engine"]
    w, h = data["canvas"]["width"], data["canvas"]["height"]
    font_attr = _font_attr(data["font_family"], data["weight"])
    font_size = data["font_size"]
    colors = data["colors"]

    flat = _layout_units(data)
    n = len(flat)
    max_end_s = 0.0
    layer_blocks = []

    for item in flat:
        unit = item["unit"]
        lx, ly, s = item["lx"], item["ly"], item["start_s"]
        wrap_w = max(140, int(len(unit) * font_size * 0.95) + 60)

        if engine == "flip":
            transform_lines, effect_lines = _build_flip_letter(lx, ly, s, font_size, colors)
            own_end_s = s + 2.2
        elif engine in ("right", "popup"):
            transform_lines, effect_lines = _build_rightpopup_letter(
                engine, lx, ly, s, font_size, colors, data["extrude_depth"], data["curve"]
            )
            own_end_s = s + 2.2
        elif engine == "longshadow":
            transform_lines, effect_lines = _build_longshadow_letter(lx, ly, s, font_size, colors)
            own_end_s = s + 1.9
        else:  # offset
            transform_lines, effect_lines = _build_offset_letter(lx, ly, s, font_size)
            own_end_s = s + 2.2

        max_end_s = max(max_end_s, own_end_s)

        fill_attr = "" if engine == "offset" else f' fillColor="#FF{colors["base"][1:]}"'
        layer_lines = [
            f'<text id="{9000 + item["idx"]}" label="{esc_attr(unit)}" startTime="0" endTime="999999" '
            f'fillType="color" size="{font_size:.6f}" font="{esc_attr(font_attr)}" wrapWidth="{wrap_w}" '
            f'align="center"{fill_attr}>',
            "  <transform>",
        ]
        layer_lines.append("\n".join(transform_lines))
        layer_lines.append("  </transform>")
        if effect_lines:
            layer_lines.append("\n".join(effect_lines))
        layer_lines.append(f"  <content>{esc_text(unit)}</content>")
        layer_lines.append("</text>")
        layer_blocks.append("\n".join(layer_lines))

    end_hold_s = data["end_hold_ms"] / 1000.0
    total_s = max_end_s + end_hold_s
    total_ms = max(300, int(total_s * 1000))

    for block_idx in range(len(layer_blocks)):
        layer_blocks[block_idx] = layer_blocks[block_idx].replace('endTime="999999"', f'endTime="{total_ms}"')

    background_lines = []
    if engine == "offset":
        background_lines = _offset_background_shapes(style.get("background"), data["canvas"], colors)

    body_xml = "\n".join(layer_blocks)
    if background_lines:
        body_xml += "\n" + "\n".join(background_lines)

    now_ms = int(time.time() * 1000)
    title = f"3D Text {style['name']} - {' '.join(data['lines'])[:30]}"

    xml_text = (
        am_xml_header()
        + f'<scene title="{esc_attr(title)}" width="{w}" height="{h}" exportWidth="{w}" '
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
    filename = f"fyymotion-3dtext-{safe_style}-{now_ms}.xml"
    return xml_text, filename
