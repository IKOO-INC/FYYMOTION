"""
FYY MOTION — Portal Manajemen Order & Keuangan Jasa Animasi Motion Graphic
===========================================================================
- Backend  : Python Flask (single file, siap deploy Vercel)
- Database : MongoDB Atlas (utama, via MONGODB_URI) + JSON fallback/seed
- Backup   : Download / Upload file JSON (Backup & Restore)
- Akuntansi: Jurnal Umum (double-entry) -> Buku Besar -> Neraca Saldo -> Laba Rugi

CATATAN PENYIMPANAN:
Bila MONGODB_URI terpasang, data disimpan permanen di MongoDB Atlas pada
koleksi accounts, orders, transactions, dan app_state. Bila URI belum ada
atau koneksi MongoDB sedang gagal, aplikasi memakai JSON fallback agar tetap
bisa dibuka: file lokal database.json, atau /tmp/fyymotion_database.json di
Vercel. File /tmp bersifat sementara, jadi pasang MONGODB_URI untuk produksi
dan tetap download backup JSON sebagai arsip offline secara berkala.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import secrets
import shutil
import threading
import uuid
from copy import deepcopy
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path
from urllib.parse import quote, urlparse

from flask import (
    Flask, Response, abort, flash, g, redirect, render_template,
    request, send_file, session, url_for,
)

from alight_presets import (
    CANVAS_PRESETS,
    CATEGORY_LABELS,
    CURVES,
    FONTS,
    PRESETS,
    ValidationError,
    build_text_scene_xml,
    list_presets_by_category,
)
from text_fx import (
    TEXT_FX_MAPPINGS,
    TEXT_FX_MODES,
    build_text_fx_xml,
    list_text_fx_styles,
)

# --------------------------------------------------------------------------- #
# Konfigurasi dasar
# --------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).resolve().parent
SEED_PATH = BASE_DIR / "database.json"

if os.environ.get("DATABASE_PATH"):
    DB_PATH = Path(os.environ["DATABASE_PATH"])
elif os.environ.get("VERCEL"):
    DB_PATH = Path("/tmp/fyymotion_database.json")
else:
    DB_PATH = SEED_PATH

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "fyymotion123")

# MongoDB Atlas adalah penyimpanan utama bila URI tersedia. Jangan pernah
# menaruh connection string asli di repo; pasang melalui Environment Variables.
MONGODB_URI = os.environ.get("MONGODB_URI", "").strip()
MONGODB_DB_NAME = os.environ.get("MONGODB_DB_NAME", "").strip()

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "fyymotion-secret-key-ganti-di-production"),
    MAX_CONTENT_LENGTH=8 * 1024 * 1024,  # upload backup maks 8 MB
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
)

_DB_LOCK = threading.Lock()
_MONGO_CLIENT = None
_MONGO_DB = None
_MONGO_READY = False
_MONGO_INIT_LOCK = threading.Lock()

# --------------------------------------------------------------------------- #
# Konstanta domain
# --------------------------------------------------------------------------- #
STATUS_ORDER = [
    ("masuk", "Order Masuk", "primary"),
    ("antri", "Dalam Antrian", "secondary"),
    ("proses", "Sedang Diproses", "warning"),
    ("revisi", "Minta Revisi", "danger"),
    ("selesai", "Selesai / Sudah Jadi", "success"),
    ("batal", "Batal", "dark"),
]
STATUS_LABEL = {k: v for k, v, _ in STATUS_ORDER}
STATUS_BADGE = {k: c for k, _, c in STATUS_ORDER}
STATUS_AKTIF = ["masuk", "antri", "proses", "revisi"]

STATUS_PEMBAYARAN = [
    ("belum", "Belum Bayar", "danger"),
    ("dp", "DP / Sebagian", "warning"),
    ("lunas", "Lunas", "success"),
]
PAY_LABEL = {k: v for k, v, _ in STATUS_PEMBAYARAN}
PAY_BADGE = {k: c for k, _, c in STATUS_PEMBAYARAN}

JENIS_ANIMASI = [
    "Motion Graphic", "Explainer Video", "Logo Animation", "Iklan / Ads",
    "Video Lirik / Lyric", "Animasi Sosmed", "Intro / Outro Youtube",
    "Presentasi Animasi", "Whiteboard Animation", "Lainnya",
]
PRIORITAS = ["Normal", "Prioritas", "Urgent / Express"]
METODE_BAYAR = ["Transfer Bank", "DANA", "OVO", "GoPay", "QRIS", "Tunai", "PayPal", "Lainnya"]
TIPE_AKUN = ["Aset", "Kewajiban", "Modal", "Pendapatan", "Beban"]

# Preset jenis transaksi -> (Debit, Kredit) untuk memudahkan input
JENIS_TRANSAKSI = [
    ("pemasukan_order", "Pemasukan — Pembayaran Order (Lunas)", "101", "401"),
    ("dp_order", "Pemasukan — DP Order dari Client", "101", "202"),
    ("pemasukan_lain", "Pemasukan — Pendapatan Lainnya", "101", "402"),
    ("beban_software", "Pengeluaran — Software & Langganan", "501", "101"),
    ("beban_internet", "Pengeluaran — Internet & Listrik", "502", "101"),
    ("beban_freelancer", "Pengeluaran — Bayar Freelancer / Outsourcing", "503", "101"),
    ("beban_iklan", "Pengeluaran — Iklan & Promosi", "504", "101"),
    ("beban_lain", "Pengeluaran — Beban Lainnya", "505", "101"),
    ("modal_masuk", "Modal — Setoran Modal Pemilik", "101", "301"),
    ("prive", "Modal — Prive / Ambil Pribadi", "302", "101"),
    ("beli_peralatan", "Aset — Beli Peralatan (Laptop, dll)", "104", "101"),
    ("manual", "Jurnal Manual (pilih akun sendiri)", "", ""),
]
JENIS_LABEL = {k: v for k, v, _, _ in JENIS_TRANSAKSI}
JENIS_PRESET = {k: (d, kr) for k, _, d, kr in JENIS_TRANSAKSI}

DEFAULT_ACCOUNTS = [
    {"kode": "101", "nama": "Kas", "tipe": "Aset", "saldo_normal": "Debit", "is_cash": True},
    {"kode": "102", "nama": "Bank / E-Wallet", "tipe": "Aset", "saldo_normal": "Debit", "is_cash": True},
    {"kode": "103", "nama": "Piutang Usaha", "tipe": "Aset", "saldo_normal": "Debit", "is_cash": False},
    {"kode": "104", "nama": "Peralatan (Laptop/PC, dll)", "tipe": "Aset", "saldo_normal": "Debit", "is_cash": False},
    {"kode": "105", "nama": "Perlengkapan & Aset Digital", "tipe": "Aset", "saldo_normal": "Debit", "is_cash": False},
    {"kode": "201", "nama": "Utang Usaha", "tipe": "Kewajiban", "saldo_normal": "Kredit", "is_cash": False},
    {"kode": "202", "nama": "Pendapatan Diterima di Muka (DP Client)", "tipe": "Kewajiban", "saldo_normal": "Kredit", "is_cash": False},
    {"kode": "301", "nama": "Modal Pemilik", "tipe": "Modal", "saldo_normal": "Kredit", "is_cash": False},
    {"kode": "302", "nama": "Prive Pemilik", "tipe": "Modal", "saldo_normal": "Debit", "is_cash": False},
    {"kode": "401", "nama": "Pendapatan Jasa Animasi", "tipe": "Pendapatan", "saldo_normal": "Kredit", "is_cash": False},
    {"kode": "402", "nama": "Pendapatan Lainnya", "tipe": "Pendapatan", "saldo_normal": "Kredit", "is_cash": False},
    {"kode": "501", "nama": "Beban Software & Langganan", "tipe": "Beban", "saldo_normal": "Debit", "is_cash": False},
    {"kode": "502", "nama": "Beban Internet & Listrik", "tipe": "Beban", "saldo_normal": "Debit", "is_cash": False},
    {"kode": "503", "nama": "Beban Freelancer / Outsourcing", "tipe": "Beban", "saldo_normal": "Debit", "is_cash": False},
    {"kode": "504", "nama": "Beban Iklan & Promosi", "tipe": "Beban", "saldo_normal": "Debit", "is_cash": False},
    {"kode": "505", "nama": "Beban Lainnya", "tipe": "Beban", "saldo_normal": "Debit", "is_cash": False},
]

BULAN_ID = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
            "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
BULAN_SINGKAT = ["", "Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


# --------------------------------------------------------------------------- #
# Database JSON — load / save / validasi
# --------------------------------------------------------------------------- #
def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def today_str() -> str:
    return date.today().isoformat()


PROFILE_STRING_FIELDS = {
    "nav_cta_label": 60,
    "hero_badge": 140,
    "hero_title_prefix": 90,
    "hero_title_accent": 90,
    "hero_title_suffix": 140,
    "hero_subtitle": 900,
    "hero_primary_label": 80,
    "hero_primary_url": 600,
    "hero_secondary_label": 80,
    "hero_secondary_url": 600,
    "hero_note": 300,
    "hero_image_url": 600,
    "showreel_label": 80,
    "showreel_title": 180,
    "showreel_text": 900,
    "showreel_url": 600,
    "trusted_label": 120,
    "about_eyebrow": 100,
    "about_title": 220,
    "about_text": 1600,
    "works_eyebrow": 100,
    "works_title": 220,
    "works_text": 900,
    "services_eyebrow": 100,
    "services_title": 220,
    "services_text": 900,
    "process_eyebrow": 100,
    "process_title": 220,
    "process_text": 900,
    "testimonial_eyebrow": 100,
    "testimonial_title": 220,
    "cta_title": 260,
    "cta_text": 1000,
    "cta_label": 80,
    "cta_url": 600,
    "email": 160,
    "location": 180,
    "instagram_url": 600,
    "youtube_url": 600,
    "behance_url": 600,
    "footer_text": 500,
}

PROFILE_REQUIRED_FIELDS = {
    "nav_cta_label", "hero_badge", "hero_title_prefix", "hero_title_accent",
    "hero_title_suffix", "hero_subtitle", "hero_primary_label", "hero_secondary_label",
    "hero_note", "showreel_label", "showreel_title", "showreel_text", "trusted_label",
    "about_eyebrow", "about_title", "about_text", "works_eyebrow", "works_title",
    "works_text", "services_eyebrow", "services_title", "services_text",
    "process_eyebrow", "process_title", "process_text", "testimonial_eyebrow",
    "testimonial_title", "cta_title", "cta_text", "cta_label", "footer_text",
}


def default_profile() -> dict:
    """Teks awal halaman profil publik. Semua isi dapat diganti dari admin."""
    return {
        "nav_cta_label": "Mulai Project",
        "hero_badge": "Partner motion graphic untuk brand & startup",
        "hero_title_prefix": "Motion",
        "hero_title_accent": "Graphic",
        "hero_title_suffix": "Partner untuk Brand & Startup",
        "hero_subtitle": (
            "Lewati proses produksi yang ribet. Bekerja langsung dengan FYY MOTION untuk "
            "membuat explainer, iklan, logo animation, dan konten motion yang tajam, rapi, "
            "dan siap membantu brand Anda tampil lebih meyakinkan."
        ),
        "hero_primary_label": "Konsultasi Gratis",
        "hero_primary_url": "",
        "hero_secondary_label": "Lihat Portofolio",
        "hero_secondary_url": "#works",
        "hero_note": "Garansi revisi sesuai paket  •  Update progress jelas  •  File final rapi",
        "hero_image_url": "",
        "showreel_label": "Showreel FYY MOTION",
        "showreel_title": "Top-tier motion at startup speed",
        "showreel_text": (
            "Dari brief sederhana sampai video final: konsep visual, storyboard/scene plan, "
            "animasi, sound direction, revisi, dan delivery dikelola dalam satu alur yang jelas."
        ),
        "showreel_url": "",
        "trusted_label": "Layanan motion yang paling sering dipesan",
        "about_eyebrow": "Kenapa FYY MOTION?",
        "about_title": "Motion berkualitas agency, proses tetap ringan",
        "about_text": (
            "FYY MOTION membantu brand, UMKM, creator, dan startup mengubah pesan yang kompleks "
            "menjadi visual bergerak yang mudah dipahami. Setiap project masuk antrian produksi, "
            "memiliki progress yang dapat dipantau, dan dikerjakan dengan arahan visual yang konsisten."
        ),
        "works_eyebrow": "Recent motion work",
        "works_title": "Portofolio pilihan",
        "works_text": "Contoh kategori project yang dapat dikerjakan. Ganti judul, gambar, dan link video dari ruang admin.",
        "services_eyebrow": "Services",
        "services_title": "Semua kebutuhan motion dalam satu partner",
        "services_text": "Pilih satu video untuk campaign berikutnya atau jadikan FYY MOTION partner produksi konten rutin.",
        "process_eyebrow": "How it works",
        "process_title": "Proses simpel, progress selalu jelas",
        "process_text": "Tidak perlu menebak project sudah sampai mana. Setiap tahap memiliki output yang jelas.",
        "testimonial_eyebrow": "Client words",
        "testimonial_title": "Apa kata client?",
        "cta_title": "Punya brief? Kirim hari ini dan masuk antrian produksi.",
        "cta_text": (
            "Ceritakan produk, target audience, durasi, dan referensi visual yang Anda suka. "
            "FYY MOTION akan membantu menyusun arah motion yang paling sesuai."
        ),
        "cta_label": "Chat WhatsApp",
        "cta_url": "",
        "email": "",
        "location": "Indonesia — melayani client online",
        "instagram_url": "",
        "youtube_url": "",
        "behance_url": "",
        "footer_text": "FYY MOTION — Motion Graphic Partner untuk brand yang ingin bergerak lebih cepat.",
        "marquee_items": [
            "Explainer Video", "Logo Animation", "Motion Ads", "Social Media Motion",
            "Product Video", "Intro YouTube", "Lyric Video", "Company Profile",
        ],
        "stats": [
            {"value": "1 Partner", "label": "Semua kebutuhan motion"},
            {"value": "Queue Jelas", "label": "Antrian & progress transparan"},
            {"value": "Revisi Terarah", "label": "Feedback per scene lebih rapi"},
            {"value": "File Siap Pakai", "label": "Output sesuai platform"},
        ],
        "benefits": [
            {"title": "Ongoing atau one-off", "description": "Butuh satu video campaign atau konten rutin setiap bulan? Alur produksi dapat menyesuaikan kebutuhan brand."},
            {"title": "Bekerja langsung dengan creator", "description": "Komunikasi lebih cepat tanpa lapisan birokrasi. Brief, preview, dan revisi dibahas langsung secara jelas."},
            {"title": "Hasil dalam hitungan hari", "description": "Workflow scene-by-scene membuat produksi lebih terukur, dengan update progress di setiap tahap penting."},
        ],
        "services": [
            {
                "title": "Explainer & Product Video",
                "description": "Menjelaskan produk, aplikasi, atau layanan dengan visual yang ringkas dan mudah diingat.",
                "items": ["Script & scene plan", "Storyboard visual", "Voice-over direction", "Subtitle & final render"],
            },
            {
                "title": "Motion Ads & Social Media",
                "description": "Konten promosi vertikal, square, dan landscape yang dirancang untuk menghentikan scroll.",
                "items": ["Instagram & TikTok ads", "Promo produk", "Motion poster", "Template campaign"],
            },
            {
                "title": "Logo Animation & Branding",
                "description": "Logo reveal dan identitas gerak yang membuat brand terasa premium di setiap pembuka video.",
                "items": ["Logo reveal", "Intro / outro", "Lower third", "Motion identity"],
            },
            {
                "title": "Company Profile & Presentation",
                "description": "Presentasi perusahaan dan pitch deck bergerak dengan ritme visual yang profesional.",
                "items": ["Company profile", "Pitch video", "Infografis animasi", "Presentasi produk"],
            },
        ],
        "process": [
            {"title": "Brief & konsultasi", "description": "Kirim tujuan video, script atau poin utama, aset brand, referensi, durasi, dan deadline."},
            {"title": "Konsep & scene plan", "description": "Arah visual, pembagian scene, teks layar, dan kebutuhan aset disusun sebelum animasi dimulai."},
            {"title": "Produksi & preview", "description": "Animasi dikerjakan per scene. Anda menerima preview untuk memeriksa ritme, teks, dan visual."},
            {"title": "Revisi & final delivery", "description": "Feedback diterapkan secara terarah, lalu file final dikirim dalam format siap publish."},
        ],
        "portfolio": [
            {"title": "Explainer Video Produk", "category": "Explainer", "description": "Video penjelasan produk dengan visual bersih, typography tegas, dan CTA yang jelas.", "image_url": "", "link_url": ""},
            {"title": "Motion Ads untuk Social Media", "category": "Ads", "description": "Konten promosi singkat dengan hook visual cepat untuk Instagram, TikTok, dan Reels.", "image_url": "", "link_url": ""},
            {"title": "Logo Animation Premium", "category": "Branding", "description": "Reveal logo sinematik untuk pembuka video, presentasi, dan identitas brand.", "image_url": "", "link_url": ""},
            {"title": "Company Profile Motion", "category": "Corporate", "description": "Profil perusahaan bergerak dengan infografis, data, dan narasi yang profesional.", "image_url": "", "link_url": ""},
        ],
        "testimonials": [],
    }

def empty_db() -> dict:
    return {
        "meta": {"app": "FYY MOTION Portal", "version": 1,
                 "created_at": now_iso(), "updated_at": now_iso()},
        "settings": {"nama_usaha": "FYY MOTION", "tagline": "Jasa Pembuatan Animasi Motion Graphic",
                     "pemilik": "", "wa_admin": "", "mata_uang": "IDR"},
        "accounts": deepcopy(DEFAULT_ACCOUNTS),
        "orders": [],
        "transactions": [],
        "clipboard_items": [],
        "profile": default_profile(),
    }


def sample_db() -> dict:
    """Data contoh agar dashboard langsung terisi. Bisa dikosongkan dari menu Backup."""
    db = empty_db()
    t = date.today()
    def d(offset): return (t - timedelta(days=offset)).isoformat()
    db["orders"] = [
        {"id": "ord-contoh-1", "order_code": "FYY-0001", "queue_no": 1,
         "client_name": "Budi Santoso", "wa_number": "6281234567890",
         "judul": "Video Explainer Produk Kopi", "jenis_animasi": "Explainer Video",
         "paket": "Premium 60 detik", "durasi": "60 detik", "resolusi": "1080p",
         "format_output": "MP4", "prioritas": "Normal",
         "tanggal_masuk": d(12), "deadline": d(5),
         "harga": 1500000, "dp": 1500000, "status_pembayaran": "lunas",
         "metode_bayar": "Transfer Bank", "status": "selesai", "progress": 100,
         "brief": "Explainer untuk launching produk kopi kemasan. Nuansa hangat, warna cokelat & oranye.",
         "script_teks": "Scene 1: Logo muncul.\nScene 2: \"Ngopi enak nggak harus mahal!\"\nScene 3: Tampilan produk + harga.\nScene 4: CTA ke WhatsApp.",
         "referensi": "Style flat illustration, referensi dikirim via WA.",
         "catatan_revisi": "", "drive_assets_url": "", "link_preview": "", "link_hasil": "",
         "created_at": now_iso(), "updated_at": now_iso()},
        {"id": "ord-contoh-2", "order_code": "FYY-0002", "queue_no": 2,
         "client_name": "Sari Dewi", "wa_number": "6289876543210",
         "judul": "Motion Graphic Iklan Skincare", "jenis_animasi": "Iklan / Ads",
         "paket": "Standard 30 detik", "durasi": "30 detik", "resolusi": "1080x1350",
         "format_output": "MP4", "prioritas": "Prioritas",
         "tanggal_masuk": d(4), "deadline": d(-2),
         "harga": 850000, "dp": 425000, "status_pembayaran": "dp",
         "metode_bayar": "DANA", "status": "revisi", "progress": 80,
         "brief": "Iklan Instagram skincare, target wanita 20-35 tahun, warna pink pastel.",
         "script_teks": "Teks utama: \"Kulit cerah dalam 7 hari!\"\nSub-teks: promo diskon 30 persen hanya minggu ini.",
         "referensi": "Contoh gaya: iklan skincare Korea.",
         "catatan_revisi": "Revisi 1: Ganti font judul jadi lebih bold, logo diperbesar di akhir video.",
         "drive_assets_url": "", "link_preview": "", "link_hasil": "",
         "created_at": now_iso(), "updated_at": now_iso()},
        {"id": "ord-contoh-3", "order_code": "FYY-0003", "queue_no": 3,
         "client_name": "Contoh Indo", "wa_number": "6285712345678",
         "judul": "Logo Animation PT Teknologi Nusantara", "jenis_animasi": "Logo Animation",
         "paket": "Basic", "durasi": "5 detik", "resolusi": "4K",
         "format_output": "MOV + MP4", "prioritas": "Normal",
         "tanggal_masuk": d(2), "deadline": d(-3),
         "harga": 500000, "dp": 250000, "status_pembayaran": "dp",
         "metode_bayar": "QRIS", "status": "proses", "progress": 45,
         "brief": "Animasi logo perusahaan teknologi, kesan modern & profesional.",
         "script_teks": "Logo reveal dengan garis cahaya, diakhiri tagline \"Inovasi Tanpa Batas\".",
         "referensi": "File logo AI/SVG dikirim client via email.",
         "catatan_revisi": "", "drive_assets_url": "", "link_preview": "", "link_hasil": "",
         "created_at": now_iso(), "updated_at": now_iso()},
        {"id": "ord-contoh-4", "order_code": "FYY-0004", "queue_no": 4,
         "client_name": "Andi Wijaya", "wa_number": "6282298765432",
         "judul": "Intro Youtube Channel Gaming", "jenis_animasi": "Intro / Outro Youtube",
         "paket": "Standard", "durasi": "10 detik", "resolusi": "1080p",
         "format_output": "MP4", "prioritas": "Normal",
         "tanggal_masuk": d(0), "deadline": d(-6),
         "harga": 350000, "dp": 0, "status_pembayaran": "belum",
         "metode_bayar": "OVO", "status": "masuk", "progress": 0,
         "brief": "Intro energik tema gaming, musik EDM.",
         "script_teks": "Nama channel: ANDI PLAY — efek glitch + neon ungu.",
         "referensi": "Link referensi menyusul dari client.",
         "catatan_revisi": "", "drive_assets_url": "", "link_preview": "", "link_hasil": "",
         "created_at": now_iso(), "updated_at": now_iso()},
    ]
    db["transactions"] = [
        {"id": "trx-contoh-1", "tanggal": d(30), "keterangan": "Setoran modal awal usaha",
         "jenis": "modal_masuk", "akun_debit": "101", "akun_kredit": "301",
         "jumlah": 5000000, "order_id": "", "metode_bayar": "Transfer Bank",
         "bukti": "", "created_at": now_iso()},
        {"id": "trx-contoh-2", "tanggal": d(28), "keterangan": "Langganan Adobe Creative Cloud 1 bulan",
         "jenis": "beban_software", "akun_debit": "501", "akun_kredit": "101",
         "jumlah": 450000, "order_id": "", "metode_bayar": "QRIS",
         "bukti": "", "created_at": now_iso()},
        {"id": "trx-contoh-3", "tanggal": d(12), "keterangan": "Pelunasan order FYY-0001 — Budi Santoso",
         "jenis": "pemasukan_order", "akun_debit": "101", "akun_kredit": "401",
         "jumlah": 1500000, "order_id": "ord-contoh-1", "metode_bayar": "Transfer Bank",
         "bukti": "", "created_at": now_iso()},
        {"id": "trx-contoh-4", "tanggal": d(4), "keterangan": "DP order FYY-0002 — Sari Dewi",
         "jenis": "dp_order", "akun_debit": "101", "akun_kredit": "202",
         "jumlah": 425000, "order_id": "ord-contoh-2", "metode_bayar": "DANA",
         "bukti": "", "created_at": now_iso()},
        {"id": "trx-contoh-5", "tanggal": d(3), "keterangan": "Bayar internet IndiHome bulan ini",
         "jenis": "beban_internet", "akun_debit": "502", "akun_kredit": "101",
         "jumlah": 350000, "order_id": "", "metode_bayar": "DANA",
         "bukti": "", "created_at": now_iso()},
        {"id": "trx-contoh-6", "tanggal": d(2), "keterangan": "DP order FYY-0003 — Andi Wijaya",
         "jenis": "dp_order", "akun_debit": "101", "akun_kredit": "202",
         "jumlah": 250000, "order_id": "ord-contoh-3", "metode_bayar": "QRIS",
         "bukti": "", "created_at": now_iso()},
    ]
    return db


def _profile_text(value, limit: int) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()[:limit]


def _profile_string_list(value, *, limit_items: int = 24, limit_chars: int = 180) -> list[str]:
    if isinstance(value, str):
        raw_items = re.split(r"[\n,]+", value)
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = []
    items = []
    for item in raw_items:
        text = _profile_text(item, limit_chars).lstrip("-• ").strip()
        if text:
            items.append(text)
        if len(items) >= limit_items:
            break
    return items


def _normalize_profile_cards(value, *, with_items: bool = False, limit_items: int = 12) -> list[dict]:
    if not isinstance(value, list):
        return []
    cards = []
    for raw in value[:limit_items]:
        if not isinstance(raw, dict):
            continue
        title = _profile_text(raw.get("title"), 160)
        if not title:
            continue
        card = {
            "title": title,
            "description": _profile_text(raw.get("description"), 900),
        }
        if with_items:
            card["items"] = _profile_string_list(raw.get("items"), limit_items=12, limit_chars=160)
        cards.append(card)
    return cards


def normalize_profile(raw) -> dict:
    """Lengkapi profil dari database/backup lama tanpa menghilangkan teks admin."""
    profile = default_profile()
    if not isinstance(raw, dict):
        return profile

    for field, limit in PROFILE_STRING_FIELDS.items():
        value = _profile_text(raw.get(field), limit)
        if value or field not in PROFILE_REQUIRED_FIELDS:
            profile[field] = value

    for field in (
        "hero_primary_url", "hero_secondary_url", "hero_image_url", "showreel_url",
        "cta_url", "instagram_url", "youtube_url", "behance_url",
    ):
        if profile[field] and not is_valid_profile_url(profile[field]):
            profile[field] = ""

    marquee = _profile_string_list(raw.get("marquee_items"), limit_items=24, limit_chars=90)
    if marquee:
        profile["marquee_items"] = marquee

    stats = []
    if isinstance(raw.get("stats"), list):
        for item in raw["stats"][:8]:
            if not isinstance(item, dict):
                continue
            value = _profile_text(item.get("value"), 60)
            label = _profile_text(item.get("label"), 120)
            if value or label:
                stats.append({"value": value, "label": label})
    if stats:
        profile["stats"] = stats

    for field in ("benefits", "process"):
        cards = _normalize_profile_cards(raw.get(field), limit_items=12)
        if cards:
            profile[field] = cards

    services = _normalize_profile_cards(raw.get("services"), with_items=True, limit_items=16)
    if services:
        profile["services"] = services

    portfolio = []
    if isinstance(raw.get("portfolio"), list):
        for item in raw["portfolio"][:24]:
            if not isinstance(item, dict):
                continue
            title = _profile_text(item.get("title"), 180)
            if not title:
                continue
            image_url = _profile_text(item.get("image_url"), 600)
            link_url = _profile_text(item.get("link_url"), 600)
            portfolio.append({
                "title": title,
                "category": _profile_text(item.get("category"), 100) or "Motion Graphic",
                "description": _profile_text(item.get("description"), 900),
                "image_url": image_url if is_valid_profile_url(image_url) else "",
                "link_url": link_url if is_valid_profile_url(link_url) else "",
            })
    # Daftar portofolio memang boleh dikosongkan dari admin; halaman publik
    # akan memakai order selesai sebagai cadangan bila daftar ini kosong.
    if "portfolio" in raw:
        profile["portfolio"] = portfolio

    testimonials = []
    if isinstance(raw.get("testimonials"), list):
        for item in raw["testimonials"][:12]:
            if not isinstance(item, dict):
                continue
            quote = _profile_text(item.get("quote"), 1000)
            if not quote:
                continue
            testimonials.append({
                "quote": quote,
                "name": _profile_text(item.get("name"), 120),
                "role": _profile_text(item.get("role"), 160),
            })
    profile["testimonials"] = testimonials
    return profile


def normalize_db(data) -> dict:
    """Validasi & lengkapi struktur database hasil baca / upload."""
    if not isinstance(data, dict):
        raise ValueError("File JSON harus berupa object { } berisi accounts, orders, transactions.")
    for key in ("accounts", "orders", "transactions"):
        if key not in data:
            raise ValueError(f"Key '{key}' tidak ditemukan di file JSON.")
        if not isinstance(data[key], list):
            raise ValueError(f"Key '{key}' harus berupa ARRAY [ ].")
        for item in data[key]:
            if not isinstance(item, dict):
                raise ValueError(f"Semua isi '{key}' harus berupa object {{ }}.")
    if "clipboard_items" in data:
        if not isinstance(data["clipboard_items"], list):
            raise ValueError("Key 'clipboard_items' harus berupa ARRAY [ ].")
        for item in data["clipboard_items"]:
            if not isinstance(item, dict):
                raise ValueError("Semua isi 'clipboard_items' harus berupa object { }.")
    if "profile" in data and not isinstance(data["profile"], dict):
        raise ValueError("Key 'profile' harus berupa OBJECT { }.")
    base = empty_db()
    base.update({k: data[k] for k in ("accounts", "orders", "transactions")})
    if isinstance(data.get("clipboard_items"), list):
        base["clipboard_items"] = data["clipboard_items"]
    base["profile"] = normalize_profile(data.get("profile"))
    if isinstance(data.get("settings"), dict):
        base["settings"].update(data["settings"])
    if isinstance(data.get("meta"), dict):
        base["meta"].update(data["meta"])
    if not base["accounts"]:
        base["accounts"] = deepcopy(DEFAULT_ACCOUNTS)
    # pastikan field penting order/transaksi ada (tahan file lama)
    for o in base["orders"]:
        o.setdefault("id", uuid.uuid4().hex)
        o.setdefault("status", "masuk")
        o.setdefault("status_pembayaran", "belum")
        o.setdefault("harga", 0); o.setdefault("dp", 0); o.setdefault("progress", 0)
        o.setdefault("drive_assets_url", ""); o.setdefault("link_preview", ""); o.setdefault("link_hasil", "")
    for t in base["transactions"]:
        t.setdefault("id", uuid.uuid4().hex)
        t.setdefault("jumlah", 0)
    seen_clipboard_ids = set()
    for item in base["clipboard_items"]:
        item_id = str(item.get("id") or "").strip()
        if not item_id or item_id in seen_clipboard_ids:
            item_id = uuid.uuid4().hex
        seen_clipboard_ids.add(item_id)
        content = str(item.get("content") or "").replace("\r\n", "\n").replace("\r", "\n")
        title = str(item.get("title") or "").strip()
        if not title:
            first_line = next((line.strip() for line in content.splitlines() if line.strip()), "Teks Clipboard")
            title = first_line[:80] + ("…" if len(first_line) > 80 else "")
        item["id"] = item_id
        item["title"] = title
        item["content"] = content
        item["created_at"] = str(item.get("created_at") or now_iso())
        item["updated_at"] = str(item.get("updated_at") or item["created_at"])
    return base


# --------------------------------------------------------------------------- #
# Lapisan penyimpanan: MongoDB Atlas (utama) + JSON (fallback)
# API publik tetap load_db()/save_db() agar seluruh halaman & akuntansi sama.
# --------------------------------------------------------------------------- #
def storage_backend() -> str:
    return "mongodb" if MONGODB_URI else "json"


def mongo_database_name() -> str:
    if MONGODB_DB_NAME:
        return MONGODB_DB_NAME
    if MONGODB_URI:
        db_name = urlparse(MONGODB_URI).path.strip("/").split("/")[0]
        if db_name and db_name not in ("admin", "local"):
            return db_name
    return "fyymotion"


def mongo_host() -> str:
    return urlparse(MONGODB_URI).hostname or "-" if MONGODB_URI else "-"


def storage_info(ping: bool = False) -> dict:
    if MONGODB_URI:
        info = {
            "backend": "mongodb",
            "label": "MongoDB Atlas",
            "configured": True,
            "connected": None,
            "location": f"MongoDB Atlas @ {mongo_host()} / database: {mongo_database_name()}",
            "database": mongo_database_name(),
            "host": mongo_host(),
            "db_path": f"mongodb://{mongo_host()}/{mongo_database_name()}",
        }
        if ping:
            try:
                get_mongo_db().command("ping")
                info["connected"] = True
            except Exception as exc:
                info["connected"] = False
                info["error"] = f"{type(exc).__name__}: {exc}"[:240]
        return info
    return {
        "backend": "json",
        "label": "JSON fallback",
        "configured": False,
        "connected": True,
        "location": str(DB_PATH),
        "database": "database.json",
        "host": "local",
        "db_path": str(DB_PATH),
    }


def get_mongo_db():
    global _MONGO_CLIENT, _MONGO_DB, _MONGO_READY
    if _MONGO_DB is not None:
        return _MONGO_DB
    if not MONGODB_URI:
        raise RuntimeError("MONGODB_URI belum terpasang")
    with _MONGO_INIT_LOCK:
        if _MONGO_DB is not None:
            return _MONGO_DB
        from pymongo import MongoClient

        client = MongoClient(
            MONGODB_URI,
            serverSelectionTimeoutMS=10000,
            connectTimeoutMS=10000,
            socketTimeoutMS=30000,
            retryWrites=True,
            appname="FYYMOTIONPortal",
        )
        client.admin.command("ping")
        db = client[mongo_database_name()]
        if not _MONGO_READY:
            db["orders"].create_index([("queue_no", 1), ("status", 1)])
            db["orders"].create_index([("tanggal_masuk", -1)])
            db["transactions"].create_index([("tanggal", -1), ("order_id", 1)])
            db["accounts"].create_index([("kode", 1)], unique=True)
            db["clipboard_items"].create_index([("updated_at", -1)])
            _MONGO_READY = True
        _MONGO_CLIENT = client
        _MONGO_DB = db
        return db


def _load_seed_db() -> dict:
    """Seed pertama: utamakan file JSON aktif, lalu file bawaan repo, lalu contoh."""
    for path in (DB_PATH, SEED_PATH):
        try:
            if path.exists():
                return normalize_db(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
    return sample_db()


def _mongo_doc(collection: str, item: dict) -> dict:
    doc = {k: deepcopy(v) for k, v in item.items() if k != "_id" and not k.startswith("_")}
    if collection == "accounts":
        doc["_id"] = str(doc.get("kode") or uuid.uuid4().hex)
    else:
        doc.setdefault("id", uuid.uuid4().hex)
        doc["_id"] = str(doc["id"])
    return doc


def _sync_collection(db_mongo, collection: str, items: list[dict]):
    from pymongo import DeleteMany, ReplaceOne

    coll = db_mongo[collection]
    docs = [_mongo_doc(collection, item) for item in items]
    desired_ids = {doc["_id"] for doc in docs}
    ops = []
    existing_ids = {doc["_id"] for doc in coll.find({}, {"_id": 1})}
    stale_ids = list(existing_ids - desired_ids)
    if stale_ids:
        ops.append(DeleteMany({"_id": {"$in": stale_ids}}))
    ops.extend(ReplaceOne({"_id": doc["_id"]}, doc, upsert=True) for doc in docs)
    if ops:
        coll.bulk_write(ops, ordered=False)


def _save_db_mongo(db: dict):
    db_mongo = get_mongo_db()
    for collection in ("accounts", "orders", "transactions", "clipboard_items"):
        _sync_collection(db_mongo, collection, db.get(collection, []))
    db_mongo["app_state"].replace_one(
        {"_id": "state"},
        {
            "_id": "state",
            "meta": db.get("meta", {}),
            "settings": db.get("settings", {}),
            "profile": normalize_profile(db.get("profile")),
        },
        upsert=True,
    )


def _load_db_mongo() -> dict:
    db_mongo = get_mongo_db()
    state = db_mongo["app_state"].find_one({"_id": "state"}, {"_id": 0})
    counts = {name: db_mongo[name].estimated_document_count()
              for name in ("accounts", "orders", "transactions", "clipboard_items")}
    if state is None and sum(counts.values()) == 0:
        seed = _load_seed_db()
        _save_db_mongo(seed)
        return normalize_db(seed)

    data = {
        "meta": (state or {}).get("meta", {}),
        "settings": (state or {}).get("settings", {}),
        "profile": (state or {}).get("profile", {}),
        "accounts": list(db_mongo["accounts"].find({}, {"_id": 0}).sort("kode", 1)),
        "orders": list(db_mongo["orders"].find({}, {"_id": 0})),
        "transactions": list(db_mongo["transactions"].find({}, {"_id": 0})),
        "clipboard_items": list(db_mongo["clipboard_items"].find({}, {"_id": 0})),
    }
    return normalize_db(data)


def _ensure_db_json():
    if DB_PATH.exists():
        return
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if SEED_PATH.exists() and SEED_PATH.resolve() != DB_PATH.resolve():
        shutil.copyfile(SEED_PATH, DB_PATH)
    else:
        _save_db_json(empty_db())


def _load_db_json() -> dict:
    _ensure_db_json()
    try:
        raw = json.loads(DB_PATH.read_text(encoding="utf-8"))
        return normalize_db(raw)
    except (ValueError, json.JSONDecodeError):
        db = empty_db()
        db["_warning"] = "database.json rusak/tidak valid — upload backup yang benar di menu Backup."
        return db


def _save_db_json(db: dict):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = DB_PATH.with_suffix(".tmp.json")
    tmp.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(DB_PATH)


def load_db() -> dict:
    with _DB_LOCK:
        if MONGODB_URI:
            try:
                return _load_db_mongo()
            except Exception as exc:
                app.logger.exception("MongoDB load gagal; fallback JSON sementara")
                db = _load_db_json()
                db["_warning"] = f"MongoDB Atlas belum terhubung ({type(exc).__name__}); aplikasi memakai JSON sementara."
                db["_storage_fallback"] = True
                return db
        return _load_db_json()


def save_db(db: dict):
    use_json_fallback = bool(db.get("_storage_fallback"))
    db = {k: deepcopy(v) for k, v in db.items() if not k.startswith("_")}
    db.setdefault("meta", {})["updated_at"] = now_iso()
    db["meta"]["version"] = max(int(db["meta"].get("version") or 1), 2)
    with _DB_LOCK:
        if MONGODB_URI and not use_json_fallback:
            try:
                _save_db_mongo(db)
                return
            except Exception:
                app.logger.exception("MongoDB save gagal; data disimpan ke JSON fallback")
        _save_db_json(db)


# --------------------------------------------------------------------------- #
# Helper umum
# --------------------------------------------------------------------------- #
def parse_int(value, default=0) -> int:
    if value is None:
        return default
    s = str(value).strip()
    s = re.sub(r"(?i)rp", "", s).replace(".", "").replace(" ", "")
    s = s.split(",")[0]  # buang desimal sen (mis. ",00")
    s = re.sub(r"[^0-9\-]", "", s)
    try:
        return int(s) if s not in ("", "-") else default
    except ValueError:
        return default


def fmt_rupiah(value) -> str:
    try:
        n = int(round(float(value or 0)))
    except (TypeError, ValueError):
        n = 0
    sign = "-" if n < 0 else ""
    return f"{sign}Rp{abs(n):,}".replace(",", ".")


def fmt_tanggal(value) -> str:
    if not value:
        return "-"
    try:
        dt = datetime.fromisoformat(str(value)[:19]) if "T" in str(value) else date.fromisoformat(str(value)[:10])
    except ValueError:
        return str(value)
    return f"{dt.day:02d} {BULAN_ID[dt.month]} {dt.year}"


def normalize_wa(raw: str) -> str:
    digits = re.sub(r"\D", "", str(raw or ""))
    if digits.startswith("0"):
        digits = "62" + digits[1:]
    elif digits.startswith("8"):
        digits = "62" + digits
    return digits


def is_valid_url(value) -> bool:
    """URL opsional: kosong valid; bila diisi wajib URL HTTP(S) lengkap."""
    url = str(value or "").strip()
    if not url:
        return True
    if any(ch.isspace() for ch in url):
        return False
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc) and ("." in host or host == "localhost")


def wa_link(o: dict) -> str:
    nomor = normalize_wa(o.get("wa_number", ""))
    if not nomor:
        return "#"
    pesan = (f"Halo {o.get('client_name','')}, saya dari FYY MOTION. "
             f"Mengenai order *{o.get('order_code','')} — {o.get('judul','')}* "
             f"saat ini statusnya: *{STATUS_LABEL.get(o.get('status',''), o.get('status',''))}*. Terima kasih!")
    from urllib.parse import quote
    return f"https://wa.me/{nomor}?text={quote(pesan)}"


def sisa_bayar(o: dict) -> int:
    return max(parse_int(o.get("harga", 0)) - parse_int(o.get("dp", 0)), 0)


def accounts_by_code(db) -> dict:
    return {a["kode"]: a for a in db["accounts"]}


def account_label(db, kode) -> str:
    a = accounts_by_code(db).get(str(kode))
    return f"{kode} — {a['nama']}" if a else str(kode or "-")


def sorted_transactions(db, reverse=False):
    return sorted(db["transactions"], key=lambda x: (str(x.get("tanggal", "")), str(x.get("created_at", ""))), reverse=reverse)


def sorted_orders_by_queue(db):
    return sorted(db["orders"], key=lambda x: (parse_int(x.get("queue_no", 999999)), str(x.get("created_at", ""))))


def next_queue_no(db) -> int:
    return max([parse_int(o.get("queue_no", 0)) for o in db["orders"]], default=0) + 1


def gen_order_code(db, queue_no: int) -> str:
    return f"FYY-{queue_no:04d}"


def find_by_id(items, item_id):
    return next((x for x in items if str(x.get("id")) == str(item_id)), None)


def clipboard_title_from_content(content: str) -> str:
    first_line = next((line.strip() for line in str(content or "").splitlines() if line.strip()), "Teks Clipboard")
    return first_line[:80] + ("…" if len(first_line) > 80 else "")


def sorted_clipboard_items(db):
    return sorted(
        db.get("clipboard_items", []),
        key=lambda x: (str(x.get("updated_at", "")), str(x.get("created_at", ""))),
        reverse=True,
    )


def clipboard_from_form():
    title = request.form.get("title", "").strip()
    content = str(request.form.get("content", "")).replace("\r\n", "\n").replace("\r", "\n").strip()
    errors = []
    if len(title) > 120:
        errors.append("Judul maksimal 120 karakter.")
    if not content:
        errors.append("Isi teks clipboard wajib diisi.")
    if len(content) > 20000:
        errors.append("Isi teks maksimal 20.000 karakter.")
    if not title and content:
        title = clipboard_title_from_content(content)
    return {"title": title or "Teks Clipboard", "content": content}, errors


def is_valid_profile_url(value: str) -> bool:
    value = str(value or "").strip()
    if not value:
        return True
    if value.startswith(("#", "/", "mailto:", "tel:")):
        return True
    return is_valid_url(value)


def _split_profile_blocks(text: str) -> list[list[str]]:
    blocks = []
    for block in re.split(r"\n\s*\n", str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if lines:
            blocks.append(lines)
    return blocks


def _parse_profile_stats(text: str) -> list[dict]:
    stats = []
    for line in str(text or "").splitlines():
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split("|", 1)]
        stats.append({
            "value": parts[0][:60],
            "label": (parts[1] if len(parts) > 1 else "")[:120],
        })
    return stats[:8]


def _parse_profile_cards(text: str, *, with_items: bool = False) -> list[dict]:
    cards = []
    for lines in _split_profile_blocks(text):
        description_lines = []
        items = []
        for line in lines[1:]:
            if with_items and line.startswith(("-", "•")):
                items.append(line.lstrip("-• ").strip()[:160])
            else:
                description_lines.append(line)
        card = {"title": lines[0][:160], "description": "\n".join(description_lines)[:900]}
        if with_items:
            card["items"] = items[:12]
        cards.append(card)
    return cards[:16]


def _parse_profile_portfolio(text: str) -> tuple[list[dict], list[str]]:
    portfolio = []
    errors = []
    for lines in _split_profile_blocks(text):
        meta = [part.strip() for part in lines[0].split("|")]
        meta += [""] * (4 - len(meta))
        title, category, image_url, link_url = meta[:4]
        if not title:
            continue
        if image_url and not is_valid_profile_url(image_url):
            errors.append(f"URL gambar portofolio '{title}' tidak valid.")
        if link_url and not is_valid_profile_url(link_url):
            errors.append(f"URL link portofolio '{title}' tidak valid.")
        portfolio.append({
            "title": title[:180],
            "category": (category or "Motion Graphic")[:100],
            "description": "\n".join(lines[1:])[:900],
            "image_url": image_url[:600],
            "link_url": link_url[:600],
        })
    return portfolio[:24], errors


def _parse_profile_testimonials(text: str) -> list[dict]:
    testimonials = []
    for lines in _split_profile_blocks(text):
        name = ""
        role = ""
        quote_lines = lines
        if len(lines) > 1 and "|" in lines[-1]:
            name_role = [part.strip() for part in lines[-1].split("|", 1)]
            name = name_role[0][:120]
            role = (name_role[1] if len(name_role) > 1 else "")[:160]
            quote_lines = lines[:-1]
        testimonials.append({
            "quote": "\n".join(quote_lines)[:1000],
            "name": name,
            "role": role,
        })
    return testimonials[:12]


def profile_form_data(db: dict) -> dict:
    profile = normalize_profile(db.get("profile"))
    settings = db.get("settings", {})
    form = {
        "nama_usaha": settings.get("nama_usaha", "FYY MOTION"),
        "tagline": settings.get("tagline", ""),
        "pemilik": settings.get("pemilik", ""),
        "wa_admin": settings.get("wa_admin", ""),
    }
    form.update({field: profile.get(field, "") for field in PROFILE_STRING_FIELDS})
    form["marquee_text"] = "\n".join(profile.get("marquee_items", []))
    form["stats_text"] = "\n".join(
        f"{item.get('value', '')} | {item.get('label', '')}".strip(" |")
        for item in profile.get("stats", [])
    )

    def cards_text(items, with_items=False):
        blocks = []
        for item in items:
            lines = [item.get("title", "")]
            if item.get("description"):
                lines.append(item["description"])
            if with_items:
                lines.extend(f"- {point}" for point in item.get("items", []))
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    form["benefits_text"] = cards_text(profile.get("benefits", []))
    form["services_cards_text"] = cards_text(profile.get("services", []), with_items=True)
    form["process_cards_text"] = cards_text(profile.get("process", []))
    portfolio_blocks = []
    for item in profile.get("portfolio", []):
        header = " | ".join([
            item.get("title", ""), item.get("category", ""),
            item.get("image_url", ""), item.get("link_url", ""),
        ]).rstrip(" |")
        lines = [header]
        if item.get("description"):
            lines.append(item["description"])
        portfolio_blocks.append("\n".join(lines))
    form["portfolio_text"] = "\n\n".join(portfolio_blocks)
    testimonial_blocks = []
    for item in profile.get("testimonials", []):
        lines = [item.get("quote", "")]
        if item.get("name") or item.get("role"):
            lines.append(" | ".join([item.get("name", ""), item.get("role", "")]).strip(" |"))
        testimonial_blocks.append("\n".join(lines))
    form["testimonials_text"] = "\n\n".join(testimonial_blocks)
    return form


PROFILE_URL_FIELDS = {
    "hero_primary_url": "URL tombol utama hero",
    "hero_secondary_url": "URL tombol kedua hero",
    "hero_image_url": "URL gambar hero/showreel",
    "showreel_url": "URL showreel",
    "cta_url": "URL tombol CTA akhir",
    "instagram_url": "URL Instagram",
    "youtube_url": "URL YouTube",
    "behance_url": "URL Behance/Dribbble",
}


def profile_from_form():
    profile = default_profile()
    errors = []
    for field, limit in PROFILE_STRING_FIELDS.items():
        profile[field] = _profile_text(request.form.get(field, ""), limit)
        if field in PROFILE_REQUIRED_FIELDS and not profile[field]:
            profile[field] = default_profile()[field]

    for field, label in PROFILE_URL_FIELDS.items():
        if not is_valid_profile_url(profile[field]):
            errors.append(f"{label} harus kosong, diawali # atau /, atau URL http/https yang valid.")

    email = profile.get("email", "")
    if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        errors.append("Format email profil tidak valid.")

    profile["marquee_items"] = _profile_string_list(request.form.get("marquee_text", ""), limit_items=24, limit_chars=90)
    if not profile["marquee_items"]:
        profile["marquee_items"] = default_profile()["marquee_items"]
    profile["stats"] = _parse_profile_stats(request.form.get("stats_text", "")) or default_profile()["stats"]
    profile["benefits"] = _parse_profile_cards(request.form.get("benefits_text", "")) or default_profile()["benefits"]
    profile["services"] = _parse_profile_cards(request.form.get("services_cards_text", ""), with_items=True) or default_profile()["services"]
    profile["process"] = _parse_profile_cards(request.form.get("process_cards_text", "")) or default_profile()["process"]
    portfolio, portfolio_errors = _parse_profile_portfolio(request.form.get("portfolio_text", ""))
    profile["portfolio"] = portfolio
    errors.extend(portfolio_errors)
    profile["testimonials"] = _parse_profile_testimonials(request.form.get("testimonials_text", ""))

    wa_admin = request.form.get("wa_admin", "").strip()
    normalized_wa = normalize_wa(wa_admin)
    if wa_admin and not normalized_wa:
        errors.append("Nomor WhatsApp admin tidak valid.")
    settings = {
        "nama_usaha": request.form.get("nama_usaha", "").strip()[:80] or "FYY MOTION",
        "tagline": request.form.get("tagline", "").strip()[:160],
        "pemilik": request.form.get("pemilik", "").strip()[:100],
        "wa_admin": normalized_wa,
    }
    return normalize_profile(profile), settings, errors


def public_whatsapp_url(db: dict) -> str:
    from urllib.parse import quote

    settings = db.get("settings", {})
    number = normalize_wa(settings.get("wa_admin", ""))
    if not number:
        return ""
    brand = settings.get("nama_usaha") or "FYY MOTION"
    message = f"Halo {brand}, saya ingin konsultasi project motion graphic. Boleh info paket dan antrian produksi?"
    return f"https://wa.me/{number}?text={quote(message)}"


def in_range(tanggal, d_from, d_to) -> bool:
    t = str(tanggal or "")[:10]
    if d_from and t < d_from:
        return False
    if d_to and t > d_to:
        return False
    return True


def period_params(args):
    """Kembalikan (preset, date_from, date_to) dari query string."""
    preset = args.get("periode", "bulan_ini")
    today = date.today()
    if preset == "hari_ini":
        f = t = today
    elif preset == "bulan_lalu":
        first_this = today.replace(day=1)
        t = first_this - timedelta(days=1)
        f = t.replace(day=1)
    elif preset == "tahun_ini":
        f, t = today.replace(month=1, day=1), today.replace(month=12, day=31)
    elif preset == "semua":
        return preset, "", ""
    elif preset == "custom":
        return preset, args.get("from", "")[:10], args.get("to", "")[:10]
    else:  # bulan_ini
        f = today.replace(day=1)
        t = (f + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return preset, f.isoformat(), t.isoformat()


def paginate(items, per_page=20):
    page = max(parse_int(request.args.get("page", 1), 1), 1)
    total = len(items)
    pages = max((total + per_page - 1) // per_page, 1)
    page = min(page, pages)
    start = (page - 1) * per_page
    return items[start:start + per_page], {"page": page, "pages": pages, "total": total, "per_page": per_page}


# --------------------------------------------------------------------------- #
# Mesin akuntansi: Jurnal -> Buku Besar -> Neraca Saldo -> Laba Rugi
# --------------------------------------------------------------------------- #
def cash_codes(db) -> set:
    return {a["kode"] for a in db["accounts"] if a.get("is_cash")}


def journal_rows(db, d_from="", d_to="", query=""):
    """Jurnal Umum: tiap transaksi dipecah 2 baris (Debit & Kredit)."""
    acc = accounts_by_code(db)
    rows = []
    for trx in sorted_transactions(db):
        if not in_range(trx.get("tanggal"), d_from, d_to):
            continue
        if query and query.lower() not in json.dumps(trx, ensure_ascii=False).lower():
            continue
        jumlah = parse_int(trx.get("jumlah", 0))
        d_acc = acc.get(str(trx.get("akun_debit")), {})
        k_acc = acc.get(str(trx.get("akun_kredit")), {})
        rows.append({"trx": trx, "tanggal": trx.get("tanggal"), "keterangan": trx.get("keterangan", ""),
                     "akun": d_acc.get("nama", trx.get("akun_debit")), "kode": trx.get("akun_debit"),
                     "ref": trx.get("akun_debit"), "debit": jumlah, "kredit": 0, "indent": False})
        rows.append({"trx": trx, "tanggal": trx.get("tanggal"), "keterangan": trx.get("keterangan", ""),
                     "akun": k_acc.get("nama", trx.get("akun_kredit")), "kode": trx.get("akun_kredit"),
                     "ref": trx.get("akun_kredit"), "debit": 0, "kredit": jumlah, "indent": True})
    return rows


def ledger_for_account(db, kode, d_from="", d_to=""):
    acc = accounts_by_code(db).get(str(kode))
    if not acc:
        return None
    is_debit_normal = acc.get("saldo_normal", "Debit") == "Debit"
    rows, total_d, total_k, saldo = [], 0, 0, 0
    for trx in sorted_transactions(db):
        jumlah = parse_int(trx.get("jumlah", 0))
        d = jumlah if str(trx.get("akun_debit")) == str(kode) else 0
        k = jumlah if str(trx.get("akun_kredit")) == str(kode) else 0
        if not d and not k:
            continue
        total_d += d; total_k += k
        saldo = (total_d - total_k) if is_debit_normal else (total_k - total_d)
        if in_range(trx.get("tanggal"), d_from, d_to):
            rows.append({"tanggal": trx.get("tanggal"), "keterangan": trx.get("keterangan", ""),
                         "debit": d, "kredit": k, "saldo": saldo, "trx_id": trx.get("id")})
    return {"account": acc, "rows": rows, "total_debit": total_d, "total_kredit": total_k,
            "saldo_akhir": saldo}


def trial_balance(db, d_from="", d_to=""):
    """Neraca Saldo: saldo debit/kredit tiap akun, total wajib seimbang."""
    rows = []
    td = tk = 0
    for a in sorted(db["accounts"], key=lambda x: x["kode"]):
        led = ledger_for_account(db, a["kode"], d_from, d_to)
        raw = led["total_debit"] - led["total_kredit"] if led else 0
        # saldo_akhir dari ledger dihitung seluruhnya; untuk periode pakai mutasi periode:
        if d_from or d_to:
            d_sum = sum(parse_int(t["jumlah"]) for t in db["transactions"]
                        if str(t.get("akun_debit")) == a["kode"] and in_range(t.get("tanggal"), d_from, d_to))
            k_sum = sum(parse_int(t["jumlah"]) for t in db["transactions"]
                        if str(t.get("akun_kredit")) == a["kode"] and in_range(t.get("tanggal"), d_from, d_to))
            raw = d_sum - k_sum
            tot_d, tot_k = d_sum, k_sum
        else:
            tot_d, tot_k = (led["total_debit"], led["total_kredit"]) if led else (0, 0)
        saldo_debit = raw if raw > 0 else 0
        saldo_kredit = -raw if raw < 0 else 0
        td += saldo_debit; tk += saldo_kredit
        rows.append({**a, "total_debit": tot_d, "total_kredit": tot_k,
                     "saldo_debit": saldo_debit, "saldo_kredit": saldo_kredit})
    return rows, td, tk


def income_statement(db, d_from="", d_to=""):
    rows, _, _ = trial_balance(db, d_from, d_to)
    pendapatan = [r for r in rows if r["tipe"] == "Pendapatan"]
    beban = [r for r in rows if r["tipe"] == "Beban"]
    total_pendapatan = sum(r["saldo_kredit"] - r["saldo_debit"] for r in pendapatan)
    total_beban = sum(r["saldo_debit"] - r["saldo_kredit"] for r in beban)
    return {"pendapatan": pendapatan, "beban": beban,
            "total_pendapatan": total_pendapatan, "total_beban": total_beban,
            "laba_bersih": total_pendapatan - total_beban}


def cash_in_out(db, d_from="", d_to=""):
    """Pemasukan = Kas/Bank di-DEBIT, Pengeluaran = Kas/Bank di-KREDIT (transparan dari Jurnal)."""
    codes = cash_codes(db)
    masuk = keluar = 0
    for t in db["transactions"]:
        if not in_range(t.get("tanggal"), d_from, d_to):
            continue
        if str(t.get("akun_debit")) in codes:
            masuk += parse_int(t.get("jumlah", 0))
        if str(t.get("akun_kredit")) in codes:
            keluar += parse_int(t.get("jumlah", 0))
    return masuk, keluar


def monthly_series(db, months=6):
    labels, masuk_s, keluar_s = [], [], []
    today = date.today()
    for i in range(months - 1, -1, -1):
        y, m = today.year, today.month - i
        while m <= 0:
            m += 12; y -= 1
        f = date(y, m, 1)
        t = (f + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        mi, mo = cash_in_out(db, f.isoformat(), t.isoformat())
        labels.append(f"{BULAN_SINGKAT[m]} {y}")
        masuk_s.append(mi); keluar_s.append(mo)
    return labels, masuk_s, keluar_s


# --------------------------------------------------------------------------- #
# Auth + CSRF
# --------------------------------------------------------------------------- #
def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


@app.context_processor
def inject_globals():
    db = getattr(g, "_db_cache", None) or load_db()
    active_orders = [o for o in db["orders"] if o.get("status") in STATUS_AKTIF]
    return {
        "settings": db.get("settings", {}),
        "profile": normalize_profile(db.get("profile")),
        "STATUS_ORDER": STATUS_ORDER, "STATUS_LABEL": STATUS_LABEL, "STATUS_BADGE": STATUS_BADGE,
        "STATUS_PEMBAYARAN": STATUS_PEMBAYARAN, "PAY_LABEL": PAY_LABEL, "PAY_BADGE": PAY_BADGE,
        "JENIS_ANIMASI": JENIS_ANIMASI, "PRIORITAS": PRIORITAS, "METODE_BAYAR": METODE_BAYAR,
        "JENIS_TRANSAKSI": JENIS_TRANSAKSI, "JENIS_LABEL": JENIS_LABEL, "JENIS_PRESET": JENIS_PRESET,
        "TIPE_AKUN": TIPE_AKUN,
        "count_clipboard": len(db.get("clipboard_items", [])),
        "count_antrian": len(active_orders),
        "count_revisi": len([o for o in db["orders"] if o.get("status") == "revisi"]),
        "count_masuk": len([o for o in db["orders"] if o.get("status") == "masuk"]),
        "csrf_token": csrf_token,
        "now_year": date.today().year,
        "page_url": _page_url,
        "storage": storage_info(),
    }


def _page_url(page: int) -> str:
    args = request.args.to_dict(flat=True)
    args["page"] = str(page)
    return f"{request.path}?{'&'.join(f'{k}={v}' for k, v in args.items())}"


app.jinja_env.filters["rupiah"] = fmt_rupiah
app.jinja_env.filters["tanggal"] = fmt_tanggal
app.jinja_env.filters["wa"] = normalize_wa


@app.before_request
def guard():
    endpoint = request.endpoint or ""
    if endpoint in (
        "static", "login", "health", "public_profile",
        "teks_creator", "teks_creator_generate", "academy", "daftar_academy",
        "text_fx_tool", "text_fx_generate",
    ):
        pass
    elif not session.get("logged_in"):
        return redirect(url_for("login", next=request.path))
    if request.method == "POST":
        token = request.form.get("csrf_token") or request.headers.get("X-CSRFToken", "")
        if not token or not secrets.compare_digest(str(token), str(session.get("_csrf", ""))):
            abort(400, "Token CSRF tidak valid. Muat ulang halaman lalu coba lagi.")


@app.route("/health")
def health():
    info = storage_info(ping=True)
    return {
        "status": "ok" if info.get("connected") is not False else "degraded",
        "app": "FYY MOTION Portal",
        "storage": info["backend"],
        "storage_label": info["label"],
        "database": info["database"],
        "database_connected": info.get("connected"),
        "db": info["db_path"],
        "vercel": bool(os.environ.get("VERCEL")),
    }


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("logged_in"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        user_ok = secrets.compare_digest(request.form.get("username", ""), ADMIN_USERNAME)
        pass_ok = secrets.compare_digest(request.form.get("password", ""), ADMIN_PASSWORD)
        if user_ok and pass_ok:
            session.permanent = True
            session["logged_in"] = True
            session["username"] = ADMIN_USERNAME
            session["_csrf"] = secrets.token_hex(16)
            flash("Selamat datang di Portal FYY MOTION!", "success")
            nxt = request.args.get("next") or url_for("dashboard")
            return redirect(nxt if nxt.startswith("/") else url_for("dashboard"))
        flash("Username atau password salah.", "danger")
    return render_template("login.html", default_hint=(ADMIN_PASSWORD == "fyymotion123"))


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


# --------------------------------------------------------------------------- #
# Profil publik & editor profil admin
# --------------------------------------------------------------------------- #
@app.route("/")
def public_profile():
    """Halaman profil/portofolio publik FYY MOTION di root domain."""
    db = load_db()
    profile = normalize_profile(db.get("profile"))
    settings = db.get("settings", {})
    portfolio = profile.get("portfolio", [])
    if not portfolio:
        fallback = []
        for order in sorted_orders_by_queue(db):
            if order.get("status") != "selesai":
                continue
            fallback.append({
                "title": order.get("judul") or "Project Motion Graphic",
                "category": order.get("jenis_animasi") or "Motion Graphic",
                "description": " • ".join(
                    part for part in [order.get("paket", ""), order.get("durasi", ""), order.get("resolusi", "")]
                    if part
                ),
                "image_url": "",
                "link_url": order.get("link_hasil") or order.get("link_preview") or "",
            })
        portfolio = fallback

    wa_url = public_whatsapp_url(db)
    primary_url = profile.get("hero_primary_url") or wa_url or "#contact"
    secondary_url = profile.get("hero_secondary_url") or "#works"
    cta_url = profile.get("cta_url") or wa_url or "#contact"
    showreel_url = profile.get("showreel_url") or "#works"
    return render_template(
        "profile.html",
        profile=profile,
        settings=settings,
        portfolio=portfolio,
        wa_url=wa_url,
        primary_url=primary_url,
        secondary_url=secondary_url,
        cta_url=cta_url,
        showreel_url=showreel_url,
        is_admin=bool(session.get("logged_in")),
        page_title=f"{settings.get('nama_usaha') or 'FYY MOTION'} — {settings.get('tagline') or 'Motion Graphic Partner'}",
    )


@app.route("/admin/profil", methods=["GET", "POST"])
def profile_edit():
    """Edit seluruh teks halaman profil publik dari ruang admin."""
    db = load_db()
    if request.method == "POST":
        profile, settings_updates, errors = profile_from_form()
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "profile_edit.html",
                form={key: value for key, value in request.form.items()},
                page_title="Edit Profil Publik",
                page_icon="fa-solid fa-pen-ruler",
            )
        db["settings"].update(settings_updates)
        db["profile"] = profile
        save_db(db)
        flash("Profil publik berhasil diperbarui. Buka route / untuk melihat hasilnya.", "success")
        return redirect(url_for("profile_edit"))
    return render_template(
        "profile_edit.html",
        form=profile_form_data(db),
        page_title="Edit Profil Publik",
        page_icon="fa-solid fa-pen-ruler",
    )


# --------------------------------------------------------------------------- #
# Dashboard admin
# --------------------------------------------------------------------------- #
@app.route("/dashboard")
def dashboard():
    db = load_db()
    preset, d_from, d_to = period_params(request.args)
    masuk, keluar = cash_in_out(db, d_from, d_to)
    masuk_all, keluar_all = cash_in_out(db)
    is_data = income_statement(db, d_from, d_to)
    orders = sorted_orders_by_queue(db)
    aktif = [o for o in orders if o.get("status") in STATUS_AKTIF]
    sedang_proses = next((o for o in aktif if o.get("status") in ("proses", "revisi")), aktif[0] if aktif else None)

    total_piutang = sum(sisa_bayar(o) for o in db["orders"] if o.get("status") != "batal")
    nilai_order_periode = sum(parse_int(o.get("harga", 0)) for o in db["orders"]
                               if in_range(o.get("tanggal_masuk"), d_from, d_to) and o.get("status") != "batal")
    labels, m_masuk, m_keluar = monthly_series(db, 6)
    status_counts = {k: len([o for o in db["orders"] if o.get("status") == k]) for k, _, _ in STATUS_ORDER}
    pay_counts = {k: len([o for o in db["orders"] if o.get("status_pembayaran") == k]) for k, _, _ in STATUS_PEMBAYARAN}
    priority_counts = {p: len([o for o in aktif if o.get("prioritas") == p]) for p in PRIORITAS}

    stats = {
        "pemasukan": masuk, "pengeluaran": keluar, "laba_bersih": is_data["laba_bersih"],
        "saldo_kas": masuk_all - keluar_all,
        "total_order": len(db["orders"]),
        "order_selesai": status_counts.get("selesai", 0),
        "order_revisi": status_counts.get("revisi", 0),
        "order_aktif": len(aktif), "total_piutang": total_piutang,
        "nilai_order_periode": nilai_order_periode,
        "total_pendapatan": is_data["total_pendapatan"], "total_beban": is_data["total_beban"],
    }
    recent_orders = sorted(db["orders"], key=lambda x: str(x.get("created_at", "")), reverse=True)[:8]
    recent_trx = sorted_transactions(db, reverse=True)[:8]
    return render_template("dashboard.html", stats=stats, preset=preset, d_from=d_from, d_to=d_to,
                           aktif=aktif[:8], sedang_proses=sedang_proses,
                           recent_orders=recent_orders, recent_trx=recent_trx,
                           account_label=lambda k: account_label(db, k),
                           chart={"labels": labels, "masuk": m_masuk, "keluar": m_keluar,
                                  "status_labels": [STATUS_LABEL[k] for k in status_counts],
                                  "status_data": list(status_counts.values()),
                                  "pay_labels": [PAY_LABEL[k] for k in pay_counts],
                                  "pay_data": list(pay_counts.values()),
                                  "priority_labels": list(priority_counts),
                                  "priority_data": list(priority_counts.values())},
                           wa_link=wa_link, sisa_bayar=sisa_bayar)


# --------------------------------------------------------------------------- #
# Order (Pesanan) CRUD
# --------------------------------------------------------------------------- #
def order_from_form(db, existing=None):
    f = request.form
    harga, dp = parse_int(f.get("harga")), parse_int(f.get("dp"))
    status_bayar = f.get("status_pembayaran") or ("lunas" if dp >= harga and harga > 0 else ("dp" if dp > 0 else "belum"))
    data = {
        "client_name": f.get("client_name", "").strip(),
        "wa_number": normalize_wa(f.get("wa_number", "")),
        "judul": f.get("judul", "").strip(),
        "jenis_animasi": f.get("jenis_animasi", "Motion Graphic"),
        "paket": f.get("paket", "").strip(),
        "durasi": f.get("durasi", "").strip(),
        "resolusi": f.get("resolusi", "").strip(),
        "format_output": f.get("format_output", "").strip(),
        "prioritas": f.get("prioritas", "Normal"),
        "tanggal_masuk": (f.get("tanggal_masuk") or today_str())[:10],
        "deadline": (f.get("deadline") or "")[:10],
        "harga": harga, "dp": dp, "status_pembayaran": status_bayar,
        "metode_bayar": f.get("metode_bayar", "Transfer Bank"),
        "status": f.get("status", "masuk"),
        "progress": min(max(parse_int(f.get("progress", 0)), 0), 100),
        "brief": f.get("brief", "").strip(),
        "script_teks": f.get("script_teks", "").strip(),
        "referensi": f.get("referensi", "").strip(),
        "catatan_revisi": f.get("catatan_revisi", "").strip(),
        "drive_assets_url": f.get("drive_assets_url", "").strip(),
        "link_preview": f.get("link_preview", "").strip(),
        "link_hasil": f.get("link_hasil", "").strip(),
        "updated_at": now_iso(),
    }
    if data["status"] == "selesai":
        data["progress"] = 100
    errors = []
    if not data["client_name"]:
        errors.append("Nama client wajib diisi.")
    if not data["wa_number"]:
        errors.append("Nomor WhatsApp wajib diisi (agar tidak lupa menghubungi client).")
    if not data["judul"]:
        errors.append("Judul pesanan wajib diisi.")
    if dp > harga:
        errors.append("DP tidak boleh lebih besar dari harga total.")
    for field, label in (("drive_assets_url", "Link Google Drive Assets"),
                         ("link_preview", "Link Preview"), ("link_hasil", "Link Hasil Final")):
        if not is_valid_url(data.get(field, "")):
            errors.append(f"{label} harus berupa URL lengkap diawali http:// atau https://")
    if errors:
        return None, errors
    if existing:
        existing.update(data)
        return existing, []
    q = parse_int(f.get("queue_no")) or next_queue_no(db)
    data.update({"id": uuid.uuid4().hex, "queue_no": q,
                 "order_code": f.get("order_code", "").strip() or gen_order_code(db, q),
                 "created_at": now_iso()})
    return data, []


@app.route("/orders")
def orders_list():
    db = load_db()
    q = request.args.get("q", "").strip().lower()
    status = request.args.get("status", "")
    bayar = request.args.get("bayar", "")
    prioritas = request.args.get("prioritas", "")
    sort = request.args.get("sort", "antrian")
    preset, d_from, d_to = period_params({**request.args, "periode": request.args.get("periode", "semua")})

    items = list(db["orders"])
    if q:
        items = [o for o in items if q in json.dumps(o, ensure_ascii=False).lower()]
    if status:
        items = [o for o in items if o.get("status") == status]
    if bayar:
        items = [o for o in items if o.get("status_pembayaran") == bayar]
    if prioritas:
        items = [o for o in items if o.get("prioritas") == prioritas]
    if d_from or d_to:
        items = [o for o in items if in_range(o.get("tanggal_masuk"), d_from, d_to)]

    if sort == "terbaru":
        items.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
    elif sort == "deadline":
        items.sort(key=lambda x: (str(x.get("deadline") or "9999-12-31"), parse_int(x.get("queue_no", 0))))
    elif sort == "harga":
        items.sort(key=lambda x: parse_int(x.get("harga", 0)), reverse=True)
    else:
        items.sort(key=lambda x: (parse_int(x.get("queue_no", 999999)), str(x.get("created_at", ""))))

    # posisi antrian aktif (urutan kerja nyata)
    aktif_sorted = [o["id"] for o in sorted_orders_by_queue(db) if o.get("status") in STATUS_AKTIF]
    posisi = {oid: i + 1 for i, oid in enumerate(aktif_sorted)}

    summary = {
        "total_nilai": sum(parse_int(o.get("harga", 0)) for o in items),
        "total_dp": sum(parse_int(o.get("dp", 0)) for o in items),
        "total_sisa": sum(sisa_bayar(o) for o in items),
    }
    page_items, pg = paginate(items, 20)
    return render_template("orders.html", orders=page_items, pg=pg, posisi=posisi, summary=summary,
                           q=q, status=status, bayar=bayar, prioritas=prioritas, sort=sort,
                           preset=preset, d_from=d_from, d_to=d_to, wa_link=wa_link, sisa_bayar=sisa_bayar)


@app.route("/orders/new", methods=["GET", "POST"])
def order_new():
    db = load_db()
    if request.method == "POST":
        order, errors = order_from_form(db)
        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("order_form.html", order=request.form, mode="new",
                                   next_queue=next_queue_no(db)), 400
        db["orders"].append(order)
        # opsi: catat DP otomatis ke Jurnal/Kas
        if request.form.get("catat_dp") == "1" and parse_int(order["dp"]) > 0:
            db["transactions"].append({
                "id": uuid.uuid4().hex, "tanggal": order["tanggal_masuk"],
                "keterangan": f"DP order {order['order_code']} — {order['client_name']}",
                "jenis": "dp_order", "akun_debit": "101", "akun_kredit": "202",
                "jumlah": parse_int(order["dp"]), "order_id": order["id"],
                "metode_bayar": order["metode_bayar"], "bukti": "Otomatis dari pembuatan order",
                "created_at": now_iso(),
            })
            flash("Order dibuat & DP otomatis tercatat di Jurnal (Kas / DP Client).", "success")
        else:
            flash(f"Order {order['order_code']} berhasil dibuat. Nomor antrian: #{order['queue_no']}", "success")
        save_db(db)
        return redirect(url_for("order_detail", order_id=order["id"]))
    return render_template("order_form.html", order={"tanggal_masuk": today_str(), "status": "masuk",
                                                     "status_pembayaran": "belum", "progress": 0},
                           mode="new", next_queue=next_queue_no(db))


@app.route("/orders/<order_id>")
def order_detail(order_id):
    db = load_db()
    o = find_by_id(db["orders"], order_id) or abort(404)
    aktif_sorted = [x["id"] for x in sorted_orders_by_queue(db) if x.get("status") in STATUS_AKTIF]
    posisi = aktif_sorted.index(o["id"]) + 1 if o["id"] in aktif_sorted else None
    trx = [t for t in sorted_transactions(db) if str(t.get("order_id")) == str(order_id)]
    total_trx_in = sum(parse_int(t["jumlah"]) for t in trx if str(t.get("akun_debit")) in cash_codes(db))
    return render_template("order_detail.html", o=o, posisi=posisi, total_antrian=len(aktif_sorted),
                           trx=trx, total_trx_in=total_trx_in, wa_link=wa_link(o),
                           sisa=sisa_bayar(o), account_label=lambda k: account_label(db, k))


@app.route("/orders/<order_id>/edit", methods=["GET", "POST"])
def order_edit(order_id):
    db = load_db()
    o = find_by_id(db["orders"], order_id) or abort(404)
    if request.method == "POST":
        updated, errors = order_from_form(db, existing=dict(o))
        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("order_form.html", order={**o, **request.form}, mode="edit"), 400
        # queue_no & order_code boleh diubah manual dari form edit
        updated["queue_no"] = parse_int(request.form.get("queue_no"), updated["queue_no"])
        updated["order_code"] = request.form.get("order_code", "").strip() or updated["order_code"]
        idx = db["orders"].index(o)
        db["orders"][idx] = updated
        save_db(db)
        flash("Order berhasil diperbarui.", "success")
        return redirect(url_for("order_detail", order_id=order_id))
    return render_template("order_form.html", order=o, mode="edit")


@app.route("/orders/<order_id>/status", methods=["POST"])
def order_status(order_id):
    db = load_db()
    o = find_by_id(db["orders"], order_id) or abort(404)
    new_status = request.form.get("status", "")
    if new_status in STATUS_LABEL:
        o["status"] = new_status
        if new_status == "selesai":
            o["progress"] = 100
        o["updated_at"] = now_iso()
        save_db(db)
        flash(f"Status {o.get('order_code')} diubah menjadi: {STATUS_LABEL[new_status]}", "success")
    return redirect(request.referrer or url_for("orders_list"))


@app.route("/orders/<order_id>/delete", methods=["POST"])
def order_delete(order_id):
    db = load_db()
    o = find_by_id(db["orders"], order_id) or abort(404)
    db["orders"] = [x for x in db["orders"] if x["id"] != order_id]
    save_db(db)
    flash(f"Order {o.get('order_code')} — {o.get('client_name')} telah dihapus. (Transaksi keuangan terkait tidak ikut dihapus)", "warning")
    return redirect(url_for("orders_list"))


@app.route("/antrian")
def antrian():
    db = load_db()
    orders = sorted_orders_by_queue(db)
    board = {k: [o for o in orders if o.get("status") == k] for k, _, _ in STATUS_ORDER}
    aktif = [o for o in orders if o.get("status") in STATUS_AKTIF]
    current = next((o for o in aktif if o.get("status") in ("proses", "revisi")), aktif[0] if aktif else None)
    return render_template("antrian.html", board=board, aktif=aktif, current=current,
                           wa_link=wa_link, sisa_bayar=sisa_bayar)


# --------------------------------------------------------------------------- #
# Clipboard — tempat simpan teks manual yang sering dipakai ulang
# --------------------------------------------------------------------------- #
@app.route("/clipboard", methods=["GET", "POST"])
def clipboard_page():
    db = load_db()
    items = sorted_clipboard_items(db)
    editing = None
    form_item = {}

    if request.method == "POST":
        item_id = request.form.get("item_id", "").strip()
        existing = find_by_id(db["clipboard_items"], item_id) if item_id else None
        if item_id and not existing:
            abort(404)
        data, errors = clipboard_from_form()
        if errors:
            for error in errors:
                flash(error, "danger")
            form_item = {**(existing or {}), **data}
            return render_template("clipboard.html", items=items, editing=existing,
                                   form_item=form_item), 400
        if existing:
            updated = dict(existing)
            updated.update(data)
            updated["updated_at"] = now_iso()
            idx = db["clipboard_items"].index(existing)
            db["clipboard_items"][idx] = updated
            flash(f"Clipboard '{updated['title']}' berhasil diperbarui.", "success")
        else:
            data.update({
                "id": uuid.uuid4().hex,
                "created_at": now_iso(),
                "updated_at": now_iso(),
            })
            db["clipboard_items"].append(data)
            flash(f"Teks '{data['title']}' berhasil disimpan ke Clipboard.", "success")
        save_db(db)
        return redirect(url_for("clipboard_page"))

    edit_id = request.args.get("edit", "").strip()
    if edit_id:
        editing = find_by_id(db["clipboard_items"], edit_id) or abort(404)
        form_item = dict(editing)
    return render_template("clipboard.html", items=items, editing=editing, form_item=form_item)


@app.route("/clipboard/<item_id>/delete", methods=["POST"])
def clipboard_delete(item_id):
    db = load_db()
    item = find_by_id(db["clipboard_items"], item_id) or abort(404)
    db["clipboard_items"] = [x for x in db["clipboard_items"] if str(x.get("id")) != str(item_id)]
    save_db(db)
    flash(f"Clipboard '{item.get('title')}' telah dihapus.", "warning")
    return redirect(url_for("clipboard_page"))


# --------------------------------------------------------------------------- #
# Transaksi CRUD (sumber Jurnal / Buku Besar / Neraca Saldo)
# --------------------------------------------------------------------------- #
def transaction_from_form(db, existing=None):
    f = request.form
    data = {
        "tanggal": (f.get("tanggal") or today_str())[:10],
        "keterangan": f.get("keterangan", "").strip(),
        "jenis": f.get("jenis", "manual"),
        "akun_debit": f.get("akun_debit", "").strip(),
        "akun_kredit": f.get("akun_kredit", "").strip(),
        "jumlah": parse_int(f.get("jumlah")),
        "order_id": f.get("order_id", "").strip(),
        "metode_bayar": f.get("metode_bayar", "Transfer Bank"),
        "bukti": f.get("bukti", "").strip(),
    }
    codes = set(accounts_by_code(db).keys())
    errors = []
    if not data["keterangan"]:
        errors.append("Keterangan transaksi wajib diisi.")
    if data["akun_debit"] not in codes:
        errors.append("Akun DEBIT tidak valid — pilih dari Daftar Akun.")
    if data["akun_kredit"] not in codes:
        errors.append("Akun KREDIT tidak valid — pilih dari Daftar Akun.")
    if data["akun_debit"] and data["akun_debit"] == data["akun_kredit"]:
        errors.append("Akun Debit dan Kredit tidak boleh sama.")
    if data["jumlah"] <= 0:
        errors.append("Jumlah harus lebih besar dari 0.")
    if errors:
        return None, errors
    if existing:
        existing.update(data)
        return existing, []
    data.update({"id": uuid.uuid4().hex, "created_at": now_iso()})
    return data, []


@app.route("/transactions")
def transactions_list():
    db = load_db()
    q = request.args.get("q", "").strip().lower()
    arah = request.args.get("arah", "")  # masuk | keluar
    akun = request.args.get("akun", "")
    jenis = request.args.get("jenis", "")
    preset, d_from, d_to = period_params(request.args)
    codes = cash_codes(db)

    items = sorted_transactions(db, reverse=True)
    items = [t for t in items if in_range(t.get("tanggal"), d_from, d_to)]
    if q:
        items = [t for t in items if q in json.dumps(t, ensure_ascii=False).lower()
                 or q in account_label(db, t.get("akun_debit")).lower()
                 or q in account_label(db, t.get("akun_kredit")).lower()]
    if arah == "masuk":
        items = [t for t in items if str(t.get("akun_debit")) in codes]
    elif arah == "keluar":
        items = [t for t in items if str(t.get("akun_kredit")) in codes]
    if akun:
        items = [t for t in items if akun in (str(t.get("akun_debit")), str(t.get("akun_kredit")))]
    if jenis:
        items = [t for t in items if t.get("jenis") == jenis]

    masuk, keluar = cash_in_out(db, d_from, d_to)
    page_items, pg = paginate(items, 25)
    orders_map = {o["id"]: o for o in db["orders"]}
    return render_template("transactions.html", trx=page_items, pg=pg, preset=preset,
                           d_from=d_from, d_to=d_to, q=q, arah=arah, akun=akun, jenis=jenis,
                           accounts=sorted(db["accounts"], key=lambda x: x["kode"]),
                           cash_codes=codes, masuk=masuk, keluar=keluar, orders_map=orders_map,
                           account_label=lambda k: account_label(db, k))


@app.route("/transactions/new", methods=["GET", "POST"])
def transaction_new():
    db = load_db()
    if request.method == "POST":
        trx, errors = transaction_from_form(db)
        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("transaction_form.html", trx=request.form, mode="new",
                                   accounts=sorted(db["accounts"], key=lambda x: x["kode"]),
                                   orders=sorted_orders_by_queue(db)), 400
        db["transactions"].append(trx)
        save_db(db)
        flash("Transaksi tercatat di Jurnal Umum.", "success")
        return redirect(url_for("transactions_list"))
    prefill = {"tanggal": today_str(), "jenis": "pemasukan_order", "akun_debit": "101", "akun_kredit": "401"}
    order_id = request.args.get("order_id", "")
    if order_id:
        o = find_by_id(db["orders"], order_id)
        if o:
            prefill.update({"order_id": o["id"], "jumlah": sisa_bayar(o) or parse_int(o.get("harga", 0)),
                            "keterangan": f"Pembayaran order {o.get('order_code')} — {o.get('client_name')}",
                            "metode_bayar": o.get("metode_bayar", "Transfer Bank")})
    return render_template("transaction_form.html", trx=prefill, mode="new",
                           accounts=sorted(db["accounts"], key=lambda x: x["kode"]),
                           orders=sorted_orders_by_queue(db))


@app.route("/transactions/<trx_id>/edit", methods=["GET", "POST"])
def transaction_edit(trx_id):
    db = load_db()
    trx = find_by_id(db["transactions"], trx_id) or abort(404)
    if request.method == "POST":
        updated, errors = transaction_from_form(db, existing=dict(trx))
        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("transaction_form.html", trx={**trx, **request.form}, mode="edit",
                                   accounts=sorted(db["accounts"], key=lambda x: x["kode"]),
                                   orders=sorted_orders_by_queue(db)), 400
        db["transactions"][db["transactions"].index(trx)] = updated
        save_db(db)
        flash("Transaksi berhasil diperbarui.", "success")
        return redirect(url_for("transactions_list"))
    return render_template("transaction_form.html", trx=trx, mode="edit",
                           accounts=sorted(db["accounts"], key=lambda x: x["kode"]),
                           orders=sorted_orders_by_queue(db))


@app.route("/transactions/<trx_id>/delete", methods=["POST"])
def transaction_delete(trx_id):
    db = load_db()
    find_by_id(db["transactions"], trx_id) or abort(404)
    db["transactions"] = [t for t in db["transactions"] if t["id"] != trx_id]
    save_db(db)
    flash("Transaksi telah dihapus dari Jurnal.", "warning")
    return redirect(url_for("transactions_list"))


# --------------------------------------------------------------------------- #
# Laporan akuntansi
# --------------------------------------------------------------------------- #
@app.route("/Jurnal")
def jurnal():
    db = load_db()
    preset, d_from, d_to = period_params({**request.args, "periode": request.args.get("periode", "semua")})
    q = request.args.get("q", "")
    rows = journal_rows(db, d_from, d_to, q)
    total_d = sum(r["debit"] for r in rows)
    total_k = sum(r["kredit"] for r in rows)
    return render_template("Jurnal.html", rows=rows, total_d=total_d, total_k=total_k,
                           preset=preset, d_from=d_from, d_to=d_to, q=q)


@app.route("/buku-besar")
def buku_besar():
    db = load_db()
    preset, d_from, d_to = period_params({**request.args, "periode": request.args.get("periode", "semua")})
    kode = request.args.get("akun", "")
    accounts = sorted(db["accounts"], key=lambda x: x["kode"])
    ledgers = []
    targets = [kode] if kode else [a["kode"] for a in accounts]
    for k in targets:
        led = ledger_for_account(db, k, d_from, d_to)
        if led and (kode or led["rows"]):
            ledgers.append(led)
    return render_template("buku_besar.html", ledgers=ledgers, accounts=accounts, kode=kode,
                           preset=preset, d_from=d_from, d_to=d_to)


@app.route("/neraca-saldo")
def neraca_saldo_page():
    db = load_db()
    preset, d_from, d_to = period_params({**request.args, "periode": request.args.get("periode", "semua")})
    rows, td, tk = trial_balance(db, d_from, d_to)
    return render_template("neraca_saldo.html", rows=rows, td=td, tk=tk, seimbang=(td == tk),
                           preset=preset, d_from=d_from, d_to=d_to)


@app.route("/laporan")
def laporan():
    db = load_db()
    preset, d_from, d_to = period_params(request.args)
    is_data = income_statement(db, d_from, d_to)
    masuk, keluar = cash_in_out(db, d_from, d_to)
    orders_p = [o for o in db["orders"] if in_range(o.get("tanggal_masuk"), d_from, d_to)]
    ringkasan_order = {
        "jumlah_order": len(orders_p),
        "nilai_order": sum(parse_int(o.get("harga", 0)) for o in orders_p if o.get("status") != "batal"),
        "dp_masuk": sum(parse_int(o.get("dp", 0)) for o in orders_p if o.get("status") != "batal"),
        "sisa_piutang": sum(sisa_bayar(o) for o in orders_p if o.get("status") != "batal"),
        "selesai": len([o for o in orders_p if o.get("status") == "selesai"]),
    }
    return render_template("laporan.html", is_data=is_data, masuk=masuk, keluar=keluar,
                           ringkasan_order=ringkasan_order, preset=preset, d_from=d_from, d_to=d_to)


# --------------------------------------------------------------------------- #
# Daftar Akun (Chart of Accounts)
# --------------------------------------------------------------------------- #
@app.route("/accounts")
def accounts_list():
    db = load_db()
    rows, _, _ = trial_balance(db)
    saldo_map = {r["kode"]: (r["saldo_debit"] - r["saldo_kredit"]) for r in rows}
    used = set()
    for t in db["transactions"]:
        used.add(str(t.get("akun_debit"))); used.add(str(t.get("akun_kredit")))
    return render_template("accounts.html", accounts=sorted(db["accounts"], key=lambda x: x["kode"]),
                           saldo_map=saldo_map, used=used)


@app.route("/accounts/save", methods=["POST"])
def account_save():
    db = load_db()
    kode = request.form.get("kode", "").strip()
    nama = request.form.get("nama", "").strip()
    tipe = request.form.get("tipe", "Aset")
    old_kode = request.form.get("old_kode", "").strip()
    if not kode or not nama:
        flash("Kode dan Nama akun wajib diisi.", "danger")
        return redirect(url_for("accounts_list"))
    saldo_normal = "Kredit" if tipe in ("Kewajiban", "Modal", "Pendapatan") and kode != "302" else "Debit"
    payload = {"kode": kode, "nama": nama, "tipe": tipe,
               "saldo_normal": request.form.get("saldo_normal") or saldo_normal,
               "is_cash": request.form.get("is_cash") == "1"}
    if old_kode:
        acc = next((a for a in db["accounts"] if a["kode"] == old_kode), None) or abort(404)
        if kode != old_kode and any(a["kode"] == kode for a in db["accounts"]):
            flash(f"Kode akun {kode} sudah dipakai.", "danger")
            return redirect(url_for("accounts_list"))
        acc.update(payload)
        if kode != old_kode:  # perbarui referensi di transaksi
            for t in db["transactions"]:
                if str(t.get("akun_debit")) == old_kode:
                    t["akun_debit"] = kode
                if str(t.get("akun_kredit")) == old_kode:
                    t["akun_kredit"] = kode
        flash("Akun diperbarui.", "success")
    else:
        if any(a["kode"] == kode for a in db["accounts"]):
            flash(f"Kode akun {kode} sudah dipakai.", "danger")
            return redirect(url_for("accounts_list"))
        db["accounts"].append(payload)
        flash("Akun baru ditambahkan.", "success")
    save_db(db)
    return redirect(url_for("accounts_list"))


@app.route("/accounts/<kode>/delete", methods=["POST"])
def account_delete(kode):
    db = load_db()
    used = any(kode in (str(t.get("akun_debit")), str(t.get("akun_kredit"))) for t in db["transactions"])
    if used:
        flash("Akun tidak bisa dihapus karena sudah dipakai di transaksi/Jurnal.", "danger")
        return redirect(url_for("accounts_list"))
    db["accounts"] = [a for a in db["accounts"] if a["kode"] != kode]
    save_db(db)
    flash(f"Akun {kode} dihapus.", "warning")
    return redirect(url_for("accounts_list"))


# --------------------------------------------------------------------------- #
# Backup & Restore + Export Excel/CSV + Pengaturan
# --------------------------------------------------------------------------- #
@app.route("/backup")
def backup_page():
    db = load_db()
    export_db = {k: v for k, v in db.items() if not k.startswith("_")}
    raw = json.dumps(export_db, ensure_ascii=False, indent=2)
    info = storage_info(ping=True)
    info.update({
        "di_vercel": bool(os.environ.get("VERCEL")),
        "jml_order": len(db["orders"]), "jml_transaksi": len(db["transactions"]),
        "jml_akun": len(db["accounts"]), "ukuran_kb": round(len(raw.encode()) / 1024, 1),
        "updated_at": db.get("meta", {}).get("updated_at", "-"),
        "sha": hashlib.sha256(raw.encode()).hexdigest()[:16],
        "warning": db.get("_warning", ""),
    })
    return render_template("backup.html", info=info, raw_json=raw)


@app.route("/backup/download")
def backup_download():
    db = load_db()
    payload = json.dumps({k: v for k, v in db.items() if not k.startswith("_")},
                         ensure_ascii=False, indent=2).encode("utf-8")
    nama = f"fyymotion-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    return send_file(io.BytesIO(payload), mimetype="application/json",
                     as_attachment=True, download_name=nama)


@app.route("/backup/upload", methods=["POST"])
def backup_upload():
    raw_text = ""
    file = request.files.get("file")
    if file and file.filename:
        raw_text = file.read().decode("utf-8", errors="strict")
    elif request.form.get("json_text", "").strip():
        raw_text = request.form["json_text"]
    else:
        flash("Pilih file .json backup atau tempel isi JSON terlebih dahulu.", "danger")
        return redirect(url_for("backup_page"))
    try:
        data = json.loads(raw_text)
        # dukung juga format array murni: [ {order...}, ... ] dianggap daftar orders
        if isinstance(data, list):
            db = load_db()
            data = {**db, "orders": data}
            flash("File berupa ARRAY murni — diimpor sebagai daftar ORDERS (transaksi & akun lama tetap dipertahankan).", "warning")
        new_db = normalize_db(data)
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as e:
        flash(f"Restore GAGAL — file tidak valid: {e}", "danger")
        return redirect(url_for("backup_page"))
    save_db(new_db)
    flash(f"Restore BERHASIL! {len(new_db['orders'])} order & {len(new_db['transactions'])} transaksi dimuat dari backup.", "success")
    return redirect(url_for("dashboard"))


@app.route("/backup/reset-sample", methods=["POST"])
def backup_reset_sample():
    save_db(sample_db())
    flash("Database di-reset ke DATA CONTOH. Silakan edit/hapus sesuai usaha Anda.", "warning")
    return redirect(url_for("dashboard"))


@app.route("/backup/clear", methods=["POST"])
def backup_clear():
    if request.form.get("confirm", "").strip().lower() != "kosongkan":
        flash('Ketik kata "kosongkan" untuk konfirmasi pengosongan data.', "danger")
        return redirect(url_for("backup_page"))
    db = load_db()
    db["orders"], db["transactions"] = [], []
    save_db(db)
    flash("Semua order & transaksi dikosongkan (Daftar Akun tetap dipertahankan). Mulai dari nol!", "warning")
    return redirect(url_for("dashboard"))


@app.route("/settings/save", methods=["POST"])
def settings_save():
    db = load_db()
    for key in ("nama_usaha", "tagline", "pemilik", "wa_admin"):
        db["settings"][key] = request.form.get(key, "").strip()
    save_db(db)
    flash(f"Pengaturan usaha disimpan di {storage_info()['label']}.", "success")
    return redirect(url_for("backup_page"))


def csv_response(filename, header, rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


ORDERS_EXPORT_HEADERS = [
    "No Antrian", "Kode", "Client", "WA", "Judul", "Jenis", "Tgl Masuk", "Deadline",
    "Harga", "DP", "Sisa", "Status Bayar", "Status Order", "Progress %",
    "Google Drive Assets", "Link Preview", "Link Hasil Final",
]
TRANSACTIONS_EXPORT_HEADERS = [
    "Tanggal", "Keterangan", "Jenis", "Akun Debit", "Akun Kredit", "Jumlah", "Metode",
]
Jurnal_EXPORT_HEADERS = ["Tanggal", "Akun", "Ref/Kode", "Keterangan", "Debit", "Kredit"]
NERACA_EXPORT_HEADERS = ["Kode", "Nama Akun", "Tipe", "Saldo Debit", "Saldo Kredit"]


def orders_export_rows(db):
    return [[
        o.get("queue_no"), o.get("order_code"), o.get("client_name"), o.get("wa_number"),
        o.get("judul"), o.get("jenis_animasi"), o.get("tanggal_masuk"), o.get("deadline"),
        parse_int(o.get("harga")), parse_int(o.get("dp")), sisa_bayar(o),
        PAY_LABEL.get(o.get("status_pembayaran"), ""), STATUS_LABEL.get(o.get("status"), ""),
        parse_int(o.get("progress", 0)), o.get("drive_assets_url", ""), o.get("link_preview", ""),
        o.get("link_hasil", ""),
    ] for o in sorted_orders_by_queue(db)]


def transactions_export_rows(db):
    return [[
        t.get("tanggal"), t.get("keterangan"), JENIS_LABEL.get(t.get("jenis"), t.get("jenis")),
        account_label(db, t.get("akun_debit")), account_label(db, t.get("akun_kredit")),
        parse_int(t.get("jumlah")), t.get("metode_bayar"),
    ] for t in sorted_transactions(db)]


def Jurnal_export_rows(db):
    return [[
        r["tanggal"], r["akun"], r["kode"], r["keterangan"], r["debit"] or "", r["kredit"] or "",
    ] for r in journal_rows(db)]


def neraca_export_data(db):
    rows_data, td, tk = trial_balance(db)
    rows = [[
        r["kode"], r["nama"], r["tipe"], r["saldo_debit"] or "", r["saldo_kredit"] or "",
    ] for r in rows_data]
    return rows, td, tk


def _excel_value(value):
    if value is None:
        return ""
    if isinstance(value, str):
        text = value.strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            try:
                return date.fromisoformat(text)
            except ValueError:
                return value
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?", text):
            try:
                return datetime.fromisoformat(text.replace(" ", "T"))
            except ValueError:
                return value
    return value


def _safe_excel_name(value: str, fallback: str = "Sheet") -> str:
    name = re.sub(r"[^A-Za-z0-9_ ]", "", str(value or "")).strip() or fallback
    return name[:31]


def _safe_table_name(value: str, index: int) -> str:
    name = re.sub(r"[^A-Za-z0-9_]", "", str(value or "")) or f"Tabel{index}"
    if name[0].isdigit():
        name = f"Tabel{name}"
    suffix = f"_{index}" if index else ""
    return (name[:240 - len(suffix)] + suffix) or f"Tabel{index}"


def excel_response(filename: str, sheets: list[dict]):
    """Buat file .xlsx dengan Excel Table asli (bukan CSV yang diganti nama)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.table import Table, TableStyleInfo

    workbook = Workbook()
    workbook.remove(workbook.active)
    workbook.properties.creator = "FYY MOTION Portal"
    workbook.properties.title = "Export FYY MOTION"
    workbook.properties.created = datetime.now()

    header_fill = PatternFill("solid", fgColor="11120F")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFF9E8")
    body_font = Font(name="Calibri", size=10, color="181913")
    link_font = Font(name="Calibri", size=10, color="5B3DF5", underline="single")
    footer_fill = PatternFill("solid", fgColor="C8F169")
    footer_font = Font(name="Calibri", size=11, bold=True, color="11120F")
    thin_border = Border(
        left=Side(style="thin", color="D8D0BF"),
        right=Side(style="thin", color="D8D0BF"),
        top=Side(style="thin", color="D8D0BF"),
        bottom=Side(style="thin", color="D8D0BF"),
    )

    used_titles = set()
    for sheet_index, sheet in enumerate(sheets, start=1):
        headers = [str(header) for header in sheet.get("headers", [])]
        rows = [[_excel_value(value) for value in row] for row in sheet.get("rows", [])]
        footer_rows = [[_excel_value(value) for value in row] for row in sheet.get("footer_rows", [])]
        money_columns = set(sheet.get("money_columns", []))
        percent_columns = set(sheet.get("percent_columns", []))
        date_columns = set(sheet.get("date_columns", []))
        widths = sheet.get("widths") or {}

        title = _safe_excel_name(sheet.get("title"), f"Sheet {sheet_index}")
        base_title = title
        suffix_number = 2
        while title.lower() in used_titles:
            suffix = f" {suffix_number}"
            title = (base_title[:31 - len(suffix)] + suffix).strip()
            suffix_number += 1
        used_titles.add(title.lower())
        ws = workbook.create_sheet(title=title)
        ws.sheet_view.showGridLines = False
        ws.freeze_panes = "A2"
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.orientation = "landscape"
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.print_title_rows = "1:1"

        ws.append(headers)
        if rows:
            for row in rows:
                ws.append((list(row) + [""] * len(headers))[:len(headers)])
        else:
            # Satu baris kosong membuat range tetap menjadi Excel Table yang
            # valid meskipun database belum mempunyai data.
            ws.append([""] * len(headers))

        last_table_row = ws.max_row
        last_column = get_column_letter(max(len(headers), 1))
        table = Table(
            displayName=_safe_table_name(sheet.get("table_name") or title, sheet_index),
            ref=f"A1:{last_column}{last_table_row}",
        )
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium9",
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=True,
            showColumnStripes=False,
        )
        ws.add_table(table)

        ws.row_dimensions[1].height = 30
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = thin_border

        for row_index, row in enumerate(ws.iter_rows(min_row=2, max_row=last_table_row), start=2):
            ws.row_dimensions[row_index].height = 22
            for column_index, cell in enumerate(row, start=1):
                cell.font = body_font
                cell.border = thin_border
                cell.alignment = Alignment(
                    vertical="center",
                    wrap_text=isinstance(cell.value, str) and (len(cell.value) > 42 or "\n" in cell.value),
                )
                if isinstance(cell.value, str) and cell.value.startswith(("http://", "https://")):
                    cell.hyperlink = cell.value
                    cell.font = link_font
                header_name = headers[column_index - 1] if column_index <= len(headers) else ""
                if header_name in money_columns and isinstance(cell.value, (int, float)):
                    cell.number_format = '"Rp"#,##0'
                elif header_name in percent_columns and isinstance(cell.value, (int, float)):
                    cell.number_format = '0"%"'
                elif header_name in date_columns and isinstance(cell.value, (date, datetime)):
                    cell.number_format = "dd-mmm-yyyy"
                if isinstance(cell.value, str) and (len(cell.value) > 90 or cell.value.count("\n") >= 2):
                    ws.row_dimensions[row_index].height = max(ws.row_dimensions[row_index].height or 22, 46)

        for column_index, header in enumerate(headers, start=1):
            letter = get_column_letter(column_index)
            requested_width = widths.get(header) or widths.get(column_index)
            if requested_width:
                ws.column_dimensions[letter].width = requested_width
                continue
            max_length = len(header)
            for row in rows[:250]:
                if column_index <= len(row):
                    cell_text = str(row[column_index - 1] or "")
                    max_length = max(max_length, min(len(cell_text), 60))
            ws.column_dimensions[letter].width = max(11, min(max_length + 2, 48))

        if footer_rows:
            ws.append([""] * len(headers))
            footer_start = ws.max_row + 1
            for footer in footer_rows:
                ws.append((list(footer) + [""] * len(headers))[:len(headers)])
            for row in ws.iter_rows(min_row=footer_start, max_row=ws.max_row):
                for column_index, cell in enumerate(row, start=1):
                    cell.fill = footer_fill
                    cell.font = footer_font
                    cell.border = thin_border
                    cell.alignment = Alignment(vertical="center", wrap_text=True)
                    header_name = headers[column_index - 1] if column_index <= len(headers) else ""
                    if header_name in money_columns and isinstance(cell.value, (int, float)):
                        cell.number_format = '"Rp"#,##0'

    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return send_file(
        buffer,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )


