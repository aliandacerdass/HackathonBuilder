"""V1 boru hattı: konu → refiner → konsey (2 tur) → judge → sıralı fikirler → kullanıcı seçimi.

Terminalden:
    python -m backend.pipeline "Sağlıkta yapay zeka" --hours 24 --team "2 kişi, Python"
"""
import argparse
import asyncio
import json
import re
import time
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ValidationError

from .runners import RunnerError, ask
from .schemas import Idea, Ideas, Refined, Round2, Verdict, json_schema

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
RUNS = ROOT / "runs"

COUNCIL = ["claude", "gpt", "gemini"]
FALLBACK = ["claude", "gemini", "gpt"]  # refiner/judge: ilki düşerse sıradaki
IDEAS_PER_MEMBER = 2
WEIGHTS = {"jury_fit": 0.25, "feasibility": 0.25, "wow": 0.2, "originality": 0.15, "demo": 0.15}

# Kullanıcının okuduğu metni yazan skill'ler seçilen dilde yazar.
# query-writer (arama sorgusu) ve coder (kod) her zaman İngilizce kalır.
TRANSLATED = {"refiner", "council-member", "judge", "planner", "security-reviewer",
              "feature-extractor", "stats-extractor", "web-researcher", "repo-reviewer"}
LANG_RULE = {"tr": ("\n\n# Output language\nWrite every human-readable text value in Turkish, with correct "
                    "Turkish characters (ç ğ ı ö ş ü). This overrides any 'Write in English' rule above. "
                    "Keep JSON keys, enum values, ids, numbers, URLs, file paths and code identifiers unchanged.")}


# ---------- yardımcılar ----------

def build_prompt(skill: str, task: str, data: dict, lang: str = "en") -> str:
    """Skill dosyası (rol + kurallar) + görev + girdi JSON'u = tek prompt."""
    rules = (SKILLS / f"{skill}.md").read_text()
    if skill in TRANSLATED:
        rules += LANG_RULE.get(lang, "")
    body = json.dumps(data, indent=2, ensure_ascii=False)
    return f"{rules}\n\n# Task\n{task}\n\n# Input\n```json\n{body}\n```"


async def call(run: "Run", stage: str, model: str, skill: str, task: str, data: dict,
               out: type[BaseModel], web: bool = False):
    """ask() + pydantic doğrulama + süre ölçümü. Şemaya uymayan cevap da hata sayılır."""
    t0 = time.monotonic()
    try:
        raw = await ask(model, build_prompt(skill, task, data, run.lang), json_schema(out), web=web)
        try:
            result = out.model_validate(raw)
        except ValidationError as e:
            raise RunnerError(f"{model}: şemaya uymayan cevap: {e.errors()[0]['msg']}")
        if run.lang == "tr" and model == "gpt" and skill in TRANSLATED:
            result = await fix_turkish(result, out)
    except RunnerError:
        run.timing(stage, model, t0, ok=False)
        raise
    run.timing(stage, model, t0, ok=True)
    return result


async def fix_turkish(result: BaseModel, out: type[BaseModel]) -> BaseModel:
    """GPT Türkçe karakterleri düşürüyor ("cuzdan"): Claude düzeltir. Olmazsa GPT'nin cevabı aynen kalır."""
    prompt = ("Fix the Turkish in every text value of this JSON: restore missing Turkish characters (ç ğ ı ö ş ü) "
              "and translate any English text to Turkish. Do not change the meaning, keys, enum values, ids, "
              "numbers, URLs or file paths.\n\n```json\n"
              + json.dumps(result.model_dump(), ensure_ascii=False) + "\n```")
    try:
        return out.model_validate(await ask("claude", prompt, json_schema(out)))
    except (RunnerError, ValidationError):
        return result


async def call_first(run: "Run", stage: str, models: list[str], *args):
    """Modelleri sırayla dener, ilk başaranı döner: (model, sonuç)."""
    errors = []
    for m in models:
        try:
            return m, await call(run, stage, m, *args)
        except RunnerError as e:
            errors.append(str(e))
    raise RunnerError("hiçbir model cevap vermedi: " + " | ".join(errors))


