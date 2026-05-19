"""Search service — all source functions, AI router singleton, and aggregation logic."""
import re
import time
import json
import urllib.parse
import urllib.request
import requests

from config.settings import AIConfig
from core.ai_router import AISearchRouter

_ai_router: AISearchRouter | None = None

FR_SOURCES = {"hal", "persee", "openedition", "erudit"}
EN_SOURCES = {"arxiv", "gutenberg", "archive"}

_FR_STOPWORDS = {
    "le","la","les","de","du","des","un","une","et","en","au","aux","sur",
    "avec","pour","par","que","qui","dans","est","sont","il","elle","nous",
    "vous","ils","elles","ce","se","ne","pas","plus","où","à","ou","ni",
    "si","car","mais","donc","or","méthode","méthodes","analyse","résultats",
    "étude","approche","modèle","modèles","théorie","application","éléments",
    "finis","calcul","numérique","équation","équations","solution","problème",
}


def _first(v):
    if isinstance(v, list):
        v = v[0] if v else ""
    return v if isinstance(v, str) else str(v) if v is not None else ""


def detect_lang(text: str) -> str:
    words = set(text.lower().split())
    return "fr" if len(words & _FR_STOPWORDS) >= 2 else "en"


def get_ai_router() -> AISearchRouter:
    global _ai_router
    if _ai_router is None:
        _ai_router = AISearchRouter()
    return _ai_router


# ── Individual source functions ───────────────────────────────────────────────

def _search_arxiv(query, limit=10):
    q = urllib.parse.quote(query)
    url = f"https://export.arxiv.org/api/query?search_query=all:{q}&max_results={limit}"
    headers = {"User-Agent": "Scholara/1.0 (open-access research platform; mailto:scholara@open.edu)"}
    try:
        for _ in range(2):
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code == 429:
                time.sleep(3)
                continue
            r.raise_for_status()
            xml = r.text
            break
        else:
            return [{"source": "arXiv", "icon": "📄",
                     "title": "arXiv rate-limited — wait a moment and retry",
                     "url": "", "pdf_url": "", "snippet": "", "authors": ""}]
        entries = re.findall(r'<entry>(.*?)</entry>', xml, re.DOTALL)
        results = []
        for e in entries:
            title   = re.search(r'<title>(.*?)</title>', e, re.DOTALL)
            link    = re.search(r'<id>(.*?)</id>', e)
            summ    = re.search(r'<summary>(.*?)</summary>', e, re.DOTALL)
            auth    = re.findall(r'<name>(.*?)</name>', e)
            pub     = re.search(r'<published>(.*?)</published>', e)
            abs_id  = link.group(1).strip().split("/abs/")[-1] if link else ""
            year    = int(pub.group(1)[:4]) if pub else None
            abs_url = link.group(1).strip() if link else ""
            pdf_url = f"https://arxiv.org/pdf/{abs_id}.pdf" if abs_id else ""
            results.append({
                "source": "arXiv", "icon": "📄",
                "title":  title.group(1).strip() if title else "—",
                "authors": ", ".join(auth[:3]),
                "url":    abs_url,
                "pdf_url": pdf_url,
                "snippet": summ.group(1).strip()[:200] if summ else "",
                "open_access": True,
                "year": year, "language": "en",
            })
        return results
    except Exception as ex:
        return [{"source": "arXiv", "icon": "📄", "title": f"Error: {ex}",
                 "url": "", "pdf_url": "", "snippet": "", "authors": ""}]


def _search_gutenberg(query, limit=5):
    q   = urllib.parse.quote(query)
    url = f"https://gutendex.com/books/?search={q}&languages=en,fr"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
        results = []
        for b in data.get("results", [])[:limit]:
            fmts  = b.get("formats", {})
            pdf   = fmts.get("application/pdf", "")
            txt   = fmts.get("text/plain; charset=utf-8", fmts.get("text/plain", ""))
            langs = b.get("languages", [])
            results.append({
                "source":  "Gutenberg", "icon": "📚",
                "title":   b.get("title", "—"),
                "authors": ", ".join(a["name"] for a in b.get("authors", [])),
                "url":     f"https://www.gutenberg.org/ebooks/{b['id']}",
                "pdf_url": pdf or txt,
                "snippet": f"Language: {', '.join(langs)} | Subjects: {', '.join(b.get('subjects',[])[:3])}",
                "open_access": True,
                "language": langs[0] if langs else None,
            })
        return results
    except Exception as ex:
        return [{"source": "Gutenberg", "icon": "📚", "title": f"Error: {ex}",
                 "url": "", "pdf_url": "", "snippet": "", "authors": ""}]