def workbook_sheets(db):
    neraca_rows, total_debit, total_kredit = neraca_export_data(db)
    income = income_statement(db)
    laba_rows = []
    for row in income["pendapatan"]:
        laba_rows.append([
            "Pendapatan", row["kode"], row["nama"],
            parse_int(row["saldo_kredit"]) - parse_int(row["saldo_debit"]),
        ])
    for row in income["beban"]:
        laba_rows.append([
            "Beban", row["kode"], row["nama"],
            parse_int(row["saldo_debit"]) - parse_int(row["saldo_kredit"]),
        ])
    return [
        {
            "title": "Orders", "table_name": "OrdersFYY", "headers": ORDERS_EXPORT_HEADERS,
            "rows": orders_export_rows(db),
            "money_columns": {"Harga", "DP", "Sisa"},
            "percent_columns": {"Progress %"},
            "date_columns": {"Tgl Masuk", "Deadline"},
            "widths": {"WA": 18, "Judul": 38, "Google Drive Assets": 34, "Link Preview": 34, "Link Hasil Final": 34},
        },
        {
            "title": "Transaksi", "table_name": "TransaksiFYY", "headers": TRANSACTIONS_EXPORT_HEADERS,
            "rows": transactions_export_rows(db),
            "money_columns": {"Jumlah"}, "date_columns": {"Tanggal"},
            "widths": {"Keterangan": 48, "Jenis": 34, "Akun Debit": 28, "Akun Kredit": 28},
        },
        {
            "title": "Jurnal Umum", "table_name": "JurnalUmumFYY", "headers": Jurnal_EXPORT_HEADERS,
            "rows": Jurnal_export_rows(db),
            "money_columns": {"Debit", "Kredit"}, "date_columns": {"Tanggal"},
            "widths": {"Akun": 34, "Keterangan": 48},
        },
        {
            "title": "Neraca Saldo", "table_name": "NeracaSaldoFYY", "headers": NERACA_EXPORT_HEADERS,
            "rows": neraca_rows,
            "footer_rows": [["", "TOTAL", "", total_debit, total_kredit]],
            "money_columns": {"Saldo Debit", "Saldo Kredit"},
            "widths": {"Nama Akun": 42},
        },
        {
            "title": "Laba Rugi", "table_name": "LabaRugiFYY",
            "headers": ["Kategori", "Kode", "Nama Akun", "Jumlah"],
            "rows": laba_rows,
            "footer_rows": [
                ["", "", "TOTAL PENDAPATAN", income["total_pendapatan"]],
                ["", "", "TOTAL BEBAN", income["total_beban"]],
                ["", "", "LABA BERSIH", income["laba_bersih"]],
            ],
            "money_columns": {"Jumlah"}, "widths": {"Nama Akun": 42},
        },
        {
            "title": "Akun COA", "table_name": "AkunCOAFYY",
            "headers": ["Kode", "Nama Akun", "Tipe", "Saldo Normal", "Kas/Bank"],
            "rows": [[
                account.get("kode"), account.get("nama"), account.get("tipe"),
                account.get("saldo_normal"), "Ya" if account.get("is_cash") else "Tidak",
            ] for account in sorted(db.get("accounts", []), key=lambda item: str(item.get("kode", "")))],
            "widths": {"Nama Akun": 42},
        },
        {
            "title": "Clipboard", "table_name": "ClipboardFYY",
            "headers": ["Judul", "Isi Teks", "Dibuat", "Diperbarui"],
            "rows": [[
                item.get("title"), item.get("content"), item.get("created_at"), item.get("updated_at"),
            ] for item in sorted_clipboard_items(db)],
            "date_columns": {"Dibuat", "Diperbarui"},
            "widths": {"Judul": 34, "Isi Teks": 70},
        },
    ]


