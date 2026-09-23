"""V2 araştırma: seçilen fikir → sorgular → (makale ‖ repo ‖ web ‖ video) → doğrulama → (istatistik ‖ özellik).

Girdi: V1 turunun klasörü (decision.json olmalı). Çıktı aynı klasöre: research.json.
Terminalden:
    python -m backend.research runs/20260923-164606-egitimde-yapay-zeka
"""
import argparse
import asyncio
from datetime import datetime
from pathlib import Path

from . import tools
from .pipeline import RUNS, Run, RunnerError, call, call_first
from .schemas import Features, Queries, RepoReview, Stats, WebFindings

ANALYSTS = ["gemini", "gpt", "claude"]  # analiz: Gemini önce (web'siz rol)
MAX_PAPERS, MAX_REPOS = 8, 6


def norm(url: str) -> str:
    return url.strip().rstrip("/").lower()


async def run_research(run_dir: Path, emit) -> dict:
    run = Run(run_dir, emit)
    decision = run.load("decision")
    ctx = {"brief": run.load("refined"), **run.load("input"), "idea": decision["chosen"]["idea"]}
    ctx.pop("model", None)
    ctx["brief"].pop("model", None)
    if decision.get("note"):
        ctx["team_note"] = decision["note"]

    try:
        # 1) Sorgular (LLM): fikirden her kaynak için arama terimi
        run.begin("research_queries")
        model, q = await call_first(run, "research_queries", ["claude", "gpt", "gemini"],
                                    "query-writer", "Write search queries for this idea.", ctx, Queries)
        run.emit("queries", {"model": model, **q.model_dump()})

        # 2) Toplama: API'ler + web araştırmacıları paralel
        run.begin("research_collect")
        papers, repos, web, videos = await asyncio.gather(
            collect_papers(run, q.paper_queries),
            collect_repos(run, ctx, q.repo_queries),
            web_search(run, ctx, "gpt", q.web_queries,
                       "Find articles, official statistics and past hackathon projects for these queries."),
            web_search(run, ctx, "claude", q.video_queries,
                       "Find YouTube videos (demos, talks, explainers) for these queries. "
                       "Use youtube.com/watch URLs. kind must be 'video'."),
        )

        # 3) Doğrulama (kod): web/video linkleri gerçekten var mı
        run.begin("research_verify")
        sources = await verify(run, web + videos)

        # 4) Analiz (LLM, web'siz): sadece toplanan kaynaklardan
        run.begin("research_analyze")
        material = {
            **ctx,
            "papers": [{k: p[k] for k in ("title", "url", "year", "abstract")} for p in papers],
            "web_sources": [{k: s[k] for k in ("title", "url", "finding", "status")} for s in sources],
            "repos": [{k: r[k] for k in ("name", "url", "description", "reuse")} for r in repos if r.get("reuse")],
        }
        known = {norm(p["url"]) for p in papers} | {norm(s["url"]) for s in sources} | {norm(r["url"]) for r in repos}
        status = {norm(p["url"]): "verified" for p in papers} | {norm(r["url"]): "verified" for r in repos} \
            | {norm(s["url"]): s["status"] for s in sources}

        (sm, stats), (fm, feats) = await asyncio.gather(
            call_first(run, "research_analyze", ANALYSTS, "stats-extractor",
                       "Extract the strongest numbers from these sources.", material, Stats),
            call_first(run, "research_analyze", ANALYSTS, "feature-extractor",
                       "Suggest features for the idea based on these sources.", material, Features),
        )

        # Uydurma kaynak filtresi: link bizim topladığımız listede değilse at
        good_stats, dropped = [], []
        for s in stats.stats:
            if norm(s.source_url) in known:
                good_stats.append({**s.model_dump(), "status": status[norm(s.source_url)]})
            else:
                dropped.append(s.source_url)
        features = []
        for f in feats.features:
            urls = [u for u in f.source_urls if norm(u) in known]
            dropped += [u for u in f.source_urls if norm(u) not in known]
            if urls:
                features.append({**f.model_dump(), "source_urls": urls})
        if dropped:
            run.emit("error", {"stage": "research_analyze", "model": f"{sm}/{fm}",
                               "error": f"listede olmayan {len(dropped)} kaynak atıldı"})
    except RunnerError as e:
        run.save_timings("research_timings")
        run.emit("fatal", {"error": str(e)})
        raise

    result = {"queries": q.model_dump(), "papers": papers, "repos": repos, "sources": sources,
              "stats": good_stats, "features": features, "dropped_urls": dropped,
              "analysts": {"stats": sm, "features": fm},
              "created_at": datetime.now().isoformat(timespec="seconds")}
    run.save("research", result)
    total, stages = run.save_timings("research_timings")
    run.emit("research", result)
    run.emit("done", {"run_dir": run.dir.name, "total": total, "stages": stages})
    return result


# ---------- toplayıcılar ----------

