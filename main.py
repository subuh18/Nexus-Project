from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests
import os

app = FastAPI(title="NEXUS Backend API")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
SEMANTIC_SCHOLAR_API_KEY = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")

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


def ambil_openalex(q: str, jumlah: int = 5):
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
            "sumber": "OpenAlex",
        })
    return hasil


def ambil_crossref(q: str, jumlah: int = 5):
    url = "https://api.crossref.org/works"
    params = {
        "query": q,
        "rows": jumlah,
    }
    response = requests.get(url, params=params, timeout=10)
    data = response.json()

    hasil = []
    for item in data.get("message", {}).get("items", []):
        judul_list = item.get("title", [])
        hasil.append({
            "judul": judul_list[0] if judul_list else None,
            "tahun": (
                item.get("issued", {})
                .get("date-parts", [[None]])[0][0]
            ),
            "penulis": [
                f"{a.get('given', '')} {a.get('family', '')}".strip()
                for a in item.get("author", [])[:3]
            ],
            "link": item.get("URL"),
            "sumber": "Crossref",
        })
    return hasil


def ambil_semantic_scholar(q: str, jumlah: int = 5):
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": q,
        "limit": jumlah,
        "fields": "title,year,authors,url",
    }
    headers = {}
    if SEMANTIC_SCHOLAR_API_KEY:
        headers["x-api-key"] = SEMANTIC_SCHOLAR_API_KEY

    response = requests.get(url, params=params, headers=headers, timeout=10)

    # Kalau statusnya bukan 200, jangan diam-diam kembalikan list kosong —
    # lempar error yang jelas supaya kelihatan di /publikasi-gabungan.
    if response.status_code != 200:
        raise Exception(
            f"status {response.status_code} — {response.text[:150]}"
        )

    data = response.json()
    hasil = []
    for item in data.get("data", []):
        hasil.append({
            "judul": item.get("title"),
            "tahun": item.get("year"),
            "penulis": [a.get("name") for a in item.get("authors", [])[:3]],
            "link": item.get("url"),
            "sumber": "Semantic Scholar",
        })
    return hasil


@app.get("/publikasi-terbaru")
def publikasi_terbaru(q: str = "Islamic environmental ethics"):
    return ambil_openalex(q)


@app.get("/publikasi-gabungan")
def publikasi_gabungan(q: str = "Islamic environmental ethics"):
    # Ambil dari 3 sumber berbeda, gabungkan jadi satu daftar dengan
    # format yang sama (setiap item punya field "sumber" untuk menandai
    # asalnya). Kalau salah satu sumber gagal, jangan sampai bikin
    # seluruh endpoint ikut gagal — tangkap errornya per sumber.
    hasil = []
    for fungsi in (ambil_openalex, ambil_crossref, ambil_semantic_scholar):
        try:
            hasil.extend(fungsi(q, 3))
        except Exception as e:
            hasil.append({"error": f"{fungsi.__name__} gagal: {e}"})
    return hasil


@app.get("/ringkasan-riset")
def ringkasan_riset(q: str = "Islamic environmental ethics"):
    if not GROQ_API_KEY:
        return {"error": "GROQ_API_KEY belum diatur di environment variable."}

    publikasi = ambil_openalex(q, jumlah=5)

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