class Run:
    """Tek çalıştırmanın klasörü + olay yayını. Mevcut klasörü açar (V2 araştırma aynı klasöre yazar)."""

    def __init__(self, run_dir: Path, emit):
        self.dir = run_dir
        self.emit = emit
        self.t0 = time.monotonic()
        self.calls: list[dict] = []     # her model çağrısı: aşama, model, süre, başarı
        self.stages: dict[str, float] = {}  # aşama → başlangıç (saniye, t0'a göre)
        inp = run_dir / "input.json"  # dil turun başında seçilir; araştırma/kodlama da aynı dili kullanır
        self.lang = json.loads(inp.read_text()).get("lang", "en") if inp.exists() else "en"

    @classmethod
    def new(cls, brief: dict, emit) -> "Run":
        tr = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
        slug = re.sub(r"[^a-z0-9]+", "-", brief["topic"].translate(tr).lower()).strip("-")[:40]
        run_dir = RUNS / f"{datetime.now():%Y%m%d-%H%M%S}-{slug}"
        run_dir.mkdir(parents=True)
        run = cls(run_dir, emit)
        run.save("input", brief)
        run.lang = brief.get("lang", "en")
        return run

    def load(self, name: str):
        return json.loads((self.dir / f"{name}.json").read_text())

    def begin(self, stage: str):
        self.stages[stage] = round(time.monotonic() - self.t0, 1)
        self.emit("stage", {"stage": stage})

    def timing(self, stage: str, model: str, t0: float, ok: bool):
        d = {"stage": stage, "model": model, "seconds": round(time.monotonic() - t0, 1), "ok": ok}
        self.calls.append(d)
        self.emit("timing", d)

    def save_timings(self, name: str = "timings"):
        total = round(time.monotonic() - self.t0, 1)
        names = list(self.stages)
        ends = [self.stages[n] for n in names[1:]] + [total]
        stages = {n: round(e - self.stages[n], 1) for n, e in zip(names, ends)}
        self.save(name, {"total": total, "stages": stages, "calls": self.calls})
        return total, stages

    def save(self, name: str, data):
        (self.dir / f"{name}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))


# ---------- aşamalar ----------

async def refine(run: Run, brief: dict) -> Refined:
    run.begin("refine")
    model, refined = await call_first(
        run, "refine", FALLBACK, "refiner", "Turn this hackathon theme into a precise brief.", brief, Refined)
    run.save("refined", {"model": model, **refined.model_dump()})
    run.emit("refined", {"model": model, **refined.model_dump()})
    return refined


async def council(run: Run, ctx: dict) -> tuple[dict[str, Idea], dict[str, dict]]:
    """2 turlu konsey. Döner: (fikirler {id: Idea}, meta {id: {author, round}})."""
    ideas: dict[str, Idea] = {}
    meta: dict[str, dict] = {}

    def add(idea: Idea, author: str, rnd: int):
        iid = f"I{len(ideas) + 1}"  # anonim id: yazar gizli
        ideas[iid], meta[iid] = idea, {"author": author, "round": rnd}
        run.emit("idea", {"idea_id": iid, **meta[iid], **idea.model_dump()})

    # Tur 1 — bağımsız: modeller birbirini görmez (anchoring önlenir)
    run.begin("council_round1")
    task1 = f"Propose exactly {IDEAS_PER_MEMBER} clearly different hackathon ideas for this brief."

    async def round1(m):
        try:
            r = await call(run, "council_round1", m, "council-member", task1, ctx, Ideas)
        except RunnerError as e:
            run.emit("error", {"stage": "council_round1", "model": m, "error": str(e)})
            return
        for idea in r.ideas[:IDEAS_PER_MEMBER]:
            add(idea, m, 1)

    await asyncio.gather(*(round1(m) for m in COUNCIL))
    if not ideas:
        raise RunnerError("konsey: hiçbir model fikir üretemedi")
    run.save("round1", {i: {**meta[i], **ideas[i].model_dump()} for i in ideas})

    # Tur 2 — tartışma: herkes başkalarının fikrini eleştirir + geliştirilmiş fikir önerir
    members = sorted({meta[i]["author"] for i in ideas})
    critiques = []
    if len(members) >= 2:
        run.begin("council_round2")
        pool = {i: ideas[i].model_dump() for i in ideas}

        async def round2(m):
            own = [i for i in ideas if meta[i]["author"] == m]
            task2 = (f"Your own ideas are {own}; do not critique them. Critique every other idea. "
                     "Then propose ONE improved idea: a stronger version of the best idea, "
                     "or a combination of the strongest parts of several ideas.")
            try:
                r = await call(run, "council_round2", m, "council-member", task2,
                               {**ctx, "ideas": pool}, Round2)
            except RunnerError as e:
                run.emit("error", {"stage": "council_round2", "model": m, "error": str(e)})
                return
            for c in r.critiques:
                if c.idea_id in pool and c.idea_id not in own:
                    critiques.append({"by": m, **c.model_dump()})
                    run.emit("critique", {"by": m, **c.model_dump()})
            add(r.improved_idea, m, 2)

        await asyncio.gather(*(round2(m) for m in members))
        run.save("round2", {"critiques": critiques,
                            "improved": {i: {**meta[i], **ideas[i].model_dump()}
                                         for i in ideas if meta[i]["round"] == 2}})
    return ideas, meta


async def judge(run: Run, ctx: dict, ideas: dict[str, Idea], meta: dict[str, dict]) -> list[dict]:
    run.begin("judge")
    data = {**ctx, "ideas": {i: ideas[i].model_dump() for i in ideas}}  # yazar bilgisi YOK
    model, verdict = await call_first(
        run, "judge", FALLBACK, "judge", "Score every idea in `ideas`.", data, Verdict)

    scores = {s.idea_id: s for s in verdict.scores if s.idea_id in ideas}
    ranking = []
    for iid, s in scores.items():
        parts = {k: max(1, min(10, getattr(s, k))) for k in WEIGHTS}  # 1-10'a sıkıştır
        total = round(sum(WEIGHTS[k] * v for k, v in parts.items()), 2)  # hesap Python'da
        ranking.append({"idea_id": iid, **meta[iid], "total": total, "scores": parts,
                        "reasoning": s.reasoning, "idea": ideas[iid].model_dump()})
    ranking.sort(key=lambda r: r["total"], reverse=True)
    for n, r in enumerate(ranking, 1):
        r["rank"] = n

    missing = [i for i in ideas if i not in scores]
    if missing:
        run.emit("error", {"stage": "judge", "model": model, "error": f"puanlanmayan: {missing}"})
    run.save("ranking", {"judge": model, "ranking": ranking, "unscored": missing})
    run.emit("ranking", {"judge": model, "ranking": ranking})
    return ranking


async def run_pipeline(topic: str, hours: int, team: str, emit, lang: str = "tr") -> tuple[Run, list[dict]]:
    brief = {"topic": topic, "hours": hours, "team": team}
    run = Run.new({**brief, "lang": lang}, emit)
    try:
        refined = await refine(run, brief)
        ctx = {"brief": refined.model_dump(), "hours": hours, "team": team}
        ideas, meta = await council(run, ctx)
        ranking = await judge(run, ctx, ideas, meta)
    except RunnerError as e:
        run.save_timings()
        run.emit("fatal", {"error": str(e)})
        raise
    total, stages = run.save_timings()
    run.emit("done", {"run_dir": run.dir.name, "total": total, "stages": stages})
    return run, ranking


def save_decision(run_dir: Path, choice: dict, note: str = ""):
    """Kullanıcının seçtiği fikir → decision.json (V2+ bunu okur)."""
    data = {"chosen": choice, "note": note, "decided_at": datetime.now().isoformat(timespec="seconds")}
    (run_dir / "decision.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))


# ---------- terminal ----------

def print_event(event: str, d: dict):
    if event == "stage":
        print(f"\n▶ {d['stage']}")
    elif event == "refined":
        print(f"  [{d['model']}] {d['topic']}\n  jüri: {', '.join(d['jury_criteria'])}")
    elif event == "idea":
        print(f"  {d['idea_id']} [{d['author']}, tur {d['round']}] {d['title']} — {d['pitch']}")
    elif event == "critique":
        print(f"  {d['by']} → {d['idea_id']}: -{'; '.join(d['weaknesses'][:1])}")
    elif event == "timing":
        print(f"  ⏱ {d['model']:<7} {d['seconds']:6.1f}s {'' if d['ok'] else '✗'}")
    elif event == "error":
        print(f"  ✗ {d['stage']} / {d['model']}: {d['error'][:200]}")
    elif event == "fatal":
        print(f"\n✗ DURDU: {d['error']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("topic")
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--team", default="")
    ap.add_argument("--lang", choices=["tr", "en"], default="tr", help="model çıktılarının dili")
    a = ap.parse_args()

    run, ranking = asyncio.run(run_pipeline(a.topic, a.hours, a.team, print_event, a.lang))
    t = json.loads((run.dir / "timings.json").read_text())
    print(f"\n⏱ Toplam {t['total']}s — " + ", ".join(f"{k} {v}s" for k, v in t["stages"].items()))

    print("\n🏆 SIRALAMA")
    for r in ranking:
        print(f"  {r['rank']}. [{r['total']:.2f}] {r['idea']['title']} ({r['idea_id']}, {r['author']})")
        print(f"     {r['reasoning']}")

    pick = input("\nHangi fikir? (sıra no, boş = sonra karar ver): ").strip()
    if pick.isdigit() and 1 <= int(pick) <= len(ranking):
        note = input("Not (opsiyonel): ").strip()
        save_decision(run.dir, ranking[int(pick) - 1], note)
        print(f"✓ Karar kaydedildi: runs/{run.dir.name}/decision.json")
    else:
        print(f"Karar verilmedi. Çıktılar: runs/{run.dir.name}/")


if __name__ == "__main__":
    main()
