from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests
import os
import xml.etree.ElementTree as ET
from neo4j import GraphDatabase

app = FastAPI(title="NEXUS Backend API")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
SEMANTIC_SCHOLAR_API_KEY = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

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
        {"nama": "Research Agent", "status": "aktif"},
        {"nama": "News Agent", "status": "aktif"},
        {"nama": "Crawler Agent", "status": "terjadwal"},
        {"nama": "Fact Checker Agent", "status": "aktif"},
        {"nama": "Trend Agent", "status": "aktif"},
        {"nama": "Report Agent", "status": "aktif"},
        {"nama": "Publisher Agent", "status": "aktif"},
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


@app.get("/graph-data")
def graph_data():
    if not driver:
        return {"nodes": [], "edges": []}

    with driver.session() as session:
        # Ambil node: id internal Neo4j, jenisnya (label), dan nama
        # yang enak dibaca (judul untuk Publikasi, nama untuk yang lain).
        hasil_node = session.run(
            """
            MATCH (n)
            RETURN elementId(n) AS id, labels(n)[0] AS jenis,
                   coalesce(n.judul, n.nama) AS nama
            LIMIT 300
            """
        )
        nodes = [
            {"id": r["id"], "label": (r["nama"] or "")[:40], "group": r["jenis"]}
            for r in hasil_node
        ]

        # Ambil relationship: dari node mana ke node mana, jenis apa.
        hasil_edge = session.run(
            """
            MATCH (a)-[r]->(b)
            RETURN elementId(a) AS source, elementId(b) AS target, type(r) AS tipe
            LIMIT 300
            """
        )
        edges = [
            {"from": r["source"], "to": r["target"], "label": r["tipe"]}
            for r in hasil_edge
        ]

    return {"nodes": nodes, "edges": edges}


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
                int(published_tag.text[:4]) if published_tag is not None else None
            ),
            "penulis": penulis,
            "link": id_tag.text if id_tag is not None else None,
            "sumber": "arXiv",
        })
        if len(hasil) >= jumlah:
            break
    return hasil


def ambil_berita(q: str, jumlah: int = 5):
    # Google News RSS — gratis, tidak perlu API key.
    # hl=id, gl=ID, ceid=ID:id -> minta hasil dalam Bahasa Indonesia.
    url = "https://news.google.com/rss/search"
    params = {"q": q, "hl": "id", "gl": "ID", "ceid": "ID:id"}
    response = requests.get(url, params=params, timeout=10)

    # RSS (beda dari Atom-nya arXiv) biasanya tidak butuh namespace khusus
    # untuk tag standarnya seperti <item>, <title>, <link>, <pubDate>.
    root = ET.fromstring(response.text)

    hasil = []
    for item in root.findall(".//item")[:jumlah]:
        judul = item.find("title")
        link = item.find("link")
        tanggal = item.find("pubDate")
        sumber = item.find("source")

        hasil.append({
            "judul": judul.text if judul is not None else None,
            "tanggal": tanggal.text if tanggal is not None else None,
            "link": link.text if link is not None else None,
            "media": sumber.text if sumber is not None else "Tidak diketahui",
        })
    return hasil


@app.get("/publikasi-terbaru")
def publikasi_terbaru(q: str):
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
def simpan_graph(q: str):
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
def publikasi_gabungan(q: str):
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


