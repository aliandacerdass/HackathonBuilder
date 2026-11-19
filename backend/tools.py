"""Deterministik araştırma araçları: LLM yok, uydurma sonuç yok. Hepsi ücretsiz ve key'siz.

    papers = await search_papers("medication reconciliation AI", since_year=2024)
    repos  = await search_repos("drug interaction checker")
    readme = await repo_readme("owner/name")
    title  = await youtube_title("https://www.youtube.com/watch?v=...")   # gerçek başlık | None
    status = await check_url("https://...")   # "verified" | "unverified" | "dead"
"""
import asyncio
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

UA = "HackathonBuilder/0.1 (+https://github.com/aliandacerdass/HackathonBuilder)"
TIMEOUT = 20


class ToolError(Exception):
    pass


def _get(url: str, headers: dict | None = None) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ToolError(f"{url}: bağlantı hatası: {e}")


async def _get_json(url: str, headers: dict | None = None) -> dict:
    code, body = await asyncio.to_thread(_get, url, headers)
    if code != 200:
        raise ToolError(f"{url}: HTTP {code}")
    return json.loads(body)


# ---------- makaleler: OpenAlex ----------

def _abstract(inverted: dict | None, limit: int = 600) -> str:
    """OpenAlex özeti {kelime: [pozisyonlar]} olarak verir → düz metne çevir."""
    if not inverted:
        return ""
    words = sorted((p, w) for w, ps in inverted.items() for p in ps)
    return " ".join(w for _, w in words)[:limit]


async def search_papers(query: str, since_year: int = 2023, n: int = 5) -> list[dict]:
    params = urllib.parse.urlencode({
        "search": query,
        "filter": f"from_publication_date:{since_year}-01-01",
        "per_page": n,
        "select": "title,doi,publication_year,cited_by_count,abstract_inverted_index",
    })
    data = await _get_json(f"https://api.openalex.org/works?{params}")
    return [{
        "title": w["title"],
        "url": w["doi"],
        "year": w["publication_year"],
        "citations": w["cited_by_count"],
        "abstract": _abstract(w.get("abstract_inverted_index")),
    } for w in data["results"] if w.get("title") and w.get("doi")]


# ---------- repolar: GitHub (key'siz: dakikada 10 arama, saatte 60 diğer istek) ----------

async def search_repos(query: str, n: int = 5, by_stars: bool = True) -> list[dict]:
    """by_stars=False: GitHub'ın en iyi eşleşme sırası."""
    params = urllib.parse.urlencode({"q": query, "per_page": n, **({"sort": "stars"} if by_stars else {})})
    code, body = await asyncio.to_thread(_get, f"https://api.github.com/search/repositories?{params}")
    if code == 403:
        raise ToolError("GitHub arama limiti doldu (key'siz dakikada 10 arama), bir dakika sonra tekrar dene")
    if code != 200:
        raise ToolError(f"GitHub arama: HTTP {code}")
    return [{
        "name": r["full_name"],
        "url": r["html_url"],
        "description": r["description"] or "",
        "stars": r["stargazers_count"],
        "language": r["language"],
        "last_push": r["pushed_at"][:10],
        "license": (r.get("license") or {}).get("spdx_id"),
    } for r in json.loads(body)["items"]]


async def repo_readme(full_name: str, limit: int = 3000) -> str:
    code, body = await asyncio.to_thread(
        _get, f"https://api.github.com/repos/{full_name}/readme",
        {"Accept": "application/vnd.github.raw+json"})
    return body.decode(errors="replace")[:limit] if code == 200 else ""


# ---------- link doğrulama ----------

async def youtube_title(url: str) -> str | None:
    """YouTube videosunun gerçek başlığı (oEmbed). Video yoksa None."""
    q = urllib.parse.quote(url, safe="")
    code, body = await asyncio.to_thread(_get, f"https://www.youtube.com/oembed?url={q}&format=json")
    return json.loads(body).get("title", "") if code == 200 else None


DOI_RE = re.compile(r"10\.\d{4,9}/[^\s?#]+")
PMC_RE = re.compile(r"ncbi\.nlm\.nih\.gov/(?:pmc/)?articles/PMC(\d+)")
YT_RE = re.compile(r"(youtube\.com/watch|youtu\.be/)")


async def check_url(url: str) -> str:
    """verified = var olduğu kanıtlandı · dead = yok (404 vb.) · unverified = site engelledi (403 vb.)"""
    try:
        if YT_RE.search(url):
            return "verified" if await youtube_title(url) is not None else "dead"

        if m := PMC_RE.search(url):
            data = await _get_json(
                f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pmc&id={m[1]}&retmode=json")
            rec = data["result"].get(m[1], {})
            return "dead" if "error" in rec or not rec.get("title") else "verified"

        if m := DOI_RE.search(url):
            code, _ = await asyncio.to_thread(_get, f"https://api.crossref.org/works/{m[0]}")
            if code == 200:
                return "verified"
            # DOI yanlış kesilmiş olabilir (ör. ".../full"), sayfanın kendisine bak

        code, _ = await asyncio.to_thread(_get, url)
        if 200 <= code < 300:
            return "verified"
        if code in (404, 410):
            return "dead"
        return "unverified"  # 403/429/5xx: site botları engelliyor, yok demek değil
    except ToolError:
        return "unverified"


# ---------- self-test (gerçek ağ çağrıları) ----------

async def _selftest() -> int:
    checks = []

    def ok(name, cond, detail=""):
        checks.append(cond)
        print(f"{'✓' if cond else '✗'} {name}  {detail}")

    papers = await search_papers("AI medication reconciliation", since_year=2024, n=3)
    ok("OpenAlex makale", len(papers) >= 1 and papers[0]["url"].startswith("https://doi.org/"),
       f"{len(papers)} sonuç, ilk: {papers[0]['title'][:50] if papers else '-'}")

    repos = await search_repos("drug interaction checker", n=3)
    ok("GitHub repo", len(repos) >= 1, f"{len(repos)} sonuç, ilk: {repos[0]['name'] if repos else '-'}")
    readme = await repo_readme(repos[0]["name"]) if repos else ""
    ok("GitHub README", len(readme) > 50, f"{len(readme)} karakter")

    cases = [
        ("https://www.nature.com/articles/s41598-024-83631-w", "verified"),               # DOI → Crossref
        ("https://pmc.ncbi.nlm.nih.gov/articles/PMC11953325/", "verified"),               # PMC → eutils
        ("https://pmc.ncbi.nlm.nih.gov/articles/PMC99999999999/", "dead"),                # sahte PMC
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "verified"),                      # oEmbed
        ("https://www.youtube.com/watch?v=aaaaaaaaaaa", "dead"),                          # sahte video
        ("https://github.com/aliandacerdass/bu-repo-yok-xyz-123", "dead"),                # 404
        ("https://www.sciencedirect.com/science/article/pii/S1551741124001177", None),    # bot engeli: ? veya ✓
    ]
    for url, want in cases:
        got = await check_url(url)
        good = got in ("verified", "unverified") if want is None else got == want
        ok(f"check_url → {got:<10}", good, url[:70])

    print(f"{sum(checks)}/{len(checks)}")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(asyncio.run(_selftest()))
    print("Kullanım: python -m backend.tools --selftest")