def _search_doaj(query, limit=5, lang=""):
    q           = urllib.parse.quote(query)
    lang_filter = f"+AND+bibjson.journal.language%3A{lang.upper()}" if lang else ""
    url         = f"https://doaj.org/api/search/articles/{q}{lang_filter}?pageSize={limit}"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
        results = []
        for art in data.get("results", [])[:limit]:
            bib  = art.get("bibjson", {})
            link = next((l["url"] for l in bib.get("link", []) if l.get("type") == "fulltext"), "")
            year = bib.get("year")
            results.append({
                "source":  "DOAJ", "icon": "🔓",
                "title":   bib.get("title", "—"),
                "authors": ", ".join(a.get("name", "") for a in bib.get("author", [])[:3]),
                "url":     link,
                "pdf_url": link,
                "snippet": bib.get("abstract", "")[:200],
                "open_access": True,
                "year": int(year) if year else None,
                "journal": bib.get("journal", {}).get("title", ""),
            })
        return results
    except Exception as ex:
        return [{"source": "DOAJ", "icon": "🔓", "title": f"Error: {ex}",
                 "url": "", "pdf_url": "", "snippet": "", "authors": ""}]


def _search_openalex(query, limit=10, lang=""):
    q           = urllib.parse.quote(query)
    lang_filter = f",language:{lang}" if lang else ""
    url         = (f"https://api.openalex.org/works?search={q}"
                   f"&filter=is_oa:true{lang_filter}&per-page={limit}&mailto=scholara@open.edu")
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
        results = []
        for w in data.get("results", []):
            pdf         = w.get("open_access", {}).get("oa_url", "") or ""
            doi         = w.get("doi", "") or ""
            openalex_id = w.get("id", "") or ""
            open_url    = pdf or doi or openalex_id
            host_venue  = (w.get("primary_location") or {}).get("source") or {}
            journal     = host_venue.get("display_name", "") or ""
            results.append({
                "source":  "OpenAlex", "icon": "🔬",
                "title":   w.get("title") or "—",
                "authors": ", ".join(
                    a["author"]["display_name"]
                    for a in w.get("authorships", [])[:3]
                    if a.get("author")
                ),
                "url":     open_url,
                "pdf_url": pdf,
                "snippet": (w.get("abstract") or f"Cited by {w.get('cited_by_count', 0)}"),
                "open_access": True,
                "year": w.get("publication_year"),
                "journal": journal,
            })
        return results
    except Exception as ex:
        return [{"source": "OpenAlex", "icon": "🔬", "title": f"Error: {ex}",
                 "url": "", "pdf_url": "", "snippet": "", "authors": ""}]


def _search_archive(query, limit=5):
    q   = urllib.parse.quote(query)
    url = (f"https://archive.org/advancedsearch.php"
           f"?q={q}+AND+mediatype:texts"
           f"&fl[]=identifier,title,creator,description,mediatype"
           f"&rows={limit}&output=json")
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
        results = []
        for doc in data.get("response", {}).get("docs", []):
            idf = doc.get("identifier", "")
            results.append({
                "source":  "Archive.org", "icon": "📚",
                "title":   doc.get("title", "—"),
                "authors": doc.get("creator", ""),
                "url":     f"https://archive.org/details/{idf}",
                "pdf_url": f"https://archive.org/download/{idf}/{idf}.pdf",
                "snippet": (doc.get("description", "") or "")[:200],
                "open_access": True,
            })
        return results
    except Exception as ex:
        return [{"source": "Archive.org", "icon": "📚", "title": f"Error: {ex}",
                 "url": "", "pdf_url": "", "snippet": "", "authors": ""}]


