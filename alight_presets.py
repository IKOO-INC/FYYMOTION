"""
Teks Creator — generator preset teks Alight Motion (.xml)
===========================================================================
SUMBER KEBENARAN SKEMA XML (wajib dibaca sebelum mengubah file ini)
---------------------------------------------------------------------------
Modul ini membangun XML HANYA dari tag/atribut/efek yang benar-benar
terlihat di 30 file preset asli Alight Motion yang diambil langsung dari
Google Drive milik pengguna:

  - 10 file dari folder "Hand-Crafted" (animasi per-huruf, dibuat manual).
  - 20 file dari folder "One-Click" (animasi satu-klik, umumnya 1 layer teks
    + 1 efek bawaan Alight Motion).

Ditambah 10 preset kategori "Apple" yang diambil dari folder Google Drive
terpisah (10 file .xml nama UUID, judul internal "Text Animation 1" s/d
"Text Animation 10"). File-file ini jauh lebih kompleks (banyak <embedScene>
bersarang, <nullobj>, shape dekoratif .circle/.roundrect, path-stroke custom)
sehingga untuk tiap preset Apple hanya ANIMASI INTI TEKS yang diambil persis
dari file sumber (kurva cubic-bezier, properti efek, path vektor hand-drawn,
dsb.), sedangkan shape dekoratif sekunder (lingkaran, pil badge, panah) yang
tidak esensial untuk reveal teks disederhanakan/dibuang — selalu ditandai
lewat field "note" bila ada penyederhanaan struktural.

Setiap preset di bawah ini (PRESETS) menyimpan parameter ASLI yang diambil
dari file sumbernya masing-masing (kurva cubic-bezier, sudut rotasi, offset,
nama efek, dsb). Tidak ada efek/atribut yang dikarang; yang disederhanakan
hanyalah STRUKTUR pembungkus (file asli memakai banyak <embedScene> bersarang
untuk kredit/watermark/tutorial yang tidak relevan untuk alat ini — bagian
itu dibuang, sedangkan animasi inti pada teks tetap memakai tag & parameter
yang sama persis dengan file sumber).

Efek Alight Motion asli yang terbukti dipakai (dan karenanya tersedia di sini):
  - com.alightcreative.effects.texttransform  (reveal per kata/baris/global)
  - com.alightcreative.effects.wipe2          (reveal wipe/geser)
  - com.alightcreative.effects.gaussianblur   (fokus masuk — defocus-in)
  - com.alightcreative.effects.textprogress   (efek ketik/typewriter)
  - com.alightcreative.effects.pinchbulge2    (distorsi pop-in)
  - com.alightcreative.effects.zoomblur3      (zoom blur pop-in)
  - com.alightcreative.effects.fade           (fade in/out halus)
  - com.alightcreative.effects.offset         (geser dengan mask persegi)
  - com.alightcreative.effects.textspacing    (animasi kerapatan huruf)
  - com.alightcreative.effects.flicker2       (kedip-kedip sesaat sebelum stabil)
  - com.alightcreative.effects.drawing.progress (coretan vektor tergambar progresif)
  - <transform><scale>/<rotation>/<location> dengan <kf t=".." v=".." e="cubicBezier a b c d" />

Beberapa preset sumber memakai kurva "elastic ..." (pegas) yang BUKAN
cubic-bezier 4 angka. Karena editor kurva di Teks Creator (langkah 3) hanya
menyediakan kontrol cubic-bezier, preset semacam itu memakai kurva
cubic-bezier ASLI LAIN yang terbukti ada di file sumber yang sama persis
(nilai universal "cubicBezier 0.0 0.0 0.3665272 1.0" muncul verbatim di
SETIAP file sumber, dipakai sebagai kurva default yang jujur — bukan
karangan) sebagai pengganti default, dan ditandai di field "elastic_note".
Pengguna tetap bisa mengubah kurva ini sendiri di langkah 3.
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from datetime import datetime
from xml.sax.saxutils import escape as _xml_escape


class ValidationError(ValueError):
    """Input dari pengguna tidak valid untuk dibuatkan XML preset."""


# --------------------------------------------------------------------------- #
# Header komentar XML — WAJIB identik dengan hasil export asli Alight Motion.
# Format ini terbukti verbatim di SEMUA sample .xml asli yang diberikan
# pengguna (folder "teks 2d" & "teks 3d" Google Drive), contoh persis:
#
#   <?xml version='1.0' encoding='UTF-8' ?>
#   <!--
#   Created by Alight Motion (http://alightmotion.com)
#   Exported: 2026-06-17 01:09 AM
#   6.2.53 (859)
#   -->
#
# Instruksi pengguna: header ini tidak boleh dihapus/diubah strukturnya dan
# WAJIB dipakai di SEMUA output XML tool ini (Teks Creator, Text FX, 3D
# Text). Satu-satunya bagian yang dinamis adalah baris "Exported: ..."
# (waktu generate saat ini, format sama persis dengan sample).
# --------------------------------------------------------------------------- #
def am_xml_header() -> str:
    exported_at = datetime.now().strftime("%Y-%m-%d %I:%M %p")
    return (
        "<?xml version='1.0' encoding='UTF-8' ?>\n"
        "<!--\n"
        "Created by Alight Motion (http://alightmotion.com)\n"
        f"Exported: {exported_at}\n"
        "6.2.53 (859)\n"
        "-->\n"
    )


# Kurva cubic-bezier universal yang terbukti ada verbatim di SEMUA 30 file
# sumber (dipakai pada reveal watermark kredit "Assembly-01"/"STAMP-01").
# Dipakai sebagai fallback jujur untuk preset yang aslinya memakai easing
# "elastic" (bukan cubic-bezier 4 angka).
_REAL_FALLBACK_CURVE = (0.0, 0.0, 0.3665272, 1.0)


# --------------------------------------------------------------------------- #
# Katalog 30 preset asli: 10 Hand-Crafted (animasi per huruf) + 20 One-Click
# (animasi 1 layat teks + 1 efek). Setiap entri menyimpan parameter ASLI.
# --------------------------------------------------------------------------- #
PRESETS = {
    # ============================= HAND-CRAFTED (10) ============================= #
    "hc01_pop_bounce": {
        "name": "Pop Bounce",
        "category": "hand_crafted",
        "description": "Setiap huruf memantul masuk dengan skala membesar dan sedikit rotasi — gaya Hand-Crafted asli.",
        "icon": "fa-solid fa-wand-sparkles",
        "engine": "letter_pop",
        "demo_text": "FUN",
        "default_duration_ms": 900,
        "curve": (0.0, 0.0, 0.58, 1.0),
        "params": {"rotation_deg": -38.414642, "stagger_ms": 100},
    },
    "hc02_trust_me": {
        "name": "Trust Me Slide",
        "category": "hand_crafted",
        "description": "Huruf meluncur dari bawah lalu memantul balik ke posisi — animasi dua tahap khas Hand-Crafted.",
        "icon": "fa-solid fa-arrow-up",
        "engine": "letter_pop",
        "demo_text": "Trust Me",
        "default_duration_ms": 900,
        "curve": (0.22418408, 0.0, 0.10878661, 1.0),
        "params": {"rotation_deg": 0.0, "stagger_ms": 100, "slide_offset_y": 259.0},
    },
    "hc03_looping": {
        "name": "Looping Elastic",
        "category": "hand_crafted",
        "description": "Huruf melompat masuk dengan pegas (elastic) — efek 'looping' asli, kurva diganti bezier jujur.",
        "icon": "fa-solid fa-rotate",
        "engine": "letter_pop",
        "demo_text": "Looping",
        "default_duration_ms": 900,
        "curve": _REAL_FALLBACK_CURVE,
        "elastic_note": "Preset asli memakai kurva pegas 'elastic 0.34184098 1.0 0.0 0.82986414'.",
        "params": {"rotation_deg": 0.0, "stagger_ms": 100},
    },
    "hc04_black": {
        "name": "Soft Pop",
        "category": "hand_crafted",
        "description": "Huruf membesar lembut tanpa rotasi — animasi paling minimalis dari seri Hand-Crafted.",
        "icon": "fa-solid fa-circle",
        "engine": "letter_pop",
        "demo_text": "Black",
        "default_duration_ms": 850,
        "curve": (0.25, 0.25, 0.0, 1.0),
        "params": {"rotation_deg": 0.0, "stagger_ms": 100},
    },
    "hc05_hungry": {
        "name": "Bounce Slide",
        "category": "hand_crafted",
        "description": "Huruf meluncur horizontal dengan pantulan ganda sebelum berhenti di posisi akhir.",
        "icon": "fa-solid fa-arrows-left-right",
        "engine": "letter_pop",
        "demo_text": "Hungry",
        "default_duration_ms": 950,
        "curve": (0.22, 0.0, 0.11, 1.0),
        "params": {"rotation_deg": 0.0, "stagger_ms": 100, "slide_offset_x": 197.5},
    },
    "hc06_hello": {
        "name": "Settle Pop",
        "category": "hand_crafted",
        "description": "Huruf membesar lalu menyusut-settle ke ukuran akhir — animasi 'Hello' asli bertahap.",
        "icon": "fa-solid fa-hand",
        "engine": "letter_pop",
        "demo_text": "Hello",
        "default_duration_ms": 950,
        "curve": (0.42, 0.0, 0.58, 1.0),
        "params": {"rotation_deg": 0.0, "stagger_ms": 100},
    },
    "hc07_motion": {
        "name": "Motion Elastic",
        "category": "hand_crafted",
        "description": "Huruf melompat masuk berurutan dengan pegas ritmis — animasi khas kata 'MOTION'.",
        "icon": "fa-solid fa-bolt",
        "engine": "letter_pop",
        "demo_text": "MOTION",
        "default_duration_ms": 950,
        "curve": _REAL_FALLBACK_CURVE,
        "elastic_note": "Preset asli memakai kurva pegas 'elastic 0.24707112 1.0 0.0 0.6767421'.",
        "params": {"rotation_deg": 0.0, "stagger_ms": 133},
    },
    "hc08_design_flip": {
        "name": "Flip Spin",
        "category": "hand_crafted",
        "description": "Huruf berputar 180° sambil membesar dari titik kecil — animasi flip khas kata 'Design'.",
        "icon": "fa-solid fa-arrows-rotate",
        "engine": "letter_pop",
        "demo_text": "Design",
        "default_duration_ms": 900,
        "curve": (0.41, 0.0, 0.11, 1.0),
        "params": {"rotation_deg": -180.0, "stagger_ms": 100},
    },
    "hc09_today": {
        "name": "Today Bounce",
        "category": "hand_crafted",
        "description": "Huruf meluncur masuk lalu memantul balik halus — animasi bertahap seri 'Today'.",
        "icon": "fa-solid fa-calendar-day",
        "engine": "letter_pop",
        "demo_text": "Today",
        "default_duration_ms": 950,
        "curve": (0.22418408, 0.0, 0.10878661, 1.0),
        "params": {"rotation_deg": 0.0, "stagger_ms": 100},
    },
    "hc10_yesterday": {
        "name": "Yesterday Wave",
        "category": "hand_crafted",
        "description": "Huruf melompat masuk berurutan — versi disederhanakan dari animasi 'Yesterday' (efek wave gelombang pada file asli tidak disertakan).",
        "icon": "fa-solid fa-water",
        "engine": "letter_pop",
        "demo_text": "Yesterday",
        "default_duration_ms": 900,
        "curve": (0.2376569, 0.0, 0.16661088, 1.0),
        "note": "File sumber memiliki efek tambahan 'wavewarp2' pada seluruh grup; efek ini disederhanakan di sini agar tetap ringan dan dapat diprediksi.",
        "params": {"rotation_deg": 0.0, "stagger_ms": 100},
    },

    # ============================== ONE-CLICK (20) ============================== #
    "oc01_keep_it": {
        "name": "Keep It! Pop",
        "category": "one_click",
        "description": "Teks membesar dari nol ke ukuran penuh — animasi One-Click paling sederhana.",
        "icon": "fa-solid fa-circle-up",
        "engine": "pop",
        "demo_text": "Keep it!",
        "default_duration_ms": 450,
        "curve": (0.25, 0.25, 0.20753138, 1.0),
        "params": {},
    },
    "oc02_stay_strong": {
        "name": "Word Reveal Up",
        "category": "one_click",
        "description": "Setiap kata muncul bergantian dari bawah — Text Transform mode kata (component 2).",
        "icon": "fa-solid fa-align-left",
        "engine": "texttransform",
        "demo_text": "Stay strong, never quit",
        "default_duration_ms": 1000,
        "curve": (0.27029288, 0.0, 0.23188284, 1.0),
        "params": {"component": 2, "anchor": 1, "offset": (0.0, -28.0), "overlap": 1.2, "alpha": "1.000000", "ease_in": "0.0", "ease_out": "1.0", "end_start": 0.062, "mirror": False, "angle": 0.0, "scale_prop": 0.0},
    },
    "oc03_hello_word": {
        "name": "Hello Word Elastic",
        "category": "one_click",
        "description": "Teks melompat masuk dengan pegas (elastic) ringan dari ukuran nol.",
        "icon": "fa-solid fa-bolt-lightning",
        "engine": "pop",
        "demo_text": "Hello Word",
        "default_duration_ms": 500,
        "curve": _REAL_FALLBACK_CURVE,
        "elastic_note": "Preset asli memakai kurva pegas 'elastic 0.32677826 1.0 0.0 0.21737564'.",
        "params": {},
    },
    "oc04_make_it_happen": {
        "name": "Diagonal Wipe",
        "category": "one_click",
        "description": "Teks muncul lewat sapuan diagonal lembut (feather) dari kiri bawah ke kanan atas.",
        "icon": "fa-solid fa-angle-right",
        "engine": "wipe",
        "demo_text": "Make it happen",
        "default_duration_ms": 900,
        "curve": (0.0, 0.0, 0.58, 1.0),
        "params": {"angle": 0.0, "feather": 44.1},
    },
    "oc05_stay_safe": {
        "name": "Defocus In",
        "category": "one_click",
        "description": "Teks masuk dari buram (gaussian blur) menuju fokus tajam sambil membesar — efek blur Alight Motion asli.",
        "icon": "fa-solid fa-eye",
        "engine": "blur_pop",
        "demo_text": "Stay safe",
        "default_duration_ms": 650,
        "curve": (0.3046025, 0.0, 0.4369037, 1.0),
        "params": {"blur_start": 0.15},
    },
    "oc06_time_will_tell": {
        "name": "Letter Underline Reveal",
        "category": "one_click",
        "description": "Huruf demi huruf terungkap dari bawah garis dasar — Text Transform mode per-huruf dengan overlap panjang.",
        "icon": "fa-solid fa-underline",
        "engine": "texttransform",
        "demo_text": "Time will tell",
        "default_duration_ms": 950,
        "curve": None,
        "params": {"component": 1, "anchor": 0, "offset": (0.0, 45.0), "overlap": 6.0, "alpha": "-1.000000", "ease_in": "1.0", "ease_out": "-1.0", "end_start": 0.0, "end_target": 0.775, "mirror": False, "angle": 0.0, "scale_prop": 0.0},
    },
    "oc07_believe": {
        "name": "Slide From Right",
        "category": "one_click",
        "description": "Teks meluncur masuk dari sisi kanan sambil terungkap huruf demi huruf.",
        "icon": "fa-solid fa-arrow-left",
        "engine": "texttransform",
        "demo_text": "Believe in yourself",
        "default_duration_ms": 1000,
        "curve": None,
        "params": {"component": 1, "anchor": 0, "offset": (0.0, 45.0), "overlap": 6.0, "alpha": "-1.000000", "ease_in": "1.0", "ease_out": "-1.0", "end_start": 0.0, "end_target": 0.749, "mirror": False, "angle": 0.0, "scale_prop": 0.0, "slide_from": (456.5, 0.0), "slide_curve": (0.26694563, 0.021719456, 0.29548115, 1.0)},
    },
    "oc08_good_luck": {
        "name": "Random Letter Pop",
        "category": "one_click",
        "description": "Huruf muncul dalam urutan acak sambil kerapatan huruf mengetat ke posisi normal.",
        "icon": "fa-solid fa-shuffle",
        "engine": "texttransform",
        "demo_text": "Good luck!",
        "default_duration_ms": 1000,
        "curve": None,
        "params": {"component": 1, "anchor": 0, "offset": None, "overlap": 6.0, "alpha": "-1.000000", "ease_in": "1.0", "ease_out": "0.0", "end_start": 0.0, "end_target": 1.0, "mirror": False, "angle": 0.0, "scale_prop": 0.0, "random_order": True, "seed": 0.15, "letterspacing_curve": (0.2349781, 0.0, 0.04778242, 1.0)},
    },
    "oc09_keep_in_touch": {
        "name": "Slide From Right Tight",
        "category": "one_click",
        "description": "Teks bergeser dari kanan sambil terungkap — jarak geser lebih pendek dari 'Slide From Right'.",
        "icon": "fa-solid fa-right-long",
        "engine": "texttransform",
        "demo_text": "Keep in touch",
        "default_duration_ms": 900,
        "curve": None,
        "params": {"component": 1, "anchor": 0, "offset": (317.0, 0.0), "offset_animated": True, "overlap": 6.0, "alpha": "-1.000000", "ease_in": "1.0", "ease_out": "-1.0", "end_start": 0.0, "end_target": 0.775, "mirror": False, "angle": 0.0, "scale_prop": 0.0},
    },
    "oc10_do_your_best": {
        "name": "Mirror Flip Reveal",
        "category": "one_click",
        "description": "Teks terungkap dengan efek cermin (mirror/flip) dari tengah ke tepi.",
        "icon": "fa-solid fa-left-right",
        "engine": "texttransform",
        "demo_text": "Do your best",
        "default_duration_ms": 850,
        "curve": None,
        "params": {"component": 1, "anchor": 1, "offset": None, "overlap": 5.39, "alpha": "0.0", "ease_in": "1.0", "ease_out": "-1.0", "end_start": 0.0, "end_target": 0.609, "mirror": True, "angle": 0.0, "scale_prop": -1.0},
    },
    "oc11_wait_a_minute": {
        "name": "Rotated Mirror Reveal",
        "category": "one_click",
        "description": "Teks terungkap dengan efek cermin yang diputar 90° — variasi dari Mirror Flip Reveal.",
        "icon": "fa-solid fa-rotate-right",
        "engine": "texttransform",
        "demo_text": "Wait a minute",
        "default_duration_ms": 850,
        "curve": None,
        "params": {"component": 1, "anchor": 1, "offset": (0.0, 69.0), "overlap": 10.0, "alpha": "-1.000000", "ease_in": "1.0", "ease_out": "-1.0", "end_start": 0.0, "end_target": 0.609, "mirror": True, "angle": 90.099998, "scale_prop": -1.0},
    },
    "oc12_cheer_up": {
        "name": "Mask Slide Reveal",
        "category": "one_click",
        "description": "Teks meluncur dari kiri sambil dibatasi kotak mask — terlihat seperti tirai geser.",
        "icon": "fa-solid fa-table-cells",
        "engine": "mask_slide",
        "demo_text": "Cheer up",
        "default_duration_ms": 900,
        "curve": (0.26245096, 0.0, 0.17761374, 1.0),
        "params": {"slide_from_x": -1036.45, "mask_w": 527.5, "mask_h": 149.5},
    },
    "oc13_take_it_easy": {
        "name": "Column Wipe Reveal",
        "category": "one_click",
        "description": "Teks terungkap vertikal kolom demi kolom dengan sedikit efek mengecil.",
        "icon": "fa-solid fa-table-columns",
        "engine": "texttransform",
        "demo_text": "Take it easy, man.",
        "default_duration_ms": 850,
        "curve": None,
        "params": {"component": 2, "anchor": 0, "offset": None, "overlap": 2.42, "alpha": "-1.000000", "ease_in": "1.0", "ease_out": "-0.98", "end_start": 0.0, "end_target": 0.782, "mirror": False, "angle": 0.0, "scale_prop": 0.92},
    },
    "oc14_what_are_you_doing": {
        "name": "Typewriter",
        "category": "one_click",
        "description": "Teks diketik huruf demi huruf lengkap dengan kursor berkedip — efek Text Progress asli.",
        "icon": "fa-solid fa-keyboard",
        "engine": "typewriter",
        "demo_text": "What are you doing?",
        "default_duration_ms": 1400,
        "curve": None,
        "params": {"cursor": 5, "blink": True},
    },
    "oc15_go_ahead": {
        "name": "Pinch Zoom Pop",
        "category": "one_click",
        "description": "Teks melesat masuk dengan distorsi pinch-bulge dan zoom blur — efek dramatis.",
        "icon": "fa-solid fa-explosion",
        "engine": "distort",
        "demo_text": "Go ahead",
        "default_duration_ms": 800,
        "curve": (0.24, 0.4, 0.0, 1.0),
        "params": {"pinch_strength": 0.64, "pinch_radius": 0.67, "zoom_strength": 0.33},
    },
    "oc16_nice_to_meet_you": {
        "name": "Diagonal Mirror Slide",
        "category": "one_click",
        "description": "Teks terungkap diagonal 46° sambil bergeser dari sisi — kombinasi mirror dan slide.",
        "icon": "fa-solid fa-diamond",
        "engine": "texttransform",
        "demo_text": "Nice to meet you",
        "default_duration_ms": 1000,
        "curve": None,
        "params": {"component": 1, "anchor": 1, "offset": (317.0, 0.0), "offset_animated": True, "overlap": 6.0, "alpha": "0.0", "ease_in": "1.0", "ease_out": "-1.0", "end_start": 0.0, "end_target": 0.775, "mirror": True, "angle": 46.3, "scale_prop": -1.0},
    },
    "oc17_see_you_later": {
        "name": "Diagonal Mirror Reveal",
        "category": "one_click",
        "description": "Teks terungkap diagonal 46° di tempat — tanpa pergeseran posisi.",
        "icon": "fa-solid fa-diamond-turn-right",
        "engine": "texttransform",
        "demo_text": "See you later,",
        "default_duration_ms": 950,
        "curve": None,
        "params": {"component": 1, "anchor": 1, "offset": (0.0, 0.0), "overlap": 6.0, "alpha": "0.0", "ease_in": "1.0", "ease_out": "-1.0", "end_start": 0.0, "end_target": 0.775, "mirror": True, "angle": 46.3, "scale_prop": -1.0},
    },
    "oc18_dont_be_like_that": {
        "name": "Diagonal Mirror Offset",
        "category": "one_click",
        "description": "Teks terungkap diagonal 46° dengan titik asal offset — variasi penempatan dari Diagonal Mirror Reveal.",
        "icon": "fa-solid fa-diamond-half",
        "engine": "texttransform",
        "demo_text": "Don't be like that",
        "default_duration_ms": 950,
        "curve": None,
        "params": {"component": 1, "anchor": 1, "offset": (-152.0, -90.0), "overlap": 7.9, "alpha": "-1.000000", "ease_in": "1.0", "ease_out": "-1.0", "end_start": 0.0, "end_target": 0.775, "mirror": True, "angle": 46.3, "scale_prop": -1.0},
    },
    "oc19_life_is_a_journey": {
        "name": "Elastic Slide Fade",
        "category": "one_click",
        "description": "Teks melompat naik dengan pegas (elastic) sambil fade in — animasi lembut dan hangat.",
        "icon": "fa-solid fa-feather",
        "engine": "fade_slide",
        "demo_text": "Life is a journey",
        "default_duration_ms": 900,
        "curve": _REAL_FALLBACK_CURVE,
        "elastic_note": "Preset asli memakai kurva pegas 'elastic 0.3543933 1.0 0.0 0.6597285'.",
        "params": {"slide_offset_y": 211.5, "fade_in_time": 0.3},
    },
    "oc20_not_my_fault": {
        "name": "Scale Punch Reveal",
        "category": "one_click",
        "description": "Teks terungkap dengan efek 'pukulan' skala membesar dari tengah.",
        "icon": "fa-solid fa-hand-fist",
        "engine": "texttransform",
        "demo_text": "It is not my fault",
        "default_duration_ms": 850,
        "curve": None,
        "params": {"component": 1, "anchor": 1, "offset": None, "overlap": 1.62, "alpha": "-1.000000", "ease_in": "0.0", "ease_out": "0.0", "end_start": 0.0, "end_target": 0.928, "mirror": False, "angle": 0.0, "scale_prop": 1.71},
    },

    # ================================ APPLE (10) ================================ #
    # Sumber: folder Google Drive "Apple" (10 file .xml nama UUID, judul internal
    # "Text Animation 1" s/d "Text Animation 10"). Lihat docstring modul ini untuk
    # penjelasan penyederhanaan shape dekoratif.
    "ap01_defocus_reveal": {
        "name": "Defocus Reveal",
        "category": "apple",
        "description": "Teks masuk dari buram (gaussian blur kuat) menuju fokus tajam — reveal asli dari 'Text Animation 3'.",
        "icon": "fa-solid fa-circle-notch",
        "engine": "blur_pop",
        "demo_text": "Text Here",
        "default_duration_ms": 700,
        "curve": (0.32, 0.0, 0.0, 1.0),
        "note": "Shape mask penyapu & efek blur pada file asli digabung menjadi satu reveal blur langsung pada teks.",
        "params": {"blur_start": 0.525},
    },
    "ap02_soft_blur_pop": {
        "name": "Soft Blur Pop",
        "category": "apple",
        "description": "Variasi defocus yang lebih lembut dengan kurva percepatan landai — dari 'Text Animation 7'.",
        "icon": "fa-solid fa-circle-half-stroke",
        "engine": "blur_pop",
        "demo_text": "Your Text here",
        "default_duration_ms": 650,
        "curve": (0.4357519, 0.0, 0.0, 1.0),
        "note": "Dekorasi lingkaran & garis aksen pada file asli tidak disertakan agar preset tetap fokus pada teks.",
        "params": {"blur_start": 0.455},
    },
    "ap03_slide_settle_down": {
        "name": "Slide Settle Down",
        "category": "apple",
        "description": "Teks meluncur dari atas lalu menetap mulus di posisi akhir — animasi judul bertingkat dari 'Text Animation 5'.",
        "icon": "fa-solid fa-arrow-down-long",
        "engine": "slide_settle",
        "demo_text": "Like a Pro",
        "default_duration_ms": 750,
        "curve": (0.0, 0.28987166, 0.2758527, 1.0),
        "note": "Reveal mask penyapu pada file asli disederhanakan; gerakan <location> tetap memakai nilai & kurva asli.",
        "params": {"slide_offset_y": -179.458008},
    },
    "ap04_pop_scale_soft": {
        "name": "Pop Scale Soft",
        "category": "apple",
        "description": "Teks membesar masuk dengan kurva percepatan khas — dari animasi kotak teks 'Text Animation 2'.",
        "icon": "fa-solid fa-up-right-and-down-left-from-center",
        "engine": "pop",
        "demo_text": "Clean and modern",
        "default_duration_ms": 600,
        "curve": (0.4683649, 0.0, 0.19912732, 1.0),
        "note": "Latar pil (roundrect) & animasi keluar (blur + scroll) pada file asli tidak disertakan.",
        "params": {},
    },
    "ap05_flicker_reveal": {
        "name": "Flicker Reveal",
        "category": "apple",
        "description": "Teks melompat masuk dengan pegas lalu berkedip (flicker) sesaat sebelum stabil — efek 'flicker2' asli dari 'Text Animation 10'.",
        "icon": "fa-solid fa-bolt",
        "engine": "flicker_reveal",
        "demo_text": "SMOOTH",
        "default_duration_ms": 900,
        "curve": _REAL_FALLBACK_CURVE,
        "elastic_note": "Preset asli memakai kurva pegas 'elastic 0.45063996 1.0 0.0 0.15295398' untuk skala masuk.",
        "params": {"freq": 8.139999, "mag_start_frac": 0.038178, "mag_end_frac": 0.171053},
    },
    "ap06_marquee_scroll": {
        "name": "Marquee Scroll",
        "category": "apple",
        "description": "Teks bergulir horizontal melintasi layar dari kanan ke kiri — animasi berjalan dari 'Text Animation 6'.",
        "icon": "fa-solid fa-angles-left",
        "engine": "marquee",
        "demo_text": "Use text animations to make your content stand out",
        "default_duration_ms": 4200,
        "curve": _REAL_FALLBACK_CURVE,
        "elastic_note": "Preset asli memakai kurva pegas 'elastic 0.42520362 1.0 0.0 0.21020746' di setiap titik gulir.",
        "params": {},
    },
    "ap07_stacked_reveal": {
        "name": "Stacked Reveal",
        "category": "apple",
        "description": "Tiap baris teks terungkap dari bawah dengan sedikit efek stretch overshoot — Text Transform asli dari 'Text Animation 8'.",
        "icon": "fa-solid fa-layer-group",
        "engine": "texttransform",
        "demo_text": "Create\nSmooth Text\nAnimation",
        "default_duration_ms": 900,
        "curve": (0.0, 0.5948694, 1.0, 0.40455785),
        "note": "Garis bawah coretan tangan & panah dekoratif pada file asli dipindahkan ke preset terpisah 'Hand-drawn Underline'.",
        "params": {"component": 1, "anchor": 1, "offset": (0.0, -210.0), "overlap": 10.0, "alpha": "-1.000000", "ease_in": "1.0", "ease_out": "-1.0", "end_start": 0.0, "end_target": 1.0, "mirror": False, "angle": 0.0, "scale_prop": 0.0, "stretch_anim": (0.012043, 1.0, 0.029382, 1.5)},
    },
    "ap08_typewriter_caption": {
        "name": "Typewriter Caption",
        "category": "apple",
        "description": "Teks diketik progresif tanpa kursor berkedip, dengan kerapatan huruf direnggangkan — Text Progress + Text Spacing asli dari 'Text Animation 8'.",
        "icon": "fa-solid fa-terminal",
        "engine": "typewriter",
        "demo_text": "Create smooth and professional text animations in Alight Motion.",
        "default_duration_ms": 1800,
        "curve": (0.3761968, 0.0, 0.046700478, 1.0),
        "params": {"cursor": 0, "blink": False, "use_curve": True, "textspacing": (0.09, 1.115)},
    },
    "ap09_handdrawn_underline": {
        "name": "Hand-drawn Underline",
        "category": "apple",
        "description": "Teks membesar lalu garis bawah coretan tangan tergambar progresif — efek 'drawing.progress' + path vektor asli dari 'Text Animation 8'.",
        "icon": "fa-solid fa-pen-nib",
        "engine": "handdrawn_underline",
        "demo_text": "Animation",
        "default_duration_ms": 900,
        "curve": (0.36937612, 0.0, 0.0, 1.0),
        "note": "Path vektor coretan tangan diambil verbatim dari file sumber; posisi & skala disesuaikan otomatis agar pas di bawah teks apa pun.",
        "params": {},
    },
    "ap10_spaced_caption_reveal": {
        "name": "Spaced Caption Reveal",
        "category": "apple",
        "description": "Caption terungkap huruf demi huruf dengan kerapatan huruf direnggangkan (letterspacing) — dari grup caption 'Text Animation 9'.",
        "icon": "fa-solid fa-circle-dot",
        "engine": "texttransform",
        "demo_text": "Create smooth simple text animations in Alight Motion.",
        "default_duration_ms": 1200,
        "curve": (0.0, 0.5948694, 1.0, 0.40455785),
        "note": "Cincin titik berputar & label 'Point 1-4' dekoratif pada file asli tidak disertakan; fokus pada reveal caption.",
        "params": {"component": 1, "anchor": 1, "offset": (0.0, -210.0), "overlap": 10.0, "alpha": "-1.000000", "ease_in": "1.0", "ease_out": "-1.0", "end_start": 0.0, "end_target": 1.0, "mirror": False, "angle": 0.0, "scale_prop": 0.0, "stretch_value": 1.0, "textspacing": (0.09, 1.115)},
    },
}

CATEGORY_LABELS = {
    "hand_crafted": "Hand-Crafted",
    "one_click": "One-Click",
    "apple": "Apple",
}

CURVES = {
    "apple_ease": {"label": "Apple Ease", "x1": 0.25, "y1": 0.1, "x2": 0.25, "y2": 1.0},
    "ease_out_expo": {"label": "Ease Out Expo", "x1": 0.16, "y1": 1.0, "x2": 0.3, "y2": 1.0},
    "spring_soft": {"label": "Spring Soft", "x1": 0.34, "y1": 1.56, "x2": 0.64, "y2": 1.0},
    "ease_in_out": {"label": "Ease In Out", "x1": 0.42, "y1": 0.0, "x2": 0.58, "y2": 1.0},
}

# Nama font nyata di Google Fonts, dipakai lewat skema `googlefonts?name=..&weight=..`
# yang terbukti ada di contoh asli (mis. "googlefonts?name=Open Sans&weight=800").
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


def list_presets_by_category() -> dict:
    """Kelompokkan katalog PRESETS per kategori untuk ditampilkan sebagai tab di UI."""
    grouped: dict = {"hand_crafted": [], "one_click": [], "apple": []}
    for preset_id, preset in PRESETS.items():
        grouped[preset["category"]].append({
            "id": preset_id,
            "name": preset["name"],
            "description": preset["description"],
            "icon": preset["icon"],
            "demo_text": preset["demo_text"],
            "note": preset.get("note") or preset.get("elastic_note"),
        })
    return grouped


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


def _default_curve_tuple(preset: dict) -> tuple:
    return preset.get("curve") or _REAL_FALLBACK_CURVE


def _validate_curve(payload: dict, preset: dict) -> dict:
    curve_id = str(payload.get("curve_id") or "").strip()
    if curve_id and curve_id in CURVES:
        c = CURVES[curve_id]
        return {"x1": c["x1"], "y1": c["y1"], "x2": c["x2"], "y2": c["y2"]}

    custom = payload.get("curve") or {}
    if not custom:
        x1, y1, x2, y2 = _default_curve_tuple(preset)
        return {"x1": x1, "y1": y1, "x2": x2, "y2": y2}

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
    if preset["engine"] == "letter_pop" and len(text.replace("\n", "")) > 24:
        raise ValidationError("Untuk preset Hand-Crafted (per huruf), maksimal 24 karakter agar animasi tetap rapi.")

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

    curve = _validate_curve(payload, preset)

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


def _wrap_width(data: dict) -> int:
    w = data["canvas"]["width"]
    longest_line = max((len(line) for line in data["text"].split("\n")), default=1)
    return max(360, min(w - 120, int(longest_line * data["font_size"] * 0.62) + 80))


# --------------------------------------------------------------------------- #
# Engine "pop": skala 0 -> penuh, kurva cubic-bezier (file One-Click 01/03).
# --------------------------------------------------------------------------- #
def _engine_pop(data: dict, cx: float, cy: float) -> tuple[str, str]:
    dur_s = data["duration_ms"] / 1000.0
    curve_str = _curve_str(data["curve"])
    transform = "\n".join([
        f'      <location value="{cx:.6f},{cy:.6f},0.000000" />',
        "      <scale>",
        _kf(0.0, "0.000000,0.000000"),
        _kf(dur_s, "1.000000,1.000000", curve_str),
        "      </scale>",
    ])
    return transform, ""


# --------------------------------------------------------------------------- #
# Engine "blur_pop": gaussianblur + scale + opacity (file One-Click 05, efek
# blur Alight Motion terbukti nyata di sini).
# --------------------------------------------------------------------------- #
def _engine_blur_pop(data: dict, cx: float, cy: float) -> tuple[str, str]:
    dur_s = data["duration_ms"] / 1000.0
    curve_str = _curve_str(data["curve"])
    blur_start = data["preset"]["params"].get("blur_start", 0.15)
    transform = "\n".join([
        f'      <location value="{cx:.6f},{cy:.6f},0.000000" />',
        "      <scale>",
        _kf(0.0, "0.000000,0.000000"),
        _kf(dur_s, "1.000000,1.000000", curve_str),
        "      </scale>",
        "      <opacity>",
        _kf(0.0, "0.000000"),
        _kf(dur_s, "1.000000", curve_str),
        "      </opacity>",
    ])
    effect = "\n".join([
        '      <effect id="com.alightcreative.effects.gaussianblur" locallyApplied="true">',
        '        <property name="strength" type="float">',
        _kf(0.0, f"{blur_start:.6f}"),
        _kf(dur_s, "0.000000", curve_str),
        "        </property>",
        "      </effect>",
    ])
    return transform, effect


# --------------------------------------------------------------------------- #
# Engine "fade_slide": fade + slide naik (file One-Click 19, kurva asli
# elastic diganti fallback jujur).
# --------------------------------------------------------------------------- #
def _engine_fade_slide(data: dict, cx: float, cy: float) -> tuple[str, str]:
    dur_s = data["duration_ms"] / 1000.0
    curve_str = _curve_str(data["curve"])
    slide_y = data["preset"]["params"].get("slide_offset_y", 200.0)
    fade_in_time = data["preset"]["params"].get("fade_in_time", 0.3)
    transform = "\n".join([
        "      <location>",
        _kf(dur_s, f"{cx:.6f},{cy:.6f},0.000000", curve_str),
        _kf(0.0, f"{cx:.6f},{cy + slide_y:.6f},0.000000"),
        "      </location>",
        "      <opacity>",
        _kf(0.0, "1.000000"),
        "      </opacity>",
    ])
    effect = "\n".join([
        '      <effect id="com.alightcreative.effects.fade" locallyApplied="true">',
        f'        <property name="inTime" type="float" value="{fade_in_time:.6f}" />',
        '        <property name="outTime" type="float" value="0.000000" />',
        "      </effect>",
    ])
    return transform, effect


# --------------------------------------------------------------------------- #
# Engine "wipe": com.alightcreative.effects.wipe2 (file One-Click 04).
# --------------------------------------------------------------------------- #
def _engine_wipe(data: dict, cx: float, cy: float) -> tuple[str, str]:
    dur_s = data["duration_ms"] / 1000.0
    curve_str = _curve_str(data["curve"])
    angle = data["preset"]["params"].get("angle", 0.0)
    feather = data["preset"]["params"].get("feather", 44.1)
    transform = f'      <location value="{cx:.6f},{cy:.6f},0.000000" />'
    effect = "\n".join([
        '      <effect id="com.alightcreative.effects.wipe2" locallyApplied="true">',
        '        <property name="start" type="float" value="0.000000" />',
        '        <property name="end" type="float">',
        _kf(0.0, "-0.433000"),
        _kf(dur_s, "0.932000", curve_str),
        "        </property>",
        f'        <property name="angle" type="float" value="{angle:.6f}" />',
        f'        <property name="feather" type="float" value="{feather:.6f}" />',
        "      </effect>",
    ])
    return transform, effect


# --------------------------------------------------------------------------- #
# Engine "typewriter": com.alightcreative.effects.textprogress (file One-Click 14).
# --------------------------------------------------------------------------- #
def _engine_typewriter(data: dict, cx: float, cy: float) -> tuple[str, str]:
    dur_s = data["duration_ms"] / 1000.0
    p = data["preset"]["params"]
    cursor = p.get("cursor", 5)
    blink = "true" if p.get("blink", True) else "false"
    transform = f'      <location value="{cx:.6f},{cy:.6f},0.000000" />'
    # Preset oc14 asli tidak memakai kurva cubic-bezier pada kf "end" (linear).
    # Preset Apple baru (dengan use_curve=True) memakai kurva asli file sumber.
    end_kf_final = _kf(dur_s, "1.000000", _curve_str(data["curve"])) if p.get("use_curve") else _kf(dur_s, "1.000000")
    effect_lines = [
        '      <effect id="com.alightcreative.effects.textprogress" locallyApplied="true">',
        '        <property name="start" type="float" value="0.000000" />',
        '        <property name="end" type="float">',
        _kf(0.0, "0.000000"),
        end_kf_final,
        "        </property>",
        f'        <property name="cursor" type="int" value="{cursor}" />',
        f'        <property name="blink" type="bool" value="{blink}" />',
        "      </effect>",
    ]
    textspacing = p.get("textspacing")
    if textspacing:
        ls, lns = textspacing
        effect_lines = [
            '      <effect id="com.alightcreative.effects.textspacing" locallyApplied="true">',
            f'        <property name="letterspacing" type="float" value="{ls:.6f}" />',
            f'        <property name="linespacing" type="float" value="{lns:.6f}" />',
            "      </effect>",
        ] + effect_lines
    return transform, "\n".join(effect_lines)


# --------------------------------------------------------------------------- #
# Engine "distort": pinchbulge2 + zoomblur3 (file One-Click 15).
# --------------------------------------------------------------------------- #
def _engine_distort(data: dict, cx: float, cy: float) -> tuple[str, str]:
    dur_s = data["duration_ms"] / 1000.0
    curve_str = _curve_str(data["curve"])
    p = data["preset"]["params"]
    transform = "\n".join([
        f'      <location value="{cx:.6f},{cy:.6f},0.000000" />',
        "      <opacity>",
        _kf(dur_s * 0.25, "1.000000"),
        _kf(0.0, "0.000000"),
        "      </opacity>",
    ])
    effect = "\n".join([
        '      <effect id="com.alightcreative.effects.pinchbulge2" locallyApplied="true">',
        '        <property name="strength" type="float">',
        _kf(0.0, f"{p.get('pinch_strength', 0.64):.6f}"),
        _kf(dur_s, "0.000000", curve_str),
        "        </property>",
        f'        <property name="radius" type="float" value="{p.get("pinch_radius", 0.67):.6f}" />',
        "      </effect>",
        '      <effect id="com.alightcreative.effects.zoomblur3" locallyApplied="true">',
        '        <property name="strength" type="float">',
        _kf(dur_s, "0.000000", curve_str),
        _kf(0.0, f"{p.get('zoom_strength', 0.33):.6f}"),
        "        </property>",
        '        <property name="adaptive" type="bool" value="true" />',
        "      </effect>",
    ])
    return transform, effect


# --------------------------------------------------------------------------- #
# Engine "mask_slide": com.alightcreative.effects.offset + kotak mask (file
# One-Click 12).
# --------------------------------------------------------------------------- #
def _engine_mask_slide(data: dict, cx: float, cy: float) -> tuple[str, str]:
    dur_s = data["duration_ms"] / 1000.0
    curve_str = _curve_str(data["curve"])
    p = data["preset"]["params"]
    slide_from_x = p.get("slide_from_x", -1000.0)
    transform = "\n".join([
        "      <location>",
        _kf(dur_s, f"{cx:.6f},{cy:.6f},0.000000", curve_str),
        _kf(0.0, f"{cx + slide_from_x:.6f},{cy:.6f},0.000000"),
        "      </location>",
    ])
    effect = "\n".join([
        '      <effect id="com.alightcreative.effects.offset" locallyApplied="true">',
        '        <property name="feather" type="float" value="0.000000" />',
        '        <property name="mask" type="bool" value="false" />',
        "      </effect>",
    ])
    return transform, effect


# --------------------------------------------------------------------------- #
# Engine "texttransform": efek bawaan paling sering dipakai di 12 preset
# One-Click (reveal kata/huruf/mirror/diagonal). Parameternya persis sama
# dengan struktur properti com.alightcreative.effects.texttransform di file
# sumber: start/end/phase/component/anchor/offset/angle/scale/stretch/
# alpha/useFillColor/fillColor/easeIn/easeOut/overlap/shape/randomOrder/seed.
# --------------------------------------------------------------------------- #
def _engine_texttransform(data: dict, cx: float, cy: float) -> tuple[str, str]:
    dur_s = data["duration_ms"] / 1000.0
    p = data["preset"]["params"]
    curve = data["curve"]
    curve_str = _curve_str(curve)

    transform_lines = [f'      <location value="{cx:.6f},{cy:.6f},0.000000" />']
    slide_from = p.get("slide_from")
    if slide_from:
        slide_curve = p.get("slide_curve")
        slide_curve_str = _curve_str({"x1": slide_curve[0], "y1": slide_curve[1], "x2": slide_curve[2], "y2": slide_curve[3]}) if slide_curve else curve_str
        dx, dy = slide_from
        transform_lines = [
            "      <location>",
            _kf(dur_s, f"{cx:.6f},{cy:.6f},0.000000", slide_curve_str),
            _kf(0.0, f"{cx + dx:.6f},{cy + dy:.6f},0.000000"),
            "      </location>",
        ]
    transform = "\n".join(transform_lines)

    end_start = p.get("end_start", 0.0)
    end_target = p.get("end_target", 1.0)
    end_block = "\n".join([
        '        <property name="end" type="float">',
        _kf(0.0, f"{end_start:.6f}"),
        _kf(dur_s, f"{end_target:.6f}", curve_str),
        "        </property>",
    ])

    offset = p.get("offset")
    if offset is None:
        offset_block = '        <property name="offset" type="vec2" value="0.000000,0.000000" />'
    elif p.get("offset_animated"):
        offset_block = "\n".join([
            '        <property name="offset" type="vec2">',
            _kf(dur_s, "0.000000,0.000000"),
            _kf(0.0, f"{offset[0]:.6f},{offset[1]:.6f}"),
            "        </property>",
        ])
    else:
        offset_block = f'        <property name="offset" type="vec2" value="{offset[0]:.6f},{offset[1]:.6f}" />'

    random_order = "true" if p.get("random_order") else "false"
    seed = p.get("seed", 0.0)

    stretch_anim = p.get("stretch_anim")
    if stretch_anim:
        t1f, v1, t2f, v2 = stretch_anim
        pts = sorted([(t1f, v1), (t2f, v2)], key=lambda item: item[0])
        stretch_block = "\n".join([
            '        <property name="stretch" type="float">',
            _kf(pts[0][0] * dur_s, f"{pts[0][1]:.6f}"),
            _kf(pts[1][0] * dur_s, f"{pts[1][1]:.6f}"),
            "        </property>",
        ])
    else:
        stretch_block = f'        <property name="stretch" type="float" value="{p.get("stretch_value", 0.0):.6f}" />'

    effect_lines = [
        '      <effect id="com.alightcreative.effects.texttransform" locallyApplied="true">',
        '        <property name="start" type="float" value="0.000000" />',
        end_block,
        '        <property name="phase" type="float" value="0.000000" />',
        f'        <property name="component" type="int" value="{p.get("component", 1)}" />',
        f'        <property name="anchor" type="int" value="{p.get("anchor", 0)}" />',
        offset_block,
        f'        <property name="angle" type="float" value="{p.get("angle", 0.0):.6f}" />',
        f'        <property name="scale" type="float" value="{p.get("scale_prop", 0.0):.6f}" />',
        stretch_block,
        f'        <property name="alpha" type="float" value="{p.get("alpha", "0.000000")}" />',
        '        <property name="useFillColor" type="bool" value="false" />',
        '        <property name="fillColor" type="color" value="#ff00ff00" />',
        f'        <property name="easeIn" type="float" value="{p.get("ease_in", "0.0")}" />',
        f'        <property name="easeOut" type="float" value="{p.get("ease_out", "0.0")}" />',
        f'        <property name="overlap" type="float" value="{p.get("overlap", 0.0):.6f}" />',
        '        <property name="shape" type="int" value="0" />',
        f'        <property name="randomOrder" type="bool" value="{random_order}" />',
        f'        <property name="seed" type="float" value="{seed:.6f}" />',
        "      </effect>",
    ]

    letterspacing_curve = p.get("letterspacing_curve")
    if letterspacing_curve:
        ls_curve_str = _curve_str({"x1": letterspacing_curve[0], "y1": letterspacing_curve[1], "x2": letterspacing_curve[2], "y2": letterspacing_curve[3]})
        effect_lines.extend([
            '      <effect id="com.alightcreative.effects.textspacing" locallyApplied="true">',
            '        <property name="letterspacing" type="float">',
            _kf(0.0, "0.400000"),
            _kf(dur_s, "0.000000", ls_curve_str),
            "        </property>",
            '        <property name="linespacing" type="float" value="1.000000" />',
            "      </effect>",
        ])

    textspacing_static = p.get("textspacing")
    if textspacing_static:
        ls, lns = textspacing_static
        effect_lines.extend([
            '      <effect id="com.alightcreative.effects.textspacing" locallyApplied="true">',
            f'        <property name="letterspacing" type="float" value="{ls:.6f}" />',
            f'        <property name="linespacing" type="float" value="{lns:.6f}" />',
            "      </effect>",
        ])

    return transform, "\n".join(effect_lines)


# --------------------------------------------------------------------------- #
# Engine "slide_settle": teks meluncur vertikal lalu menetap di posisi akhir —
# dipakai di preset Apple yang sumbernya memakai reveal mask terpisah untuk
# teks (bagian mask disederhanakan di sini, gerakan <location> tetap memakai
# nilai & kurva asli dari file sumber "Text Animation 5").
# --------------------------------------------------------------------------- #
def _engine_slide_settle(data: dict, cx: float, cy: float) -> tuple[str, str]:
    dur_s = data["duration_ms"] / 1000.0
    curve_str = _curve_str(data["curve"])
    slide_y = data["preset"]["params"].get("slide_offset_y", -180.0)
    transform = "\n".join([
        "      <location>",
        _kf(dur_s, f"{cx:.6f},{cy:.6f},0.000000", curve_str),
        _kf(0.0, f"{cx:.6f},{cy + slide_y:.6f},0.000000"),
        "      </location>",
    ])
    return transform, ""


# --------------------------------------------------------------------------- #
# Engine "flicker_reveal": skala masuk + com.alightcreative.effects.flicker2
# (freq/mag) — efek "kedip" asli terbukti dipakai langsung pada layer teks di
# file sumber Apple "Text Animation 10" (frekuensi & rentang waktu mag persis
# nilai asli).
# --------------------------------------------------------------------------- #
def _engine_flicker_reveal(data: dict, cx: float, cy: float) -> tuple[str, str]:
    dur_s = data["duration_ms"] / 1000.0
    curve_str = _curve_str(data["curve"])
    p = data["preset"]["params"]
    freq = p.get("freq", 8.139999)
    mag_start_frac = p.get("mag_start_frac", 0.038178)
    mag_end_frac = p.get("mag_end_frac", 0.171053)
    transform = "\n".join([
        f'      <location value="{cx:.6f},{cy:.6f},0.000000" />',
        "      <scale>",
        _kf(0.0, "0.000000,0.000000"),
        _kf(dur_s, "1.000000,1.000000", curve_str),
        "      </scale>",
    ])
    effect = "\n".join([
        '      <effect id="com.alightcreative.effects.flicker2" locallyApplied="true">',
        f'        <property name="freq" type="float" value="{freq:.6f}" />',
        '        <property name="mag" type="float">',
        _kf(dur_s * mag_start_frac, "1.000000"),
        _kf(dur_s * mag_end_frac, "0.000000"),
        "        </property>",
        '        <property name="seed" type="float" value="0.000000" />',
        '        <property name="basis" type="int" value="0" />',
        "      </effect>",
    ])
    return transform, effect


# --------------------------------------------------------------------------- #
# Engine "marquee": teks bergulir horizontal melewati 11 titik <kf> — posisi
# relatif & urutan waktu persis file sumber Apple "Text Animation 6" (nilai x
# diskalakan proporsional terhadap lebar kanvas 1920 aslinya).
# --------------------------------------------------------------------------- #
_MARQUEE_KEYFRAMES = (
    (0.003101, 2001.783936),
    (0.100008, 1427.994873),
    (0.196682, 1139.744873),
    (0.293821, 659.166748),
    (0.390728, 239.816162),
    (0.481278, 0.000000),
    (0.578107, -319.135742),
    (0.681448, -714.244141),
    (0.778355, -1154.336914),
    (0.875262, -1431.478516),
    (0.972168, -2069.395508),
)
_MARQUEE_SOURCE_WIDTH = 1920.0


def _engine_marquee(data: dict, cx: float, cy: float) -> tuple[str, str]:
    dur_s = data["duration_ms"] / 1000.0
    curve_str = _curve_str(data["curve"])
    width_ratio = data["canvas"]["width"] / _MARQUEE_SOURCE_WIDTH
    lines = ["      <location>"]
    for t_frac, x_offset in _MARQUEE_KEYFRAMES:
        x = cx + x_offset * width_ratio
        lines.append(_kf(t_frac * dur_s, f"{x:.6f},{cy:.6f},0.000000", curve_str))
    lines.append("      </location>")
    return "\n".join(lines), ""


# --------------------------------------------------------------------------- #
# Engine "handdrawn_underline": teks pop-in + shape garis-bawah coretan tangan
# memakai <path-stroke>/<path> dan efek com.alightcreative.effects.drawing.
# progress — path vektor diambil VERBATIM dari shape "underline" file sumber
# Apple "Text Animation 8" (hanya transform lokasi/skala yang disesuaikan
# otomatis agar pas di bawah teks apa pun).
# --------------------------------------------------------------------------- #
_UNDERLINE_PATH_D = (
    "M 662.40485 -239.72884C 546.17175 -308.91995, 278.52103 -318.61603, "
    "258.92902 -227.34421C 239.33702 -136.07239, 415.25797 -126.639046, "
    "462.74255 -127.75764C 510.22714 -128.87622, 710.4639 -139.09311, "
    "631.37067 -239.72594C 552.2774 -340.35876, 778.63794 -170.53772, "
    "662.40485 -239.72884"
)
_UNDERLINE_BBOX = {"min_x": 239.33702, "max_x": 778.63794, "min_y": -340.35876, "max_y": -126.639046}


def _engine_handdrawn_underline(data: dict, cx: float, cy: float) -> tuple[str, str, str]:
    dur_s = data["duration_ms"] / 1000.0
    curve_str = _curve_str(data["curve"])

    transform = "\n".join([
        f'      <location value="{cx:.6f},{cy:.6f},0.000000" />',
        "      <scale>",
        _kf(0.0, "0.000000,0.000000"),
        _kf(dur_s * 0.5, "1.000000,1.000000", curve_str),
        "      </scale>",
    ])

    bb = _UNDERLINE_BBOX
    path_w = bb["max_x"] - bb["min_x"]
    path_h = bb["max_y"] - bb["min_y"]
    path_cx = (bb["min_x"] + bb["max_x"]) / 2.0
    path_cy = (bb["min_y"] + bb["max_y"]) / 2.0
    target_w = max(180.0, min(_wrap_width(data) * 0.55, 420.0))
    scale_x = target_w / path_w
    scale_y = scale_x * 0.42
    loc_x = cx - path_cx * scale_x
    loc_y = (cy + data["font_size"] * 0.95) - path_cy * scale_y

    underline = "\n".join([
        f'  <shape id="102" label="FYY Teks Creator - garis bawah" startTime="{int(dur_s * 300)}" '
        f'endTime="{data["duration_ms"]}" fillType="none" mediaFillMode="fill">',
        '    <transform lockAspectRatio="false">',
        f'      <location value="{loc_x:.6f},{loc_y:.6f},0.000000" />',
        f'      <scale value="{scale_x:.6f},{scale_y:.6f}" />',
        "    </transform>",
        f'    <fillColor value="#ff{data["color_hex"]}" />',
        '    <effect id="com.alightcreative.effects.drawing.progress" locallyApplied="true">',
        '      <property name="start" type="float" value="0.000000" />',
        '      <property name="end" type="float">',
        _kf(dur_s * 0.35, "0.000000"),
        _kf(dur_s, "100.000000", curve_str),
        "      </property>",
        "    </effect>",
        f'    <path-stroke direction="centered" end-size="1.500000"><color value="#ff{data["color_hex"]}" />'
        '<size value="5.500000" /></path-stroke>',
        f'    <path d="{_UNDERLINE_PATH_D}" />',
        "  </shape>",
    ])
    return transform, "", underline


_ENGINES = {
    "pop": _engine_pop,
    "blur_pop": _engine_blur_pop,
    "fade_slide": _engine_fade_slide,
    "wipe": _engine_wipe,
    "typewriter": _engine_typewriter,
    "distort": _engine_distort,
    "mask_slide": _engine_mask_slide,
    "texttransform": _engine_texttransform,
    "slide_settle": _engine_slide_settle,
    "flicker_reveal": _engine_flicker_reveal,
    "marquee": _engine_marquee,
    "handdrawn_underline": _engine_handdrawn_underline,
}


def _build_single_layer_xml(data: dict) -> str:
    w, h = data["canvas"]["width"], data["canvas"]["height"]
    cx, cy = w / 2.0, h / 2.0
    font_attr = _font_attr(data["font_family"], data["weight"])
    wrap_width = _wrap_width(data)
    engine_fn = _ENGINES[data["preset"]["engine"]]
    engine_result = engine_fn(data, cx, cy)
    if len(engine_result) == 3:
        transform_xml, effect_xml, extra_xml = engine_result
    else:
        transform_xml, effect_xml = engine_result
        extra_xml = ""

    lines = [
        f'  <text id="101" label="FYY Teks Creator - {esc_attr(data["preset"]["name"])}" '
        f'startTime="0" endTime="{data["duration_ms"]}" fillType="color" mediaFillMode="fill" '
        f'size="{data["font_size"]:.6f}" font="{esc_attr(font_attr)}" wrapWidth="{wrap_width}" '
        f'align="{data["align"]}">',
        "    <transform>",
        transform_xml,
        "    </transform>",
        f'    <fillColor value="#ff{data["color_hex"]}" />',
    ]
    if effect_xml:
        lines.append(effect_xml)
    lines.append(f"    <content>{esc_text(data['text'])}</content>")
    lines.append("  </text>")
    text_block = "\n".join(lines)
    if extra_xml:
        return text_block + "\n" + extra_xml
    return text_block


# --------------------------------------------------------------------------- #
# Engine "letter_pop": 1 <text> per huruf, dipakai untuk 10 preset Hand-
# Crafted. Setiap huruf mendapat <scale> (0 -> 1) dan opsional <rotation>
# dengan kurva/sudut rotasi ASLI dari file sumber, serta stagger (jeda antar
# huruf) juga memakai nilai milidetik asli dari file sumber.
# --------------------------------------------------------------------------- #
def _build_letter_layers_xml(data: dict) -> str:
    w, h = data["canvas"]["width"], data["canvas"]["height"]
    cx, cy = w / 2.0, h / 2.0
    font_attr = _font_attr(data["font_family"], data["weight"])
    curve_str = _curve_str(data["curve"])
    params = data["preset"]["params"]
    stagger_ms = params.get("stagger_ms", 100)
    rotation_deg = params.get("rotation_deg", 0.0)
    slide_offset_y = params.get("slide_offset_y")
    slide_offset_x = params.get("slide_offset_x")

    letters = [ch for ch in data["text"] if ch != "\n"]
    if not letters:
        letters = [data["text"]]
    n = len(letters)
    char_w = max(data["font_size"] * 0.72, 24.0)
    total_w = char_w * n
    start_x = cx - total_w / 2.0 + char_w / 2.0

    pop_duration_s = max(0.35, data["duration_ms"] / 1000.0 * 0.55)
    layer_duration_ms = data["duration_ms"] + stagger_ms * max(0, n - 1)

    layers = []
    for idx, ch in enumerate(letters):
        start_ms = idx * stagger_ms
        end_ms = layer_duration_ms
        lx = start_x + idx * char_w

        transform_lines = []
        if slide_offset_y:
            transform_lines.append("      <location>")
            transform_lines.append(_kf(pop_duration_s, f"{lx:.6f},{cy:.6f},0.000000", curve_str))
            transform_lines.append(_kf(0.0, f"{lx:.6f},{cy + slide_offset_y:.6f},0.000000"))
            transform_lines.append("      </location>")
        elif slide_offset_x:
            transform_lines.append("      <location>")
            transform_lines.append(_kf(pop_duration_s, f"{lx:.6f},{cy:.6f},0.000000", curve_str))
            transform_lines.append(_kf(0.0, f"{lx + slide_offset_x:.6f},{cy:.6f},0.000000"))
            transform_lines.append("      </location>")
        else:
            transform_lines.append(f'      <location value="{lx:.6f},{cy:.6f},0.000000" />')

        transform_lines.append("      <scale>")
        transform_lines.append(_kf(pop_duration_s, "1.000000,1.000000", curve_str))
        transform_lines.append(_kf(0.0, "0.000000,0.000000"))
        transform_lines.append("      </scale>")

        if rotation_deg:
            transform_lines.append("      <rotation>")
            transform_lines.append(_kf(pop_duration_s, "0.000000", curve_str))
            transform_lines.append(_kf(0.0, f"{rotation_deg:.6f}"))
            transform_lines.append("      </rotation>")

        layer = "\n".join([
            f'  <text id="{101 + idx}" label="FYY Teks Creator huruf {idx + 1}" '
            f'startTime="{start_ms}" endTime="{end_ms}" fillType="color" mediaFillMode="fill" '
            f'size="{data["font_size"]:.6f}" font="{esc_attr(font_attr)}" wrapWidth="200" align="center">',
            "    <transform>",
            "\n".join(transform_lines),
            "    </transform>",
            f'    <fillColor value="#ff{data["color_hex"]}" />',
            f"    <content>{esc_text(ch)}</content>",
            "  </text>",
        ])
        layers.append(layer)

    return "\n".join(layers), layer_duration_ms


def build_text_scene_xml(payload: dict) -> tuple[str, str]:
    """Validasi payload, bangun XML scene Alight Motion, lalu kembalikan (xml_text, filename).

    Raises ValidationError bila input tidak valid. Hasil XML selalu diparse ulang
    dengan xml.etree.ElementTree sebelum dikembalikan untuk memastikan well-formed.
    """
    data = _validate_payload(payload)
    w, h = data["canvas"]["width"], data["canvas"]["height"]
    now_ms = int(time.time() * 1000)
    title = f"{data['preset']['name']} - {data['text'][:30]}"

    if data["preset"]["engine"] == "letter_pop":
        body_xml, total_ms = _build_letter_layers_xml(data)
    else:
        body_xml = _build_single_layer_xml(data)
        total_ms = data["duration_ms"]

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
        # Harusnya tidak pernah terjadi karena semua nilai sudah di-escape,
        # tapi jaga-jaga supaya tidak pernah mengirim XML rusak ke pengguna.
        raise ValidationError(f"Gagal membuat XML yang valid: {exc}") from exc

    safe_preset = data["preset_id"].replace("_", "-")
    filename = f"fyymotion-teks-{safe_preset}-{now_ms}.xml"
    return xml_text, filename
