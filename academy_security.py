"""
FYY MOTION Academy — util keamanan: hash password/OTP, rate limit, validasi.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import smtplib
import urllib.error
import urllib.request
from datetime import timedelta
from email.mime.text import MIMEText

from werkzeug.security import check_password_hash, generate_password_hash

from academy_db import col_rate_limits, new_id, utcnow

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# --------------------------------------------------------------------------- #
# Password & OTP hashing
# --------------------------------------------------------------------------- #
def hash_password(raw: str) -> str:
    return generate_password_hash(raw, method="pbkdf2:sha256", salt_length=16)


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return check_password_hash(hashed, raw)
    except Exception:
        return False


def generate_otp_code() -> str:
    return f"{secrets.randbelow(1000000):06d}"


def hash_otp(code: str) -> str:
    return generate_password_hash(code, method="pbkdf2:sha256", salt_length=8)


def verify_otp_hash(code: str, hashed: str) -> bool:
    try:
        return check_password_hash(hashed, code)
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Validasi input sederhana
# --------------------------------------------------------------------------- #
def is_valid_email(email: str) -> bool:
    email = (email or "").strip()
    return bool(email) and len(email) <= 190 and bool(EMAIL_RE.match(email))


def is_valid_password(pw: str) -> bool:
    return bool(pw) and 6 <= len(pw) <= 128


def clean_text(value: str, max_len: int = 500) -> str:
    value = (value or "").strip()
    value = re.sub(r"\s+", " ", value)
    return value[:max_len]


# --------------------------------------------------------------------------- #
# Rate limiting berbasis MongoDB (aman untuk lingkungan serverless multi-instance)
# --------------------------------------------------------------------------- #
def rate_limit_hit(key: str, max_hits: int, window_seconds: int) -> bool:
    """Kembalikan True jika request BOLEH diteruskan (belum melewati batas).

    Memakai koleksi `rate_limits` dengan upsert atomik supaya aman dipakai
    bersamaan oleh beberapa instance serverless.
    """
    col = col_rate_limits()
    now = utcnow()
    doc = col.find_one({"_id": key})
    if not doc or doc.get("expires_at") and doc["expires_at"] < now:
        col.update_one(
            {"_id": key},
            {"$set": {"count": 1, "expires_at": now + timedelta(seconds=window_seconds)}},
            upsert=True,
        )
        return True
    if doc.get("count", 0) >= max_hits:
        return False
    col.update_one({"_id": key}, {"$inc": {"count": 1}})
    return True


# --------------------------------------------------------------------------- #
# Pengiriman email OTP via SMTP (stdlib smtplib, tanpa dependensi tambahan)
# --------------------------------------------------------------------------- #
def smtp_configured() -> bool:
    return bool(os.environ.get("SMTP_HOST") and os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASS"))


def send_email(to_email: str, subject: str, body: str) -> tuple[bool, str]:
    """Kirim email teks biasa. Return (sukses, pesan_error_jika_gagal)."""
    host = os.environ.get("SMTP_HOST", "").strip()
    port = int(os.environ.get("SMTP_PORT", "587") or "587")
    user = os.environ.get("SMTP_USER", "").strip()
    pw = os.environ.get("SMTP_PASS", "").strip()
    sender = os.environ.get("SMTP_FROM", user).strip() or user
    if not (host and user and pw):
        return False, "SMTP belum dikonfigurasi di server."
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = to_email
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=15) as server:
                server.login(user, pw)
                server.sendmail(sender, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(user, pw)
                server.sendmail(sender, [to_email], msg.as_string())
        return True, ""
    except Exception as exc:  # pragma: no cover - butuh SMTP nyata
        return False, str(exc)


# --------------------------------------------------------------------------- #
# Fyymail (Fyymotion Auth) — layanan OTP email terpusat (IKOO-INC/fyymail)
# Dipakai sebagai metode pengiriman OTP UTAMA. Sejak update Fyymail, layanan
# ini PRIVATE TANPA API KEY — cukup FYMAIL_URL. Kalau URL kosong (misal
# sengaja dikosongkan di env), kode otomatis jatuh ke mode SMTP langsung /
# dev-mode (lihat academy_routes.py::_issue_otp) supaya platform tetap bisa
# dipakai.
# --------------------------------------------------------------------------- #
FYMAIL_URL = os.environ.get("FYMAIL_URL", "https://auth-fyymotion.vercel.app").strip().rstrip("/")
FYMAIL_APP_NAME = "FYY MOTION Academy"
FYMAIL_TIMEOUT = 10


def fyymail_configured() -> bool:
    return bool(FYMAIL_URL)


def _fyymail_request(path: str, payload: dict) -> tuple[bool, dict, int]:
    """POST ke Fyymail (tanpa apikey — layanan private tanpa autentikasi).

    Return (ok_koneksi, data_json, status_code).
    """
    url = f"{FYMAIL_URL}{path}"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=FYMAIL_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8") or "{}")
            return True, data, resp.status
    except urllib.error.HTTPError as exc:
        try:
            data = json.loads(exc.read().decode("utf-8") or "{}")
        except Exception:
            data = {}
        return True, data, exc.code
    except Exception as exc:  # timeout / DNS / koneksi putus, dsb.
        return False, {"error": str(exc)}, 0


def fyymail_send_otp(email: str, purpose_label: str) -> tuple[bool, str, str]:
    """Minta Fyymail kirim OTP ke email.

    Return (sukses, pesan_error_jika_gagal, preview_url_jika_mode_temp_mail).
    `preview_url` hanya terisi kalau Fyymail sedang jalan mode Ethereal
    (TEMP_MAIL=true di sisi Fyymail) — email tidak benar-benar masuk inbox,
    jadi kita tampilkan link pratinjau supaya alur tetap bisa diuji.
    """
    ok, data, status = _fyymail_request("/api/send-otp", {
        "email": email, "appName": FYMAIL_APP_NAME, "purpose": purpose_label,
    })
    if not ok:
        return False, "Tidak bisa menghubungi layanan email (Fyymail). Coba lagi sebentar lagi.", ""
    if status == 200 and data.get("success"):
        return True, "", data.get("previewUrl") or ""
    if status == 429:
        return False, data.get("error") or "Terlalu banyak permintaan OTP. Coba lagi dalam beberapa menit.", ""
    if status == 502:
        return False, "Layanan email sedang bermasalah mengirim pesan. Coba lagi sebentar lagi.", ""
    return False, data.get("error") or "Gagal mengirim kode OTP lewat email. Coba lagi sebentar lagi.", ""


def fyymail_verify_otp(email: str, otp: str) -> tuple[bool, str]:
    """Verifikasi OTP lewat Fyymail. Return (valid, pesan_error_jika_tidak_valid).

    Fyymail selalu balas HTTP 200 untuk hasil verifikasi (valid true/false),
    jadi kita baca field `valid`/`error` dari body, bukan status code.
    """
    ok, data, status = _fyymail_request("/api/verify-otp", {
        "email": email, "otp": otp, "appName": FYMAIL_APP_NAME,
    })
    if not ok:
        return False, "Tidak bisa menghubungi layanan email (Fyymail). Coba lagi sebentar lagi."
    if data.get("valid"):
        return True, ""
    return False, data.get("error") or "Kode OTP tidak valid."


def otp_email_body(nama: str, code: str, purpose_label: str) -> str:
    return (
        f"Halo {nama or 'Sahabat FYY MOTION'},\n\n"
        f"Kode OTP {purpose_label} kamu di FYY MOTION Academy adalah:\n\n"
        f"    {code}\n\n"
        "Kode ini berlaku 10 menit dan hanya bisa dipakai 1 kali. "
        "Jangan bagikan kode ini ke siapa pun, termasuk pihak yang mengaku dari FYY MOTION.\n\n"
        "Jika kamu tidak merasa meminta kode ini, abaikan saja email ini.\n\n"
        "Salam,\nTim FYY MOTION Academy"
    )


# --------------------------------------------------------------------------- #
# Konversi URL video -> embed (YouTube / Google Drive / Vimeo)
# --------------------------------------------------------------------------- #
def url_to_embed(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    # Sudah berupa embed URL
    if "/embed/" in url or "player.vimeo.com" in url:
        return url
    # YouTube
    yt_patterns = [
        r"youtu\.be/([A-Za-z0-9_-]{6,})",
        r"youtube\.com/watch\?v=([A-Za-z0-9_-]{6,})",
        r"youtube\.com/shorts/([A-Za-z0-9_-]{6,})",
        r"youtube\.com/live/([A-Za-z0-9_-]{6,})",
    ]
    for pat in yt_patterns:
        m = re.search(pat, url)
        if m:
            return f"https://www.youtube.com/embed/{m.group(1)}"
    # Google Drive: https://drive.google.com/file/d/<id>/view...
    m = re.search(r"drive\.google\.com/file/d/([A-Za-z0-9_-]+)", url)
    if m:
        return f"https://drive.google.com/file/d/{m.group(1)}/preview"
    m = re.search(r"drive\.google\.com/open\?id=([A-Za-z0-9_-]+)", url)
    if m:
        return f"https://drive.google.com/file/d/{m.group(1)}/preview"
    # Vimeo
    m = re.search(r"vimeo\.com/(\d+)", url)
    if m:
        return f"https://player.vimeo.com/video/{m.group(1)}"
    # Tidak dikenali -> kembalikan apa adanya (admin tetap bisa pakai iframe custom)
    return url


def new_kode_transaksi(tanggal) -> str:
    """Format ACD-YYMMDD-XXXXX (XXXXX = 5 digit acak unik)."""
    yymmdd = tanggal.strftime("%y%m%d")
    suffix = f"{secrets.randbelow(100000):05d}"
    return f"ACD-{yymmdd}-{suffix}"