def _search_hal(query, limit=5):
    q   = urllib.parse.quote(query)
    fl  = "title_s,abstract_s,author_s,halId_s,uri_s,publicationDate_tdate,journalTitle_s"
    url = f"https://api.archives-ouvertes.fr/search/?q={q}&fl={fl}&rows={limit}&wt=json"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
        results = []
        for doc in data.get("response", {}).get("docs", []):
            hal_id  = (doc.get("halId_s") or [""])[0] if isinstance(doc.get("halId_s"), list) else doc.get("halId_s", "")
            uri_val = doc.get("uri_s", "")
            uri     = uri_val[0] if isinstance(uri_val, list) else uri_val
            pdf_url = uri if uri.endswith(".pdf") else (f"https://hal.science/{hal_id}/document" if hal_id else "")
            title_v = doc.get("title_s", ["—"])
            title   = title_v[0] if isinstance(title_v, list) else title_v
            abst_v  = doc.get("abstract_s", [""])
            snippet = (abst_v[0] if isinstance(abst_v, list) else abst_v)[:300]
            authors = doc.get("author_s", [])
            pub     = doc.get("publicationDate_tdate", "")
            year    = int(pub[:4]) if pub and len(pub) >= 4 else None
            journal_v = doc.get("journalTitle_s", "")
            journal   = journal_v[0] if isinstance(journal_v, list) else journal_v
            results.append({
                "source":  "HAL", "icon": "🏛️",
                "title":   title,
                "authors": ", ".join(authors[:3]) if isinstance(authors, list) else authors,
                "url":     uri or f"https://hal.science/{hal_id}",
                "pdf_url": pdf_url,
                "snippet": snippet,
                "open_access": True,
                "year": year, "journal": journal, "language": "fr",
            })
        return results
    except Exception as ex:
        return [{"source": "HAL", "icon": "🏛️", "title": f"Error: {ex}",
                 "url": "", "pdf_url": "", "snippet": "", "authors": ""}]


def _search_persee(query, limit=5):
    q   = urllib.parse.quote(query)
    url = f"https://www.persee.fr/search/list?q={q}&rows={limit}&format=json"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
        results = []
        for item in (data.get("items") or data.get("results") or [])[:limit]:
            results.append({
                "source":  "Persée", "icon": "📰",
                "title":   item.get("title", "—"),
                "authors": item.get("author", ""),
                "url":     item.get("link", ""),
                "pdf_url": item.get("pdfLink", ""),
                "snippet": (item.get("abstract", "") or "")[:300],
                "open_access": True,
                "language": "fr",
            })
        if not results:
            raise ValueError("empty")
        return results
    except Exception:
        try:
            from bs4 import BeautifulSoup
            q2   = urllib.parse.quote(query)
            url2 = f"https://www.persee.fr/search?q={q2}"
            req2 = urllib.request.Request(url2, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req2, timeout=10) as r:
                html = r.read().decode("utf-8", errors="replace")
            soup    = BeautifulSoup(html, "html.parser")
            results = []
            for card in soup.select(".result-item, .search-result, article")[:limit]:
                t_el    = card.find(["h2", "h3", "a"])
                link_el = card.find("a", href=True)
                snip_el = card.find("p")
                title   = t_el.get_text(strip=True) if t_el else "—"
                link    = link_el["href"] if link_el else ""
                if link and not link.startswith("http"):
                    link = "https://www.persee.fr" + link
                results.append({
                    "source": "Persée", "icon": "📰",
                    "title": title, "authors": "", "url": link, "pdf_url": "",
                    "snippet": snip_el.get_text(strip=True)[:300] if snip_el else "",
                    "open_access": True, "language": "fr",
                })
            return results or [{"source": "Persée", "icon": "📰", "title": "No results",
                                "url": "", "pdf_url": "", "snippet": "", "authors": ""}]
        except Exception as ex2:
            return [{"source": "Persée", "icon": "📰", "title": f"Error: {ex2}",
                     "url": "", "pdf_url": "", "snippet": "", "authors": ""}]