def _timestamp_name(prefix: str) -> str:
    return f"{prefix}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.xlsx"


@app.route("/export/workbook.xlsx")
def export_workbook_excel():
    db = load_db()
    return excel_response(_timestamp_name("fyymotion-workbook"), workbook_sheets(db))


@app.route("/export/orders.csv")
def export_orders():
    db = load_db()
    return csv_response("fyymotion-orders.csv", ORDERS_EXPORT_HEADERS, orders_export_rows(db))


@app.route("/export/orders.xlsx")
def export_orders_excel():
    db = load_db()
    return excel_response(_timestamp_name("fyymotion-orders"), [workbook_sheets(db)[0]])


@app.route("/export/transactions.csv")
def export_transactions():
    db = load_db()
    return csv_response("fyymotion-transaksi.csv", TRANSACTIONS_EXPORT_HEADERS, transactions_export_rows(db))


@app.route("/export/transactions.xlsx")
def export_transactions_excel():
    db = load_db()
    return excel_response(_timestamp_name("fyymotion-transaksi"), [workbook_sheets(db)[1]])


@app.route("/export/Jurnal.csv")
def export_jurnal():
    db = load_db()
    return csv_response("fyymotion-Jurnal-umum.csv", Jurnal_EXPORT_HEADERS, Jurnal_export_rows(db))


