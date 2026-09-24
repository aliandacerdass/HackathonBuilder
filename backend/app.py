"""Yerel web arayüzü: python -m backend.app → http://127.0.0.1:8000

POST /api/runs                 → konseyi başlatır, {run_id} döner
GET  /api/runs/{id}/events     → SSE: pipeline olayları canlı akar (kopunca kaldığı yerden devam)
POST /api/runs/{id}/decision   → kullanıcının seçtiği fikir → decision.json
POST /api/runs/{id}/research   → V2 araştırmayı başlatır, {research_id} döner (olaylar aynı /events ile)
POST /api/runs/{id}/research-decision → seçilen özellikler → research_decision.json
POST /api/runs/{id}/build      → V3 kodlamayı başlatır ({resume}), {build_id} döner
POST /api/runs/{id}/build/approve → bekleyen plan/paket onayına cevap ({ok, note})
POST /api/runs/{id}/build/stop → kodlamayı durdurur (sonra resume ile devam edilebilir)
"""
import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .builder import resumable, run_build
from .pipeline import RUNS, RunnerError, run_pipeline, save_decision
from .research import run_research

HOST, PORT = "127.0.0.1", 8000  # sadece bu bilgisayar: CLI'lar senin aboneliğinle çalışıyor
FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
ALLOWED_ORIGINS = {f"http://{HOST}:{PORT}", f"http://localhost:{PORT}"}

app = FastAPI()
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


@app.middleware("http")
async def same_origin_only(request: Request, call_next):
    """Başka bir site tarayıcın üzerinden bu sunucuya istek atamasın (kota/prompt kötüye kullanımı)."""
    origin = request.headers.get("origin")
    if origin and origin not in ALLOWED_ORIGINS:
        return JSONResponse({"error": "izin verilmeyen kaynak"}, status_code=403)
    return await call_next(request)


class Live:
    """Çalışan bir boru hattının olay geçmişi. SSE bağlantısı koparsa geçmişten devam edilir."""

    def __init__(self):
        self.events: list[tuple[str, dict]] = []
        self.changed = asyncio.Event()
        self.finished = False
        self.ranking: list[dict] = []
        self.run_dir: Path | None = None
        self.task: asyncio.Task | None = None
        self.pending: asyncio.Future | None = None  # builder kullanıcı onayı bekliyor

    def emit(self, event: str, data: dict):
        self.events.append((event, data))
        if event == "ranking":
            self.ranking = data["ranking"]
        elif event == "done":
            self.run_dir = RUNS / data["run_dir"]
        self.changed.set()

    async def approve(self, kind: str, data: dict) -> dict:
        """Builder'ın onay çağrısı: arayüze sorar, POST .../build/approve cevabını bekler."""
        self.pending = asyncio.get_running_loop().create_future()
        self.emit("approval", {"kind": kind, "data": data})
        try:
            return await self.pending
        finally:
            self.pending = None


LIVE: dict[str, Live] = {}


class RunIn(BaseModel):
    topic: str
    hours: int = 24
    team: str = ""


class DecisionIn(BaseModel):
    idea_id: str
    note: str = ""


class ResearchDecisionIn(BaseModel):
    features: list[str]
    note: str = ""


class BuildIn(BaseModel):
    resume: bool = False


class ApproveIn(BaseModel):
    ok: bool
    note: str = ""


@app.get("/")
async def index():
    return FileResponse(FRONTEND / "index.html")


@app.post("/api/runs")
async def start(body: RunIn):
    topic = body.topic.strip()
    if not topic:
        raise HTTPException(400, "Konu boş olamaz")
    if not 1 <= body.hours <= 168:
        raise HTTPException(400, "Süre 1-168 saat arası olmalı")

    run_id = uuid.uuid4().hex[:12]
    live = LIVE[run_id] = Live()
    start_job(live, run_pipeline(topic, body.hours, body.team.strip(), live.emit))
    return {"run_id": run_id}


