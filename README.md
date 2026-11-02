# FYY MOTION — Portal Order & Keuangan Jasa Animasi Motion Graphic

Website admin (portal) untuk mengelola usaha jasa pembuatan animasi **Motion Graphic**:
orderan & nomor antrian, data pesanan teks, pemasukan/pengeluaran, sampai akuntansi lengkap
(**Jurnal Umum → Buku Besar → Neraca Saldo → Laba Rugi**). Dibangun dengan **Python Flask**,
 database **JSON array** (`database.json`) yang bisa **di-download (backup)** dan **di-upload (restore)**,
tampilan **Admin Bootstrap 5**, dan siap **deploy ke Vercel**.

---

## ✨ Fitur

| Kebutuhan | Implementasi |
|---|---|
| Portal admin rapi | Login (session + CSRF), sidebar admin Bootstrap 5 + Bootstrap Icons, responsif HP & desktop, bisa print laporan |
| Pemasukan & pengeluaran | Dashboard kartu Pemasukan (Kas masuk), Pengeluaran (Kas keluar), Laba Bersih, Saldo Kas + grafik 6 bulan (Chart.js), semua bisa difilter periode |
| Daftar orderan & nomor antrian | Nomor antrian otomatis (`#1, #2, ...`) + kode order `FYY-0001`, halaman khusus **Antrian Kerja** (antrian terdepan, urutan aktif, papan Kanban per status) |
| Data pesanan teks | Per order ada **Brief**, **Script/Teks yang dianimasikan**, **Referensi**, **Catatan Revisi**, link preview & hasil — ada tombol **Salin** dan **Print Brief Kerja** |
| Detail nama & nomor WA | Nama client + nomor WhatsApp wajib diisi, otomatis format `62...`, tombol **Chat WA (`wa.me`)** dengan pesan status siap kirim + tombol salin nomor |
| Status dibedakan | **Order Masuk → Dalam Antrian → Sedang Diproses → Minta Revisi → Selesai/Sudah Jadi → Batal** (badge warna berbeda) + status bayar **Belum / DP / Lunas** + progress % |
| Dashboard bisa difilter | Filter periode (Hari Ini/Bulan Ini/Bulan Lalu/Tahun Ini/Semua/Custom), cari nama/WA/kode, filter status/bayar/prioritas, urut antrian/terbaru/deadline/harga, filter cepat 1-klik per status |
| Transaksi transparan | Halaman **Transaksi (In/Out)**: semua uang masuk-keluar terlihat, terkait order mana, metode apa, akun debit/kreditnya apa |
| Akuntansi lengkap | **Jurnal Umum** double-entry (cek Debit = Kredit), **Buku Besar** per akun dengan saldo berjalan, **Neraca Saldo** (cek balance), **Laporan Laba Rugi**, **Daftar Akun/COA** bisa tambah/edit |
| Database JSON array | Satu file `database.json` berisi array `orders`, `transactions`, `accounts` (+ `settings`) — mudah dibaca/diedit manusia |
| Backup & restore | **Download** `database.json` kapan saja; **Upload/Restore** file `.json` (atau paste teks JSON) untuk memulihkan data; export CSV (Orders/Transaksi/Jurnal/Neraca); reset data contoh / kosongkan data |

---

## 🔐 Login

| | |
|---|---|
| **Username bawaan** | `admin` |
| **Password bawaan** | `fyymotion123` |

Ganti sebelum dipakai publik melalui Environment Variables: `ADMIN_USERNAME`, `ADMIN_PASSWORD`, dan `SECRET_KEY` (lihat `.env.example`).

---

## ▶️ Jalankan di Lokal (Laptop)

Butuh Python 3.10+ (disarankan 3.11/3.12).

```bash
# 1) masuk folder proyek
cd FYYMOTION

# 2) buat virtual environment & install Flask
python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt

# 3) (opsional) atur akun & secret lewat environment
# Windows PowerShell:
#   $env:ADMIN_PASSWORD="password-baru-anda"; $env:SECRET_KEY="acak-panjang"
# macOS/Linux:
#   export ADMIN_PASSWORD="password-baru-anda" SECRET_KEY="acak-panjang"

# 4) jalankan
python app.py
```

