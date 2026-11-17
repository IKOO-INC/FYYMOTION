"""
FYY MOTION Academy — panel admin (/admin/academy/*).

Memakai ulang sesi admin yang sudah ada di aplikasi utama (session['logged_in'],
diisi oleh route /login yang sudah ada) — lihat academy_admin_required di
academy_routes.py. Modul ini HANYA berisi handler untuk 5 submenu admin:
1. Kelas (CRUD)             -> /admin/academy/kelas
2. Pelajaran (CRUD + bulk)  -> /admin/academy/kelas/<course_id>/pelajaran
3. Pembayaran (approve/reject, idempotent) -> /admin/academy/pembayaran
4. Pengumuman (CRUD + pin)  -> /admin/academy/pengumuman
5. Siswa (kelola akun)      -> /admin/academy/siswa
"""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime

from flask import abort, flash, jsonify, redirect, render_template, request, session, url_for

import academy_db as adb
from academy_security import clean_text, generate_otp_code, hash_password, is_valid_email, url_to_embed


def _slugify(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or adb.new_id()[:8]


def _unique_slug(base_slug: str, exclude_id: str | None = None) -> str:
    slug = base_slug
    i = 2
    while True:
        q = {"slug": slug}
        if exclude_id:
            q["_id"] = {"$ne": exclude_id}
        if not adb.col_courses().find_one(q):
            return slug
        slug = f"{base_slug}-{i}"
        i += 1


# --------------------------------------------------------------------------- #
# 1) KELAS (COURSES)
# --------------------------------------------------------------------------- #
def admin_academy_home():
    return redirect(url_for("admin_academy_courses"))


def admin_academy_courses():
    if request.method == "POST":
        course_id = request.form.get("course_id", "").strip()
        judul = clean_text(request.form.get("judul", ""), 150)
        deskripsi = clean_text(request.form.get("deskripsi", ""), 3000)
        harga = request.form.get("harga", "0")
        thumbnail_url = clean_text(request.form.get("thumbnail_url", ""), 500)
        status = request.form.get("status", "draft")
        urutan = request.form.get("urutan", "0")
        try:
            harga_i = max(0, int(re.sub(r"[^0-9]", "", harga) or "0"))
        except ValueError:
            harga_i = 0
        try:
            urutan_i = int(urutan)
        except ValueError:
            urutan_i = 0
        if not judul or len(judul) < 3:
            flash("Judul kelas minimal 3 karakter.", "danger")
        elif status not in ("draft", "published"):
            flash("Status tidak valid.", "danger")
        else:
            now = adb.utcnow()
            if course_id:
                existing = adb.col_courses().find_one({"_id": course_id})
                if not existing:
                    flash("Kelas tidak ditemukan.", "danger")
                    return redirect(url_for("admin_academy_courses"))
                slug = existing["slug"]
                if clean_text(existing.get("judul", "")) != judul:
                    slug = _unique_slug(_slugify(judul), exclude_id=course_id)
                adb.col_courses().update_one(
                    {"_id": course_id},
                    {"$set": {
                        "judul": judul, "slug": slug, "deskripsi": deskripsi, "harga": harga_i,
                        "thumbnail_url": thumbnail_url, "status": status, "urutan": urutan_i, "updated_at": now,
                    }},
                )
                flash(f"Kelas '{judul}' berhasil diperbarui.", "success")
            else:
                slug = _unique_slug(_slugify(judul))
                adb.col_courses().insert_one({
                    "_id": adb.new_id(), "slug": slug, "judul": judul, "deskripsi": deskripsi,
                    "harga": harga_i, "thumbnail_url": thumbnail_url, "status": status, "urutan": urutan_i,
                    "created_at": now, "updated_at": now,
                })
                flash(f"Kelas '{judul}' berhasil dibuat.", "success")
        return redirect(url_for("admin_academy_courses"))

    courses = list(adb.col_courses().find({}).sort("urutan", 1))
    for c in courses:
        c["jumlah_pelajaran"] = adb.col_lessons().count_documents({"course_id": c["_id"]})
        c["jumlah_siswa"] = adb.col_enrollments().count_documents({"course_id": c["_id"]})
    return render_template("admin_academy_courses.html", page_title="Kelola Kelas — Admin Academy", courses=courses)


def admin_academy_course_delete(course_id):
    siswa = adb.col_enrollments().count_documents({"course_id": course_id})
    if siswa > 0:
        flash("Kelas tidak bisa dihapus karena sudah punya siswa terdaftar. Ubah status jadi draft saja.", "danger")
        return redirect(url_for("admin_academy_courses"))
    adb.col_lessons().delete_many({"course_id": course_id})
    adb.col_courses().delete_one({"_id": course_id})
    flash("Kelas (tanpa siswa) berhasil dihapus beserta pelajarannya.", "success")
    return redirect(url_for("admin_academy_courses"))


# --------------------------------------------------------------------------- #
# 2) PELAJARAN (LESSONS)
# --------------------------------------------------------------------------- #
def admin_academy_lessons(course_id):
    course = adb.col_courses().find_one({"_id": course_id})
    if not course:
        abort(404)
    if request.method == "POST":
        lesson_id = request.form.get("lesson_id", "").strip()
        judul = clean_text(request.form.get("judul", ""), 150)
        deskripsi = clean_text(request.form.get("deskripsi", ""), 2000)
        video_url = clean_text(request.form.get("video_url", ""), 500)
        durasi = request.form.get("durasi_menit", "0")
        try:
            durasi_i = max(0, int(re.sub(r"[^0-9]", "", durasi) or "0"))
        except ValueError:
            durasi_i = 0
        embed_url = url_to_embed(video_url)
        if not judul:
            flash("Judul pelajaran wajib diisi.", "danger")
        else:
            now = adb.utcnow()
            if lesson_id:
                adb.col_lessons().update_one(
                    {"_id": lesson_id, "course_id": course_id},
                    {"$set": {
                        "judul": judul, "deskripsi": deskripsi, "video_url": video_url,
                        "embed_url": embed_url, "durasi_menit": durasi_i, "updated_at": now,
                    }},
                )
                flash(f"Pelajaran '{judul}' berhasil diperbarui.", "success")
            else:
                max_urutan = adb.col_lessons().count_documents({"course_id": course_id})
                adb.col_lessons().insert_one({
                    "_id": adb.new_id(), "course_id": course_id, "judul": judul, "deskripsi": deskripsi,
                    "video_url": video_url, "embed_url": embed_url, "durasi_menit": durasi_i,
                    "urutan": max_urutan, "created_at": now, "updated_at": now,
                })
                flash(f"Pelajaran '{judul}' berhasil ditambahkan.", "success")
        return redirect(url_for("admin_academy_lessons", course_id=course_id))

    lessons = list(adb.col_lessons().find({"course_id": course_id}).sort("urutan", 1))
    return render_template(
        "admin_academy_lessons.html", page_title=f"Pelajaran — {course.get('judul','')}",
        course=course, lessons=lessons,
    )


def admin_academy_lesson_delete(course_id, lesson_id):
    adb.col_lessons().delete_one({"_id": lesson_id, "course_id": course_id})
    adb.col_progress().delete_many({"lesson_id": lesson_id})
    _resequence_lessons(course_id)
    flash("Pelajaran berhasil dihapus.", "success")
    return redirect(url_for("admin_academy_lessons", course_id=course_id))


def _resequence_lessons(course_id):
    lessons = list(adb.col_lessons().find({"course_id": course_id}).sort("urutan", 1))
    for idx, l in enumerate(lessons):
        if l.get("urutan") != idx:
            adb.col_lessons().update_one({"_id": l["_id"]}, {"$set": {"urutan": idx}})


def admin_academy_lesson_reorder(course_id, lesson_id):
    direction = request.form.get("arah", "")
    lessons = list(adb.col_lessons().find({"course_id": course_id}).sort("urutan", 1))
    idx = next((i for i, l in enumerate(lessons) if l["_id"] == lesson_id), None)
    if idx is None:
        return jsonify({"ok": False}), 404
    swap_with = idx - 1 if direction == "atas" else idx + 1
    if 0 <= swap_with < len(lessons):
        a, b = lessons[idx], lessons[swap_with]
        adb.col_lessons().update_one({"_id": a["_id"]}, {"$set": {"urutan": b["urutan"]}})
        adb.col_lessons().update_one({"_id": b["_id"]}, {"$set": {"urutan": a["urutan"]}})
    return redirect(url_for("admin_academy_lessons", course_id=course_id))


def admin_academy_lesson_import(course_id):
    course = adb.col_courses().find_one({"_id": course_id})
    if not course:
        abort(404)
    raw_json = request.form.get("json_data", "").strip()
    file = request.files.get("csv_file")
    rows = []
    try:
        if raw_json:
            data = json.loads(raw_json)
            if not isinstance(data, list):
                raise ValueError("JSON harus berupa array/list.")
            rows = data
        elif file and file.filename:
            content = file.read().decode("utf-8-sig", errors="ignore")
            reader = csv.DictReader(io.StringIO(content))
            rows = list(reader)
        else:
            flash("Isi data JSON atau unggah file CSV terlebih dahulu.", "danger")
            return redirect(url_for("admin_academy_lessons", course_id=course_id))
    except Exception as exc:
        flash(f"Gagal membaca data impor: {exc}", "danger")
        return redirect(url_for("admin_academy_lessons", course_id=course_id))

    if len(rows) > 100:
        flash("Maksimal 100 pelajaran per sekali impor.", "danger")
        return redirect(url_for("admin_academy_lessons", course_id=course_id))

    now = adb.utcnow()
    start_urutan = adb.col_lessons().count_documents({"course_id": course_id})
    inserted, skipped = 0, 0
    docs = []
    for i, row in enumerate(rows):
        judul = clean_text(str(row.get("judul") or row.get("title") or ""), 150)
        video_url = clean_text(str(row.get("video_url") or row.get("url") or ""), 500)
        deskripsi = clean_text(str(row.get("deskripsi") or row.get("description") or ""), 2000)
        try:
            durasi_i = max(0, int(row.get("durasi_menit") or row.get("duration") or 0))
        except (TypeError, ValueError):
            durasi_i = 0
        if not judul or not video_url:
            skipped += 1
            continue
        docs.append({
            "_id": adb.new_id(), "course_id": course_id, "judul": judul, "deskripsi": deskripsi,
            "video_url": video_url, "embed_url": url_to_embed(video_url), "durasi_menit": durasi_i,
            "urutan": start_urutan + inserted, "created_at": now, "updated_at": now,
        })
        inserted += 1
    if docs:
        adb.col_lessons().insert_many(docs)
    flash(f"Impor selesai: {inserted} pelajaran ditambahkan, {skipped} baris dilewati (data tidak lengkap).", "success" if inserted else "warning")
    return redirect(url_for("admin_academy_lessons", course_id=course_id))


# --------------------------------------------------------------------------- #
# 3) PEMBAYARAN (TRANSACTIONS)
# --------------------------------------------------------------------------- #
def admin_academy_payments():
    q = clean_text(request.args.get("q", ""), 100)
    status_f = request.args.get("status", "")
    query = {}
    if status_f in ("menunggu", "approved", "ditolak"):
        query["status"] = status_f
    if q:
        users = list(adb.col_users().find(
            {"$or": [{"nama": {"$regex": re.escape(q), "$options": "i"}}, {"email": {"$regex": re.escape(q), "$options": "i"}}]}
        ))
        user_ids = [u["_id"] for u in users]
        query["$or"] = [
            {"kode_transaksi": {"$regex": re.escape(q), "$options": "i"}},
            {"user_id": {"$in": user_ids}},
        ]
    txs = list(adb.col_transactions().find(query).sort("created_at", -1).limit(300))
    user_map = {u["_id"]: u for u in adb.col_users().find({"_id": {"$in": [t["user_id"] for t in txs]}})}
    for t in txs:
        u = user_map.get(t["user_id"], {})
        t["user_nama"] = u.get("nama", "(akun dihapus)")
        t["user_email"] = u.get("email", "-")
    pending_count = adb.col_transactions().count_documents({"status": "menunggu"})
    return render_template(
        "admin_academy_payments.html", page_title="Pembayaran — Admin Academy",
        txs=txs, q=q, status_f=status_f, pending_count=pending_count,
    )


def admin_academy_payment_approve(tx_id):
    tx = adb.col_transactions().find_one({"_id": tx_id})
    if not tx:
        flash("Transaksi tidak ditemukan.", "danger")
        return redirect(url_for("admin_academy_payments"))
    if tx["status"] == "approved":
        flash(f"Transaksi {tx['kode_transaksi']} sudah di-approve sebelumnya (tidak diproses ulang).", "info")
        return redirect(url_for("admin_academy_payments"))
    now = adb.utcnow()
    adb.col_transactions().update_one(
        {"_id": tx_id, "status": "menunggu"},
        {"$set": {"status": "approved", "approved_by": session.get("username", "admin"), "approved_at": now, "updated_at": now}},
    )
    # Enrollment idempotent lewat unique index (user_id, course_id) -> update_one+upsert aman dipanggil berulang.
    adb.col_enrollments().update_one(
        {"user_id": tx["user_id"], "course_id": tx["course_id"]},
        {"$setOnInsert": {
            "_id": adb.new_id(), "user_id": tx["user_id"], "course_id": tx["course_id"],
            "enrolled_at": now, "source": "payment", "enrolled_by": "system",
        }},
        upsert=True,
    )
    flash(f"Transaksi {tx['kode_transaksi']} di-approve, siswa otomatis terdaftar ke kelasnya.", "success")
    return redirect(url_for("admin_academy_payments"))


def admin_academy_payment_reject(tx_id):
    alasan = clean_text(request.form.get("alasan", ""), 300) or "Tidak ada keterangan."
    tx = adb.col_transactions().find_one({"_id": tx_id})
    if not tx:
        flash("Transaksi tidak ditemukan.", "danger")
        return redirect(url_for("admin_academy_payments"))
    if tx["status"] != "menunggu":
        flash(f"Transaksi {tx['kode_transaksi']} sudah diproses sebelumnya (status: {tx['status']}).", "info")
        return redirect(url_for("admin_academy_payments"))
    adb.col_transactions().update_one(
        {"_id": tx_id, "status": "menunggu"},
        {"$set": {
            "status": "ditolak", "reject_reason": alasan, "approved_by": session.get("username", "admin"),
            "approved_at": adb.utcnow(), "updated_at": adb.utcnow(),
        }},
    )
    flash(f"Transaksi {tx['kode_transaksi']} ditolak.", "warning")
    return redirect(url_for("admin_academy_payments"))


# --------------------------------------------------------------------------- #
# 4) PENGUMUMAN (ANNOUNCEMENTS)
# --------------------------------------------------------------------------- #
def admin_academy_announcements():
    if request.method == "POST":
        ann_id = request.form.get("ann_id", "").strip()
        judul = clean_text(request.form.get("judul", ""), 150)
        isi = clean_text(request.form.get("isi", ""), 3000)
        course_id = request.form.get("course_id", "").strip() or None
        pinned = request.form.get("pinned") == "1"
        if not judul or not isi:
            flash("Judul dan isi pengumuman wajib diisi.", "danger")
        else:
            now = adb.utcnow()
            if ann_id:
                adb.col_announcements().update_one(
                    {"_id": ann_id},
                    {"$set": {"judul": judul, "isi": isi, "course_id": course_id, "pinned": pinned, "updated_at": now}},
                )
                flash("Pengumuman berhasil diperbarui.", "success")
            else:
                adb.col_announcements().insert_one({
                    "_id": adb.new_id(), "judul": judul, "isi": isi, "course_id": course_id,
                    "pinned": pinned, "aktif": True, "created_at": now, "updated_at": now,
                })
                flash("Pengumuman berhasil dibuat.", "success")
        return redirect(url_for("admin_academy_announcements"))

    announcements = list(adb.col_announcements().find({}).sort([("pinned", -1), ("created_at", -1)]))
    courses = list(adb.col_courses().find({}).sort("judul", 1))
    course_map = {c["_id"]: c.get("judul", "") for c in courses}
    for a in announcements:
        a["course_judul"] = course_map.get(a.get("course_id")) if a.get("course_id") else "Semua Siswa"
    return render_template(
        "admin_academy_announcements.html", page_title="Pengumuman — Admin Academy",
        announcements=announcements, courses=courses,
    )


def admin_academy_announcement_delete(ann_id):
    adb.col_announcements().delete_one({"_id": ann_id})
    flash("Pengumuman berhasil dihapus.", "success")
    return redirect(url_for("admin_academy_announcements"))


def admin_academy_announcement_toggle(ann_id):
    ann = adb.col_announcements().find_one({"_id": ann_id})
    if ann:
        adb.col_announcements().update_one({"_id": ann_id}, {"$set": {"aktif": not ann.get("aktif", True)}})
    return redirect(url_for("admin_academy_announcements"))


def admin_academy_announcement_pin(ann_id):
    ann = adb.col_announcements().find_one({"_id": ann_id})
    if ann:
        adb.col_announcements().update_one({"_id": ann_id}, {"$set": {"pinned": not ann.get("pinned", False)}})
    return redirect(url_for("admin_academy_announcements"))


# --------------------------------------------------------------------------- #
# 5) SISWA (STUDENTS)
# --------------------------------------------------------------------------- #
def admin_academy_students():
    q = clean_text(request.args.get("q", ""), 100)
    status_f = request.args.get("status", "")
    query = {}
    if q:
        query["$or"] = [
            {"nama": {"$regex": re.escape(q), "$options": "i"}},
            {"email": {"$regex": re.escape(q), "$options": "i"}},
        ]
    if status_f in ("active", "blocked"):
        query["status"] = status_f
    students = list(adb.col_users().find(query).sort("created_at", -1).limit(300))
    for s in students:
        s["jumlah_kelas"] = adb.col_enrollments().count_documents({"user_id": s["_id"]})
    return render_template("admin_academy_students.html", page_title="Siswa — Admin Academy", students=students, q=q, status_f=status_f)


def admin_academy_student_detail(user_id):
    student = adb.col_users().find_one({"_id": user_id})
    if not student:
        abort(404)
    enrollments = list(adb.col_enrollments().find({"user_id": user_id}))
    course_ids = [e["course_id"] for e in enrollments]
    courses_map = {c["_id"]: c for c in adb.col_courses().find({"_id": {"$in": course_ids}})}
    for e in enrollments:
        c = courses_map.get(e["course_id"], {})
        e["course_judul"] = c.get("judul", "(kelas dihapus)")
        total = adb.col_lessons().count_documents({"course_id": e["course_id"]})
        selesai = adb.col_progress().count_documents({"user_id": user_id, "course_id": e["course_id"], "completed": True})
        e["progress_persen"] = round(selesai * 100 / total) if total else 0
    txs = list(adb.col_transactions().find({"user_id": user_id}).sort("created_at", -1))
    all_courses = list(adb.col_courses().find({"status": "published"}).sort("judul", 1))
    return render_template(
        "admin_academy_student_detail.html", page_title=f"Siswa — {student.get('nama','')}",
        student=student, enrollments=enrollments, txs=txs, all_courses=all_courses,
    )


def admin_academy_student_enroll(user_id):
    course_id = request.form.get("course_id", "").strip()
    course = adb.col_courses().find_one({"_id": course_id})
    if not course:
        flash("Kelas tidak ditemukan.", "danger")
        return redirect(url_for("admin_academy_student_detail", user_id=user_id))
    adb.col_enrollments().update_one(
        {"user_id": user_id, "course_id": course_id},
        {"$setOnInsert": {
            "_id": adb.new_id(), "user_id": user_id, "course_id": course_id,
            "enrolled_at": adb.utcnow(), "source": "manual", "enrolled_by": session.get("username", "admin"),
        }},
        upsert=True,
    )
    flash(f"Siswa berhasil didaftarkan manual ke kelas '{course.get('judul','')}'.", "success")
    return redirect(url_for("admin_academy_student_detail", user_id=user_id))


def admin_academy_student_revoke(user_id, course_id):
    adb.col_enrollments().delete_one({"user_id": user_id, "course_id": course_id})
    flash("Akses kelas siswa berhasil dicabut.", "success")
    return redirect(url_for("admin_academy_student_detail", user_id=user_id))


def admin_academy_student_block(user_id):
    student = adb.col_users().find_one({"_id": user_id})
    if not student:
        abort(404)
    new_status = "blocked" if student.get("status") != "blocked" else "active"
    adb.col_users().update_one({"_id": user_id}, {"$set": {"status": new_status, "updated_at": adb.utcnow()}})
    flash(f"Status siswa diubah menjadi '{new_status}'.", "success")
    return redirect(url_for("admin_academy_student_detail", user_id=user_id))


def admin_academy_student_reset_password(user_id):
    student = adb.col_users().find_one({"_id": user_id})
    if not student:
        abort(404)
    temp_password = generate_otp_code() + generate_otp_code()[:3]
    adb.col_users().update_one(
        {"_id": user_id}, {"$set": {"password_hash": hash_password(temp_password), "updated_at": adb.utcnow()}}
    )
    flash(
        f"Password sementara untuk {student.get('email','')}: {temp_password} "
        "— sampaikan ke siswa secara manual (WhatsApp/email), lalu minta mereka login dan ganti password.",
        "success",
    )
    return redirect(url_for("admin_academy_student_detail", user_id=user_id))


def admin_academy_student_delete(user_id):
    adb.col_users().delete_one({"_id": user_id})
    adb.col_enrollments().delete_many({"user_id": user_id})
    adb.col_progress().delete_many({"user_id": user_id})
    flash("Akun siswa berhasil dihapus permanen beserta progres belajarnya.", "success")
    return redirect(url_for("admin_academy_students"))
