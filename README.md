# Setup repo

Struktur tambahan: `answers/` untuk jawaban lokal, `captures/` untuk soal/screenshot, `examples/` untuk contoh yang dilacak Git, `config/` dan `ai/` untuk template AI, serta `scripts/` untuk installer. Contoh di root tetap tersedia agar perintah lama tidak rusak.

## Mulai dari GitHub (Windows)

Butuh Git dan Python 3.10+. Alternatif tanpa Git: Code > Download ZIP, ekstrak, lalu buka PowerShell di folder hasil ekstrak.

```powershell
git clone https://github.com/Frask-nivis/briton.git
cd briton
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
.\.venv\Scripts\python.exe briton.py login
.\.venv\Scripts\python.exe briton.py capture --url "https://learn.onbriton.com/course/learn/162?group=817" --out captures/questions817.json
.\.venv\Scripts\python.exe briton.py apply answers/match817.json --allow-retry
```

Installer mengunduh dependensi dan Chromium, membuat folder kerja, lalu menyalin contoh tanpa menimpa jawaban/config lokal yang sudah ada. Periksa `answers/match817.json` dan set `reviewed:true` hanya setelah memeriksa materi. Jangan menjalankan apply sebelum itu. Perintah apply di atas tidak mengirim jawaban.

AI masih **template**, bukan fitur yang sudah aktif. Lihat [panduan AI](ai/README.md). Workflow GitHub Actions belum berhasil diunggah: API menolak penulisan `.github/workflows/check.yml` dengan error 404. Template workflow disiapkan terpisah. Setelah dipasang, workflow tersebut hanya memeriksa sintaks Python, JSON, CLI, dan PowerShell; tidak login ke Brit On atau mengirim jawaban. Pemeriksaan lokal sintaks Python, JSON, dan PowerShell sudah lolos, tetapi instalasi dan browser end-to-end belum diuji.

File jawaban, capture, screenshot hasil, konfigurasi lokal, dan `.env` diabaikan Git. Ini tidak menghapus file yang sudah pernah di-commit; periksa `git status` sebelum push dan jangan pakai `git add -f` untuk data pribadi.

---

# Brit On — Python Playwright

Dibuat berdasarkan inspeksi lesson 56, aktivitas 804 (input) dan 817 (pencocokan). Ini helper browser dengan jawaban yang kamu periksa, bukan AI yang mengerjakan seluruh course sendiri. Skills Review tidak didukung. Script tidak mengubah nilai/progress lewat API.

## Windows PowerShell

Buka terminal di folder ini. Butuh Python 3.10+ dan koneksi internet.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe briton.py login
.\.venv\Scripts\python.exe briton.py scan --url "https://learn.onbriton.com/course/lesson/56" --out activities.json
.\.venv\Scripts\python.exe briton.py capture --url "https://learn.onbriton.com/course/learn/162?group=817" --out questions817.json
```

Chromium perlu diunduh saat instalasi; tidak perlu Selenium, ChromeDriver, atau API key. Login sendiri satu kali di browser yang muncul. Sesi Strawberry tidak otomatis ikut. Profil berisi sesi login disimpan di %LOCALAPPDATA%/BritonHelper/browser-profile, di luar folder script/sinkronisasi. Jangan bagikan profil tersebut. Tutup proses script sebelumnya sebelum menjalankan lagi.

## Mengisi pencocokan 817

Baca questions817.json dan periksa lima jawaban di match817.example.json terhadap bacaan. Setelah sesuai, ubah reviewed menjadi true. Contoh ini ditandai retry:true karena situs menampilkan Retry activity; status ini bukan bukti soal sudah pernah disubmit.

```powershell
.\.venv\Scripts\python.exe briton.py apply match817.example.json --allow-retry
```

Default hanya mengisi, memverifikasi drop, mengambil screenshot, lalu menunggu pemeriksaanmu. Tidak mengirim. Opsi --allow-retry berarti kamu mengizinkan membuka aktivitas yang berstatus retry; script tidak menekan tombol Retry/reset.

Untuk mengirim jawaban yang sudah diperiksa:

```powershell
.\.venv\Scripts\python.exe briton.py apply match817.example.json --allow-retry --submit
```

Tetap ada konfirmasi KIRIM per aktivitas. Setelah klik Submit, periksa hasil di browser; script tidak menganggap klik sama dengan keberhasilan atau skor sempurna. Jangan ulang submit saat jaringan bermasalah sebelum mengecek hasil.

## Format action lain

Dalam actions suatu aktivitas, input dapat ditulis sebagai:

```json
{"type":"fill","form":"#miniQuizForm804","selector":"input[name='q2374[0]']","value":"ISI_JAWABAN_TERVERIFIKASI"}
```

Isi semua field aktivitas, bukan hanya field pertama. Jenis check (radio/checkbox) memakai form dan selector, tanpa value. Jenis select memakai form, selector, dan label pilihan. Ambil selector/name dari hasil capture, jangan menebak. Untuk aktivitas belum dikerjakan yang sudah dipastikan, set retry:false. Ketika ragu, biarkan proses berhenti.

## Batas dan privasi

Auto-wait Playwright dipakai tanpa sleep tetap. Drop dicek dari elemen jawaban yang benar-benar berpindah, bukan posisi kursor. Input text dan struktur match diperiksa langsung pada situs; handler check/select disediakan tetapi belum diuji pada contoh pilihan ganda situs ini. Belum ada uji end-to-end menggunakan Playwright lokal atau submit aktual. Perubahan struktur situs bisa memerlukan pembaruan selector. Kategori drag-and-drop, soal rusak, dan pemahaman audio otomatis belum diimplementasikan. capture menyimpan teks halaman dan screenshot lokal yang mungkin memuat nama akun; jangan bagikan tanpa pemeriksaan. Gunakan sesuai aturan penyelenggara course.