Buka **http://127.0.0.1:5000** → login → langsung terlihat dashboard berisi **data contoh**.
Di lokal, semua perubahan tersimpan permanen di `database.json`.

> Mulai usaha yang sesungguhnya? Buka menu **Backup & Restore → Zona Berbahaya → Kosongkan Order & Transaksi**
> (ketik `kosongkan`) untuk menghapus data contoh dan mulai dari nol. Daftar Akun standar akuntansi tetap dipertahankan.

---

## ▲ Deploy ke Vercel

Aplikasi ini mengikuti cara resmi Vercel untuk Flask modern: Vercel mencari instance Flask bernama `app`
pada entrypoint `app.py` di root repositori — lihat dokumentasi:
[Deploy a Flask app on Vercel](https://vercel.com/docs/frameworks/backend/flask).
`api/index.py` disediakan sebagai entrypoint cadangan untuk konfigurasi lama, dan `vercel.json`
memastikan folder `templates/`, `static/`, dan `database.json` ikut terbawa ke serverless function.

### Cara 1 — Lewat GitHub (disarankan)

1. Push/merge kode ini ke branch **`main`** di GitHub (repository `IKOO-INC/FYYMOTION`).
2. Masuk ke [vercel.com](https://vercel.com) → **Add New… → Project** → **Import** repository `FYYMOTION`.
3. **Framework Preset**: pilih/biarkan **Flask** (terdeteksi otomatis). **Root Directory**: `./` (root). Tidak perlu Build/Output command khusus.
4. Tambahkan **Environment Variables**:
   - `SECRET_KEY` = string acak panjang (wajib diganti)
   - `ADMIN_USERNAME` = `admin` (atau nama Anda)
   - `ADMIN_PASSWORD` = password kuat Anda (jangan pakai bawaan)
5. Klik **Deploy**. Setelah selesai, buka URL `*.vercel.app` Anda dan login.

### Cara 2 — Lewat Vercel CLI

```bash
npm i -g vercel
cd FYYMOTION
vercel          # pertama kali: hubungkan proyek (preview)
vercel --prod   # deploy production
```

### ⚠️ PENTING — Penyimpanan data di Vercel (baca ini!)

Filesystem Vercel (serverless) bersifat **read-only & sementara**. Aplikasi otomatis memakai
`/tmp/fyymotion_database.json` saat berjalan di Vercel. Folder `/tmp` **bisa ter-reset** kapan saja
(redeploy, function dingin/cold-start). Artinya:

1. **Setiap selesai bekerja di Vercel, klik menu _Backup & Restore → Download database.json_** dan simpan file-nya (HP/laptop/Google Drive).
2. Jika data tiba-tiba kembali ke data contoh, **Upload (Restore)** file backup terakhir Anda di menu yang sama — data langsung kembali.
3. Untuk master data yang permanen tanpa perlu upload ulang, jalankan juga aplikasi ini **di lokal**
   (data tersimpan permanen di `database.json`), atau jadikan Vercel khusus tampilan/demo & akses cepat.
   Pengembangan berikutnya bisa mengganti JSON lokal dengan database cloud (mis. Vercel Postgres/Blob, Supabase) bila ingin permanen penuh di cloud — struktur datanya sudah siap dipindahkan.

---

## 🧭 Alur Kerja Sehari-hari

1. **Order masuk** → menu **Order Baru**: isi nama client, **no. WA**, judul, harga & DP, lalu tempel **brief + script teks** dari chat client. Centang *"Catat DP otomatis"* supaya DP langsung masuk Jurnal/Kas. Status awal: **Order Masuk**, nomor antrian terbit otomatis.
2. **Kerjakan sesuai antrian** → buka **Antrian Kerja**: antrian terdepan tampil paling atas. Buka detailnya untuk membaca script/teks (ada tombol Salin & Print). Ubah status: **Dalam Antrian → Sedang Diproses**, geser progress %.
3. **Client minta revisi** → ubah status ke **Minta Revisi** dan tulis poin revisi di kolom Catatan Revisi. Menu sidebar *Minta Revisi* menampilkan badge jumlahnya supaya tidak ada yang terlupa.
4. **Selesai & pelunasan** → status **Selesai/Sudah Jadi**, lalu dari detail order klik **Catat Pembayaran/Pelunasan** (form transaksi terisi otomatis sebesar sisa bayar). Kirim kabar ke client lewat tombol **WA**.
5. **Pengeluaran** (langganan software, internet, freelancer, iklan) → menu **Transaksi → Catat Transaksi Baru**, pilih jenisnya — akun Debit/Kredit terisi otomatis.
6. **Cek keuangan** → **Dashboard** (ringkas), **Jurnal Umum** (detail double-entry), **Buku Besar** (per akun), **Neraca Saldo** (pastikan *SEIMBANG*), **Laba Rugi** — semua bisa difilter per bulan dan di-print/export CSV.
7. **Tutup hari** → **Download Backup** `database.json`. Simpan dengan nama bertanggal.

---

## 🗄️ Struktur Database (`database.json`)

```jsonc
{
  "settings":     { "nama_usaha": "FYY MOTION", "tagline": "...", "pemilik": "", "wa_admin": "" },
  "accounts":     [ { "kode": "101", "nama": "Kas", "tipe": "Aset", "saldo_normal": "Debit", "is_cash": true }, ... ],
  "orders":       [ { "id": "...", "order_code": "FYY-0001", "queue_no": 1,
                      "client_name": "...", "wa_number": "628...", "judul": "...",
                      "jenis_animasi": "Motion Graphic", "brief": "...", "script_teks": "...",
                      "harga": 1500000, "dp": 750000, "status_pembayaran": "dp",
                      "status": "proses", "progress": 50, "deadline": "2026-10-28", ... }, ... ],
  "transactions": [ { "id": "...", "tanggal": "2026-10-21", "keterangan": "DP order FYY-0002 ...",
                      "jenis": "dp_order", "akun_debit": "101", "akun_kredit": "202",
                      "jumlah": 425000, "order_id": "...", "metode_bayar": "DANA" }, ... ]
}
```

- **Pemasukan** = transaksi yang akun **Debit**-nya Kas/Bank (`is_cash: true`). **Pengeluaran** = Kas/Bank di sisi **Kredit**.
- Jurnal, Buku Besar, Neraca Saldo & Laba Rugi **dihitung otomatis** dari array `transactions`, jadi selalu konsisten dan transparan.
- Restore juga menerima **array murni** `[{...order...}, ...]` — akan diimpor sebagai daftar `orders`.

---

## 📁 Struktur Proyek

```
FYYMOTION/
├── app.py                 # Aplikasi Flask lengkap (entrypoint utama Vercel & lokal)
├── api/index.py           # Entrypoint cadangan Vercel (re-export app)
├── database.json          # DATABASE — JSON array (orders, transactions, accounts)
├── requirements.txt       # Flask saja (ringan)
├── vercel.json            # Konfigurasi Vercel (include templates/static/database)
├── .vercelignore / .env.example
├── templates/             # 15 halaman Admin Bootstrap 5 (Jinja2)
└── static/css/style.css, static/js/app.js
```

## 🔧 Troubleshooting

| Masalah | Solusi |
|---|---|
| Data di Vercel kembali ke contoh | Itu `/tmp` ter-reset. **Restore** file backup `database.json` terakhir di menu Backup & Restore. Biasakan download backup tiap selesai bekerja. |
| Lupa password | Password diatur dari Environment Variable `ADMIN_PASSWORD` (bawaan `fyymotion123`). Ubah di Vercel → Settings → Environment Variables, lalu Redeploy. |
| Restore gagal "file tidak valid" | Pastikan file adalah hasil **Download Backup** aplikasi ini (JSON berisi array `accounts`, `orders`, `transactions`), ukuran < 8 MB. |
| Neraca tidak seimbang | Periksa Transaksi/Jurnal pada periode itu — biasanya ada transaksi yang diedit manual dengan akun/jumlah keliru. |
| DP belum masuk pendapatan di Laba Rugi | Memang benar secara akuntansi: DP tercatat di akun **202 (DP Client)**. Saat lunas/selesai, catat pembayaran dengan jenis *Pembayaran Order (Lunas)* → akun **401** agar masuk pendapatan. Uang riilnya tetap terlihat di Kas. |

---

*Dibuat untuk FYY MOTION — usaha jasa animasi Motion Graphic. Semoga orderan makin ramai & keuangan makin rapi!* 🎬
