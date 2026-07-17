from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests
import os

app = FastAPI(title="NEXUS Backend API")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

# CORS: mengizinkan dashboard (yang di-hosting di domain lain, misalnya
# GitHub Pages) untuk boleh memanggil API ini dari browser.
# "*" berarti izinkan semua asal dulu — nanti di produksi sebaiknya
# dipersempit hanya ke domain dashboard-mu.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"status": "NEXUS Backend aktif"}


@app.get("/sumber-data")
def sumber_data():
    return [
        {"nama": "OpenAlex", "status": "aktif"},
        {"nama": "Crossref", "status": "aktif"},
        {"nama": "Semantic Scholar", "status": "sinkron"},
        {"nama": "arXiv", "status": "menunggu"},
        {"nama": "RSS Berita", "status": "aktif"},
        {"nama": "BMKG", "status": "menunggu"},
        {"nama": "BPS", "status": "menunggu"},
    ]


@app.get("/agents")
def agents():
    return [
        {"nama": "Research Agent", "status": "belum dipasang"},
        {"nama": "News Agent", "status": "belum dipasang"},
        {"nama": "Crawler Agent", "status": "belum dipasang"},
        {"nama": "Fact Checker Agent", "status": "belum dipasang"},
        {"nama": "Trend Agent", "status": "belum dipasang"},
        {"nama": "Report Agent", "status": "belum dipasang"},
        {"nama": "Publisher Agent", "status": "belum dipasang"},
        {"nama": "Dashboard Agent", "status": "menampilkan ini"},
    ]


@app.get("/knowledge-graph")
def knowledge_graph():
    return {"nodes": 0, "edges": 0, "topics": 0, "concepts": 0}


@app.get("/insights")
def insights():
    return [
        {
            "tag": "Tafsir & Etika Lingkungan",
            "teks": "Contoh tampilan — belum ada data nyata.",
        },
        {
            "tag": "Tren Riset",
            "teks": "Contoh tampilan — belum ada data nyata.",
        },
    ]


def ambil_publikasi(q: str, jumlah: int = 5):
    # Fungsi ini dipakai bersama oleh endpoint /publikasi-terbaru
    # dan /ringkasan-riset, supaya logikanya tidak ditulis dua kali.
    url = "https://api.openalex.org/works"
    params = {
        "search": q,
        "per-page": jumlah,
    }
    response = requests.get(url, params=params, timeout=10)
    data = response.json()

    hasil = []
    for item in data.get("results", []):
        hasil.append({
            "judul": item.get("title"),
            "tahun": item.get("publication_year"),
            "penulis": [
                a["author"]["display_name"]
                for a in item.get("authorships", [])[:3]
            ],
            "link": item.get("id"),
        })
    return hasil


@app.get("/publikasi-terbaru")
def publikasi_terbaru(q: str = "Islamic environmental ethics"):
    return ambil_publikasi(q)


@app.get("/ringkasan-riset")
def ringkasan_riset(q: str = "Islamic environmental ethics"):
    if not GROQ_API_KEY:
        return {"error": "GROQ_API_KEY belum diatur di environment variable."}

    publikasi = ambil_publikasi(q, jumlah=5)

    # Susun daftar judul jadi satu teks yang akan dikirim ke AI
    daftar_judul = "\n".join(
        f"- {p['judul']} ({p['tahun']})" for p in publikasi
    )

    prompt = (
        "Berikut daftar judul publikasi ilmiah:\n\n"
        f"{daftar_judul}\n\n"
        "Buat ringkasan singkat (3-4 kalimat, dalam Bahasa Indonesia) "
        "tentang tema atau pola apa yang terlihat dari judul-judul ini, "
        "untuk membantu seorang peneliti tafsir memahami arah risetnya."
    )

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=30,
    )
    data = response.json()

    try:
        ringkasan = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        return {"error": "Gagal mendapat respons dari AI.", "detail": data}

    return {"ringkasan": ringkasan, "berdasarkan_publikasi": publikasi}
