from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests
import os
import xml.etree.ElementTree as ET
from neo4j import GraphDatabase

app = FastAPI(title="NEXUS Backend API")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
SEMANTIC_SCHOLAR_API_KEY = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")

NEO4J_URI = os.environ.get("NEO4J_URI")
NEO4J_USER = os.environ.get("NEO4J_USER")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD")

driver = None
if NEO4J_URI and NEO4J_USER and NEO4J_PASSWORD:
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

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
    if not driver:
        return {"nodes": 0, "edges": 0, "topics": 0, "concepts": 0}

    with driver.session() as session:
        nodes = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        edges = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
        topics = session.run("MATCH (t:Topik) RETURN count(t) AS c").single()["c"]
        # "concepts" di dashboard sementara kita isi dengan jumlah Penulis,
        # karena node jenis Concept belum kita buat.
        penulis = session.run("MATCH (a:Penulis) RETURN count(a) AS c").single()["c"]

    return {"nodes": nodes, "edges": edges, "topics": topics, "concepts": penulis}


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


# Bidang ilmu yang kemungkinan besar TIDAK relevan untuk riset tafsir/
# studi Islam — dipakai untuk menyaring hasil pencarian yang cuma
# "kebetulan" mengandung kata kunci yang sama, padahal beda dunia keilmuan.
BIDANG_TIDAK_RELEVAN = {
    "Computer science", "Artificial intelligence", "Mathematics",
    "Physics", "Engineering", "Medicine", "Biology", "Chemistry",
}


def ambil_openalex(q: str, jumlah: int = 5):
    url = "https://api.openalex.org/works"
    params = {
        "search": q,
        # Minta lebih banyak dari yang dibutuhkan, karena sebagian akan
        # disaring keluar oleh filter bidang ilmu di bawah.
        "per-page": min(jumlah * 3, 50),
    }
    response = requests.get(url, params=params, timeout=10)
    data = response.json()

    hasil = []
    for item in data.get("results", []):
        # Ambil bidang ilmu yang skor relevansinya cukup tinggi (>0.4)
        # untuk item ini, lalu cek apakah bertabrakan dengan daftar
        # bidang yang tidak relevan.
        concepts = item.get("concepts", [])
        bidang_utama = {
            c["display_name"] for c in concepts if c.get("score", 0) > 0.4
        }
        if bidang_utama & BIDANG_TIDAK_RELEVAN:
            continue  # lewati — kemungkinan besar bukan riset humaniora/agama

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
        if len(hasil) >= jumlah:
            break
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


def ambil_arxiv(q: str, jumlah: int = 5):
    # arXiv mengembalikan XML (Atom feed), bukan JSON — perlu di-parse berbeda.
    url = "http://export.arxiv.org/api/query"
    params = {
        "search_query": f"all:{q}",
        "max_results": min(jumlah * 3, 50),
    }
    response = requests.get(url, params=params, timeout=10)

    # Atom feed pakai "namespace" — semacam prefix wajib di setiap tag,
    # supaya tag <title> dari Atom tidak tertukar tag <title> format lain.
    # arXiv juga punya namespace tambahan khusus untuk info kategori.
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom",
    }
    root = ET.fromstring(response.text)

    # Awalan kode kategori arXiv yang jelas-jelas bukan humaniora/agama.
    # arXiv memang tidak punya kategori tafsir/studi Islam sama sekali,
    # jadi filter ini kemungkinan besar akan membuang hampir semua hasil —
    # itu sesuai dugaan awal bahwa arXiv bukan sumber yang cocok untuk topik ini.
    KATEGORI_TIDAK_RELEVAN = (
        "cs.", "math.", "physics.", "eess.", "stat.",
        "q-bio.", "q-fin.", "cond-mat.", "astro-ph.",
        "hep-", "nlin.", "gr-qc", "quant-ph",
    )

    hasil = []
    for entry in root.findall("atom:entry", ns):
        kategori_tag = entry.find("arxiv:primary_category", ns)
        kode_kategori = kategori_tag.get("term", "") if kategori_tag is not None else ""
        if kode_kategori.startswith(KATEGORI_TIDAK_RELEVAN):
            continue  # lewati — bidang ilmu tidak relevan

        judul_tag = entry.find("atom:title", ns)
        id_tag = entry.find("atom:id", ns)
        published_tag = entry.find("atom:published", ns)
        penulis = [
            a.find("atom:name", ns).text
            for a in entry.findall("atom:author", ns)
        ][:3]

        hasil.append({
            "judul": judul_tag.text.strip() if judul_tag is not None else None,
            "tahun": (
                published_tag.text[:4] if published_tag is not None else None
            ),
            "penulis": penulis,
            "link": id_tag.text if id_tag is not None else None,
            "sumber": "arXiv",
        })
        if len(hasil) >= jumlah:
            break
    return hasil