def buat_ringkasan_ai(daftar_publikasi, topik):
    if not GROQ_API_KEY:
        raise Exception("GROQ_API_KEY belum diatur di environment variable.")

    daftar_judul = "\n".join(
        f"- {p['judul']} ({p.get('tahun')})" for p in daftar_publikasi if p.get("judul")
    )

    prompt = (
        f"Berikut daftar judul publikasi ilmiah tentang '{topik}':\n\n"
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
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise Exception(f"Gagal mendapat respons dari AI: {data}")


@app.get("/ringkasan-riset")
def ringkasan_riset(q: str):
    publikasi = ambil_openalex(q, jumlah=5)
    try:
        ringkasan = buat_ringkasan_ai(publikasi, q)
    except Exception as e:
        return {"error": str(e)}
    return {"ringkasan": ringkasan, "berdasarkan_publikasi": publikasi}


def cek_fakta_ai(ringkasan, daftar_publikasi):
    if not GROQ_API_KEY:
        raise Exception("GROQ_API_KEY belum diatur.")

    daftar_judul = "\n".join(
        f"- {p['judul']} ({p.get('tahun')})" for p in daftar_publikasi if p.get("judul")
    )

    # Prompt ini beda peran dari buat_ringkasan_ai: di sini AI berperan
    # sebagai VERIFIKATOR yang skeptis, bukan penulis ringkasan.
    prompt = (
        "Kamu adalah fact-checker yang teliti dan skeptis.\n\n"
        f"RINGKASAN yang perlu diperiksa:\n{ringkasan}\n\n"
        f"DAFTAR PUBLIKASI ASLI yang jadi dasar ringkasan itu:\n{daftar_judul}\n\n"
        "Periksa apakah setiap klaim di ringkasan benar-benar bisa dilacak "
        "ke daftar publikasi di atas. Jawab dengan format:\n"
        "STATUS: [TERVERIFIKASI atau ADA KLAIM MERAGUKAN]\n"
        "CATATAN: [jelaskan singkat, dalam Bahasa Indonesia, klaim mana "
        "(jika ada) yang tidak didukung jelas oleh judul-judul di atas]"
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
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise Exception(f"Gagal mendapat respons dari AI: {data}")


@app.get("/agent/fact-checker")
def agent_fact_checker(topik: str):
    """
    Fact Checker Agent — memverifikasi ringkasan AI terhadap data asli
    yang jadi dasarnya. Dijalankan sebagai langkah TERPISAH dari
    Research Agent, dengan AI berperan berbeda (verifikator, bukan penulis).
    """
    publikasi = ambil_openalex(topik, jumlah=10)

    try:
        ringkasan = buat_ringkasan_ai(publikasi, topik)
    except Exception as e:
        return {"error": f"Gagal membuat ringkasan: {e}"}

    try:
        hasil_cek = cek_fakta_ai(ringkasan, publikasi)
    except Exception as e:
        return {"error": f"Gagal memverifikasi: {e}", "ringkasan": ringkasan}

    return {
        "topik": topik,
        "ringkasan_yang_diperiksa": ringkasan,
        "hasil_pemeriksaan": hasil_cek,
        "jumlah_publikasi_rujukan": len(publikasi),
    }


@app.get("/agent/research")
def agent_research(topik: str):
    """
    Research Agent — satu panggilan menjalankan 3 langkah sekaligus:
    1. Ambil publikasi dari 4 sumber
    2. Simpan ke Knowledge Graph (Neo4j)
    3. Buat ringkasan AI dari hasilnya
    Ini yang membedakan "agent" dari endpoint biasa: banyak langkah
    dijalankan sebagai satu tugas utuh, bukan dipanggil manual satu-satu.
    """
    laporan = {"topik": topik, "langkah": []}

    # Langkah 1 — ambil dari 4 sumber, catat kalau ada sumber yang gagal
    publikasi = []
    for fungsi in (ambil_openalex, ambil_crossref, ambil_semantic_scholar, ambil_arxiv):
        try:
            publikasi.extend(fungsi(topik, 10))
            laporan["langkah"].append(f"{fungsi.__name__}: berhasil")
        except Exception as e:
            laporan["langkah"].append(f"{fungsi.__name__}: gagal ({e})")

    laporan["jumlah_publikasi"] = len(publikasi)

    # Langkah 2 — simpan ke graph (kalau Neo4j terhubung)
    if driver:
        try:
            simpan_ke_graph(publikasi, topik)
            laporan["langkah"].append("simpan ke graph: berhasil")
        except Exception as e:
            laporan["langkah"].append(f"simpan ke graph: gagal ({e})")
    else:
        laporan["langkah"].append("simpan ke graph: dilewati (Neo4j belum terhubung)")

    # Langkah 3 — ringkasan AI
    try:
        laporan["ringkasan"] = buat_ringkasan_ai(publikasi, topik)
        laporan["langkah"].append("ringkasan AI: berhasil")
    except Exception as e:
        laporan["langkah"].append(f"ringkasan AI: gagal ({e})")

    return laporan


@app.get("/agent/news")
def agent_news(topik: str):
    """
    News Agent — memantau berita terkini (bukan jurnal akademik) terkait
    topik riset, lalu membuat ringkasan singkat soal wacana publik
    yang sedang berkembang.
    """
    berita = ambil_berita(topik, jumlah=8)

    if not berita:
        return {"topik": topik, "berita": [], "ringkasan": "Tidak ada berita ditemukan."}

    daftar_judul_berita = "\n".join(
        f"- {b['judul']} ({b['media']})" for b in berita if b.get("judul")
    )
    prompt = (
        f"Berikut daftar judul berita terkini tentang '{topik}':\n\n"
        f"{daftar_judul_berita}\n\n"
        "Buat ringkasan singkat (2-3 kalimat, Bahasa Indonesia) soal "
        "wacana publik apa yang sedang berkembang dari berita-berita ini."
    )

    ringkasan = None
    if GROQ_API_KEY:
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=30,
            )
            ringkasan = response.json()["choices"][0]["message"]["content"]
        except Exception as e:
            ringkasan = f"Gagal membuat ringkasan: {e}"

    return {"topik": topik, "berita": berita, "ringkasan": ringkasan}


@app.get("/agent/trend")
def agent_trend(topik: str):
    """
    Trend Agent — TIDAK mengambil data baru dari internet. Dia membaca
    ulang data yang sudah tersimpan di Knowledge Graph (hasil kerja
    Research Agent sebelumnya), lalu menganalisis pola jumlah publikasi
    per tahun untuk topik tertentu.
    """
    if not driver:
        return {"error": "Neo4j belum terhubung."}

    with driver.session() as session:
        hasil = session.run(
            """
            MATCH (p:Publikasi)-[:MEMBAHAS]->(t:Topik {nama: $topik})
            WHERE p.tahun IS NOT NULL
            RETURN p.tahun AS tahun, count(p) AS jumlah
            ORDER BY tahun
            """,
            topik=topik,
        )
        per_tahun = [{"tahun": r["tahun"], "jumlah": r["jumlah"]} for r in hasil]

    if not per_tahun:
        return {
            "topik": topik,
            "per_tahun": [],
            "catatan": "Belum ada data tersimpan untuk topik ini. Jalankan /agent/research atau /simpan-graph dulu.",
        }

    # Susun data jadi teks sederhana untuk dibaca AI
    ringkasan_data = "\n".join(f"{d['tahun']}: {d['jumlah']} publikasi" for d in per_tahun)
    prompt = (
        f"Berikut data jumlah publikasi per tahun untuk topik '{topik}':\n\n"
        f"{ringkasan_data}\n\n"
        "Analisis singkat (2-3 kalimat, Bahasa Indonesia): apakah tren "
        "riset ini meningkat, menurun, atau stabil? Sebutkan tahun dengan "
        "jumlah publikasi tertinggi kalau terlihat jelas."
    )

    analisis = None
    if GROQ_API_KEY:
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=30,
            )
            analisis = response.json()["choices"][0]["message"]["content"]
        except Exception as e:
            analisis = f"Gagal membuat analisis: {e}"

    return {"topik": topik, "per_tahun": per_tahun, "analisis": analisis}


