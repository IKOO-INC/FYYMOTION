"""
Teks Creator — generator preset teks Alight Motion (.xml)
===========================================================================
PENTING soal sumber kebenaran skema XML:
File XML di modul ini dibangun HANYA dari tag/atribut/efek yang benar-benar
terlihat pada contoh preset asli Alight Motion yang dikirim pengguna lewat
Google Drive (folder "One Click" dan "Hand-Crafted"), yaitu:

  - Root  : <scene title width height exportWidth exportHeight precompose
             bgcolor totalTime fps modifiedTime amver ffver am amplatform
             retime retimeAdaptFPS>
  - Layer : <text id label? startTime endTime fillType mediaFillMode size
             font wrapWidth align> berisi <transform>, <fillColor>,
             <effect>, <content>
  - Transform: <location value="x,y,z" />, <scale value="x,y" /> ATAU
             <scale><kf t=".." v=".." e="cubicBezier a b c d" /></scale>,
             <rotation> dengan pola <kf> yang sama, <opacity value=".." />,
             <pivot value="x,y" />
  - Efek bawaan yang terverifikasi di file sumber:
      com.alightcreative.effects.texttransform dengan properti
      start/end/phase/component/anchor/offset/angle/scale/stretch/alpha/
      useFillColor/fillColor/easeIn/easeOut/overlap/shape/randomOrder/seed.
      - component="2" (mode kata, offset statis, alpha=1, overlap>0) dipakai
        verbatim pada contoh asli untuk reveal kata "Stay strong, never quit".
      - component="1" (mode blok, offset BERKEYFRAME, overlap=0, alpha=0)
        dipakai verbatim pada contoh asli untuk slide watermark "STAMP-01".

Yang DIEKSTRAPOLASI secara minimal (bukan tag/efek baru, hanya menerapkan
pola <kf> yang SAMA pada properti sejenis yang belum ada contoh ber-keyframe
secara eksplisit) — didokumentasikan juga di UI /teks-creator:
  - <opacity> dan <location> dianimasikan memakai pola <kf> yang identik
    dengan <scale>/<rotation> (yang sudah terverifikasi berkeyframe).
  - component="0" dipakai sebagai mode "per huruf" (ekstrapolasi dari pola
    component 1 vs 2 di atas; cocokkan kembali di Alight Motion setelah
    import, nama resminya bisa berbeda di tiap versi aplikasi).

Alight Motion TIDAK memiliki efek "blur" (gaussian/motion blur) yang
terlihat di contoh manapun yang dikirim, jadi preset "Fade + Blur In" DISINI
disimulasikan dengan fade opacity + soft scale-settle (bukan blur asli).
Ini supaya kita tidak mengarang skema efek yang tidak pernah terbukti ada.
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape as _xml_escape


class ValidationError(ValueError):
    """Input dari pengguna tidak valid untuk dibuatkan XML preset."""


# --------------------------------------------------------------------------- #
# Katalog preset, kurva, dan font — data terpisah dari template XML supaya
# gampang ditambah tanpa mengutak-atik logika generator.
# --------------------------------------------------------------------------- #
PRESETS = {
    "fade_blur_in": {
        "name": "Fade + Blur In",
        "description": "Teks muncul dari samar menuju tajam — gaya pembukaan slide Apple keynote.",
        "icon": "fa-solid fa-wand-magic-sparkles",
        "category": "Apple Style",
        "animation": "fade_scale",
        "default_duration_ms": 900,
        "default_curve": "apple_ease",
        "note": (
            "Alight Motion tidak punya efek blur asli yang terbukti di contoh preset. "
            "Preset ini mensimulasikan 'blur masuk' dengan fade opacity + scale lembut, "
            "bukan gaussian blur sungguhan."
        ),
    },
    "slide_up_smooth": {
        "name": "Slide Up Smooth",
        "description": "Teks naik halus sambil fade in dengan kurva ease-out.",
        "icon": "fa-solid fa-arrow-up",
        "category": "Apple Style",
        "animation": "slide_up",
        "default_duration_ms": 700,
        "default_curve": "ease_out_expo",
    },
    "scale_spring": {
        "name": "Scale Spring",
        "description": "Teks membesar dengan sedikit overshoot lalu settle, seperti pegas lembut.",
        "icon": "fa-solid fa-expand",
        "category": "Apple Style",
        "animation": "scale_spring",
        "default_duration_ms": 650,
        "default_curve": "spring_soft",
    },
    "word_by_word": {
        "name": "Word-by-Word Reveal",
        "description": "Setiap kata muncul bergantian (stagger) memakai efek Text Transform bawaan.",
        "icon": "fa-solid fa-align-left",
        "category": "Apple Style",
        "animation": "texttransform_word",
        "default_duration_ms": 1400,
        "default_curve": "ease_out_expo",
    },
    "letter_stagger": {
        "name": "Letter Stagger",
        "description": "Huruf muncul bergantian (opacity + posisi Y) memakai Text Transform per karakter.",
        "icon": "fa-solid fa-text-height",
        "category": "Apple Style",
        "animation": "texttransform_letter",
        "default_duration_ms": 1200,
        "default_curve": "ease_out_expo",
        "note": (
            "Mode 'per karakter' pada efek Text Transform (component=0) adalah hasil "
            "ekstrapolasi dari pola yang terlihat di contoh preset asli. Setelah import, "
            "cek kembali opsi 'By Character' di Alight Motion untuk memastikan sesuai."
        ),
    },
    "kinetic_tight": {
        "name": "Kinetic Tight",
        "description": "Tracking teks dari lebar menjadi rapat — ala headline keynote Apple.",
        "icon": "fa-solid fa-compress",
        "category": "Apple Style",
        "animation": "texttransform_block_slide",
        "default_duration_ms": 750,
        "default_curve": "apple_ease",
    },
}

CURVES = {
    "apple_ease": {"label": "Apple Ease", "x1": 0.25, "y1": 0.1, "x2": 0.25, "y2": 1.0},
    "ease_out_expo": {"label": "Ease Out Expo", "x1": 0.16, "y1": 1.0, "x2": 0.3, "y2": 1.0},
    "spring_soft": {"label": "Spring Soft", "x1": 0.34, "y1": 1.56, "x2": 0.64, "y2": 1.0},
    "ease_in_out": {"label": "Ease In Out", "x1": 0.42, "y1": 0.0, "x2": 0.58, "y2": 1.0},
}

# Nama font nyata di Google Fonts, dipakai lewat skema `googlefonts?name=..&weight=..`
# yang terbukti ada di contoh asli (mis. "googlefonts?name=Open Sans&weight=800").
# SF Pro bukan Google Font sehingga tidak bisa dipakai langsung; "Inter" dipakai
# sebagai default karena bentuknya paling dekat dengan SF Pro.
FONTS = {
    "inter": {"label": "Inter (mirip SF Pro)", "family": "Inter"},
    "roboto": {"label": "Roboto", "family": "Roboto"},
    "open_sans": {"label": "Open Sans", "family": "Open Sans"},
    "montserrat": {"label": "Montserrat", "family": "Montserrat"},
    "poppins": {"label": "Poppins", "family": "Poppins"},
}
ALLOWED_WEIGHTS = {300, 400, 500, 600, 700, 800, 900}
ALLOWED_ALIGN = {"left", "center", "right"}

CANVAS_PRESETS = {
    "portrait": {"label": "Portrait 9:16 (Reels/TikTok)", "width": 1080, "height": 1920},
    "square": {"label": "Square 1:1", "width": 1080, "height": 1080},
    "landscape": {"label": "Landscape 16:9", "width": 1920, "height": 1080},
}


def esc_attr(value: str) -> str:
    """Escape nilai untuk dipakai di dalam atribut XML (&, <, >, \", ')."""
    return _xml_escape(str(value), {'"': "&quot;", "'": "&apos;"})


def esc_text(value: str) -> str:
    """Escape nilai untuk dipakai sebagai text node XML (&, <, >)."""
    return _xml_escape(str(value))


def _validate_hex_color(value, field_name="warna") -> str:
    text = str(value or "").strip()
    if not text.startswith("#"):
        text = "#" + text
    if len(text) != 7:
        raise ValidationError(f"Format {field_name} tidak valid, gunakan #RRGGBB.")
    hex_part = text[1:]
    try:
        int(hex_part, 16)
    except ValueError as exc:
        raise ValidationError(f"Format {field_name} tidak valid, gunakan #RRGGBB.") from exc
    return hex_part.lower()


def _validate_curve(payload: dict, default_curve_id: str = "apple_ease") -> dict:
    curve_id = str(payload.get("curve_id") or "").strip()
    if not curve_id and not payload.get("curve"):
        curve_id = default_curve_id
    if curve_id and curve_id in CURVES:
        c = CURVES[curve_id]
        return {"x1": c["x1"], "y1": c["y1"], "x2": c["x2"], "y2": c["y2"]}

    custom = payload.get("curve") or {}
    try:
        x1 = float(custom.get("x1"))
        y1 = float(custom.get("y1"))
        x2 = float(custom.get("x2"))
        y2 = float(custom.get("y2"))
    except (TypeError, ValueError) as exc:
        raise ValidationError("Nilai kurva cubic-bezier tidak valid.") from exc

    if not (0.0 <= x1 <= 1.0) or not (0.0 <= x2 <= 1.0):
        raise ValidationError("Nilai X pada kurva cubic-bezier harus di antara 0 dan 1.")
    for label, v in (("Y1", y1), ("Y2", y2)):
        if not (-3.0 <= v <= 4.0):
            raise ValidationError(f"Nilai {label} pada kurva di luar batas wajar (-3 s.d. 4).")
    return {"x1": x1, "y1": y1, "x2": x2, "y2": y2}


def _curve_str(curve: dict) -> str:
    return f"cubicBezier {curve['x1']:.6f} {curve['y1']:.6f} {curve['x2']:.6f} {curve['y2']:.6f}"


def _validate_payload(payload: dict) -> dict:
    preset_id = str(payload.get("preset_id") or "").strip()
    if preset_id not in PRESETS:
        raise ValidationError("Jenis preset tidak dikenali. Pilih salah satu kartu preset.")
    preset = PRESETS[preset_id]

    text = str(payload.get("text") or "").strip("\r\n")
    text = text.strip()
    if not text:
        raise ValidationError("Teks tidak boleh kosong.")
    if len(text) > 240:
        raise ValidationError("Teks terlalu panjang (maksimal 240 karakter).")
    if text.count("\n") > 4:
        raise ValidationError("Maksimal 5 baris teks.")

    try:
        font_size = int(float(payload.get("font_size", 72)))
    except (TypeError, ValueError) as exc:
        raise ValidationError("Ukuran teks harus berupa angka.") from exc
    if not (10 <= font_size <= 320):
        raise ValidationError("Ukuran teks harus di antara 10 dan 320.")

    color_hex = _validate_hex_color(payload.get("color", "#111111"))

    font_id = str(payload.get("font_id") or "inter").strip()
    if font_id not in FONTS:
        raise ValidationError("Font tidak dikenali.")

    try:
        weight = int(payload.get("font_weight", 700))
    except (TypeError, ValueError) as exc:
        raise ValidationError("Berat font (weight) harus angka.") from exc
    if weight not in ALLOWED_WEIGHTS:
        raise ValidationError("Berat font harus salah satu dari: " + ", ".join(map(str, sorted(ALLOWED_WEIGHTS))))

    align = str(payload.get("align") or "center").strip().lower()
    if align not in ALLOWED_ALIGN:
        raise ValidationError("Perataan teks tidak valid.")

    try:
        duration_ms = int(float(payload.get("duration_ms", preset["default_duration_ms"])))
    except (TypeError, ValueError) as exc:
        raise ValidationError("Durasi harus berupa angka (ms).") from exc
    if not (200 <= duration_ms <= 20000):
        raise ValidationError("Durasi harus di antara 200 ms dan 20000 ms.")

    canvas_id = str(payload.get("canvas_id") or "portrait").strip()
    if canvas_id not in CANVAS_PRESETS:
        raise ValidationError("Ukuran kanvas tidak dikenali.")
    canvas = CANVAS_PRESETS[canvas_id]

    curve = _validate_curve(payload, preset.get("default_curve", "apple_ease"))

    return {
        "preset_id": preset_id,
        "preset": preset,
        "text": text,
        "font_size": font_size,
        "color_hex": color_hex,
        "font_id": font_id,
        "font_family": FONTS[font_id]["family"],
        "weight": weight,
        "align": align,
        "duration_ms": duration_ms,
        "canvas": canvas,
        "curve": curve,
    }


def _font_attr(family: str, weight: int) -> str:
    # Skema terverifikasi: googlefonts?name=<Nama Font>&weight=<angka>
    return f"googlefonts?name={family}&weight={weight}"


def _kf(t: float, v: str, easing: str | None = None) -> str:
    if easing:
        return f'        <kf t="{t:.6f}" v="{v}" e="{esc_attr(easing)}" />'
    return f'        <kf t="{t:.6f}" v="{v}" />'


def _build_transform_block(data: dict) -> str:
    """Isi <transform> sesuai jenis animasi preset (dipakai preset berbasis transform murni)."""
    anim = data["preset"]["animation"]
    w, h = data["canvas"]["width"], data["canvas"]["height"]
    cx, cy = w / 2.0, h / 2.0
    dur_s = data["duration_ms"] / 1000.0
    curve_str = _curve_str(data["curve"])
    lines = [f'      <location value="{cx:.6f},{cy:.6f},0.000000" />']

    if anim == "fade_scale":
        # Ekstrapolasi: <opacity> dan <scale> dianimasikan dengan pola <kf>
        # yang identik dengan contoh <scale>/<rotation> yang terverifikasi.
        lines.append("      <opacity>")
        lines.append(_kf(0.0, "0.000000"))
        lines.append(_kf(dur_s, "1.000000", curve_str))
        lines.append("      </opacity>")
        lines.append("      <scale>")
        lines.append(_kf(0.0, "1.080000,1.080000"))
        lines.append(_kf(dur_s, "1.000000,1.000000", curve_str))
        lines.append("      </scale>")
    elif anim == "slide_up":
        slide_px = min(140.0, data["font_size"] * 1.3)
        lines = [
            "      <location>",
            _kf(0.0, f"{cx:.6f},{cy + slide_px:.6f},0.000000"),
            _kf(dur_s, f"{cx:.6f},{cy:.6f},0.000000", curve_str),
            "      </location>",
            "      <opacity>",
            _kf(0.0, "0.000000"),
            _kf(dur_s, "1.000000", curve_str),
            "      </opacity>",
        ]
    elif anim == "scale_spring":
        # Terverifikasi langsung: pola <scale><kf .../></scale> 0 -> 1 persis
        # seperti contoh asli (mis. preset "😀" One-Click/01).
        lines.append("      <scale>")
        lines.append(_kf(0.0, "0.000000,0.000000"))
        lines.append(_kf(dur_s, "1.000000,1.000000", curve_str))
        lines.append("      </scale>")
    return "\n".join(lines)


def _build_texttransform_effect(data: dict) -> str:
    anim = data["preset"]["animation"]
    dur_s = data["duration_ms"] / 1000.0
    curve_str = _curve_str(data["curve"])

    if anim == "texttransform_word":
        # Terverifikasi langsung dari contoh asli (reveal "Stay strong, never quit").
        component, offset, overlap, alpha, ease_out = 2, "0.000000,-28.000000", 1.2, "1.000000", "1.000000"
        end_kf = [_kf(0.0, "0.050000"), _kf(dur_s, "1.000000", curve_str)]
        anchor, scale_prop, stretch_prop, ease_in = 1, "0.000000", "0.000000", "0.000000"
    elif anim == "texttransform_letter":
        # Ekstrapolasi: component=0 (per karakter) dari pola component 1 vs 2 di atas.
        component, offset, overlap, alpha, ease_out = 0, "0.000000,-14.000000", 0.6, "1.000000", "1.000000"
        end_kf = [_kf(0.0, "0.030000"), _kf(dur_s, "1.000000", curve_str)]
        anchor, scale_prop, stretch_prop, ease_in = 1, "0.000000", "0.000000", "0.000000"
    else:
        raise ValidationError("Jenis animasi texttransform tidak dikenali.")

    end_block = "\n".join(["      <property name=\"end\" type=\"float\">"] + end_kf + ["      </property>"])
    return "\n".join([
        '      <effect id="com.alightcreative.effects.texttransform" locallyApplied="true">',
        '        <property name="start" type="float" value="0.000000" />',
        end_block,
        '        <property name="phase" type="float" value="0.000000" />',
        f'        <property name="component" type="int" value="{component}" />',
        f'        <property name="anchor" type="int" value="{anchor}" />',
        f'        <property name="offset" type="vec2" value="{offset}" />',
        '        <property name="angle" type="float" value="0.000000" />',
        f'        <property name="scale" type="float" value="{scale_prop}" />',
        f'        <property name="stretch" type="float" value="{stretch_prop}" />',
        f'        <property name="alpha" type="float" value="{alpha}" />',
        '        <property name="useFillColor" type="bool" value="false" />',
        '        <property name="fillColor" type="color" value="#ff00ff00" />',
        f'        <property name="easeIn" type="float" value="{ease_in}" />',
        f'        <property name="easeOut" type="float" value="{ease_out}" />',
        f'        <property name="overlap" type="float" value="{overlap}" />',
        '        <property name="shape" type="int" value="0" />',
        '        <property name="randomOrder" type="bool" value="false" />',
        '        <property name="seed" type="float" value="0.000000" />',
        "      </effect>",
    ])


def _build_block_slide_effect(data: dict) -> str:
    # Terverifikasi langsung dari contoh asli (slide watermark "STAMP-01" / "Assembly-01"):
    # component=1, anchor=0, offset BERKEYFRAME (urutan besar->kecil), overlap=0, alpha=0.
    dur_s = data["duration_ms"] / 1000.0
    curve_str = _curve_str(data["curve"])
    tracking_px = min(600.0, data["font_size"] * 4.0)
    offset_block = "\n".join([
        '      <property name="offset" type="vec2">',
        _kf(dur_s, "0.000000,0.000000", curve_str),
        _kf(0.0, f"-{tracking_px:.6f},0.000000"),
        "      </property>",
    ])
    return "\n".join([
        '      <effect id="com.alightcreative.effects.texttransform" locallyApplied="true">',
        '        <property name="start" type="float" value="0.000000" />',
        '        <property name="end" type="float" value="1.000000" />',
        '        <property name="phase" type="float" value="0.000000" />',
        '        <property name="component" type="int" value="1" />',
        '        <property name="anchor" type="int" value="0" />',
        offset_block,
        '        <property name="angle" type="float" value="0.000000" />',
        '        <property name="scale" type="float" value="0.000000" />',
        '        <property name="stretch" type="float" value="0.000000" />',
        '        <property name="alpha" type="float" value="0.000000" />',
        '        <property name="useFillColor" type="bool" value="false" />',
        '        <property name="fillColor" type="color" value="#ff00ff00" />',
        '        <property name="easeIn" type="float" value="0.000000" />',
        '        <property name="easeOut" type="float" value="0.000000" />',
        '        <property name="overlap" type="float" value="0.000000" />',
        '        <property name="shape" type="int" value="0" />',
        '        <property name="randomOrder" type="bool" value="false" />',
        '        <property name="seed" type="float" value="0.000000" />',
        "      </effect>",
    ])


def _build_text_layer_xml(data: dict) -> str:
    anim = data["preset"]["animation"]
    w, h = data["canvas"]["width"], data["canvas"]["height"]
    cx, cy = w / 2.0, h / 2.0
    longest_line = max((len(line) for line in data["text"].split("\n")), default=1)
    wrap_width = max(360, min(w - 120, int(longest_line * data["font_size"] * 0.62) + 80))
    font_attr = _font_attr(data["font_family"], data["weight"])

    effect_xml = ""
    if anim in ("texttransform_word", "texttransform_letter"):
        transform_xml = f'      <location value="{cx:.6f},{cy:.6f},0.000000" />'
        effect_xml = "\n" + _build_texttransform_effect(data)
    elif anim == "texttransform_block_slide":
        transform_xml = f'      <location value="{cx:.6f},{cy:.6f},0.000000" />'
        effect_xml = "\n" + _build_block_slide_effect(data)
    else:
        transform_xml = _build_transform_block(data)

    return "\n".join([
        f'  <text id="101" label="FYY Teks Creator - {esc_attr(data["preset"]["name"])}" '
        f'startTime="0" endTime="{data["duration_ms"]}" fillType="color" mediaFillMode="fill" '
        f'size="{data["font_size"]:.6f}" font="{esc_attr(font_attr)}" wrapWidth="{wrap_width}" '
        f'align="{data["align"]}">',
        "    <transform>",
        transform_xml,
        "    </transform>",
        f'    <fillColor value="#ff{data["color_hex"]}" />' ,
        effect_xml,
        f"    <content>{esc_text(data['text'])}</content>",
        "  </text>",
    ])


def build_text_scene_xml(payload: dict) -> tuple[str, str]:
    """Validasi payload, bangun XML scene Alight Motion, lalu kembalikan (xml_text, filename).

    Raises ValidationError bila input tidak valid. Hasil XML selalu diparse ulang
    dengan xml.etree.ElementTree sebelum dikembalikan untuk memastikan well-formed.
    """
    data = _validate_payload(payload)
    w, h = data["canvas"]["width"], data["canvas"]["height"]
    now_ms = int(time.time() * 1000)
    title = f"{data['preset']['name']} - {data['text'][:30]}"
    text_layer_xml = _build_text_layer_xml(data)

    xml_text = (
        "<?xml version='1.0' encoding='UTF-8' ?><!--\n"
        "Dibuat oleh FYY MOTION Teks Creator (bukan diekspor dari aplikasi Alight Motion)\n"
        f"Preset: {data['preset']['name']}\n"
        "-->\r\n"
        f'<scene title="{esc_attr(title)}" width="{w}" height="{h}" exportWidth="{w}" '
        f'exportHeight="{h}" precompose="dynamicResolution" bgcolor="#00000000" '
        f'totalTime="{data["duration_ms"]}" fps="30" modifiedTime="{now_ms}" '
        'amver="1002592" ffver="106" am="com.alightcreative.motion/5.0.275" '
        'amplatform="android" retime="freeze" retimeAdaptFPS="false">\r\n'
        f"{text_layer_xml}\r\n"
        "</scene>"
    )

    try:
        ET.fromstring(xml_text)
    except ET.ParseError as exc:
        # Harusnya tidak pernah terjadi karena semua nilai sudah di-escape,
        # tapi jaga-jaga supaya tidak pernah mengirim XML rusak ke pengguna.
        raise ValidationError(f"Gagal membuat XML yang valid: {exc}") from exc

    safe_preset = data["preset_id"].replace("_", "-")
    filename = f"fyymotion-teks-{safe_preset}-{now_ms}.xml"
    return xml_text, filename
