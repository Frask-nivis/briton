# Template AI (belum terhubung)

`briton.py` belum membaca konfigurasi AI, `.env`, atau prompt ini dan tidak memanggil provider mana pun. Tidak perlu API key untuk setup sekarang.

Untuk eksperimen manual: ambil capture lokal, hapus informasi pribadi, lalu gunakan prompt `ai/prompts/draft-answers.md` dengan materi yang relevan. Periksa draf sendiri dan ubah ke format plan pada contoh. Jangan otomatis mengubah `reviewed` ke `true`.

Jika integrasi ditambahkan nanti, salin `config/ai.example.json` menjadi `config/ai.local.json`, tentukan provider/model, dan baca key dari environment. File lokal diabaikan Git. Jangan masukkan key di JSON, prompt, issue, atau log.