def _search_openedition(query, limit=10):
    q   = urllib.parse.quote(query)
    url = f"https://api.openedition.org/1.0/?q={q}&format=json&rows={limit}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Scholara/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        docs = (data.get("response", {}).get("docs")
                or data.get("docs") or data.get("items") or data.get("results") or [])
        results = []
        for doc in docs[:limit]:
            doc_url = (doc.get("identifier") or doc.get("url") or
                       doc.get("dc_identifier") or "")
            if isinstance(doc_url, list):
                doc_url = doc_url[0] if doc_url else ""
            title  = doc.get("title") or doc.get("dc_title") or "—"
            if isinstance(title, list):
                title = title[0] if title else "—"
            author = doc.get("creator") or doc.get("author") or doc.get("dc_creator") or ""
            if isinstance(author, list):
                author = ", ".join(author[:3])
            results.append({
                "source":  "OpenEdition", "icon": "📖",
                "title":   title,
                "authors": author,
                "url":     doc_url,
                "pdf_url": _first(doc.get("pdf_url") or doc.get("fulltext") or ""),
                "snippet": _first((doc.get("description") or doc.get("dc_description") or ""))[:300],
                "open_access": True,
                "journal": _first(doc.get("source") or doc.get("dc_source") or ""),
                "language": "fr",
            })
        return results or []
    except Exception as ex:
        return [{"source": "OpenEdition", "icon": "📖", "title": f"Error: {ex}",
                 "url": "", "pdf_url": "", "snippet": "", "authors": ""}]


def _search_erudit(query, limit=10):
    q = urllib.parse.quote(query)
    try:
        url = f"https://www.erudit.org/api/v1/search/?q={q}&nb_result_par_page={limit}"
        r   = requests.get(url, headers={"User-Agent": "Scholara/1.0"}, timeout=10)
        r.raise_for_status()
        data  = r.json()
        items = data if isinstance(data, list) else data.get("results", data.get("items", []))
        results = []
        for item in items[:limit]:
            author = item.get("author", item.get("authors", ""))
            if isinstance(author, list):
                author = ", ".join(
                    (a if isinstance(a, str) else a.get("name", "")) for a in author[:3]
                )
            results.append({
                "source":  "Érudit", "icon": "📚",
                "title":   item.get("title", "—"),
                "authors": author,
                "url":     item.get("url", item.get("link", "")),
                "pdf_url": item.get("pdf_url", ""),
                "snippet": (item.get("abstract", item.get("resume", "")) or "")[:300],
                "open_access": True,
                "language": "fr",
            })
        if results:
            return results
    except Exception:
        pass
    try:
        from bs4 import BeautifulSoup
        url2 = f"https://www.erudit.org/en/search/?q={q}"
        req2 = urllib.request.Request(url2, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req2, timeout=12) as r:
            html = r.read().decode("utf-8", errors="replace")
        soup    = BeautifulSoup(html, "html.parser")
        results = []
        for card in soup.select("article.media, .result-document, .search-result, li.result")[:limit]:
            t_el    = card.find(["h3", "h2", "h4"])
            link_el = card.find("a", href=True)
            snip_el = card.find("p")
            title   = t_el.get_text(strip=True) if t_el else "—"
            link    = link_el["href"] if link_el else ""
            if link and not link.startswith("http"):
                link = "https://www.erudit.org" + link
            results.append({
                "source": "Érudit", "icon": "📚",
                "title": title, "authors": "", "url": link, "pdf_url": "",
                "snippet": snip_el.get_text(strip=True)[:300] if snip_el else "",
                "open_access": True, "language": "fr",
            })
        return results or []
    except Exception as ex:
        return [{"source": "Érudit", "icon": "📚", "title": f"Error: {ex}",
                 "url": "", "pdf_url": "", "snippet": "", "authors": ""}]


# ── Global North sources ──────────────────────────────────────────────────────