def start_job(live: Live, coro):
    """Boru hattını arka planda çalıştırır; hata olsa da akış kapanır."""
    async def job():
        try:
            await coro
        except RunnerError:
            pass  # "fatal" olayı zaten yayınlandı
        except asyncio.CancelledError:  # kullanıcı durdurdu
            live.emit("stopped", {"resumable": bool(live.run_dir and resumable(live.run_dir))})
        except Exception as e:  # beklenmeyen hata da arayüze ulaşsın
            live.emit("fatal", {"error": f"beklenmeyen hata: {e}"})
        finally:
            live.finished = True
            live.changed.set()

    return asyncio.create_task(job())


@app.get("/api/runs/{run_id}/events")
async def events(run_id: str, request: Request):
    live = LIVE.get(run_id)
    if not live:
        raise HTTPException(404, "Böyle bir çalıştırma yok")
    start_at = int(request.headers.get("last-event-id", -1)) + 1

    async def stream():
        i = start_at
        while True:
            while i < len(live.events):
                event, data = live.events[i]
                yield f"id: {i}\nevent: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                i += 1
            if live.finished:
                return
            live.changed.clear()
            try:
                await asyncio.wait_for(live.changed.wait(), 15)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"  # bağlantı açık kalsın

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/api/runs/{run_id}/decision")
async def decide(run_id: str, body: DecisionIn):
    live = LIVE.get(run_id)
    if not live or not live.run_dir:
        raise HTTPException(404, "Bu çalıştırma henüz bitmedi")
    choice = next((r for r in live.ranking if r["idea_id"] == body.idea_id), None)
    if not choice:
        raise HTTPException(400, "Bu fikir sıralamada yok")
    save_decision(live.run_dir, choice, body.note.strip())
    return {"saved": f"runs/{live.run_dir.name}/decision.json"}


@app.post("/api/runs/{run_id}/research")
async def research(run_id: str):
    live = LIVE.get(run_id)
    if not live or not live.run_dir or not (live.run_dir / "decision.json").exists():
        raise HTTPException(400, "Önce bir fikir seç")
    rid = f"{run_id}-r"
    if rid in LIVE and not LIVE[rid].finished:
        return {"research_id": rid}  # zaten çalışıyor: ikinci kez başlatma (kota)
    r = LIVE[rid] = Live()
    r.run_dir = live.run_dir
    start_job(r, run_research(live.run_dir, r.emit))
    return {"research_id": rid}


@app.post("/api/runs/{run_id}/research-decision")
async def research_decide(run_id: str, body: ResearchDecisionIn):
    live = LIVE.get(run_id)
    if not live or not live.run_dir or not (live.run_dir / "research.json").exists():
        raise HTTPException(400, "Araştırma henüz bitmedi")
    research = json.loads((live.run_dir / "research.json").read_text())
    by_name = {f["name"]: f for f in research["features"]}
    chosen = [by_name[n] for n in body.features if n in by_name]
    data = {"features": chosen, "note": body.note.strip(),
            "decided_at": datetime.now().isoformat(timespec="seconds")}
    (live.run_dir / "research_decision.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return {"saved": f"runs/{live.run_dir.name}/research_decision.json", "count": len(chosen)}


@app.post("/api/runs/{run_id}/build")
async def build(run_id: str, body: BuildIn):
    live = LIVE.get(run_id)
    if not live or not live.run_dir or not (live.run_dir / "decision.json").exists():
        raise HTTPException(400, "Önce bir fikir seç")
    bid = f"{run_id}-b"
    if bid in LIVE and not LIVE[bid].finished:
        return {"build_id": bid}  # zaten çalışıyor: ikinci kez başlatma (kota)
    b = LIVE[bid] = Live()
    b.run_dir = live.run_dir
    b.task = start_job(b, run_build(live.run_dir, b.emit, b.approve, resume=body.resume))
    return {"build_id": bid}


@app.post("/api/runs/{run_id}/build/approve")
async def build_approve(run_id: str, body: ApproveIn):
    b = LIVE.get(f"{run_id}-b")
    if not b or not b.pending or b.pending.done():
        raise HTTPException(400, "Onay bekleyen bir şey yok")
    b.pending.set_result({"ok": body.ok, "note": body.note.strip()})
    return {"ok": True}


@app.post("/api/runs/{run_id}/build/stop")
async def build_stop(run_id: str):
    b = LIVE.get(f"{run_id}-b")
    if not b or b.finished:
        raise HTTPException(400, "Çalışan bir kodlama yok")
    b.task.cancel()
    return {"stopping": True}


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