@app.get("/publikasi-terbaru")
def publikasi_terbaru(q: str = "Islamic environmental ethics"):
    return ambil_openalex(q)


def simpan_ke_graph(daftar_publikasi, topik):
    if not driver:
        raise Exception("Neo4j belum terhubung — cek NEO4J_URI/USER/PASSWORD")

    with driver.session() as session:
        for p in daftar_publikasi:
            if p.get("error") or not p.get("judul"):
                continue
            # MERGE artinya "buat kalau belum ada, pakai yang sudah ada kalau sudah ada"
            # ini mencegah duplikat setiap kali endpoint dipanggil ulang.
            session.run(
                """
                MERGE (pub:Publikasi {judul: $judul})
                SET pub.tahun = $tahun, pub.link = $link, pub.sumber = $sumber
                MERGE (t:Topik {nama: $topik})
                MERGE (pub)-[:MEMBAHAS]->(t)
                """,
                judul=p["judul"], tahun=p.get("tahun"),
                link=p.get("link"), sumber=p.get("sumber"), topik=topik,
            )
            for nama_penulis in p.get("penulis", []):
                session.run(
                    """
                    MATCH (pub:Publikasi {judul: $judul})
                    MERGE (a:Penulis {nama: $nama_penulis})
                    MERGE (a)-[:MENULIS]->(pub)
                    """,
                    judul=p["judul"], nama_penulis=nama_penulis,
                )


@app.get("/simpan-graph")
def simpan_graph(q: str = "Islamic environmental ethics"):
    if not driver:
        return {"error": "Neo4j belum terhubung. Set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD di environment variable."}

    try:
        publikasi = ambil_openalex(q, 15) + ambil_crossref(q, 15) + ambil_arxiv(q, 15)
        simpan_ke_graph(publikasi, q)
    except Exception as e:
        return {"error": str(e)}
    return {"status": "tersimpan", "jumlah_publikasi": len(publikasi), "topik": q}


@app.get("/simpan-graph-banyak")
def simpan_graph_banyak(topik: str):
    # topik dikirim dipisah koma, misalnya:
    # ?topik=tafsir maqashidi lingkungan,Quranic ecology,climate change Islamic theology
    if not driver:
        return {"error": "Neo4j belum terhubung."}

    daftar_topik = [t.strip() for t in topik.split(",") if t.strip()]
    hasil = []
    for t in daftar_topik:
        try:
            publikasi = ambil_openalex(t, 15) + ambil_crossref(t, 15) + ambil_arxiv(t, 15)
            simpan_ke_graph(publikasi, t)
            hasil.append({"topik": t, "status": "tersimpan", "jumlah": len(publikasi)})
        except Exception as e:
            hasil.append({"topik": t, "status": "gagal", "error": str(e)})
    return hasil
@app.get("/publikasi-gabungan")
def publikasi_gabungan(q: str = "Islamic environmental ethics"):
    # Ambil dari 3 sumber berbeda, gabungkan jadi satu daftar dengan
    # format yang sama (setiap item punya field "sumber" untuk menandai
    # asalnya). Kalau salah satu sumber gagal, jangan sampai bikin
    # seluruh endpoint ikut gagal — tangkap errornya per sumber.
    hasil = []
    for fungsi in (ambil_openalex, ambil_crossref, ambil_semantic_scholar, ambil_arxiv):
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