def _search_semantic_scholar(query, limit=5):
    url    = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {"query": query, "limit": limit,
               "fields": "title,authors,abstract,year,journal,openAccessPdf"}
    try:
        r = requests.get(url, params=params, timeout=10, headers={"User-Agent": "Scholara/1.0"})
        r.raise_for_status()
        results = []
        for item in r.json().get("data", [])[:limit]:
            pdf = item.get("openAccessPdf") or {}
            results.append({
                "source":  "semantic_scholar", "icon": "🔬",
                "title":   item.get("title", "—"),
                "authors": [a.get("name", "") for a in item.get("authors", [])],
                "snippet": (item.get("abstract") or "")[:300],
                "url":    f"https://www.semanticscholar.org/paper/{item.get('paperId', '')}",
                "pdf_url": pdf.get("url", ""),
                "year":    str(item.get("year") or ""),
                "journal": (item.get("journal") or {}).get("name", ""),
            })
        return results
    except Exception as ex:
        return [{"source": "semantic_scholar", "icon": "🔬", "title": f"Error: {ex}",
                 "authors": [], "snippet": "", "url": "", "pdf_url": ""}]


def _search_pubmed(query, limit=5):
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    try:
        r = requests.get(f"{base}/esearch.fcgi",
                         params={"db": "pubmed", "term": query, "retmax": limit, "retmode": "json"},
                         timeout=10)
        r.raise_for_status()
        ids = r.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return []
        r2 = requests.get(f"{base}/esummary.fcgi",
                          params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"},
                          timeout=10)
        r2.raise_for_status()
        result_map = r2.json().get("result", {})
        results    = []
        for uid in ids:
            doc     = result_map.get(uid, {})
            authors = [a.get("name", "") for a in doc.get("authors", [])]
            results.append({
                "source":  "pubmed", "icon": "🧬",
                "title":   doc.get("title", "—"),
                "authors": authors,
                "snippet": "",
                "url":    f"https://pubmed.ncbi.nlm.nih.gov/{uid}/",
                "pdf_url": "",
                "year":    str(doc.get("pubdate", ""))[:4],
                "journal": doc.get("fulljournalname", ""),
            })
        return results
    except Exception as ex:
        return [{"source": "pubmed", "icon": "🧬", "title": f"Error: {ex}",
                 "authors": [], "snippet": "", "url": "", "pdf_url": ""}]


def _search_crossref(query, limit=5):
    url    = "https://api.crossref.org/works"
    params = {"query": query, "rows": limit,
               "select": "title,author,abstract,DOI,published,container-title"}
    try:
        r = requests.get(url, params=params, timeout=10,
                         headers={"User-Agent": "Scholara/1.0 (mailto:scholara@example.com)"})
        r.raise_for_status()
        results = []
        for item in r.json().get("message", {}).get("items", [])[:limit]:
            title       = (item.get("title") or ["—"])[0]
            authors     = [f"{a.get('given', '')} {a.get('family', '')}".strip()
                           for a in item.get("author", [])]
            doi         = item.get("DOI", "")
            date_parts  = (item.get("published") or {}).get("date-parts", [[]])[0]
            year        = str(date_parts[0]) if date_parts else ""
            journal     = (item.get("container-title") or [""])[0]
            results.append({
                "source":  "crossref", "icon": "📑",
                "title":   title,
                "authors": authors,
                "snippet": (item.get("abstract") or "")[:300],
                "url":    f"https://doi.org/{doi}" if doi else "",
                "pdf_url": f"https://doi.org/{doi}" if doi else "",
                "year":    year,
                "journal": journal,
            })
        return results
    except Exception as ex:
        return [{"source": "crossref", "icon": "📑", "title": f"Error: {ex}",
                 "authors": [], "snippet": "", "url": "", "pdf_url": ""}]


def _search_core(query, limit=5):
    api_key = AIConfig.CORE_API_KEY
    if not api_key:
        return []
    url = "https://api.core.ac.uk/v3/search/works"
    try:
        r = requests.get(url, params={"q": query, "limit": limit},
                         headers={"Authorization": f"Bearer {api_key}"}, timeout=10)
        r.raise_for_status()
        results = []
        for item in r.json().get("results", [])[:limit]:
            authors      = item.get("authors") or []
            author_names = [a.get("name", "") if isinstance(a, dict) else str(a) for a in authors]
            results.append({
                "source":  "core", "icon": "🗄️",
                "title":   item.get("title", "—"),
                "authors": author_names,
                "snippet": (item.get("abstract") or "")[:300],
                "url":    item.get("downloadUrl") or item.get("sourceFulltextUrls", [""])[0],
                "pdf_url": item.get("downloadUrl", ""),
                "year":    str(item.get("yearPublished") or ""),
                "journal": item.get("publisher", ""),
            })
        return results
    except Exception as ex:
        return [{"source": "core", "icon": "🗄️", "title": f"Error: {ex}",
                 "authors": [], "snippet": "", "url": "", "pdf_url": ""}]


