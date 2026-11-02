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
from urllib.parse import urlparse

from flask import (
    Flask, Response, abort, flash, g, redirect, render_template,
    request, send_file, session, url_for,
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


def empty_db() -> dict:
    return {
        "meta": {"app": "FYY MOTION Portal", "version": 1,
                 "created_at": now_iso(), "updated_at": now_iso()},
        "settings": {"nama_usaha": "FYY MOTION", "tagline": "Jasa Pembuatan Animasi Motion Graphic",
                     "pemilik": "", "wa_admin": "", "mata_uang": "IDR"},
        "accounts": deepcopy(DEFAULT_ACCOUNTS),
        "orders": [],
        "transactions": [],
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
    base = empty_db()
    base.update({k: data[k] for k in ("accounts", "orders", "transactions")})
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
    for collection in ("accounts", "orders", "transactions"):
        _sync_collection(db_mongo, collection, db.get(collection, []))
    db_mongo["app_state"].replace_one(
        {"_id": "state"},
        {"_id": "state", "meta": db.get("meta", {}), "settings": db.get("settings", {})},
        upsert=True,
    )


def _load_db_mongo() -> dict:
    db_mongo = get_mongo_db()
    state = db_mongo["app_state"].find_one({"_id": "state"}, {"_id": 0})
    counts = {name: db_mongo[name].estimated_document_count()
              for name in ("accounts", "orders", "transactions")}
    if state is None and sum(counts.values()) == 0:
        seed = _load_seed_db()
        _save_db_mongo(seed)
        return normalize_db(seed)

    data = {
        "meta": (state or {}).get("meta", {}),
        "settings": (state or {}).get("settings", {}),
        "accounts": list(db_mongo["accounts"].find({}, {"_id": 0}).sort("kode", 1)),
        "orders": list(db_mongo["orders"].find({}, {"_id": 0})),
        "transactions": list(db_mongo["transactions"].find({}, {"_id": 0})),
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
        "STATUS_ORDER": STATUS_ORDER, "STATUS_LABEL": STATUS_LABEL, "STATUS_BADGE": STATUS_BADGE,
        "STATUS_PEMBAYARAN": STATUS_PEMBAYARAN, "PAY_LABEL": PAY_LABEL, "PAY_BADGE": PAY_BADGE,
        "JENIS_ANIMASI": JENIS_ANIMASI, "PRIORITAS": PRIORITAS, "METODE_BAYAR": METODE_BAYAR,
        "JENIS_TRANSAKSI": JENIS_TRANSAKSI, "JENIS_LABEL": JENIS_LABEL, "JENIS_PRESET": JENIS_PRESET,
        "TIPE_AKUN": TIPE_AKUN,
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
    if endpoint in ("static", "login", "health"):
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
# Dashboard
# --------------------------------------------------------------------------- #
@app.route("/")
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
# Backup & Restore + Export CSV + Pengaturan
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


@app.route("/export/orders.csv")
def export_orders():
    db = load_db()
    rows = [[o.get("queue_no"), o.get("order_code"), o.get("client_name"), o.get("wa_number"),
             o.get("judul"), o.get("jenis_animasi"), o.get("tanggal_masuk"), o.get("deadline"),
             parse_int(o.get("harga")), parse_int(o.get("dp")), sisa_bayar(o),
             PAY_LABEL.get(o.get("status_pembayaran"), ""), STATUS_LABEL.get(o.get("status"), ""),
             o.get("progress", 0), o.get("drive_assets_url", ""), o.get("link_preview", ""),
             o.get("link_hasil", "")] for o in sorted_orders_by_queue(db)]
    return csv_response("fyymotion-orders.csv",
                        ["No Antrian", "Kode", "Client", "WA", "Judul", "Jenis", "Tgl Masuk", "Deadline",
                         "Harga", "DP", "Sisa", "Status Bayar", "Status Order", "Progress%",
                         "Google Drive Assets", "Link Preview", "Link Hasil Final"], rows)


@app.route("/export/transactions.csv")
def export_transactions():
    db = load_db()
    rows = [[t.get("tanggal"), t.get("keterangan"), JENIS_LABEL.get(t.get("jenis"), t.get("jenis")),
             account_label(db, t.get("akun_debit")), account_label(db, t.get("akun_kredit")),
             parse_int(t.get("jumlah")), t.get("metode_bayar")] for t in sorted_transactions(db)]
    return csv_response("fyymotion-transaksi.csv",
                        ["Tanggal", "Keterangan", "Jenis", "Akun Debit", "Akun Kredit", "Jumlah", "Metode"], rows)


@app.route("/export/Jurnal.csv")
def export_jurnal():
    db = load_db()
    rows = [[r["tanggal"], r["akun"], r["kode"], r["keterangan"], r["debit"] or "", r["kredit"] or ""]
            for r in journal_rows(db)]
    return csv_response("fyymotion-Jurnal-umum.csv",
                        ["Tanggal", "Akun", "Ref/Kode", "Keterangan", "Debit", "Kredit"], rows)


@app.route("/export/neraca-saldo.csv")
def export_neraca():
    db = load_db()
    rows_data, td, tk = trial_balance(db)
    rows = [[r["kode"], r["nama"], r["tipe"], r["saldo_debit"] or "", r["saldo_kredit"] or ""] for r in rows_data]
    rows.append(["", "TOTAL", "", td, tk])
    return csv_response("fyymotion-neraca-saldo.csv",
                        ["Kode", "Nama Akun", "Tipe", "Saldo Debit", "Saldo Kredit"], rows)


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