@app.route("/export/Jurnal.xlsx")
def export_jurnal_excel():
    db = load_db()
    return excel_response(_timestamp_name("fyymotion-Jurnal-umum"), [workbook_sheets(db)[2]])


@app.route("/export/neraca-saldo.csv")
def export_neraca():
    db = load_db()
    rows, td, tk = neraca_export_data(db)
    rows.append(["", "TOTAL", "", td, tk])
    return csv_response("fyymotion-neraca-saldo.csv", NERACA_EXPORT_HEADERS, rows)


@app.route("/export/neraca-saldo.xlsx")
def export_neraca_excel():
    db = load_db()
    return excel_response(_timestamp_name("fyymotion-neraca-saldo"), [workbook_sheets(db)[3]])


# --------------------------------------------------------------------------- #
# Teks Creator — generator preset teks Alight Motion (publik, tanpa login)
# --------------------------------------------------------------------------- #
@app.route("/teks-creator")
def teks_creator():
    """Halaman 4-langkah untuk membuat preset teks Alight Motion siap pasang."""
    db = load_db()
    profile = normalize_profile(db.get("profile"))
    wa_url = public_whatsapp_url(db)
    primary_url = profile.get("hero_primary_url") or wa_url or "#"
    return render_template(
        "teks_creator.html",
        page_title="Teks Creator — Preset Alight Motion | FYY MOTION",
        presets=PRESETS,
        preset_groups=list_presets_by_category(),
        category_labels=CATEGORY_LABELS,
        curves=CURVES,
        fonts=FONTS,
        canvas_presets=CANVAS_PRESETS,
        primary_url=primary_url,
        is_admin=bool(session.get("logged_in")),
    )


