from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests

app = FastAPI(title="NEXUS Backend API")

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


@app.get("/publikasi-terbaru")
def publikasi_terbaru(q: str = "Islamic environmental ethics"):
    # Memanggil OpenAlex API sungguhan — tidak butuh API key.
    url = "https://api.openalex.org/works"
    params = {
        "search": q,
        "per-page": 5,
        "sort": "publication_date:desc",
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
