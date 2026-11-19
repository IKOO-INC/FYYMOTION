"""
FYY MOTION Academy — platform belajar lengkap (registrasi, login OTP email,
dashboard siswa, ruang belajar, pembayaran QRIS manual via WhatsApp, dan
panel admin akademi).

Modul ini didaftarkan ke aplikasi Flask utama lewat `register_academy_routes(app, **helpers)`
dipanggil dari `app.py`, supaya tidak terjadi circular import (modul ini tidak
mengimpor apa pun dari `app.py`).

Keamanan & aturan bisnis penting (lihat juga academy_db.py / academy_security.py):
- Semua data tersimpan di MongoDB (koleksi terpisah di database `fyymotion_academy`),
  TIDAK ada state di memori proses / file lokal (serverless-safe).
- Password & OTP selalu di-hash (pbkdf2:sha256) dan diverifikasi SENDIRI dari
  MongoDB kita (persisten) — TIDAK pernah bergantung ke penyimpanan/verifikasi
  OTP bawaan Fyymail (yang bisa in-memory/hilang di serverless). OTP kedaluwarsa
  1 jam, maksimal 5 kali percobaan, cooldown kirim ulang 60 detik, serta
  rate-limit per email/IP.
- Harga transaksi SELALU diambil dari database course di server — tidak pernah
  dipercaya dari input client.
- Akses "Ruang Belajar" (daftar pelajaran) diverifikasi di backend: 403 bila
  user belum terdaftar (enrolled) di course tersebut.
- TIDAK ADA fitur upload bukti bayar — konfirmasi pembayaran murni lewat
  redirect WhatsApp ke admin.
- Approve/reject transaksi oleh admin bersifat idempotent (tidak bisa dobel approve).
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import secrets
from datetime import date, datetime, timedelta
from functools import wraps
from urllib.parse import quote

from flask import abort, flash, jsonify, redirect, render_template, request, session, url_for

import academy_db as adb
from academy_security import (
    clean_text,
    fyymail_configured,
    fyymail_send_otp,
    generate_otp_code,
    hash_otp,
    hash_password,
    is_valid_email,
    is_valid_password,
    new_kode_transaksi,
    otp_email_body,
    rate_limit_hit,
    send_email,
    smtp_configured,
    url_to_embed,
    verify_otp_hash,
    verify_password,
)

# OTP selalu disimpan (hash) & diverifikasi di MongoDB kita sendiri — TIDAK
# pernah bergantung ke penyimpanan/verifikasi OTP bawaan Fyymail, karena
# Fyymail bisa menyimpan OTP di memori proses serverless (hilang kalau
# request verify mendarat di instance berbeda dari request kirim, bikin OTP
# yang baru beberapa detik terlihat "kedaluwarsa"/"tidak ditemukan" padahal
# belum lewat TTL). Fyymail dipakai MURNI sebagai jalur pengiriman email.
OTP_TTL_SECONDS = 60 * 60  # 1 jam
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN = 60


# --------------------------------------------------------------------------- #
# Util kecil lokal (sengaja tidak impor dari app.py supaya tidak circular)
# --------------------------------------------------------------------------- #
def _csrf_token() -> str:
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


def _client_ip() -> str:
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.remote_addr or "-"


def _not_configured_response():
    return render_template("academy_setup_required.html"), 503


def academy_db_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not adb.is_configured():
            return _not_configured_response()
        try:
            return fn(*args, **kwargs)
        except adb.AcademyNotConfigured:
            return _not_configured_response()
    return wrapper


def academy_login_required(fn):
    @wraps(fn)
    @academy_db_required
    def wrapper(*args, **kwargs):
        uid = session.get("academy_user_id")
        if not uid:
            flash("Silakan login dulu untuk mengakses halaman ini.", "warning")
            return redirect(url_for("academy_login_page", next=request.path))
        user = adb.col_users().find_one({"_id": uid})
        if not user:
            session.pop("academy_user_id", None)
            flash("Sesi login tidak ditemukan, silakan login kembali.", "warning")
            return redirect(url_for("academy_login_page"))
        if user.get("status") == "blocked":
            session.pop("academy_user_id", None)
            flash("Akun kamu diblokir. Hubungi admin FYY MOTION Academy untuk info lebih lanjut.", "danger")
            return redirect(url_for("academy_login_page"))
        request.academy_user = user  # type: ignore[attr-defined]
        return fn(*args, **kwargs)
    return wrapper


def academy_admin_required(fn):
    """Panel admin akademi memakai ulang sesi admin yang sudah ada (session['logged_in'])."""
    @wraps(fn)
    @academy_db_required
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            flash("Silakan login sebagai admin untuk mengakses panel ini.", "warning")
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper


def _current_user():
    return getattr(request, "academy_user", None)


def _wa_admin_number() -> str:
    raw = os.environ.get("WA_ADMIN_NUMBER", "").strip() or os.environ.get("WA_NUMBER", "")
    return re.sub(r"\D", "", raw)


def _qris_image_url() -> str:
    return os.environ.get("GOPAY_QRIS_IMAGE_URL", "").strip()


# --------------------------------------------------------------------------- #
# Helper data
# --------------------------------------------------------------------------- #
def _course_public(c: dict) -> dict:
    return {
        "id": c["_id"],
        "slug": c["slug"],
        "judul": c.get("judul", ""),
        "deskripsi": c.get("deskripsi", ""),
        "harga": int(c.get("harga", 0)),
        "thumbnail_url": c.get("thumbnail_url", ""),
        "status": c.get("status", "draft"),
        "urutan": c.get("urutan", 0),
        "jumlah_pelajaran": adb.col_lessons().count_documents({"course_id": c["_id"]}),
    }


def _is_enrolled(user_id: str, course_id: str) -> bool:
    return adb.col_enrollments().find_one({"user_id": user_id, "course_id": course_id}) is not None


def _course_progress(user_id: str, course_id: str) -> dict:
    lessons = list(adb.col_lessons().find({"course_id": course_id}).sort("urutan", 1))
    total = len(lessons)
    if total == 0:
        return {"total": 0, "selesai": 0, "persen": 0, "lessons": []}
    done_ids = {
        p["lesson_id"]
        for p in adb.col_progress().find({"user_id": user_id, "course_id": course_id, "completed": True})
    }
    selesai = len(done_ids)
    for l in lessons:
        l["selesai"] = l["_id"] in done_ids
    return {"total": total, "selesai": selesai, "persen": round(selesai * 100 / total), "lessons": lessons}


# --------------------------------------------------------------------------- #
# REGISTER + OTP
# --------------------------------------------------------------------------- #
def academy_register_view():
    if session.get("academy_user_id"):
        return redirect(url_for("academy_dashboard"))
    if request.method == "POST":
        nama = clean_text(request.form.get("nama", ""), 120)
        email = (request.form.get("email", "") or "").strip().lower()
        password = request.form.get("password", "") or ""
        confirm = request.form.get("confirm_password", "") or ""

        if not nama or len(nama) < 3:
            flash("Nama lengkap minimal 3 karakter.", "danger")
        elif not is_valid_email(email):
            flash("Format email tidak valid.", "danger")
        elif not is_valid_password(password):
            flash("Password minimal 6 karakter.", "danger")
        elif password != confirm:
            flash("Konfirmasi password tidak sama.", "danger")
        elif not rate_limit_hit(f"register:{_client_ip()}", max_hits=10, window_seconds=600):
            flash("Terlalu banyak percobaan registrasi. Coba lagi beberapa menit lagi.", "danger")
        else:
            existing = adb.col_users().find_one({"email": email})
            if existing and existing.get("email_verified"):
                flash("Email ini sudah terdaftar. Silakan login.", "warning")
                return redirect(url_for("academy_login_page"))
            now = adb.utcnow()
            if existing:
                adb.col_users().update_one(
                    {"_id": existing["_id"]},
                    {"$set": {"nama": nama, "password_hash": hash_password(password), "updated_at": now}},
                )
                user_id = existing["_id"]
            else:
                user_id = adb.new_id()
                adb.col_users().insert_one({
                    "_id": user_id,
                    "nama": nama,
                    "email": email,
                    "password_hash": hash_password(password),
                    "status": "active",
                    "email_verified": False,
                    "created_at": now,
                    "updated_at": now,
                    "last_login_at": None,
                })
            ok, err = _issue_otp(email, "register")
            if not ok:
                flash(err, "danger")
            else:
                session["academy_pending_email"] = email
                session["academy_pending_purpose"] = "register"
                flash("Kode OTP sudah dikirim ke email kamu. Cek inbox/spam ya!", "success")
                return redirect(url_for("academy_verify_view"))
    return render_template("academy_register.html", page_title="Daftar Akun — FYY MOTION Academy")


def _otp_delivery_mode() -> str:
    """Urutan prioritas pengiriman OTP: Fyymail (layanan terpusat) -> SMTP
    langsung -> mode developer (tampil di layar, hanya kalau dua-duanya belum
    dikonfigurasi admin)."""
    if fyymail_configured():
        return "fyymail"
    if smtp_configured():
        return "smtp"
    return "dev"


def _issue_otp(email: str, purpose: str) -> tuple[bool, str]:
    if not rate_limit_hit(f"otp:{email}:{purpose}", max_hits=5, window_seconds=600):
        return False, "Terlalu banyak permintaan OTP untuk email ini. Coba lagi dalam beberapa menit."
    last = adb.col_otps().find_one({"email": email, "purpose": purpose}, sort=[("created_at", -1)])
    now = adb.utcnow()
    if last and (now - last["created_at"]).total_seconds() < OTP_RESEND_COOLDOWN:
        sisa = int(OTP_RESEND_COOLDOWN - (now - last["created_at"]).total_seconds())
        return False, f"Tunggu {sisa} detik lagi sebelum minta kode OTP baru."

    label = {"register": "verifikasi akun", "forgot": "reset password", "login": "login"}.get(purpose, "verifikasi")
    mode = _otp_delivery_mode()

    # Kode OTP SELALU kita generate, hash, simpan, DAN verifikasi sendiri di
    # MongoDB (persisten, aman di lingkungan serverless multi-instance) —
    # Fyymail (kalau dipakai) hanya jadi jalur PENGIRIMAN email, bukan
    # penyimpan/pemverifikasi kode. Ini menghindari bug "OTP langsung
    # kedaluwarsa/tidak ditemukan" yang muncul kalau verifikasi bergantung ke
    # penyimpanan in-memory Fyymail di instance serverless yang berbeda.
    code = generate_otp_code()
    ttl_minutes = max(1, OTP_TTL_SECONDS // 60)

    if mode == "fyymail":
        ok, err, preview_url = fyymail_send_otp(email, label, otp_code=code)
        if not ok:
            return False, err
        if preview_url:
            # Fyymail sedang jalan mode temp-mail (Ethereal) — email tidak
            # benar-benar masuk inbox, jadi tampilkan link pratinjau di halaman
            # verifikasi supaya alur tetap bisa diuji/dipakai.
            session["academy_otp_preview_url"] = preview_url
        else:
            session.pop("academy_otp_preview_url", None)
    elif mode == "smtp":
        sent, err = send_email(email, "Kode OTP FYY MOTION Academy", otp_email_body("", code, label, ttl_minutes))
        if not sent:
            return False, f"Gagal mengirim email OTP: {err}"
    else:
        # Mode developer: Fyymail & SMTP belum dikonfigurasi admin. Supaya alur
        # tetap bisa dipakai/diuji, kode OTP disimpan ke session agar ditampilkan
        # di halaman verifikasi dengan peringatan jelas. Di produksi dengan
        # FYMAIL_URL atau SMTP terpasang, jalur ini tidak pernah dipakai.
        session["academy_dev_otp"] = code

    adb.col_otps().insert_one({
        "_id": adb.new_id(),
        "email": email,
        "purpose": purpose,
        "provider": mode,
        "otp_hash": hash_otp(code),
        "attempts": 0,
        "max_attempts": OTP_MAX_ATTEMPTS,
        "consumed": False,
        "created_at": now,
        "expires_at": now + timedelta(seconds=OTP_TTL_SECONDS),
    })
    return True, ""


def _verify_otp(email: str, purpose: str, code: str) -> tuple[bool, str]:
    """Verifikasi kode OTP — SELALU dari hash yang kita simpan sendiri di
    MongoDB (berlaku untuk semua mode pengiriman: fyymail, smtp, developer),
    tidak pernah bergantung ke layanan eksternal untuk keputusan valid/tidak."""
    otp_doc = adb.col_otps().find_one(
        {"email": email, "purpose": purpose, "consumed": False}, sort=[("created_at", -1)]
    )
    now = adb.utcnow()
    if not otp_doc:
        return False, "Kode OTP tidak ditemukan. Minta kode baru ya."
    if otp_doc["expires_at"] < now:
        return False, "Kode OTP sudah kedaluwarsa. Minta kode baru ya."

    if otp_doc.get("attempts", 0) >= otp_doc.get("max_attempts", OTP_MAX_ATTEMPTS):
        return False, "Kode OTP sudah mencapai batas percobaan. Minta kode baru ya."
    if not verify_otp_hash(code, otp_doc.get("otp_hash", "")):
        adb.col_otps().update_one({"_id": otp_doc["_id"]}, {"$inc": {"attempts": 1}})
        sisa = otp_doc.get("max_attempts", OTP_MAX_ATTEMPTS) - otp_doc.get("attempts", 0) - 1
        return False, f"Kode OTP salah. Sisa percobaan: {max(sisa, 0)}."
    adb.col_otps().update_one({"_id": otp_doc["_id"]}, {"$set": {"consumed": True}})
    return True, ""


def academy_verify_view():
    email = session.get("academy_pending_email")
    purpose = session.get("academy_pending_purpose", "register")
    if not email:
        flash("Tidak ada proses verifikasi aktif. Silakan daftar/login ulang.", "warning")
        return redirect(url_for("academy_register_view"))
    if request.method == "POST":
        code = (request.form.get("otp", "") or "").strip()
        if not rate_limit_hit(f"otp-check:{email}", max_hits=10, window_seconds=600):
            flash("Terlalu banyak percobaan verifikasi. Coba lagi beberapa menit lagi.", "danger")
        else:
            ok, err = _verify_otp(email, purpose, code)
            if not ok:
                flash(err, "danger")
            else:
                now = adb.utcnow()
                session.pop("academy_pending_email", None)
                session.pop("academy_pending_purpose", None)
                session.pop("academy_dev_otp", None)
                session.pop("academy_otp_preview_url", None)
                if purpose == "register":
                    adb.col_users().update_one({"email": email}, {"$set": {"email_verified": True, "updated_at": now}})
                    flash("Email berhasil diverifikasi! Silakan login.", "success")
                    return redirect(url_for("academy_login_page"))
                if purpose == "forgot":
                    session["academy_reset_email"] = email
                    flash("Verifikasi berhasil. Silakan buat password baru.", "success")
                    return redirect(url_for("academy_reset_password_view"))
    return render_template(
        "academy_verify_otp.html",
        page_title="Verifikasi OTP — FYY MOTION Academy",
        email=email,
        purpose=purpose,
        dev_otp=session.get("academy_dev_otp") if _otp_delivery_mode() == "dev" else None,
        otp_mode=_otp_delivery_mode(),
        otp_preview_url=session.get("academy_otp_preview_url"),
    )


def academy_resend_otp():
    email = session.get("academy_pending_email")
    purpose = session.get("academy_pending_purpose", "register")
    if not email:
        return jsonify({"ok": False, "message": "Tidak ada proses verifikasi aktif."}), 400
    ok, err = _issue_otp(email, purpose)
    if not ok:
        return jsonify({"ok": False, "message": err}), 429
    return jsonify({
        "ok": True,
        "message": "Kode OTP baru sudah dikirim.",
        "dev_otp": session.get("academy_dev_otp") if _otp_delivery_mode() == "dev" else None,
        "otp_preview_url": session.get("academy_otp_preview_url"),
    })


# --------------------------------------------------------------------------- #
# LOGIN / LOGOUT / FORGOT PASSWORD
# --------------------------------------------------------------------------- #
def academy_login_view():
    if session.get("academy_user_id"):
        return redirect(url_for("academy_dashboard"))
    if request.method == "POST":
        email = (request.form.get("email", "") or "").strip().lower()
        password = request.form.get("password", "") or ""
        if not rate_limit_hit(f"login:{_client_ip()}", max_hits=15, window_seconds=600) or \
           not rate_limit_hit(f"login:{email}", max_hits=8, window_seconds=600):
            flash("Terlalu banyak percobaan login. Coba lagi dalam beberapa menit.", "danger")
        else:
            user = adb.col_users().find_one({"email": email})
            if not user or not verify_password(password, user.get("password_hash", "")):
                flash("Email atau password salah.", "danger")
            elif user.get("status") == "blocked":
                flash("Akun kamu diblokir. Hubungi admin FYY MOTION Academy.", "danger")
            elif not user.get("email_verified"):
                session["academy_pending_email"] = email
                session["academy_pending_purpose"] = "register"
                _issue_otp(email, "register")
                flash("Email belum diverifikasi. Kode OTP baru sudah dikirim.", "warning")
                return redirect(url_for("academy_verify_view"))
            else:
                session.clear_old = True  # no-op marker
                session["academy_user_id"] = user["_id"]
                session.permanent = True
                adb.col_users().update_one({"_id": user["_id"]}, {"$set": {"last_login_at": adb.utcnow()}})
                flash(f"Selamat datang kembali, {user.get('nama','')}!", "success")
                nxt = request.args.get("next") or request.form.get("next")
                return redirect(nxt if nxt and nxt.startswith("/academy") else url_for("academy_dashboard"))
    return render_template("academy_login.html", page_title="Masuk — FYY MOTION Academy")


def academy_logout_view():
    session.pop("academy_user_id", None)
    flash("Kamu sudah logout.", "success")
    return redirect(url_for("academy_login_page"))


def academy_forgot_view():
    if request.method == "POST":
        email = (request.form.get("email", "") or "").strip().lower()
        if not rate_limit_hit(f"forgot:{_client_ip()}", max_hits=8, window_seconds=600):
            flash("Terlalu banyak percobaan. Coba lagi beberapa menit lagi.", "danger")
        else:
            user = adb.col_users().find_one({"email": email})
            if user:
                ok, err = _issue_otp(email, "forgot")
                if not ok:
                    flash(err, "danger")
                    return render_template("academy_forgot.html", page_title="Lupa Password — FYY MOTION Academy")
            # Pesan sama persis baik email ada/tidak, supaya tidak bocorkan daftar email terdaftar.
            session["academy_pending_email"] = email
            session["academy_pending_purpose"] = "forgot"
            flash("Jika email terdaftar, kode OTP reset password sudah dikirim.", "success")
            return redirect(url_for("academy_verify_view"))
    return render_template("academy_forgot.html", page_title="Lupa Password — FYY MOTION Academy")


def academy_reset_password_view():
    email = session.get("academy_reset_email")
    if not email:
        flash("Sesi reset password tidak ditemukan. Silakan ulangi dari awal.", "warning")
        return redirect(url_for("academy_forgot_view"))
    if request.method == "POST":
        password = request.form.get("password", "") or ""
        confirm = request.form.get("confirm_password", "") or ""
        if not is_valid_password(password):
            flash("Password minimal 6 karakter.", "danger")
        elif password != confirm:
            flash("Konfirmasi password tidak sama.", "danger")
        else:
            adb.col_users().update_one(
                {"email": email}, {"$set": {"password_hash": hash_password(password), "updated_at": adb.utcnow()}}
            )
            session.pop("academy_reset_email", None)
            flash("Password berhasil diganti. Silakan login dengan password baru.", "success")
            return redirect(url_for("academy_login_page"))
    return render_template("academy_reset_password.html", page_title="Buat Password Baru — FYY MOTION Academy", email=email)


# --------------------------------------------------------------------------- #
# DASHBOARD SISWA
# --------------------------------------------------------------------------- #
def academy_dashboard_view():
    user = _current_user()
    enrollments = list(adb.col_enrollments().find({"user_id": user["_id"]}))
    course_ids = [e["course_id"] for e in enrollments]
    my_courses = []
    for c in adb.col_courses().find({"_id": {"$in": course_ids}}):
        prog = _course_progress(user["_id"], c["_id"])
        my_courses.append({**_course_public(c), "progress": prog})
    pending_tx = list(adb.col_transactions().find({"user_id": user["_id"], "status": "menunggu"}))
    announcements = list(
        adb.col_announcements().find({"aktif": True, "$or": [{"course_id": None}, {"course_id": {"$in": course_ids}}]})
        .sort([("pinned", -1), ("created_at", -1)]).limit(5)
    )
    return render_template(
        "academy_dashboard.html",
        page_title="Dashboard Siswa — FYY MOTION Academy",
        user=user,
        my_courses=my_courses,
        jumlah_kelas=len(my_courses),
        pending_tx=pending_tx,
        announcements=announcements,
    )


def academy_catalog_view():
    user = _current_user()
    my_course_ids = {e["course_id"] for e in adb.col_enrollments().find({"user_id": user["_id"]})}
    courses = [
        {**_course_public(c), "sudah_punya": c["_id"] in my_course_ids}
        for c in adb.col_courses().find({"status": "published"}).sort("urutan", 1)
    ]
    return render_template("academy_catalog.html", page_title="Katalog Kelas — FYY MOTION Academy", courses=courses)


def academy_course_detail_view(slug):
    user = _current_user()
    course = adb.col_courses().find_one({"slug": slug, "status": "published"})
    if not course:
        abort(404)
    enrolled = _is_enrolled(user["_id"], course["_id"])
    pending = adb.col_transactions().find_one(
        {"user_id": user["_id"], "course_id": course["_id"], "status": "menunggu"}
    )
    return render_template(
        "academy_course_detail.html",
        page_title=f"{course.get('judul','Kelas')} — FYY MOTION Academy",
        course=_course_public(course),
        enrolled=enrolled,
        pending=pending,
    )


def academy_beli_view(slug):
    user = _current_user()
    course = adb.col_courses().find_one({"slug": slug, "status": "published"})
    if not course:
        abort(404)
    if _is_enrolled(user["_id"], course["_id"]):
        flash("Kamu sudah terdaftar di kelas ini.", "info")
        return redirect(url_for("academy_ruang_belajar_view", slug=slug))
    existing = adb.col_transactions().find_one(
        {"user_id": user["_id"], "course_id": course["_id"], "status": "menunggu"}
    )
    if existing:
        return redirect(url_for("academy_transaksi_view", kode=existing["kode_transaksi"]))
    now = adb.utcnow()
    kode = new_kode_transaksi(now)
    # Pastikan kode transaksi benar-benar unik (index unik jadi pengaman terakhir).
    for _ in range(5):
        if not adb.col_transactions().find_one({"kode_transaksi": kode}):
            break
        kode = new_kode_transaksi(now)
    harga_server = int(course.get("harga", 0))  # HARGA SELALU DARI DATABASE, bukan dari client.
    tx = {
        "_id": adb.new_id(),
        "kode_transaksi": kode,
        "user_id": user["_id"],
        "course_id": course["_id"],
        "course_judul": course.get("judul", ""),
        "harga": harga_server,
        "status": "menunggu",
        "metode": "gopay_qris",
        "device_info": {
            "user_agent": request.headers.get("User-Agent", "")[:300],
            "ip": _client_ip(),
            "device_id": request.cookies.get("academy_device_id", ""),
        },
        "created_at": now,
        "updated_at": now,
        "approved_by": None,
        "approved_at": None,
        "reject_reason": None,
    }
    try:
        adb.col_transactions().insert_one(tx)
    except Exception:
        existing = adb.col_transactions().find_one(
            {"user_id": user["_id"], "course_id": course["_id"], "status": "menunggu"}
        )
        if existing:
            return redirect(url_for("academy_transaksi_view", kode=existing["kode_transaksi"]))
        flash("Gagal membuat transaksi, kode tidak unik. Coba lagi.", "danger")
        return redirect(url_for("academy_course_detail_view", slug=slug))
    return redirect(url_for("academy_transaksi_view", kode=kode))


def academy_transaksi_view(kode):
    user = _current_user()
    tx = adb.col_transactions().find_one({"kode_transaksi": kode})
    if not tx or tx["user_id"] != user["_id"]:
        abort(404)
    wa_number = _wa_admin_number()
    pesan = (
        f"Halo Admin FYY MOTION Academy, saya ingin konfirmasi pembayaran.\n"
        f"Kode Transaksi: {tx['kode_transaksi']}\n"
        f"Nama: {user.get('nama','')}\n"
        f"Email: {user.get('email','')}\n"
        f"Kelas: {tx.get('course_judul','')}\n"
        f"Total: Rp{tx.get('harga',0):,}".replace(",", ".") + "\n"
        "Bukti transfer saya kirim di chat ini. Mohon segera diproses, terima kasih!"
    )
    wa_link = f"https://wa.me/{wa_number}?text={quote(pesan)}" if wa_number else ""
    return render_template(
        "academy_receipt.html",
        page_title=f"Transaksi {tx['kode_transaksi']} — FYY MOTION Academy",
        tx=tx,
        wa_link=wa_link,
        wa_configured=bool(wa_number),
        qris_image_url=_qris_image_url(),
    )


def academy_transaksi_status_api(kode):
    user = _current_user()
    tx = adb.col_transactions().find_one({"kode_transaksi": kode})
    if not tx or tx["user_id"] != user["_id"]:
        return jsonify({"ok": False, "message": "Transaksi tidak ditemukan."}), 404
    return jsonify({
        "ok": True,
        "status": tx["status"],
        "kode_transaksi": tx["kode_transaksi"],
        "updated_at": tx["updated_at"].isoformat() if tx.get("updated_at") else None,
    })


def academy_ruang_belajar_view(slug):
    user = _current_user()
    course = adb.col_courses().find_one({"slug": slug})
    if not course:
        abort(404)
    if not _is_enrolled(user["_id"], course["_id"]):
        abort(403)
    prog = _course_progress(user["_id"], course["_id"])
    for l in prog["lessons"]:
        l["embed_url"] = l.get("embed_url") or url_to_embed(l.get("video_url", ""))
    return render_template(
        "academy_ruang_belajar.html",
        page_title=f"Ruang Belajar — {course.get('judul','')}",
        course=_course_public(course),
        progress=prog,
    )


def academy_lesson_selesai_api(lesson_id):
    user = _current_user()
    lesson = adb.col_lessons().find_one({"_id": lesson_id})
    if not lesson:
        return jsonify({"ok": False, "message": "Pelajaran tidak ditemukan."}), 404
    if not _is_enrolled(user["_id"], lesson["course_id"]):
        return jsonify({"ok": False, "message": "Kamu belum terdaftar di kelas ini."}), 403
    now = adb.utcnow()
    adb.col_progress().update_one(
        {"user_id": user["_id"], "lesson_id": lesson_id},
        {"$set": {
            "user_id": user["_id"], "lesson_id": lesson_id, "course_id": lesson["course_id"],
            "completed": True, "completed_at": now,
        }},
        upsert=True,
    )
    prog = _course_progress(user["_id"], lesson["course_id"])
    return jsonify({"ok": True, "persen": prog["persen"], "selesai": prog["selesai"], "total": prog["total"]})


def academy_pengumuman_view():
    user = _current_user()
    course_ids = [e["course_id"] for e in adb.col_enrollments().find({"user_id": user["_id"]})]
    announcements = list(
        adb.col_announcements().find({"aktif": True, "$or": [{"course_id": None}, {"course_id": {"$in": course_ids}}]})
        .sort([("pinned", -1), ("created_at", -1)])
    )
    courses_map = {c["_id"]: c.get("judul", "") for c in adb.col_courses().find({"_id": {"$in": course_ids}})}
    for a in announcements:
        a["course_judul"] = courses_map.get(a.get("course_id")) if a.get("course_id") else "Semua Siswa"
    return render_template("academy_announcements.html", page_title="Pengumuman — FYY MOTION Academy", announcements=announcements)


def academy_riwayat_view():
    user = _current_user()
    txs = list(adb.col_transactions().find({"user_id": user["_id"]}).sort("created_at", -1))
    return render_template("academy_history.html", page_title="Riwayat Pembayaran — FYY MOTION Academy", txs=txs)


# --------------------------------------------------------------------------- #
# Pendaftaran rute ke aplikasi Flask utama (dipanggil dari app.py)
# --------------------------------------------------------------------------- #
PUBLIC_ACADEMY_ENDPOINTS = [
    "academy_register_view", "academy_verify_view", "academy_resend_otp",
    "academy_login_page", "academy_logout_view", "academy_forgot_view", "academy_reset_password_view",
    "academy_dashboard", "academy_catalog_view", "academy_course_detail_view", "academy_beli_view",
    "academy_transaksi_view", "academy_transaksi_status_api", "academy_ruang_belajar_view",
    "academy_lesson_selesai_api", "academy_pengumuman_view", "academy_riwayat_view",
]


def register_academy_routes(app):
    import academy_admin as aa

    @app.context_processor
    def _inject_academy_globals():
        academy_user = None
        uid = session.get("academy_user_id")
        academy_pending_count = 0
        if adb.is_configured():
            try:
                if uid:
                    academy_user = adb.col_users().find_one({"_id": uid})
                if session.get("logged_in"):
                    academy_pending_count = adb.col_transactions().count_documents({"status": "menunggu"})
            except Exception:
                pass
        return {"academy_user": academy_user, "academy_pending_count": academy_pending_count}

    # ---- Auth & OTP (publik, dilindungi oleh decorator masing-masing) ----
    app.add_url_rule("/academy/daftar-akun", "academy_register_view", academy_db_required(academy_register_view), methods=["GET", "POST"])
    app.add_url_rule("/academy/verifikasi-otp", "academy_verify_view", academy_db_required(academy_verify_view), methods=["GET", "POST"])
    app.add_url_rule("/academy/kirim-ulang-otp", "academy_resend_otp", academy_db_required(academy_resend_otp), methods=["POST"])
    app.add_url_rule("/academy/login", "academy_login_page", academy_db_required(academy_login_view), methods=["GET", "POST"])
    app.add_url_rule("/academy/logout", "academy_logout_view", academy_db_required(academy_logout_view), methods=["POST"])
    app.add_url_rule("/academy/lupa-password", "academy_forgot_view", academy_db_required(academy_forgot_view), methods=["GET", "POST"])
    app.add_url_rule("/academy/reset-password", "academy_reset_password_view", academy_db_required(academy_reset_password_view), methods=["GET", "POST"])

    # ---- Area siswa (wajib login academy) ----
    app.add_url_rule("/academy/dashboard", "academy_dashboard", academy_login_required(academy_dashboard_view), methods=["GET"])
    app.add_url_rule("/academy/kelas", "academy_catalog_view", academy_login_required(academy_catalog_view), methods=["GET"])
    app.add_url_rule("/academy/kelas/<slug>", "academy_course_detail_view", academy_login_required(academy_course_detail_view), methods=["GET"])
    app.add_url_rule("/academy/kelas/<slug>/beli", "academy_beli_view", academy_login_required(academy_beli_view), methods=["POST"])
    app.add_url_rule("/academy/transaksi/<kode>", "academy_transaksi_view", academy_login_required(academy_transaksi_view), methods=["GET"])
    app.add_url_rule("/academy/transaksi/<kode>/status", "academy_transaksi_status_api", academy_login_required(academy_transaksi_status_api), methods=["GET"])
    app.add_url_rule("/academy/ruang-belajar/<slug>", "academy_ruang_belajar_view", academy_login_required(academy_ruang_belajar_view), methods=["GET"])
    app.add_url_rule("/academy/pelajaran/<lesson_id>/selesai", "academy_lesson_selesai_api", academy_login_required(academy_lesson_selesai_api), methods=["POST"])
    app.add_url_rule("/academy/pengumuman", "academy_pengumuman_view", academy_login_required(academy_pengumuman_view), methods=["GET"])
    app.add_url_rule("/academy/riwayat-pembayaran", "academy_riwayat_view", academy_login_required(academy_riwayat_view), methods=["GET"])

    # ---- Panel admin (reuse sesi admin existing, dilindungi guard() bawaan app.py) ----
    app.add_url_rule("/admin/academy", "admin_academy_home", academy_admin_required(aa.admin_academy_home), methods=["GET"])
    app.add_url_rule("/admin/academy/kelas", "admin_academy_courses", academy_admin_required(aa.admin_academy_courses), methods=["GET", "POST"])
    app.add_url_rule("/admin/academy/kelas/<course_id>/hapus", "admin_academy_course_delete", academy_admin_required(aa.admin_academy_course_delete), methods=["POST"])
    app.add_url_rule("/admin/academy/kelas/<course_id>/pelajaran", "admin_academy_lessons", academy_admin_required(aa.admin_academy_lessons), methods=["GET", "POST"])
    app.add_url_rule("/admin/academy/kelas/<course_id>/pelajaran/<lesson_id>/hapus", "admin_academy_lesson_delete", academy_admin_required(aa.admin_academy_lesson_delete), methods=["POST"])
    app.add_url_rule("/admin/academy/kelas/<course_id>/pelajaran/<lesson_id>/pindah", "admin_academy_lesson_reorder", academy_admin_required(aa.admin_academy_lesson_reorder), methods=["POST"])
    app.add_url_rule("/admin/academy/kelas/<course_id>/pelajaran/impor", "admin_academy_lesson_import", academy_admin_required(aa.admin_academy_lesson_import), methods=["POST"])
    app.add_url_rule("/admin/academy/pembayaran", "admin_academy_payments", academy_admin_required(aa.admin_academy_payments), methods=["GET"])
    app.add_url_rule("/admin/academy/pembayaran/<tx_id>/setujui", "admin_academy_payment_approve", academy_admin_required(aa.admin_academy_payment_approve), methods=["POST"])
    app.add_url_rule("/admin/academy/pembayaran/<tx_id>/tolak", "admin_academy_payment_reject", academy_admin_required(aa.admin_academy_payment_reject), methods=["POST"])
    app.add_url_rule("/admin/academy/pengumuman", "admin_academy_announcements", academy_admin_required(aa.admin_academy_announcements), methods=["GET", "POST"])
    app.add_url_rule("/admin/academy/pengumuman/<ann_id>/hapus", "admin_academy_announcement_delete", academy_admin_required(aa.admin_academy_announcement_delete), methods=["POST"])
    app.add_url_rule("/admin/academy/pengumuman/<ann_id>/toggle", "admin_academy_announcement_toggle", academy_admin_required(aa.admin_academy_announcement_toggle), methods=["POST"])
    app.add_url_rule("/admin/academy/pengumuman/<ann_id>/pin", "admin_academy_announcement_pin", academy_admin_required(aa.admin_academy_announcement_pin), methods=["POST"])
    app.add_url_rule("/admin/academy/siswa", "admin_academy_students", academy_admin_required(aa.admin_academy_students), methods=["GET"])
    app.add_url_rule("/admin/academy/siswa/<user_id>", "admin_academy_student_detail", academy_admin_required(aa.admin_academy_student_detail), methods=["GET"])
    app.add_url_rule("/admin/academy/siswa/<user_id>/daftarkan", "admin_academy_student_enroll", academy_admin_required(aa.admin_academy_student_enroll), methods=["POST"])
    app.add_url_rule("/admin/academy/siswa/<user_id>/cabut/<course_id>", "admin_academy_student_revoke", academy_admin_required(aa.admin_academy_student_revoke), methods=["POST"])
    app.add_url_rule("/admin/academy/siswa/<user_id>/blokir", "admin_academy_student_block", academy_admin_required(aa.admin_academy_student_block), methods=["POST"])
    app.add_url_rule("/admin/academy/siswa/<user_id>/reset-password", "admin_academy_student_reset_password", academy_admin_required(aa.admin_academy_student_reset_password), methods=["POST"])
    app.add_url_rule("/admin/academy/siswa/<user_id>/hapus", "admin_academy_student_delete", academy_admin_required(aa.admin_academy_student_delete), methods=["POST"])
