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

Tetap ada konfirmasi KIRIM per aktivitas. Setelah klik Submit, script menunggu feedback yang terlihat di form (maksimal 30 detik), menyimpan teks hasil ke `after-submit-N.json`, lalu menunggu pemeriksaanmu. Jika klik atau pembacaan hasil gagal, status disimpan sebagai `unknown` dan proses berhenti tanpa kirim ulang. Klik tidak dianggap bukti keberhasilan atau skor sempurna.

## Format action lain

Dalam actions suatu aktivitas, input dapat ditulis sebagai:

```json
{"type":"fill","form":"#miniQuizForm804","selector":"input[name='q2374[0]']","value":"ISI_JAWABAN_TERVERIFIKASI"}
```

Isi semua field aktivitas, bukan hanya field pertama. Jenis check (radio/checkbox) memakai form dan selector, tanpa value. Jenis select memakai form, selector, dan label pilihan. Ambil selector/name dari hasil capture, jangan menebak. Untuk aktivitas belum dikerjakan yang sudah dipastikan, set retry:false. Ketika ragu, biarkan proses berhenti.

## Batas dan privasi

Auto-wait Playwright dipakai tanpa sleep tetap. Drop dicek dari elemen jawaban yang benar-benar berpindah, bukan posisi kursor. Input text dan struktur match diperiksa langsung pada situs; handler check/select disediakan tetapi belum diuji pada contoh pilihan ganda situs ini. Belum ada uji end-to-end menggunakan Playwright lokal atau submit aktual. Perubahan struktur situs bisa memerlukan pembaruan selector. Kategori drag-and-drop, soal rusak, dan pemahaman audio otomatis belum diimplementasikan. capture menyimpan teks halaman dan screenshot lokal yang mungkin memuat nama akun; jangan bagikan tanpa pemeriksaan. Gunakan sesuai aturan penyelenggara course.

## Validasi sebelum kirim

Semua radio yang terlihat dan aktif diperiksa per grup name: tepat satu pilihan harus dipilih. Semua dropdown yang terlihat dan aktif harus punya pilihan nonkosong, bukan placeholder. Isian teks dan drop slot juga diperiksa. Kontrol tersembunyi atau disabled diabaikan. Pemeriksaan berjalan setelah pengisian dan diulang sesudah konfirmasi KIRIM, tepat sebelum Submit. Skrip menolak mengirim ulang form yang sudah menampilkan feedback lama.

## Format jawaban: peringatan, bukan koreksi otomatis

Jawaban tetap ditulis persis dari file. Spasi di tepi, karakter kontrol, kutip melengkung, serta tanda baca akhir memunculkan peringatan. Peringatan bukan berarti jawabannya salah: tanda tanya atau seru bisa memang diperlukan. Skrip tidak menghapus titik dan tidak mengganti apostrof secara otomatis.

Jika format untuk soal sudah kamu pastikan, tambahkan aturan opsional pada action fill:

```json
{"type":"fill","form":"#miniQuizForm753","selector":"input[name='CONTOH']","value":"Anna packed her suitcase last night","format":{"terminal_punctuation":"none","expected_literal":"Anna packed her suitcase last night"}}
```

Selector di atas hanya contoh, bukan selector soal 753. Ambil selector asli dari capture. terminal_punctuation menerima preserve, none, titik, tanda tanya, atau tanda seru. expected_literal memeriksa kesamaan seluruh teks secara persis. Pelanggaran aturan eksplisit menghentikan proses, bukan mengubah jawaban diam-diam. Konfirmasi KIRIM tetap wajib.

## Membaca feedback dan menjalankan tes

Laporan JSON menyimpan teks mentah serta status feedback: correct/incorrect hanya untuk pernyataan eksplisit situs. exact_match/different_text hanya menunjukkan kesamaan teks Your answer dan Correct; ini bukan perhitungan skor. Feedback multiline dipertahankan di raw_text. Perbedaan apostrof atau tanda baca tidak dinormalisasi. Periksa kunci yang bertentangan dengan materi secara manual.

Jalankan tes tanpa login atau pengiriman jawaban:

    python -m unittest -v test_quiz_checks test_progress test_resume_flow
    python -m py_compile briton.py quiz_checks.py test_quiz_checks.py

