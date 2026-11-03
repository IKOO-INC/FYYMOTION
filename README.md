# FYY MOTION — Portal Order & Keuangan Jasa Animasi Motion Graphic

Website profil publik + portal admin untuk mengelola usaha jasa pembuatan animasi **Motion Graphic**:
route `/` adalah **profil/portofolio publik FYY MOTION yang seluruh teksnya bisa diedit dari admin**,
sedangkan `/dashboard` adalah ruang operasional untuk orderan & nomor antrian, data pesanan teks,
pemasukan/pengeluaran, sampai akuntansi lengkap (**Jurnal Umum → Buku Besar → Neraca Saldo → Laba Rugi**).
Dibangun dengan **Python Flask**, database utama **MongoDB Atlas** (melalui ENV `MONGODB_URI`) dengan
**JSON fallback + backup/restore**, tampilan agency Bootstrap 5 + Font Awesome, dan siap **deploy ke Vercel**.

---

## ✨ Fitur

| Kebutuhan | Implementasi |
|---|---|
| Profil publik di route `/` | Halaman hero, showreel, marquee layanan, keunggulan, proses, portofolio, layanan, testimoni, dan CTA WhatsApp. Semua teks, URL gambar/video, daftar layanan/proses/portofolio, statistik, kontak, dan sosial media diedit dari **Admin → Edit Profil** (`/admin/profil`) |
| Portal admin rapi | Dashboard operasional kini di `/dashboard`; login session + CSRF, sidebar Bootstrap 5 + **Font Awesome (`fa-solid`/`fa-brands`)**, tipografi Inter Tight/Inter/Instrument Serif, card paper-ink dengan offset shadow, animasi reveal/hover/marquee, responsif HP & desktop, bisa print laporan |
| Pemasukan & pengeluaran | Dashboard kartu Pemasukan (Kas masuk), Pengeluaran (Kas keluar), Laba Bersih, Saldo Kas + grafik 6 bulan (Chart.js), semua bisa difilter periode |
| Daftar orderan & nomor antrian | Nomor antrian otomatis (`#1, #2, ...`) + kode order `FYY-0001`, halaman khusus **Antrian Kerja** (antrian terdepan, urutan aktif, papan Kanban per status) |
| Data pesanan & assets | Per order ada **Brief**, **Script/Teks yang dianimasikan**, **Referensi**, **Catatan Revisi**, **Link Google Drive Assets client**, link preview & hasil — ada tombol **Salin**, buka Drive 1-klik, dan **Print Brief Kerja** |
| Detail nama & nomor WA | Nama client + nomor WhatsApp wajib diisi, otomatis format `62...`, tombol **Chat WA (`wa.me`)** dengan pesan status siap kirim + tombol salin nomor |
| Status dibedakan | **Order Masuk → Dalam Antrian → Sedang Diproses → Minta Revisi → Selesai/Sudah Jadi → Batal** (badge warna berbeda) + status bayar **Belum / DP / Lunas** + progress % |
| Dashboard bisa difilter | Filter periode (Hari Ini/Bulan Ini/Bulan Lalu/Tahun Ini/Semua/Custom), cari nama/WA/kode, filter status/bayar/prioritas, urut antrian/terbaru/deadline/harga, filter cepat 1-klik per status |
| Transaksi transparan | Halaman **Transaksi (In/Out)**: semua uang masuk-keluar terlihat, terkait order mana, metode apa, akun debit/kreditnya apa |
| Akuntansi lengkap | **Jurnal Umum** double-entry (cek Debit = Kredit), **Buku Besar** per akun dengan saldo berjalan, **Neraca Saldo** (cek balance), **Laporan Laba Rugi**, **Daftar Akun/COA** bisa tambah/edit |
| Clipboard teks berulang | Simpan price list/teks manual, lalu salin dengan satu klik; tersimpan di koleksi `clipboard_items` |
| Export Excel tabel asli | Orders, Transaksi, Jurnal Umum, Neraca Saldo, dan workbook lengkap diunduh sebagai `.xlsx` dengan **Excel Table asli**, header berfilter, freeze pane, zebra rows, hyperlink, serta format Rupiah/tanggal/persen. CSV lama tetap tersedia sebagai kompatibilitas |
| MongoDB Atlas permanen | Koleksi `orders`, `transactions`, `accounts`, `clipboard_items`, dan `app_state` (meta/settings/profile) di MongoDB Atlas melalui `MONGODB_URI`; tanpa URI, aplikasi otomatis memakai JSON fallback |
| Backup & restore | **Download** snapshot JSON dari MongoDB/JSON aktif kapan saja; **Upload/Restore** file `.json` (atau paste teks JSON) untuk memulihkan data termasuk profil & clipboard; backup lama tanpa `profile` otomatis memakai teks bawaan; reset data contoh / kosongkan data |

---

## 🔐 Login

| | |
|---|---|
| **Username bawaan** | `admin` |
| **Password bawaan** | `fyymotion123` |

