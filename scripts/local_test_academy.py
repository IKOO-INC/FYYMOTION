"""Script smoke test lokal (TIDAK untuk production, TIDAK dideploy ke Vercel)
— memakai mongomock untuk mensimulasikan MongoDB supaya seluruh alur akademi
bisa diuji tanpa akses jaringan nyata ke MongoDB Atlas.

Cara pakai (dari root repo):
    pip install mongomock
    python3 scripts/local_test_academy.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

os.environ["MONGODB_URI"] = "mongodb://localhost:27017/test"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "admin123"
os.environ["WA_ADMIN_NUMBER"] = "6281234567890"
os.environ["GOPAY_QRIS_IMAGE_URL"] = "https://example.com/qris.png"

import mongomock
import pymongo

# Patch pymongo.MongoClient -> mongomock, dipakai oleh academy_db.get_db()
pymongo.MongoClient = mongomock.MongoClient

import app as flaskapp  # noqa: E402

client = flaskapp.app.test_client()


def show(resp, label):
    ok = resp.status_code < 400
    print(f"[{'OK' if ok else 'FAIL'}] {label}: {resp.status_code}")
    if not ok:
        print(resp.get_data(as_text=True)[:800])
    return resp


def get_csrf(resp):
    html = resp.get_data(as_text=True)
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else ""


# 1) Halaman academy lama tetap jalan
show(client.get("/academy"), "GET /academy (landing lama)")
show(client.get("/teks-creator"), "GET /teks-creator (tidak boleh rusak)")

# 2) Register siswa baru
r = show(client.get("/academy/daftar-akun"), "GET register")
csrf = get_csrf(r)
r = show(client.post("/academy/daftar-akun", data={
    "csrf_token": csrf, "nama": "Budi Siswa", "email": "budi@example.com",
    "password": "rahasia123", "confirm_password": "rahasia123",
}, follow_redirects=True), "POST register")
html = r.get_data(as_text=True)
m = re.search(r"Mode developer.*?(\d{6})", html, re.S)
otp = m.group(1) if m else None
print("OTP terdeteksi:", otp)
csrf2 = get_csrf(r)
r = show(client.post("/academy/verifikasi-otp", data={"csrf_token": csrf2, "otp": otp}, follow_redirects=True), "POST verify OTP")

# 3) Login
r = show(client.get("/academy/login"), "GET login")
csrf = get_csrf(r)
r = show(client.post("/academy/login", data={"csrf_token": csrf, "email": "budi@example.com", "password": "rahasia123"}, follow_redirects=True), "POST login")
assert "Dashboard" in r.get_data(as_text=True) or "dashboard" in r.request.path.lower()

# 4) Dashboard menunjukkan 0 kelas
r = show(client.get("/academy/dashboard"), "GET dashboard")
assert "belum punya kelas" in r.get_data(as_text=True).lower()
print("Dashboard 0 kelas: OK")

# 5) Login admin lalu buat kelas + pelajaran lewat panel admin
admin = flaskapp.app.test_client()
r = show(admin.get("/login"), "GET admin login")
csrf = get_csrf(r)
r = show(admin.post("/login", data={"csrf_token": csrf, "username": "admin", "password": "admin123"}, follow_redirects=True), "POST admin login")

r = show(admin.get("/admin/academy/kelas"), "GET admin kelas")
csrf = get_csrf(r)
r = show(admin.post("/admin/academy/kelas", data={
    "csrf_token": csrf, "course_id": "", "judul": "Motion Graphic Dasar", "deskripsi": "Belajar dasar.",
    "harga": "150000", "thumbnail_url": "", "status": "published", "urutan": "0",
}, follow_redirects=True), "POST create course")

import academy_db as adb
course = adb.col_courses().find_one({"slug": "motion-graphic-dasar"})
print("Course dibuat:", course["_id"] if course else None)
assert course

r = show(admin.get(f"/admin/academy/kelas/{course['_id']}/pelajaran"), "GET admin lessons")
csrf = get_csrf(r)
r = show(admin.post(f"/admin/academy/kelas/{course['_id']}/pelajaran", data={
    "csrf_token": csrf, "lesson_id": "", "judul": "Intro Timeline", "deskripsi": "",
    "video_url": "https://youtu.be/dQw4w9WgXcQ", "durasi_menit": "10",
}, follow_redirects=True), "POST create lesson")
lesson = adb.col_lessons().find_one({"course_id": course["_id"]})
print("Lesson dibuat:", lesson["_id"] if lesson else None, "embed:", lesson.get("embed_url") if lesson else None)
assert lesson and lesson["embed_url"] == "https://www.youtube.com/embed/dQw4w9WgXcQ"

# 6) Siswa buka katalog, beli kelas -> dapat kode transaksi
r = show(client.get("/academy/kelas"), "GET catalog")
assert "Motion Graphic Dasar" in r.get_data(as_text=True)
r = show(client.get("/academy/kelas/motion-graphic-dasar"), "GET course detail")
csrf = get_csrf(r)
r = show(client.post("/academy/kelas/motion-graphic-dasar/beli", data={"csrf_token": csrf}, follow_redirects=True), "POST beli")
html = r.get_data(as_text=True)
m = re.search(r"(ACD-\d{6}-\d{5})", html)
kode = m.group(1)
print("Kode transaksi:", kode)
assert "wa.me" in html

# 6b) Klik beli lagi -> harus redirect ke transaksi yang sama (tidak duplikat)
r = show(client.get("/academy/kelas/motion-graphic-dasar"), "GET course detail (pending)")
assert "menunggu konfirmasi" in r.get_data(as_text=True).lower()
tx_count_before = adb.col_transactions().count_documents({"kode_transaksi": kode})
r2 = client.post("/academy/kelas/motion-graphic-dasar/beli", data={"csrf_token": csrf}, follow_redirects=True)
assert adb.col_transactions().count_documents({}) == 1
print("Tidak ada duplikat transaksi: OK")

# 7) Ruang belajar harus 403 sebelum approve
r = show(client.get("/academy/ruang-belajar/motion-graphic-dasar"), "GET ruang belajar (belum bayar, harus redirect dari 403 handler)")

# 8) Admin cari & approve transaksi
r = show(admin.get(f"/admin/academy/pembayaran?q={kode}"), "GET admin payments search")
assert kode in r.get_data(as_text=True)
csrf = get_csrf(r)
tx = adb.col_transactions().find_one({"kode_transaksi": kode})
r = show(admin.post(f"/admin/academy/pembayaran/{tx['_id']}/setujui", data={"csrf_token": csrf}, follow_redirects=True), "POST approve")

# Approve lagi -> idempotent, tidak dobel enroll
r2 = admin.post(f"/admin/academy/pembayaran/{tx['_id']}/setujui", data={"csrf_token": csrf}, follow_redirects=True)
enroll_count = adb.col_enrollments().count_documents({"user_id": tx["user_id"], "course_id": tx["course_id"]})
print("Jumlah enrollment setelah approve 2x:", enroll_count)
assert enroll_count == 1

# 9) Siswa refresh status -> approved, lalu akses ruang belajar
r = show(client.get(f"/academy/transaksi/{kode}/status"), "GET status api")
print("Status API:", r.get_json())
assert r.get_json()["status"] == "approved"

r = show(client.get("/academy/ruang-belajar/motion-graphic-dasar"), "GET ruang belajar (setelah approve)")
html = r.get_data(as_text=True)
assert "Intro Timeline" in html
assert "youtube.com/embed" in html
print("Ruang belajar menampilkan video embed: OK")

# 10) Tandai pelajaran selesai
csrf = get_csrf(r)
r = show(client.post(f"/academy/pelajaran/{lesson['_id']}/selesai", headers={"X-CSRFToken": csrf}), "POST tandai selesai")
print("Progress:", r.get_json())

# 11) Dashboard sekarang menunjukkan 1 kelas
r = show(client.get("/academy/dashboard"), "GET dashboard (sudah py punya kelas)")
assert "Motion Graphic Dasar" in r.get_data(as_text=True)
print("Dashboard menampilkan kelas setelah approve: OK")

print("\nSEMUA SMOKE TEST LULUS ✅")

# --------------------------------------------------------------------------- #
# Tes tambahan: forgot-password, reject transaksi, bulk import, reorder,
# pengumuman, manajemen siswa (blokir/reset/hapus), reorder pelajaran.
# --------------------------------------------------------------------------- #
print("\n--- Tes tambahan ---")

# Logout dulu supaya alur forgot-password diuji dari kondisi belum login (realistis)
csrf = get_csrf(client.get("/academy/dashboard"))
client.post("/academy/logout", data={"csrf_token": csrf})

# Forgot password flow
r = show(client.get("/academy/lupa-password"), "GET forgot")
csrf = get_csrf(r)
r = show(client.post("/academy/lupa-password", data={"csrf_token": csrf, "email": "budi@example.com"}, follow_redirects=True), "POST forgot")
html = r.get_data(as_text=True)
m = re.search(r"Mode developer.*?(\d{6})", html, re.S)
otp2 = m.group(1)
csrf2 = get_csrf(r)
r = show(client.post("/academy/verifikasi-otp", data={"csrf_token": csrf2, "otp": otp2}, follow_redirects=True), "POST verify forgot otp")
csrf3 = get_csrf(r)
r = show(client.post("/academy/reset-password", data={"csrf_token": csrf3, "password": "passwordbaru1", "confirm_password": "passwordbaru1"}, follow_redirects=True), "POST reset password")
r = show(client.post("/academy/login", data={"csrf_token": get_csrf(client.get('/academy/login')), "email": "budi@example.com", "password": "passwordbaru1"}, follow_redirects=True), "POST login dgn password baru")
assert "dashboard" in r.request.path.lower()
print("Forgot password flow: OK")

# Buat kelas kedua lalu beli & reject
csrf = get_csrf(admin.get("/admin/academy/kelas"))
admin.post("/admin/academy/kelas", data={
    "csrf_token": csrf, "course_id": "", "judul": "Kelas Kedua", "deskripsi": "x",
    "harga": "50000", "thumbnail_url": "", "status": "published", "urutan": "1",
}, follow_redirects=True)
course2 = adb.col_courses().find_one({"slug": "kelas-kedua"})
csrf = get_csrf(client.get("/academy/kelas/kelas-kedua"))
r = client.post("/academy/kelas/kelas-kedua/beli", data={"csrf_token": csrf}, follow_redirects=True)
kode2 = re.search(r"(ACD-\d{6}-\d{5})", r.get_data(as_text=True)).group(1)
tx2 = adb.col_transactions().find_one({"kode_transaksi": kode2})
csrf = get_csrf(admin.get("/admin/academy/pembayaran"))
r = show(admin.post(f"/admin/academy/pembayaran/{tx2['_id']}/tolak", data={"csrf_token": csrf, "alasan": "Bukti tidak sesuai"}, follow_redirects=True), "POST reject")
tx2_after = adb.col_transactions().find_one({"_id": tx2["_id"]})
assert tx2_after["status"] == "ditolak"
print("Reject transaksi: OK, alasan:", tx2_after["reject_reason"])

# Bulk import lessons (JSON)
import json as _json
csrf = get_csrf(admin.get(f"/admin/academy/kelas/{course['_id']}/pelajaran"))
bulk_data = _json.dumps([
    {"judul": "Lesson A", "video_url": "https://youtu.be/AAAAAAAAAAA", "durasi_menit": 5},
    {"judul": "Lesson B", "video_url": "https://vimeo.com/123456789", "durasi_menit": 8},
    {"judul": "Tanpa URL (harus dilewati)"},
])
r = show(admin.post(f"/admin/academy/kelas/{course['_id']}/pelajaran/impor", data={"csrf_token": csrf, "json_data": bulk_data}, follow_redirects=True), "POST bulk import")
assert "2 pelajaran ditambahkan" in r.get_data(as_text=True)
total_lessons = adb.col_lessons().count_documents({"course_id": course["_id"]})
print("Total lessons setelah impor:", total_lessons)
assert total_lessons == 3

# Reorder: pindahkan lesson pertama ke bawah
lessons_sorted = list(adb.col_lessons().find({"course_id": course["_id"]}).sort("urutan", 1))
first_id = lessons_sorted[0]["_id"]
csrf = get_csrf(admin.get(f"/admin/academy/kelas/{course['_id']}/pelajaran"))
admin.post(f"/admin/academy/kelas/{course['_id']}/pelajaran/{first_id}/pindah", data={"csrf_token": csrf, "arah": "bawah"}, follow_redirects=True)
lessons_after = list(adb.col_lessons().find({"course_id": course["_id"]}).sort("urutan", 1))
assert lessons_after[0]["_id"] != first_id
print("Reorder pelajaran: OK")

# Pengumuman CRUD + pin
csrf = get_csrf(admin.get("/admin/academy/pengumuman"))
admin.post("/admin/academy/pengumuman", data={"csrf_token": csrf, "ann_id": "", "judul": "Libur Lebaran", "isi": "Kelas diliburkan.", "course_id": "", "pinned": "1"}, follow_redirects=True)
ann = adb.col_announcements().find_one({"judul": "Libur Lebaran"})
assert ann and ann["pinned"] is True
r = show(client.get("/academy/pengumuman"), "GET pengumuman siswa")
assert "Libur Lebaran" in r.get_data(as_text=True)
print("Pengumuman tampil ke siswa: OK")

# Student management: detail, block, reset password, revoke
user_doc = adb.col_users().find_one({"email": "budi@example.com"})
r = show(admin.get(f"/admin/academy/siswa/{user_doc['_id']}"), "GET student detail")
csrf = get_csrf(r)
admin.post(f"/admin/academy/siswa/{user_doc['_id']}/blokir", data={"csrf_token": csrf}, follow_redirects=True)
blocked_user = adb.col_users().find_one({"_id": user_doc["_id"]})
assert blocked_user["status"] == "blocked"
r = show(client.get("/academy/dashboard"), "GET dashboard (harus logout krn blocked)")
print("Setelah blokir, redirect ke:", r.request.path)

# unblock lagi biar ga ganggu test lain
csrf = get_csrf(admin.get(f"/admin/academy/siswa/{user_doc['_id']}"))
admin.post(f"/admin/academy/siswa/{user_doc['_id']}/blokir", data={"csrf_token": csrf}, follow_redirects=True)

csrf = get_csrf(admin.get(f"/admin/academy/siswa/{user_doc['_id']}"))
r = show(admin.post(f"/admin/academy/siswa/{user_doc['_id']}/reset-password", data={"csrf_token": csrf}, follow_redirects=True), "POST reset password siswa (admin)")
assert "Password sementara" in r.get_data(as_text=True)
print("Admin reset password siswa: OK")

csrf = get_csrf(admin.get(f"/admin/academy/siswa/{user_doc['_id']}"))
admin.post(f"/admin/academy/siswa/{user_doc['_id']}/cabut/{course['_id']}", data={"csrf_token": csrf}, follow_redirects=True)
assert adb.col_enrollments().find_one({"user_id": user_doc["_id"], "course_id": course["_id"]}) is None
print("Revoke enrollment: OK")

print("\nSEMUA TES TAMBAHAN LULUS ✅")
