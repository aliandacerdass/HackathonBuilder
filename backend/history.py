"""Geçmiş turlar: runs/ altındaki kayıtlı JSON'lardan arayüz olaylarını yeniden üretir (LLM çağrısı yok).

Arayüz bu olayları canlı turdaki aynı işleyicilerle çizer; tur salt okunur açılır.
python -m backend.history → her turun olaylarını üretip sayar (bozuk kayıt testi)
"""
import json
import re
from datetime import datetime
from pathlib import Path

from .pipeline import RUNS

NAME = re.compile(r"\d{8}-\d{6}-[a-z0-9-]{0,40}")
NO_OUTPUT = "Bu tur için test çıktısı kaydedilmedi."


def load(d: Path, name: str):
    f = d / f"{name}.json"
    return json.loads(f.read_text()) if f.exists() else None


def run_dir(name: str) -> Path | None:
    """Sadece adı kalıba uyan ve konseyi bitmiş tur klasörleri (yol geçişi yok)."""
    if not NAME.fullmatch(name) or not (RUNS / name / "ranking.json").exists():
        return None
    return RUNS / name


def list_runs() -> list[dict]:
    out = []
    for f in sorted(RUNS.glob("*/ranking.json"), reverse=True):  # en yeni üstte
        d = f.parent
        if not NAME.fullmatch(d.name):
            continue
        inp, decision, build = load(d, "input") or {}, load(d, "decision"), load(d, "build")
        if build:
            build = f"{sum(t['tests_ok'] for t in build['tasks'])}/{len(build['tasks'])}"
        elif (d / "plan.json").exists():
            build = "yarım"
        out.append({
            "name": d.name,
            "created": datetime.strptime(d.name[:15], "%Y%m%d-%H%M%S").isoformat(),
            "topic": inp.get("topic", ""),
            "hours": inp.get("hours"),
            "chosen": decision["chosen"]["idea"]["title"] if decision else None,
            "research": (d / "research.json").exists(),
            "build": build,
        })
    return out


def timings(t: dict | None, stage: str) -> list:
    return [("timing", c) for c in (t or {}).get("calls", []) if c["stage"] == stage]


def done(t: dict | None, d: Path) -> tuple:
    t = t or {}  # ilk turlarda timings.json yok
    return ("done", {"run_dir": d.name, "total": t.get("total"), "stages": t.get("stages", {})})


def council_events(d: Path) -> list:
    t, r2, ranking, decision = load(d, "timings"), load(d, "round2"), load(d, "ranking"), load(d, "decision")
    ev = [("stage", {"stage": "refine"}), *timings(t, "refine"), ("refined", load(d, "refined")),
          ("stage", {"stage": "council_round1"}), *timings(t, "council_round1")]
    ev += [("idea", {"idea_id": i, **idea}) for i, idea in load(d, "round1").items()]
    if r2:
        ev += [("stage", {"stage": "council_round2"}), *timings(t, "council_round2")]
        ev += [("critique", c) for c in r2["critiques"]]
        ev += [("idea", {"idea_id": i, **idea}) for i, idea in r2["improved"].items()]
    ev += [("stage", {"stage": "judge"}), *timings(t, "judge"),
           ("ranking", {"judge": ranking["judge"], "ranking": ranking["ranking"]}),
           ("decision", {"idea_id": decision["chosen"]["idea_id"] if decision else None}),
           done(t, d)]  # done akışı kapatır: ondan sonra olay gelmez
    return ev


def research_events(d: Path) -> list | None:
    r = load(d, "research")
    if not r:
        return None
    rd = load(d, "research_decision")
    ev = [("source", {"kind": "paper", "status": "verified", **p}) for p in r["papers"]]
    ev += [("repo", x) for x in r["repos"]]
    ev += [("source", s) for s in r["sources"]]
    ev += [("research", r),
           ("research_decision", {"features": [f["name"] for f in rd["features"]] if rd else []}),
           done(load(d, "research_timings"), d)]
    return ev


def build_events(d: Path) -> list | None:
    plan = load(d, "plan")
    if not plan:
        return None
    b = load(d, "build")
    if not b:  # kodlama yarıda kaldı
        return [("plan", plan), ("stopped", {"resumable": False})]
    ev = [("plan", plan)]
    for t in b["tasks"]:
        ev.append(("test", {"id": t["id"], "ok": t["tests_ok"], "attempt": t.get("fix_attempts", 0), "output": NO_OUTPUT}))
        if "security_reviewed" in t:
            ev.append(("security", {"id": t["id"], "findings": t.get("findings", []), "reviewed": t["security_reviewed"]}))
        ev.append(("task", t))
    ev += [("build", b), done(load(d, "build_timings"), d)]
    return ev


if __name__ == "__main__":
    for run in list_runs():
        d = RUNS / run["name"]
        parts = [council_events(d), research_events(d), build_events(d)]
        print(run["name"], [len(p) if p else "-" for p in parts], run["chosen"], run["build"])