Ganti sebelum dipakai publik melalui Environment Variables: `ADMIN_USERNAME`, `ADMIN_PASSWORD`, dan `SECRET_KEY`.
Untuk MongoDB Atlas tambahkan juga `MONGODB_URI` dan (opsional) `MONGODB_DB_NAME=fyymotion` (lihat `.env.example`).
Jangan pernah commit connection string MongoDB asli ke GitHub.

---

## ▶️ Jalankan di Lokal (Laptop)

Butuh Python 3.10+ (disarankan 3.11/3.12).

```bash
# 1) masuk folder proyek
cd FYYMOTION

# 2) buat virtual environment & install Flask + PyMongo + OpenPyXL
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

Buka **http://127.0.0.1:5000** untuk profil publik, lalu **http://127.0.0.1:5000/login** → login → dashboard admin di **`/dashboard`** berisi **data contoh**.
Tanpa `MONGODB_URI`, perubahan lokal tersimpan permanen di `database.json`. Bila `MONGODB_URI`
diisi, lokal dan Vercel memakai MongoDB Atlas yang sama.

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
   - `MONGODB_URI` = connection string MongoDB Atlas (Production & Preview)
   - `MONGODB_DB_NAME` = `fyymotion` (opsional bila nama database sudah ada di URI)
5. Klik **Deploy**. Setelah selesai, buka URL `*.vercel.app` Anda dan login.

### Cara 2 — Lewat Vercel CLI

```bash
npm i -g vercel
cd FYYMOTION
vercel          # pertama kali: hubungkan proyek (preview)
vercel --prod   # deploy production
```

### 🍃 MongoDB Atlas di Vercel (penyimpanan utama & permanen)

1. Buat cluster gratis dan **Database User khusus** di MongoDB Atlas.
2. Atlas → **Network Access** → tambahkan `0.0.0.0/0` agar IP server Vercel yang berubah-ubah bisa konek.
3. Atlas → **Database → Connect → Drivers** → salin connection string `mongodb+srv://...`.
4. Vercel → Project → Settings → Environment Variables → buat:
   - `MONGODB_URI` = connection string lengkap (target Production & Preview)
   - `MONGODB_DB_NAME` = `fyymotion` (opsional)
5. **Redeploy**. Saat pertama terhubung dan koleksi kosong, aplikasi otomatis men-seed data awal dari `database.json` repo ke koleksi `accounts`, `orders`, `transactions`, `clipboard_items`, dan `app_state`.
6. Cek `https://domain-anda/health`: harus menampilkan `"storage":"mongodb"` dan `"database_connected":true`.

Bila `MONGODB_URI` belum terpasang/terputus, aplikasi memakai JSON fallback agar tetap bisa dibuka.
Namun di Vercel file JSON berada di `/tmp` yang bisa ter-reset, jadi selesaikan koneksi Atlas dan tetap download backup JSON berkala sebagai arsip offline.

---

## 🧭 Alur Kerja Sehari-hari

1. **Order masuk** → menu **Order Baru**: isi nama client, **no. WA**, judul, harga & DP, tempel **brief + script teks**, lalu masukkan **link Google Drive Assets** berisi logo/foto/font/VO/referensi dari client. Centang *"Catat DP otomatis"* supaya DP langsung masuk Jurnal/Kas. Status awal: **Order Masuk**, nomor antrian terbit otomatis.
2. **Kerjakan sesuai antrian** → buka **Antrian Kerja**: antrian terdepan tampil paling atas. Buka detailnya untuk membaca script/teks (ada tombol Salin & Print). Ubah status: **Dalam Antrian → Sedang Diproses**, geser progress %.
3. **Client minta revisi** → ubah status ke **Minta Revisi** dan tulis poin revisi di kolom Catatan Revisi. Menu sidebar *Minta Revisi* menampilkan badge jumlahnya supaya tidak ada yang terlupa.
4. **Selesai & pelunasan** → status **Selesai/Sudah Jadi**, lalu dari detail order klik **Catat Pembayaran/Pelunasan** (form transaksi terisi otomatis sebesar sisa bayar). Kirim kabar ke client lewat tombol **WA**.
5. **Pengeluaran** (langganan software, internet, freelancer, iklan) → menu **Transaksi → Catat Transaksi Baru**, pilih jenisnya — akun Debit/Kredit terisi otomatis.
6. **Cek keuangan** → **Dashboard** (ringkas), **Jurnal Umum** (detail double-entry), **Buku Besar** (per akun), **Neraca Saldo** (pastikan *SEIMBANG*), **Laba Rugi** — semua bisa difilter per bulan, di-print, dan diekspor ke Excel.
7. **Perbarui etalase publik** → **Edit Profil**: ganti hero, showreel, portofolio, layanan, proses, testimoni, nomor WA, dan sosial media, lalu buka route `/` untuk pratinjau.
8. **Tutup hari** (opsional tapi dianjurkan) → **Download Backup JSON** dan/atau **Workbook Excel** dari database aktif sebagai arsip offline bertanggal.