@app.get("/agent/report")
def agent_report(topik: str):
    """
    Report Agent — TIDAK punya logika sendiri. Tugasnya memanggil ulang
    Research, Fact Checker, News, dan Trend Agent, lalu menyusun hasilnya
    jadi satu laporan lengkap. Ini contoh nyata "orchestrator" — unit yang
    mengatur unit-unit lain, bukan mengerjakan tugas dasar sendiri.
    """
    laporan = {"topik": topik, "bagian": {}}

    # --- Bagian 1: Research (ambil data + simpan graph + ringkasan) ---
    publikasi = []
    for fungsi in (ambil_openalex, ambil_crossref, ambil_semantic_scholar, ambil_arxiv):
        try:
            publikasi.extend(fungsi(topik, 10))
        except Exception:
            pass  # sumber yang gagal dilewati saja untuk laporan gabungan ini

    laporan["bagian"]["jumlah_publikasi"] = len(publikasi)

    if driver:
        try:
            simpan_ke_graph(publikasi, topik)
        except Exception as e:
            laporan["bagian"]["graph"] = f"gagal: {e}"

    ringkasan = None
    try:
        ringkasan = buat_ringkasan_ai(publikasi, topik)
        laporan["bagian"]["ringkasan"] = ringkasan
    except Exception as e:
        laporan["bagian"]["ringkasan"] = f"gagal: {e}"

    # --- Bagian 2: Fact Checker (verifikasi ringkasan di atas) ---
    if ringkasan:
        try:
            laporan["bagian"]["verifikasi"] = cek_fakta_ai(ringkasan, publikasi)
        except Exception as e:
            laporan["bagian"]["verifikasi"] = f"gagal: {e}"

    # --- Bagian 3: News (wacana publik terkini) ---
    try:
        berita = ambil_berita(topik, jumlah=5)
        laporan["bagian"]["berita_terkait"] = berita
    except Exception as e:
        laporan["bagian"]["berita_terkait"] = f"gagal: {e}"

    # --- Bagian 4: Trend (dari data graph yang baru saja diperbarui) ---
    if driver:
        try:
            with driver.session() as session:
                hasil = session.run(
                    """
                    MATCH (p:Publikasi)-[:MEMBAHAS]->(t:Topik {nama: $topik})
                    WHERE p.tahun IS NOT NULL
                    RETURN p.tahun AS tahun, count(p) AS jumlah
                    ORDER BY tahun
                    """,
                    topik=topik,
                )
                laporan["bagian"]["tren_per_tahun"] = [
                    {"tahun": r["tahun"], "jumlah": r["jumlah"]} for r in hasil
                ]
        except Exception as e:
            laporan["bagian"]["tren_per_tahun"] = f"gagal: {e}"

    return laporan