async def collect_papers(run: Run, queries: list[str]) -> list[dict]:
    since = datetime.now().year - 3
    results = await asyncio.gather(*(tools.search_papers(q, since, 4) for q in queries),
                                   return_exceptions=True)
    seen, papers = set(), []
    for q, r in zip(queries, results):
        if isinstance(r, Exception):
            run.emit("error", {"stage": "research_collect", "model": "openalex", "error": f"{q}: {r}"})
            continue
        for p in r:
            if norm(p["url"]) not in seen:
                seen.add(norm(p["url"]))
                papers.append(p)
    papers = sorted(papers, key=lambda p: p["citations"], reverse=True)[:MAX_PAPERS]
    for p in papers:
        run.emit("source", {"kind": "paper", "status": "verified", **p})
    return papers


async def collect_repos(run: Run, ctx: dict, queries: list[str]) -> list[dict]:
    results = await asyncio.gather(*(tools.search_repos(q, 4) for q in queries), return_exceptions=True)
    seen, repos = set(), []
    for q, r in zip(queries, results):
        if isinstance(r, Exception):
            run.emit("error", {"stage": "research_collect", "model": "github", "error": f"{q}: {r}"})
            continue
        for repo in r:
            if repo["name"] not in seen:
                seen.add(repo["name"])
                repos.append(repo)
    repos = sorted(repos, key=lambda r: r["stars"], reverse=True)[:MAX_REPOS]
    if not repos:
        return []

    readmes = await asyncio.gather(*(tools.repo_readme(r["name"]) for r in repos))
    data = {**ctx, "repos": [{**r, "readme": rd} for r, rd in zip(repos, readmes)]}
    try:
        _, review = await call_first(run, "research_collect", ["gpt", "claude", "gemini"],
                                     "repo-reviewer", "Pick the most useful repositories.", data, RepoReview)
    except RunnerError as e:
        run.emit("error", {"stage": "research_collect", "model": "repo-reviewer", "error": str(e)})
        review = RepoReview(picks=[])
    picks = {p.name: p for p in review.picks}
    for r in repos:
        if r["name"] in picks:
            r["reuse"], r["caution"] = picks[r["name"]].reuse, picks[r["name"]].caution
        run.emit("repo", r)
    return repos


async def web_search(run: Run, ctx: dict, model: str, queries: list[str], task: str) -> list[dict]:
    if not queries:
        return []
    try:
        r = await call(run, "research_collect", model, "web-researcher", task,
                       {"idea": ctx["idea"], "queries": queries}, WebFindings, web=True)
    except RunnerError as e:
        run.emit("error", {"stage": "research_collect", "model": model, "error": str(e)})
        return []
    return [{**s.model_dump(), "found_by": model} for s in r.sources]


async def verify(run: Run, sources: list[dict]) -> list[dict]:
    seen, unique = set(), []
    for s in sources:
        if norm(s["url"]) not in seen:
            seen.add(norm(s["url"]))
            unique.append(s)
    statuses = await asyncio.gather(*(tools.check_url(s["url"]) for s in unique))
    kept = []
    for s, st in zip(unique, statuses):
        s["status"] = st
        run.emit("source", s)
        if st != "dead":
            kept.append(s)
    return kept


# ---------- terminal ----------

def print_event(event: str, d: dict):
    if event == "stage":
        print(f"\n▶ {d['stage']}")
    elif event == "queries":
        print(f"  [{d['model']}] makale: {d['paper_queries']}\n  repo: {d['repo_queries']}")
    elif event == "timing":
        print(f"  ⏱ {d['model']:<7} {d['seconds']:6.1f}s {'' if d['ok'] else '✗'}")
    elif event == "source" and d["kind"] != "paper":
        mark = {"verified": "✓", "unverified": "?", "dead": "✗"}[d["status"]]
        print(f"  {mark} [{d['found_by']}] {d['url'][:90]}")
    elif event == "error":
        print(f"  ✗ {d['stage']} / {d['model']}: {d['error'][:200]}")
    elif event == "fatal":
        print(f"\n✗ DURDU: {d['error']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", help="decision.json içeren V1 tur klasörü")
    a = ap.parse_args()
    run_dir = Path(a.run_dir)
    if not run_dir.is_absolute() and not run_dir.exists():
        run_dir = RUNS / a.run_dir
    if not (run_dir / "decision.json").exists():
        raise SystemExit(f"{run_dir}/decision.json yok. Önce V1'de bir fikir seç.")

    r = asyncio.run(run_research(run_dir, print_event))
    print(f"\n📚 {len(r['papers'])} makale · {len(r['repos'])} repo · {len(r['sources'])} web/video kaynağı")
    print("\n📊 JÜRİ İÇİN SAYILAR")
    for s in r["stats"]:
        print(f"  {'✓' if s['status'] == 'verified' else '?'} {s['value']:>10}  {s['claim']}")
    print("\n🧩 ÖNERİLEN ÖZELLİKLER")
    for f in r["features"]:
        print(f"  [{f['effort']}] {f['name']} — {f['why']}")
    if r["dropped_urls"]:
        print(f"\n⚠ Listede olmayan {len(r['dropped_urls'])} kaynak atıldı (uydurma şüphesi)")


if __name__ == "__main__":
    main()
