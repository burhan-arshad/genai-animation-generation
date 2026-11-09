"""Free evidence retrieval: Wikipedia + PubMed. No API keys needed."""
from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET

import httpx

import os
CONTACT = os.getenv("CONTACT", "https://github.com/burhan-arshad/genai-animation-generation")
UA = {"User-Agent": f"shorts-agent/0.1 ({CONTACT}) python-httpx"}
WIKI = "https://en.wikipedia.org/w/api.php"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
def _get_json(client, url, params):
    r = client.get(url, params=params)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:120]!r}")
    return r.json()
_http = httpx.Client(headers=UA, timeout=20, follow_redirects=True)
STOP = set("the a an of to in is it and or for on that this with as are be by at from your you can will if what when how why not no do does".split())
BLOCK = re.compile(r"suicide|self[- ]harm|euthanasia|autoerotic|choking game", re.I)

def _tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", s.lower()) if w not in STOP}


def _best_paragraphs(text: str, claim: str, n: int = 2, max_chars: int = 700) -> list[str]:
    q = _tokens(claim)
    paras = [p.strip() for p in text.split("\n") if len(p.strip()) > 80]
    scored = sorted(paras, key=lambda p: len(q & _tokens(p)), reverse=True)
    return [p[:max_chars] for p in scored[:n] if q & _tokens(p)]


def wikipedia_evidence(query: str, claim: str, titles: int = 2) -> list[dict]:
    out: list[dict] = []
    try:
        hits = _get_json(_http, WIKI, {"action": "query", "list": "search", "srsearch": query,
                                       "srlimit": titles, "format": "json"})["query"]["search"]
        for h in hits:
            t = h["title"]
            if BLOCK.search(t):
                continue
            r = _get_json(_http, WIKI, {"action": "query", "prop": "extracts", "explaintext": 1,
                                        "titles": t, "redirects": 1, "format": "json"})
            page = next(iter(r["query"]["pages"].values()))
            for p in _best_paragraphs(page.get("extract", ""), claim):
                out.append({"source": "Wikipedia", "title": t,
                            "url": "https://en.wikipedia.org/wiki/" + t.replace(" ", "_"), "text": p})
    except Exception as e:
        print(f"[retrieval] wikipedia failed for '{query}': {e}")
    return out

def pubmed_evidence(query: str, n: int = 2, max_chars: int = 900) -> list[dict]:
    out: list[dict] = []
    try:
        ids = _http.get(f"{EUTILS}/esearch.fcgi", params={"db": "pubmed", "term": query, "retmax": n,
                        "retmode": "json", "sort": "relevance"}).json()["esearchresult"]["idlist"]
        if not ids:
            return out
        time.sleep(0.4)  # NCBI allows ~3 requests/sec without a key
        xml = _http.get(f"{EUTILS}/efetch.fcgi", params={"db": "pubmed", "id": ",".join(ids),
                        "retmode": "xml"}).text
        for art in ET.fromstring(xml).iter("PubmedArticle"):
            pmid = art.findtext(".//PMID")
            title_el = art.find(".//ArticleTitle")
            title = "".join(title_el.itertext()) if title_el is not None else ""
            abstract = " ".join("".join(a.itertext()) for a in art.iter("AbstractText"))
            if abstract:
                out.append({"source": "PubMed", "title": title,
                            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", "text": abstract[:max_chars]})
        time.sleep(0.4)
    except Exception as e:
        print(f"[retrieval] pubmed failed for '{query}': {type(e).__name__}")
    return out


def collect_evidence(claim: str, queries: list[str], cap: int = 6) -> list[dict]:
    seen, out = set(), []
    for q in queries[:2]:
        for ev in wikipedia_evidence(q, claim) + pubmed_evidence(q):
            key = (ev["url"], ev["text"][:60])
            if key not in seen:
                seen.add(key)
                out.append(ev)
    return out[:cap]