def kirim_telegram(pesan: str):
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        raise Exception("TELEGRAM_BOT_TOKEN atau TELEGRAM_CHAT_ID belum diatur.")

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    response = requests.post(
        url,
        json={"chat_id": TELEGRAM_CHAT_ID, "text": pesan[:4000]},  # Telegram batasi ~4096 karakter
        timeout=15,
    )
    data = response.json()
    if not data.get("ok"):
        raise Exception(f"Telegram menolak pesan: {data}")
    return data


@app.get("/agent/publisher")
def agent_publisher(topik: str):
    """
    Publisher Agent — mengambil ringkasan riset (lewat buat_ringkasan_ai,
    yang sudah dipakai Research Agent), lalu MENGIRIMKANNYA keluar sistem
    lewat Telegram. Ini agent pertama yang hasilnya sampai ke luar dashboard.
    """
    publikasi = ambil_openalex(topik, jumlah=8)

    try:
        ringkasan = buat_ringkasan_ai(publikasi, topik)
    except Exception as e:
        return {"error": f"Gagal membuat ringkasan: {e}"}

    pesan = (
        f"NEXUS — Laporan Riset Harian\n"
        f"Topik: {topik}\n\n"
        f"{ringkasan}\n\n"
        f"Berdasarkan {len(publikasi)} publikasi."
    )

    try:
        kirim_telegram(pesan)
    except Exception as e:
        return {"error": f"Ringkasan berhasil dibuat, tapi gagal kirim ke Telegram: {e}", "ringkasan": ringkasan}

    return {"status": "terkirim ke Telegram", "topik": topik, "ringkasan": ringkasan}