---

## 🗄️ Struktur Database MongoDB & Backup JSON

Di MongoDB Atlas data disimpan sebagai koleksi:

- `orders` — termasuk `drive_assets_url` untuk folder Google Drive Assets client
- `transactions` — sumber Jurnal Umum, Buku Besar, Neraca Saldo, dan Laba Rugi
- `accounts` — Chart of Accounts
- `clipboard_items` — teks price list dan teks berulang
- `app_state` — dokumen `state` berisi `meta`, `settings`, dan `profile` publik

Format file backup/restore tetap JSON berikut:

```jsonc
{
  "settings":     { "nama_usaha": "FYY MOTION", "tagline": "...", "pemilik": "", "wa_admin": "" },
  "profile":      { "hero_title_prefix": "Motion", "hero_title_accent": "Graphic", "portfolio": [ ... ] },
  "accounts":     [ { "kode": "101", "nama": "Kas", "tipe": "Aset", "saldo_normal": "Debit", "is_cash": true }, ... ],
  "orders":       [ { "id": "...", "order_code": "FYY-0001", "queue_no": 1,
                      "client_name": "...", "wa_number": "628...", "judul": "...",
                      "jenis_animasi": "Motion Graphic", "brief": "...", "script_teks": "...",
                      "harga": 1500000, "dp": 750000, "status_pembayaran": "dp",
                      "status": "proses", "progress": 50, "deadline": "2026-10-28",
                      "drive_assets_url": "https://drive.google.com/drive/folders/...", ... }, ... ],
  "transactions": [ { "id": "...", "tanggal": "2026-10-21", "keterangan": "DP order FYY-0002 ...",
                      "jenis": "dp_order", "akun_debit": "101", "akun_kredit": "202",
                      "jumlah": 425000, "order_id": "...", "metode_bayar": "DANA" }, ... ],
  "clipboard_items": [ { "title": "Price List", "content": "..." }, ... ]
}
```

- **Pemasukan** = transaksi yang akun **Debit**-nya Kas/Bank (`is_cash: true`). **Pengeluaran** = Kas/Bank di sisi **Kredit**.
- Jurnal, Buku Besar, Neraca Saldo & Laba Rugi **dihitung otomatis** dari koleksi/array `transactions`, jadi selalu konsisten dan transparan.
- Restore juga menerima **array murni** `[{...order...}, ...]` — akan diimpor sebagai daftar `orders`.

---

## 📁 Struktur Proyek

```
FYYMOTION/
├── app.py                 # Aplikasi Flask lengkap (entrypoint utama Vercel & lokal)
├── api/index.py           # Entrypoint cadangan Vercel (re-export app)
├── database.json          # Seed awal + fallback JSON + format backup/restore
├── requirements.txt       # Flask + PyMongo + OpenPyXL (Excel .xlsx)
├── vercel.json            # Konfigurasi Vercel (include templates/static/database)
├── .vercelignore / .env.example
├── templates/             # Profil publik + halaman Admin Bootstrap 5 (Jinja2)
└── static/css/style.css, static/js/app.js, static/img/motion-showreel.jpg
```

## 🔧 Troubleshooting

| Masalah | Solusi |
|---|---|
| Di Vercel masih tertulis JSON fallback | `MONGODB_URI` belum terbaca. Pasang ENV untuk Production & Preview lalu **Redeploy**; cek `/health` sampai `storage` = `mongodb` dan `database_connected` = `true`. |
| MongoDB tidak terhubung | Periksa username/password Database User di URI, nama DB, dan Atlas Network Access `0.0.0.0/0`. Menu **Backup & Database** menampilkan ringkasan error koneksi. |
| Data di Vercel kembali ke contoh | Biasanya aplikasi masih memakai JSON `/tmp`. Aktifkan MongoDB Atlas; untuk pemulihan cepat, **Restore** backup JSON terakhir. |
| Lupa password | Password diatur dari Environment Variable `ADMIN_PASSWORD` (bawaan `fyymotion123`). Ubah di Vercel → Settings → Environment Variables, lalu Redeploy. |
| Restore gagal "file tidak valid" | Pastikan file adalah hasil **Download Backup** aplikasi ini (JSON berisi array `accounts`, `orders`, `transactions`), ukuran < 8 MB. |
| Neraca tidak seimbang | Periksa Transaksi/Jurnal pada periode itu — biasanya ada transaksi yang diedit manual dengan akun/jumlah keliru. |
| DP belum masuk pendapatan di Laba Rugi | Memang benar secara akuntansi: DP tercatat di akun **202 (DP Client)**. Saat lunas/selesai, catat pembayaran dengan jenis *Pembayaran Order (Lunas)* → akun **401** agar masuk pendapatan. Uang riilnya tetap terlihat di Kas. |

---

*Dibuat untuk FYY MOTION — usaha jasa animasi Motion Graphic. Semoga orderan makin ramai & keuangan makin rapi!* 🎬