18 tes regresi untuk validasi, format, parsing feedback, dan propagasi timeout telah lulus. Pembaca DOM juga diuji read-only pada halaman Brit On group 753 dan mendeteksi lima slot kosong. Instalasi serta alur Playwright login/fill/submit menyeluruh belum diuji; tes unit bukan bukti submit langsung berhasil. Simpan briton.py, quiz_checks.py, progress.py, dan existing_answers.py dalam folder yang sama. Laporan hasil tetap lokal dan diabaikan Git; jangan membagikannya tanpa memeriksa data pribadi.

## Status aktivitas dan melanjutkan pekerjaan

Alur apply sekarang memeriksa status di situs sebelum mengisi setiap aktivitas dalam file jawaban. Cakupannya hanya daftar activities pada file tersebut, bukan seluruh course. Urutan mengikuti file jawaban yang reviewed:true.

Cek status tanpa mengisi atau mengirim:

    python briton.py apply answers/unit3.json --status-only

Isi aktivitas pertama yang belum dinilai, tanpa Submit:

    python briton.py apply answers/unit3.json --allow-retry

Lanjutkan dengan pemeriksaan dan konfirmasi KIRIM untuk setiap aktivitas:

    python briton.py apply answers/unit3.json --allow-retry --submit

--allow-retry tidak menekan tombol Retry, tidak mereset jawaban, dan tidak membuktikan aktivitas sudah selesai. Tanpa --submit, proses berhenti setelah satu aktivitas terisi agar tidak meninggalkan isian belum dikirim untuk pindah ke aktivitas berikutnya. Browser lokal tetap ditutup saat proses berakhir; checkpoint tidak menyimpan jawaban, dan isian yang tidak disimpan situs mungkin harus diisi kembali dari file terverifikasi saat dijalankan lagi.

Status yang dikenali:

- unanswered: kontrol didukung masih kosong, belum ada feedback penilaian.
- filled_unsubmitted: ada isian/pasangan/pilihan, belum ada bukti penilaian.
- graded: feedback hasil penilaian terlihat dan tombol Submit tidak masih terlihat. Aktivitas dilewati tanpa Retry atau Submit.
- uncertain atau unsupported: bukti tidak cukup atau struktur belum didukung; berhenti, bukan menebak status.

Seluruh action diperiksa sebelum ada pengisian. Isian yang sama dipertahankan. Isian teks berbeda (termasuk spasi yang sudah ada), radio yang punya pilihan lain, dropdown yang sudah memilih jawaban lain, atau slot pencocokan yang berisi pasangan berbeda akan menghentikan proses tanpa menimpa jawaban lama. Kontrol dicek lagi sebelum ditulis dan sesudah KIRIM. Tidak ada opsi paksa menimpa.

Checkpoint default berada di sebelah file jawaban, misalnya answers/unit3.checkpoint.json. Gunakan --checkpoint checkpoints/unit3.json jika ingin path lain. Isinya hanya URL aktivitas, status, alasan ringkas, waktu, dan hash file rencana; tidak ada jawaban, password, atau cookie. Penulisan menggunakan file sementara lalu replace. Gunakan satu proses untuk satu checkpoint/profil browser pada satu waktu.

Jalankan perintah yang sama untuk melanjutkan. Skrip membuka kembali aktivitas dalam urutan rencana dan membaca ulang status situs; checkpoint bukan alasan untuk menganggap nilai berhasil. Jika checkpoint pernah mencatat graded tetapi feedback situs tidak terlihat lagi, skrip berhenti untuk pemeriksaan manual. Ini sengaja konservatif karena sebagian halaman mungkin tidak menampilkan ulang feedback setelah dimuat kembali.

Sebelum klik Submit, checkpoint submission_pending disimpan. Jika klik atau feedback gagal, status menjadi submission_unknown. Pada proses berikutnya, jika bukti penilaian terlihat, status diperbarui ke graded dan aktivitas dilewati. Jika belum terlihat, proses berhenti tanpa kirim ulang. Jangan menghapus checkpoint atau mengganti path hanya untuk melewati perlindungan ini; periksa riwayat/nilai pada situs terlebih dahulu. Checkpoint terikat hash seluruh file jawaban: perubahan rencana membutuhkan checkpoint lain setelah memastikan tidak ada pengiriman yang belum pasti.

45 tes unit dan alur dengan browser tiruan lulus, termasuk melewati aktivitas dinilai, membatalkan KIRIM, dry-run, konflik jawaban, dan mencegah pengiriman ulang setelah klik gagal. Snapshot DOM nyata group 753 diuji read-only: lima slot kosong dan tombol Submit masih terlihat. Ini bukan pengujian end-to-end Playwright; tidak ada jawaban atau Submit yang dikirim ke Brit On selama pengembangan fitur resume.