@app.route("/api/teks-creator/generate", methods=["POST"])
def teks_creator_generate():
    """Validasi input lalu bangun file .xml preset teks di memori (tanpa tulis disk)."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return {"error": "Payload tidak valid. Kirim JSON dari form Teks Creator."}, 400
    try:
        xml_text, filename = build_text_scene_xml(payload)
    except ValidationError as exc:
        return {"error": str(exc)}, 400
    except Exception:
        return {"error": "Terjadi kesalahan tak terduga saat membuat XML. Coba lagi."}, 500
    return Response(
        xml_text,
        mimetype="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --------------------------------------------------------------------------- #
# Text FX — animasi teks per huruf/kata, terinspirasi tool "Text FX" Flamo
# Creative (publik, tanpa login). Halaman terpisah di bawah /tools/.
# --------------------------------------------------------------------------- #
@app.route("/tools/text-fx")
def text_fx_tool():
    """Halaman Text FX: animasi masuk per-huruf/per-kata, 11 preset asli."""
    db = load_db()
    profile = normalize_profile(db.get("profile"))
    wa_url = public_whatsapp_url(db)
    primary_url = profile.get("hero_primary_url") or wa_url or "#"
    return render_template(
        "text_fx.html",
        page_title="Text FX — Animasi Teks Per Huruf/Kata | FYY MOTION",
        styles=list_text_fx_styles(),
        modes=TEXT_FX_MODES,
        mappings=TEXT_FX_MAPPINGS,
        fonts=FONTS,
        canvas_presets=CANVAS_PRESETS,
        curves=CURVES,
        primary_url=primary_url,
        is_admin=bool(session.get("logged_in")),
    )


@app.route("/api/tools/text-fx/generate", methods=["POST"])
def text_fx_generate():
    """Validasi input lalu bangun file .xml Text FX di memori (tanpa tulis disk)."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return {"error": "Payload tidak valid. Kirim JSON dari form Text FX."}, 400
    try:
        xml_text, filename = build_text_fx_xml(payload)
    except ValidationError as exc:
        return {"error": str(exc)}, 400
    except Exception:
        return {"error": "Terjadi kesalahan tak terduga saat membuat XML. Coba lagi."}, 500
    return Response(
        xml_text,
        mimetype="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --------------------------------------------------------------------------- #
# FYY MOTION Academy — landing kelas dasar motion graphic (publik)
# --------------------------------------------------------------------------- #
@app.route("/academy")
def academy():
    wa_number = re.sub(r"\D", "", os.environ.get("WA_NUMBER", ""))
    return render_template(
        "academy.html",
        page_title="FYY MOTION Academy — Kelas Dasar Motion Graphic",
        wa_configured=bool(wa_number),
    )


@app.route("/daftar")
def daftar_academy():
    """Redirect 302 ke WhatsApp dengan pesan tetap 'J-ACADEMY'."""
    wa_number = re.sub(r"\D", "", os.environ.get("WA_NUMBER", ""))
    if not wa_number:
        return render_template("wa_not_configured.html"), 503
    return redirect(f"https://wa.me/{wa_number}?text={quote('J-ACADEMY')}", code=302)


@app.errorhandler(404)
def not_found(e):
    if session.get("logged_in"):
        flash("Halaman tidak ditemukan.", "warning")
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.errorhandler(413)
def too_big(e):
    flash("File backup terlalu besar (maks 8 MB).", "danger")
    return redirect(url_for("backup_page"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
