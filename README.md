# Translate Form

Aplikasi web untuk menerjemahkan teks instruksi kerja (Inggris → Indonesia) berdasarkan kamus,
dibuat dari file Excel `Translate Form.xlsb`. Ada login pengguna, manajemen kamus, riwayat, dan ekspor Excel.

## Menjalankan
```bash
./run.sh            # mode dev di http://127.0.0.1:5000
./run.sh prod       # produksi (gunicorn) di port 8000
# atau Docker:
docker build -t translate-form . && docker run -p 8000:8000 -v tf-data:/srv/instance translate-form
```
Saat pertama kali jalan, akun **admin** dibuat otomatis. Password acak dicetak di console
(atau tentukan lewat `ADMIN_PASSWORD`, lihat `.env.example`). Segera ganti di menu *Akun*.

## Fitur
| Menu | Asal di Excel | Fungsi |
|---|---|---|
| Terjemah | Sheet1 kolom TEXT COPAS → Revised Text | Tempel teks, hasil muncul langsung; salin / unduh .xlsx / simpan riwayat |
| Kamus | Sheet1 kolom Text To Remove / Replace | Tambah, ubah, hapus, urutkan, cari; impor & ekspor .xlsx |
| Gabung Kata | Sheet2 | Kata pertama + kata kedua |
| Riwayat | – | Terjemahan tersimpan per pengguna |
| Pengguna | – | (admin) tambah/ubah/nonaktifkan/hapus akun, reset password |

**Cara kerja terjemah** meniru fungsi `REPLACETEXTS` di Excel: aturan dijalankan berurutan dari atas ke bawah,
cocok sebagian kata, peka huruf besar/kecil. Karena itu *urutan kamus penting*.

## Keamanan
Password di-hash (scrypt), sesi HttpOnly + SameSite, proteksi CSRF, batas percobaan login (5 gagal / 10 menit),
CSP ketat, query SQL berparameter, pencegahan formula injection pada ekspor Excel.
Bila dipasang di belakang HTTPS, set `COOKIE_SECURE=1`.

## Struktur
```
app/        __init__ (factory, CSRF, header), auth, api, views, db, translator, templates/, static/
data/       seed_dictionary.json (243 aturan dari file asli), sample_input.txt
tests/      pytest  ->  python -m pytest
instance/   database SQLite + secret key (dibuat otomatis, jangan di-commit)
```
Perintah CLI: `flask --app wsgi create-user`, `flask --app wsgi init-db`.

## Deploy ke Vercel
Vercel tidak menyimpan file permanen, jadi database memakai **Postgres** (SQLite hanya untuk lokal).
1. Buat database Postgres gratis, mis. **Neon** (Vercel → Storage → Marketplace → Neon). Pakai connection string
   yang *pooled* (host mengandung `-pooler`).
2. Push folder ini ke GitHub, lalu *Import Project* di Vercel (Framework: Other).
3. Di *Settings → Environment Variables* isi:
   - `DATABASE_URL` — connection string Postgres (otomatis terisi bila memakai integrasi Neon)
   - `SECRET_KEY` — string acak panjang (`python -c "import secrets;print(secrets.token_hex(32))"`)
   - `ADMIN_USERNAME` dan `ADMIN_PASSWORD` — akun admin pertama
4. Deploy. Tabel dan 243 aturan kamus dibuat otomatis pada akses pertama, lalu login dengan akun admin tadi.

File terkait: `vercel.json` (semua rute → Flask), `api/index.py` (entry point), `psycopg` di `requirements.txt`.
Cookie otomatis `Secure` dan IP klien dibaca dari proxy Vercel untuk batas percobaan login.
Aplikasi menolak start di Vercel bila `DATABASE_URL`/`SECRET_KEY` belum diisi.
