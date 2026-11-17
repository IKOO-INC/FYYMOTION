"""
FYY MOTION Academy — lapisan penyimpanan MongoDB Atlas (database terpisah).
===========================================================================
Berbeda dari `app.py` (yang memakai pola "satu dokumen besar" untuk data
akuntansi/order lama), modul Academy memakai koleksi MongoDB asli dengan
index — karena datanya tumbuh terus (OTP, transaksi, progres belajar) dan
butuh query per-dokumen yang efisien & aman secara konkuren di lingkungan
serverless Vercel.

- Database terpisah: nama default "fyymotion_academy" (bisa dioverride lewat
  env ACADEMY_MONGODB_DB_NAME), memakai URI yang SAMA dengan aplikasi utama
  (env MONGODB_URI) — hanya nama database-nya beda, supaya tidak perlu
  cluster/URI baru.
- Koneksi (MongoClient) di-cache secara global per proses (module-level
  singleton) sesuai pola yang sudah dipakai `app.py`, supaya tidak boros
  koneksi di tiap invocation function serverless.
- Tidak ada fallback ke file lokal/JSON untuk data Academy: kalau
  MONGODB_URI belum diset, fitur Academy menampilkan halaman
  "belum dikonfigurasi" (lihat `academy_routes.py`) alih-alih mencoba
  menyimpan ke disk — sesuai arahan "jangan simpan state di memori/file
  lokal" untuk lingkungan serverless.
"""

from __future__ import annotations

import os
import threading
import uuid
from datetime import datetime

MONGODB_URI = os.environ.get("MONGODB_URI", "").strip()
ACADEMY_DB_NAME = os.environ.get("ACADEMY_MONGODB_DB_NAME", "fyymotion_academy").strip() or "fyymotion_academy"

_CLIENT = None
_DB = None
_READY = False
_LOCK = threading.Lock()


def is_configured() -> bool:
    return bool(MONGODB_URI)


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    # Naive UTC datetime -- cocok dengan perilaku round-trip BSON/pymongo
    # (MongoDB selalu menyimpan UTC, dan pymongo secara default mengembalikan
    # datetime naive saat dibaca kembali). Memakai aware datetime di sini akan
    # memicu TypeError saat dibandingkan dengan nilai yang baru dibaca dari DB.
    return datetime.utcnow()


class AcademyNotConfigured(RuntimeError):
    """MONGODB_URI belum terpasang di environment."""


def get_db():
    """Database MongoDB khusus Academy (koneksi di-cache, dipakai ulang)."""
    global _CLIENT, _DB, _READY
    if _DB is not None:
        return _DB
    if not MONGODB_URI:
        raise AcademyNotConfigured("MONGODB_URI belum terpasang di environment.")
    with _LOCK:
        if _DB is not None:
            return _DB
        from pymongo import MongoClient

        client = MongoClient(
            MONGODB_URI,
            serverSelectionTimeoutMS=10000,
            connectTimeoutMS=10000,
            socketTimeoutMS=30000,
            retryWrites=True,
            appname="FYYMOTIONAcademy",
        )
        client.admin.command("ping")
        db = client[ACADEMY_DB_NAME]
        if not _READY:
            _ensure_indexes(db)
            _READY = True
        _CLIENT = client
        _DB = db
        return db


def _ensure_indexes(db):
    db["users"].create_index([("email", 1)], unique=True, name="uniq_email")
    db["otps"].create_index([("expires_at", 1)], expireAfterSeconds=0, name="ttl_expires")
    db["otps"].create_index([("email", 1), ("purpose", 1)], name="email_purpose")
    db["courses"].create_index([("slug", 1)], unique=True, name="uniq_slug")
    db["courses"].create_index([("status", 1), ("urutan", 1)], name="status_urutan")
    db["lessons"].create_index([("course_id", 1), ("urutan", 1)], name="course_urutan")
    db["enrollments"].create_index([("user_id", 1), ("course_id", 1)], unique=True, name="uniq_enrollment")
    db["transactions"].create_index([("kode_transaksi", 1)], unique=True, name="uniq_kode")
    db["transactions"].create_index([("user_id", 1), ("course_id", 1), ("status", 1)], name="user_course_status")
    db["transactions"].create_index([("status", 1), ("created_at", -1)], name="status_created")
    db["progress"].create_index([("user_id", 1), ("lesson_id", 1)], unique=True, name="uniq_progress")
    db["announcements"].create_index([("aktif", 1), ("pinned", -1), ("created_at", -1)], name="aktif_pinned")
    db["rate_limits"].create_index([("expires_at", 1)], expireAfterSeconds=0, name="ttl_ratelimit")


# --------------------------------------------------------------------------- #
# Collection getters
# --------------------------------------------------------------------------- #
def col_users():
    return get_db()["users"]


def col_otps():
    return get_db()["otps"]


def col_courses():
    return get_db()["courses"]


def col_lessons():
    return get_db()["lessons"]


def col_enrollments():
    return get_db()["enrollments"]


def col_transactions():
    return get_db()["transactions"]


def col_progress():
    return get_db()["progress"]


def col_announcements():
    return get_db()["announcements"]


def col_rate_limits():
    return get_db()["rate_limits"]


def reset_cache_for_tests():
    """Dipakai hanya oleh skrip pengujian lokal untuk memaksa re-koneksi."""
    global _CLIENT, _DB, _READY
    _CLIENT = None
    _DB = None
    _READY = False