def _search_base(query, limit=5):
    url    = "https://api.base-search.net/cgi-bin/BaseHttpSearchInterface.fcgi"
    params = {"func": "PerformSearch", "query": query, "hits": limit, "format": "json"}
    try:
        r = requests.get(url, params=params, timeout=10, headers={"User-Agent": "Scholara/1.0"})
        r.raise_for_status()
        docs    = r.json().get("response", {}).get("docs", [])
        results = []
        for doc in docs[:limit]:
            titles      = doc.get("dctitle") or ["—"]
            creators    = doc.get("dccreator") or []
            descriptions = doc.get("dcdescription") or [""]
            identifiers = doc.get("dcidentifier") or [""]
            dates       = doc.get("dcdate") or [""]
            results.append({
                "source":  "base", "icon": "🌐",
                "title":   titles[0] if titles else "—",
                "authors": creators if isinstance(creators, list) else [creators],
                "snippet": descriptions[0][:300] if descriptions else "",
                "url":    identifiers[0] if identifiers else "",
                "pdf_url": "",
                "year":    str(dates[0])[:4] if dates else "",
                "journal": "",
            })
        return results
    except Exception as ex:
        return [{"source": "base", "icon": "🌐", "title": f"Error: {ex}",
                 "authors": [], "snippet": "", "url": "", "pdf_url": ""}]


# ── Dispatcher ────────────────────────────────────────────────────────────────

def _build_source_map() -> dict:
    src_map = {
        "arxiv":            _search_arxiv,
        "gutenberg":        _search_gutenberg,
        "doaj":             _search_doaj,
        "openalex":         _search_openalex,
        "archive":          _search_archive,
        "internet_archive": _search_archive,
        "hal":              _search_hal,
        "persee":           _search_persee,
        "openedition":      _search_openedition,
        "erudit":           _search_erudit,
    }
    if AIConfig.is_north():
        src_map.update({
            "semantic_scholar": _search_semantic_scholar,
            "pubmed":           _search_pubmed,
            "crossref":         _search_crossref,
            "core":             _search_core,
            "base":             _search_base,
        })
    return src_map


def search_source(source: str, query: str, limit: int = 10, lang: str = "") -> list:
    import logging
    src_map = _build_source_map()
    fn = src_map.get(source)
    if fn is None and source in {"semantic_scholar", "pubmed", "crossref", "core", "base"}:
        logging.warning("GN source '%s' requested but MARKET_SEGMENT is not global-north", source)
        return []
    if fn is None:
        return []
    if source in ("openalex", "doaj"):
        return fn(query, limit, lang=lang)
    return fn(query, limit)


def aggregate_search(query: str, sources: list, limit: int, lang: str) -> dict:
    """Multi-source search with language-aware ordering and allocation."""
    src_map  = _build_source_map()
    priority = [s for s in sources if s in (FR_SOURCES if lang == "fr" else EN_SOURCES)]
    rest     = [s for s in sources if s not in (FR_SOURCES if lang == "fr" else EN_SOURCES)]
    ordered  = priority + rest

    n_priority   = max(len(priority), 1)
    n_rest       = max(len(rest), 1)
    per_priority = max(limit // n_priority, 10)
    per_rest     = max(limit // (n_priority + n_rest) + 2, 6)

    results = []
    for src in ordered:
        fn  = src_map.get(src)
        if not fn:
            continue
        per = per_priority if src in priority else per_rest
        if src in ("openalex", "doaj"):
            results.extend(fn(query, per, lang=lang))
        else:
            results.extend(fn(query, per))

    def _lang_rank(r):
        rl = (r.get("language") or "").lower()
        if rl == lang:
            return 0
        if rl == "":
            return 1
        return 2

    results.sort(key=_lang_rank)
    return {"results": results[:max(limit, 100)], "detected_lang": lang}
