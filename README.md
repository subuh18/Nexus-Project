# NEXUS — Knowledge Operating System

Proyek riset pribadi yang mengumpulkan, menyaring, menyimpan, dan menganalisis
publikasi ilmiah serta berita terkait **studi Islam dan etika lingkungan**,
dengan fokus mendukung riset tafsir dengan metodologi *muqāran* (perbandingan).

Dibangun sebagai proyek belajar dari nol — dari belum pernah menulis kode
sampai memiliki sistem backend, Knowledge Graph, dan AI Agent yang berjalan
otonom setiap hari.

🔗 Dashboard: https://subuh18.github.io/Nexus-Project/
🔗 Backend API: https://nexus-project-production-c83c.up.railway.app/docs

---

## Arsitektur

```
Data (4 sumber) → Ingestion (Python/FastAPI) → Cleaning (filter bidang ilmu)
→ Knowledge Graph (Neo4j) → AI Reasoning (Groq/Llama) → Insight → Action
  (dashboard + Telegram)
```

Frontend (dashboard) dan backend (API) di-deploy terpisah:
- **Frontend**: `index.html` — statis, di-hosting di GitHub Pages
- **Backend**: `main.py` — FastAPI, di-hosting di Railway

---

## Tech Stack

| Komponen | Teknologi | Kenapa dipilih |
|---|---|---|
| Backend | FastAPI + Uvicorn | Ringan, dokumentasi API otomatis, umum dipakai untuk backend AI |
| Data akademik | OpenAlex, Crossref, Semantic Scholar, arXiv | Gratis, tidak semuanya butuh API key |
| Berita | Google News RSS | Gratis, tanpa API key, mendukung Bahasa Indonesia |
| AI (ringkasan & analisis) | Groq (Llama 3.3 70B) | Gratis, model open-source, cepat |
| Knowledge Graph | Neo4j AuraDB (free tier) | Database graph, cocok untuk data yang fokus pada hubungan antar entitas |
| Notifikasi | Telegram Bot API | Gratis, setup cepat, tidak perlu server email |
| Hosting backend | Railway | Free tier, mudah untuk pemula |
| Visualisasi graph | vis-network (CDN) | Ringan, otomatis mengatur layout node |
| Penjadwal otomatis | cron-job.org | Gratis, tidak perlu setup server tambahan |

---

## Daftar Endpoint API

### Dashboard (data mentah)
| Endpoint | Fungsi |
|---|---|
| `GET /sumber-data` | Status sumber data (dummy, untuk tampilan) |
| `GET /agents` | Status tiap AI Agent |
| `GET /knowledge-graph` | Hitungan node/edge/topik/penulis di Neo4j |
| `GET /graph-data` | Data mentah node & edge untuk visualisasi |
| `GET /publikasi-terbaru?q=` | Publikasi dari OpenAlex saja |
| `GET /publikasi-gabungan?q=` | Publikasi gabungan 4 sumber |
| `GET /ringkasan-riset?q=` | Ringkasan AI dari publikasi OpenAlex |

### Penyimpanan ke Knowledge Graph
| Endpoint | Fungsi |
|---|---|
| `GET /simpan-graph?q=` | Simpan 1 topik ke Neo4j |
| `GET /simpan-graph-banyak?topik=a,b,c` | Simpan banyak topik sekaligus |

### AI Agents
| Endpoint | Agent | Fungsi |
|---|---|---|
| `GET /agent/research?topik=` | Research Agent | Ambil dari 4 sumber → simpan ke graph → ringkas AI |
| `GET /agent/fact-checker?topik=` | Fact Checker Agent | Verifikasi ringkasan AI terhadap data asli |
| `GET /agent/news?topik=` | News Agent | Pantau berita terkini + ringkasan wacana publik |
| `GET /agent/trend?topik=` | Trend Agent | Analisis tren publikasi per tahun (dari data tersimpan) |
| `GET /agent/report?topik=` | Report Agent | Orkestrator — gabungkan 4 agent di atas jadi 1 laporan |
| `GET /agent/publisher?topik=` | Publisher Agent | Kirim ringkasan riset ke Telegram |
| *(eksternal, cron-job.org)* | Crawler Agent | Jadwalkan Research Agent & Publisher Agent berjalan otomatis harian |

---

## Environment Variables

Di-set di Railway → tab **Variables**, tidak pernah ditulis langsung di kode:

| Variable | Untuk apa |
|---|---|
| `GROQ_API_KEY` | AI ringkasan & analisis (Groq) |
| `SEMANTIC_SCHOLAR_API_KEY` | Akses lebih stabil ke Semantic Scholar (opsional, tanpa ini tetap jalan tapi rawan rate limit) |
| `NEO4J_URI` | Alamat koneksi Neo4j AuraDB |
| `NEO4J_USER` | Username Neo4j |
| `NEO4J_PASSWORD` | Password Neo4j |
| `TELEGRAM_BOT_TOKEN` | Token bot Telegram (dari @BotFather) |
| `TELEGRAM_CHAT_ID` | Chat ID tujuan pengiriman laporan |

---

## Cara Menjalankan Lokal

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Mac/Linux

pip install -r requirements.txt

# set environment variable yang dibutuhkan (lihat tabel di atas), lalu:
uvicorn main:app --reload
```

Buka `http://127.0.0.1:8000/docs` untuk melihat dokumentasi API interaktif.

---

## Keterbatasan & Catatan Metodologi

Bagian ini penting kalau temuan dari sistem ini dikutip di tulisan akademik:

- **Sampel data terbatas** — biasanya 10-30 publikasi per topik per sumber,
  bukan kajian pustaka menyeluruh.
- **Filter bidang ilmu** (OpenAlex: skor konsep >0.4 bukan bidang tak relevan;
  arXiv: exclude kategori cs/math/physics/dll) menyaring hasil, tapi belum
  sempurna — masih ada kasus lolos yang sebenarnya tidak relevan (contoh:
  paper soal COVID-19 & utilitarianisme sempat lolos di percobaan awal).
- **Ringkasan & analisis AI bisa melakukan generalisasi berlebihan** — Fact
  Checker Agent membantu menandai ini, tapi tidak menggantikan verifikasi
  manual sebelum dikutip.
- **Crossref** tidak dipakai untuk filter bidang ilmu karena metadata subjek
  antar penerbit tidak konsisten.
- Data tahun dari tiap sumber di-normalisasi ke tipe integer untuk konsistensi
  analisis tren (sempat ada bug tipe data campuran, sudah diperbaiki).

---

## Riwayat Perkembangan (ringkas)

1. Dashboard statis → terhubung ke backend FastAPI
2. Backend dummy → data nyata dari OpenAlex, lalu Crossref, Semantic Scholar, arXiv
3. Filter relevansi bidang ilmu ditambahkan setelah ditemukan data yang salah topik
4. Knowledge Graph (Neo4j) dibangun, divisualisasikan di dashboard
5. AI Agent dibangun satu per satu: Research → Fact Checker → News → Trend → Report
6. Otomatisasi: Crawler Agent (jadwal harian) dan Publisher Agent (kirim ke Telegram)

---

## Roadmap Selanjutnya (belum dikerjakan)

- Perbaiki filter relevansi agar lebih ketat (mengurangi kasus lolos yang salah topik)
- Tambah lebih banyak topik riset ke Knowledge Graph
- Eksplorasi query graph lain (selain co-authorship) untuk deteksi *research gap*
- Pertimbangkan migrasi ke n8n/LangGraph untuk orkestrasi agent yang lebih canggih
  (sesuai visi awal proyek)
