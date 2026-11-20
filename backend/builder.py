"""V3 kodlama döngüsü: seçilen fikir (+özellikler) → plan → 👤 onay → 👤 paket onayı → görev döngüsü.

Her görev: kodlayıcı (Claude/Codex/Gemini, hangisi kuruluysa) kodlar (sandbox) → testleri BİZ çalıştırırız (sandbox) → en fazla 3 düzeltme
→ Claude güvenlik incelemesi (araçsız, diff metin olarak) → ciddi bulgu varsa düzeltme → commit.

Terminalden:
    python -m backend.builder runs/20260923-220049-cevre-ve-surdurulebilirlik-icin-yapay-ze
"""
import argparse
import ast
import asyncio
import importlib.metadata
import json
import os
import shutil
import sys
import time
from pathlib import Path

from .pipeline import ROOT, RUNS, SKILLS, Run, RunnerError, call_first
from .runners import CODER, PROC_GROUP, SANDBOXED, WINDOWS, code, kill_tree, sandbox, venv_python
from .schemas import CodeReport, DemoScript, Plan, SecurityReview, json_schema
from .ui import SHOTS, capture, clean_steps

PROJECTS = Path.home() / "HackathonBuilderProjects"
MAX_FIX = 3
MAX_TASKS = 8
BASE_PACKAGES = ["fastapi", "uvicorn", "httpx", "pydantic"]  # planner.md bunları "kurulu" sayar
TEST_TIMEOUT = 300
PORT = 8001
STATIC = "app/static/"
UI_COMMIT = "UI cilası"
# Plan onayında seçilir: hangi güvenlik bulguları kodlayıcıya düzelttirilir
FIX_LEVELS = {"high": {"high"}, "medium": {"high", "medium"}, "low": {"high", "medium", "low"}}
CODER_FILES = ("AGENTS.md", "CLAUDE.md")  # kodlayıcının kendiliğinden okuduğu dosya (Gemini de AGENTS.md okur)
RUN_PY = r".venv\Scripts\python" if WINDOWS else ".venv/bin/python"  # kullanıcıya gösterilen çalıştırma komutu


class BuildStopped(RunnerError):
    """Kullanıcı reddetti veya durdurdu."""


# ---------- yardımcılar ----------

async def sh(cmd: list[str], cwd: Path, timeout: int = 120, env: dict | None = None) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=cwd, stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        env={**os.environ, **(env or {})}, **PROC_GROUP)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        kill_tree(proc)
        return 124, f"{cmd[0]}: {timeout}s içinde bitmedi"
    except asyncio.CancelledError:
        kill_tree(proc)
        raise
    return proc.returncode, out.decode(errors="replace")


async def git(project: Path, *args: str) -> str:
    code_, out = await sh(["git", *args], project)
    if code_ != 0:
        raise RunnerError(f"git {args[0]}: {out[-300:]}")
    return out


async def run_tests(project: Path) -> tuple[bool, str]:
    """Üretilen testleri sandbox'ta çalıştırır: sadece proje klasörüne yazabilir, internet yok (Windows'ta sandbox yok).
    Ajanın 'testler geçti' raporuna güvenmeyiz, sonucu bu belirler."""
    cmd = [venv_python(project), "-m", "unittest", "discover", "-s", "tests", "-v"]
    rc, out = await sh(sandbox(cmd, project, network=False), project, TEST_TIMEOUT, {"PYTHONDONTWRITEBYTECODE": "1"})
    return rc == 0, out[-3000:]


def plan_info(plan: Plan) -> dict:
    """Onay ekranı için plan + kodu kimin yazacağı + sandbox var mı (Windows'ta yok: uyarı gösterilir)."""
    return {**plan.model_dump(), "coder": CODER, "sandboxed": SANDBOXED}


# ---------- aşamalar ----------

async def make_plan(run: Run, ctx: dict, note: str = "") -> Plan:
    task = "Write the build plan for this idea."
    if note:
        task += f" The team rejected the previous plan with this feedback, follow it: {note}"
    _, plan = await call_first(run, "build_plan", ["claude", "gpt", "gemini"], "planner", task, ctx, Plan)
    plan.tasks = plan.tasks[:MAX_TASKS]
    run.save("plan", plan.model_dump())
    run.emit("plan", plan.model_dump())
    return plan


async def setup_project(run: Run, plan: Plan, ctx: dict) -> Path:
    project = PROJECTS / run.dir.name
    if project.exists() and any(project.iterdir()):
        raise RunnerError(f"{project} zaten var ve boş değil. Sil veya başka bir tur seç.")
    (project / "tests").mkdir(parents=True, exist_ok=True)
    (project / "app").mkdir(exist_ok=True)

    # Kodlayıcı bu dosyayı kendiliğinden okur (Codex ve Gemini: AGENTS.md, Claude: CLAUDE.md): skill + proje bağlamı
    agents = (SKILLS / "coder.md").read_text() + "\n\n## This project\n" + json.dumps(
        {"idea": ctx["idea"], "selected_features": ctx.get("selected_features", []),
         "hours": ctx["hours"], "plan": plan.summary, "file_tree": plan.file_tree},
        indent=2, ensure_ascii=False)
    for name in CODER_FILES:
        (project / name).write_text(agents)
    (project / ".gitignore").write_text(".venv/\n__pycache__/\n*.pyc\n.env\n.env.*\n*.log\n.DS_Store\n")
    (project / "tests" / "__init__.py").touch()

    # Sızıntı koruması üretilen projeye de kurulur (sandbox okumayı engellemiyor)
    (project / "scripts").mkdir(exist_ok=True)
    (project / ".githooks").mkdir(exist_ok=True)
    shutil.copy(ROOT / "scripts" / "pre-push-check.sh", project / "scripts" / "pre-push-check.sh")
    shutil.copy(ROOT / ".githooks" / "pre-push", project / ".githooks" / "pre-push")

    rc, out = await sh([sys.executable, "-m", "venv", "--system-site-packages", ".venv"], project)
    if rc != 0:
        raise RunnerError(f"venv kurulamadı: {out[-300:]}")
    # Temel paketler sistemde yoksa (ör. HackathonBuilder kendi .venv'inden çalışıyorsa) ürüne kurulur
    rc, _ = await sh([venv_python(project), "-c", "import " + ", ".join(BASE_PACKAGES)], project)
    if rc != 0:
        rc, out = await sh([venv_python(project), "-m", "pip", "install", "-q", *BASE_PACKAGES], project, 600)
        if rc != 0:
            raise RunnerError(f"temel paketler kurulamadı (internet?): {out[-300:]}")
    await git(project, "init", "-q", "-b", "main")
    await git(project, "config", "core.hooksPath", ".githooks")
    await git(project, "add", "-A")
    await git(project, "commit", "-qm", "Proje iskeleti (HackathonBuilder)")
    run.emit("project", {"path": str(project)})
    return project


async def install_packages(run: Run, project: Path, packages: list[str]):
    """Sandbox'ta internet yok: onaylanan paketleri biz kurarız (sandbox dışında, kullanıcı onayıyla)."""
    rc, out = await sh([venv_python(project), "-m", "pip", "install", "-q", *packages], project, 600)
    if rc != 0:
        raise RunnerError(f"paket kurulumu başarısız: {out[-400:]}")
    run.emit("packages_installed", {"packages": packages})


async def build_task(run: Run, project: Path, plan: Plan, i: int, fix: str = "high") -> dict:
    t = plan.tasks[i]
    stage = f"build_{t.id}"
    run.begin(stage)
    schema = json_schema(CodeReport)
    task_text = json.dumps(t.model_dump(), ensure_ascii=False)
    done_before = [f"{x.id} {x.title}" for x in plan.tasks[:i]]

    run.emit("task", {"id": t.id, "title": t.title, "status": "coding"})
    await timed_code(run, stage, project,
                     f"Implement this task: {task_text}\nAlready done: {done_before}\n"
                     "Follow AGENTS.md. Write tests for it, then report.", schema)

    # Test → düzeltme döngüsü (sonucu BİZİM test çalıştırmamız belirler)
    attempts = 0
    ok, out = await run_tests(project)
    run.emit("test", {"id": t.id, "ok": ok, "attempt": attempts, "output": out[-1500:]})
    while not ok and attempts < MAX_FIX:
        attempts += 1
        run.emit("task", {"id": t.id, "title": t.title, "status": f"fixing {attempts}/{MAX_FIX}"})
        await timed_code(run, stage, project,
                         f"The tests fail after task {t.id}. Fix the code (or a wrong test) so all tests pass. "
                         f"Test output:\n{out}", schema)
        ok, out = await run_tests(project)
        run.emit("test", {"id": t.id, "ok": ok, "attempt": attempts, "output": out[-1500:]})

    # Güvenlik incelemesi: Claude araçsız, diff'i metin olarak görür
    run.emit("task", {"id": t.id, "title": t.title, "status": "security review"})
    await git(project, "add", "-A")
    diff = (await git(project, "diff", "--cached"))[:20000]
    findings, reviewed = [], True
    if diff.strip():
        try:
            _, review = await call_first(run, stage, ["claude", "gpt", "gemini"], "security-reviewer",
                                         f"Review the diff of task {t.id}.", {"task": t.model_dump(), "diff": diff},
                                         SecurityReview)
            findings = [f.model_dump() for f in review.findings]
        except RunnerError as e:
            reviewed = False  # "0 bulgu" DEĞİL: inceleme hiç yapılamadı
            run.emit("error", {"stage": stage, "model": "security", "error": str(e)})
    to_fix = [f for f in findings if f["severity"] in FIX_LEVELS[fix]]
    run.emit("security", {"id": t.id, "findings": findings, "reviewed": reviewed})
    if to_fix:
        run.emit("task", {"id": t.id, "title": t.title, "status": "fixing security"})
        await timed_code(run, stage, project,
                         f"Fix these security findings, keep tests passing: {json.dumps(to_fix)}", schema)
        ok, out = await run_tests(project)
        run.emit("test", {"id": t.id, "ok": ok, "attempt": attempts + 1, "output": out[-1500:]})

    await git(project, "add", "-A")
    status = "done" if ok else "tests failing"
    await git(project, "commit", "-qm", f"{t.id}: {t.title}" + ("" if ok else " (testler kırık)"), "--allow-empty")
    result = {"id": t.id, "title": t.title, "status": status, "tests_ok": ok, "fix_attempts": attempts,
              "security_reviewed": reviewed, "findings": findings, "security_fixed": bool(to_fix)}
    run.emit("task", result)
    return result


async def timed_code(run: Run, stage: str, project: Path, prompt: str, schema: dict) -> dict:
    t0 = time.monotonic()
    try:
        r = await code(project, prompt, schema)
    except RunnerError:
        run.timing(stage, CODER, t0, ok=False)
        raise
    run.timing(stage, CODER, t0, ok=True)
    return r


# ---------- boru hattı ----------

async def done_task_ids(project: Path) -> set[str]:
    """Commit mesajlarından biten görevler: "T3: ..." (testleri kırık olanlar hariç)."""
    log = await git(project, "log", "--format=%s")
    return {line.split(":")[0] for line in log.splitlines()
            if ":" in line and line[0] == "T" and "(testler kırık)" not in line}


def resumable(run_dir: Path) -> bool:
    """--resume için onaylı plan ve kurulmuş proje gerekir."""
    return (run_dir / "plan.json").exists() and (PROJECTS / run_dir.name / ".git").exists()


async def run_build(run_dir: Path, emit, approve, resume: bool = False) -> dict:
    """approve(kind, data) → {"ok": bool, "note": str}. kind: "plan" | "packages".
    resume=True: onaylı plan.json ve proje klasörüyle, biten görevleri atlayarak devam eder (kota dolunca)."""
    run = Run(run_dir, emit)
    decision = run.load("decision")
    ctx = {"brief": run.load("refined"), **run.load("input"), "idea": decision["chosen"]["idea"]}
    ctx["brief"].pop("model", None)
    if (run.dir / "research_decision.json").exists():
        ctx["selected_features"] = run.load("research_decision")["features"]

    try:
        if resume:
            project = PROJECTS / run.dir.name
            if not resumable(run.dir):
                raise RunnerError("devam edilecek plan veya proje yok; --resume olmadan başlat")
            plan = Plan.model_validate(run.load("plan"))
            opts = run.load("build_options") if (run.dir / "build_options.json").exists() else {}
            fix, packages = opts.get("fix", "high"), opts.get("packages", [])
            run.emit("plan", plan.model_dump())
            done = await done_task_ids(project)
            run.emit("resume", {"done": sorted(done)})
            results = [{"id": t.id, "title": t.title, "status": "done (önceki çalıştırma)", "tests_ok": True}
                       for t in plan.tasks if t.id in done]
            for i, t in enumerate(plan.tasks):
                if t.id not in done:
                    results.append(await build_task(run, project, plan, i, fix))
            return await finish(run, project, plan, results, packages)

        run.begin("build_plan")
        plan = await make_plan(run, ctx)
        answer = await approve("plan", plan_info(plan))
        if not answer["ok"] and answer.get("note"):  # geri bildirimle bir kez yeniden planla
            plan = await make_plan(run, ctx, answer["note"])
            answer = await approve("plan", plan_info(plan))
        if not answer["ok"]:
            raise BuildStopped("plan reddedildi")
        fix = answer.get("fix") if answer.get("fix") in FIX_LEVELS else "high"

        run.begin("build_setup")
        project = await setup_project(run, plan, ctx)
        packages = []
        if plan.packages:
            answer = await approve("packages", {"packages": plan.packages})
            if answer["ok"]:
                await install_packages(run, project, plan.packages)
                packages = plan.packages
            else:
                for name in CODER_FILES:
                    (project / name).write_text((project / name).read_text() +
                                                f"\n\nDo NOT use these packages (not installed): {plan.packages}\n")

        run.save("build_options", {"fix": fix, "packages": packages})  # --resume aynı seçeneklerle sürer

        results = []
        for i in range(len(plan.tasks)):
            results.append(await build_task(run, project, plan, i, fix))
        return await finish(run, project, plan, results, packages)
    except RunnerError as e:
        run.save_timings("build_timings")
        run.emit("fatal", {"error": str(e), "resumable": resumable(run.dir)})
        raise


# ---------- V4: UI cilası ----------

async def keep_static_only(project: Path) -> list[str]:
    """UI ajanı sadece app/static'i değiştirebilir: dışındaki değişiklikleri geri alır."""
    reverted = []
    for line in (await git(project, "status", "--porcelain", "-uall")).splitlines():
        path = line[3:].split(" -> ")[-1]
        if path.startswith(STATIC):
            continue
        if line.startswith("??"):
            (project / path).unlink(missing_ok=True)
        else:
            await git(project, "checkout", "HEAD", "--", path)
        reverted.append(path)
    return reverted


def ui_issues(before: dict, after: dict) -> tuple[list[str], list[str]]:
    """(bozan sorunlar, kalan kusurlar): yeni JS hatası veya kırılan demo adımı bozar, yatay taşma sadece kusur."""
    breaking = []
    new_errors = [e for e in after["errors"] if e not in before["errors"]]
    if new_errors:
        breaking.append(f"New browser console errors: {new_errors}")
    if after["completed"] < before["completed"]:
        breaking.append(f"The demo flow broke (it worked before your changes): {after['failed']}")
    flaws = [f"Horizontal scroll on screenshot {v}" for v in after["overflow"]]
    return breaking, flaws


def shot_list(cap: dict) -> str:
    return ", ".join(f"{SHOTS}/{n}" for n in cap["shots"])


async def demo_steps(run: Run, project: Path, plan: Plan) -> list[dict]:
    """Ajan kodu okuyup demoyu tarayıcı eylemlerine çevirir (JSON, kod değil). Olmazsa sadece ilk ekran çekilir."""
    run.emit("ui", {"status": "scripting"})
    try:
        script = await timed_code(run, "build_ui", project, (SKILLS / "demo-scripter.md").read_text() +
                                  f"\n\n## This task\nDemo steps: {json.dumps(plan.demo_steps, ensure_ascii=False)}",
                                  json_schema(DemoScript))
        return clean_steps([s.model_dump() for s in DemoScript.model_validate(script).steps])
    except (RunnerError, ValueError) as e:
        run.emit("error", {"stage": "build_ui", "model": "demo-script", "error": str(e)[:300]})
        return []


async def polish_ui(run: Run, project: Path, plan: Plan) -> dict:
    """Ekran görüntülerine bakan UI ajanı app/static'i iyileştirir. Test kırılır veya JS hatası çıkarsa
    tüm değişiklik geri alınır: cila ürünü asla bozmaz. Ayrı commit, istenirse `git revert` ile geri alınır."""
    if UI_COMMIT in (await git(project, "log", "--format=%s")).splitlines():
        return {"status": "skipped"}  # --resume: zaten yapıldı
    stage = "build_ui"
    run.begin(stage)
    exclude = project / ".git" / "info" / "exclude"
    excluded = exclude.read_text() if exclude.exists() else ""
    if ".hb/" not in excluded:
        exclude.write_text(excluded + "\n.hb/\n")
    lang = {"tr": "Turkish", "en": "English"}[run.load("input").get("lang", "tr")]
    schema = json_schema(CodeReport)

    steps = await demo_steps(run, project, plan)
    run.emit("ui", {"status": "capturing"})
    before = await capture(project, "before", steps)
    run.emit("ui", {"status": "designing"})
    report = await timed_code(run, stage, project, (SKILLS / "ui-designer.md").read_text() + f"""

## This task
Screenshots, in demo order (first page load, then the screens after demo interactions; desktop then mobile):
{shot_list(before)}
Product: {plan.summary}
Demo steps the jury will see: {json.dumps(plan.demo_steps, ensure_ascii=False)}
Problems found by automatic checks: {json.dumps(before["errors"] + [f"Horizontal scroll on {v}" for v in before["overflow"]] + ([f"Demo flow stopped: {before['failed']}"] if before["failed"] else []))}
UI language: {lang}
Improve the UI now, then report.""", schema)

    after, fixed = None, False
    for attempt in range(2):  # 1 cila + en fazla 1 düzeltme
        await keep_static_only(project)
        ok, out = await run_tests(project)
        if ok:
            run.emit("ui", {"status": "checking"})
            after = await capture(project, "after", steps)
            breaking, flaws = ui_issues(before, after)
        else:
            breaking, flaws = [f"Tests fail:\n{out[-3000:]}"], []
        if not breaking and not flaws or attempt == 1:
            break
        fixed = True
        run.emit("ui", {"status": "fixing"})
        await timed_code(run, stage, project,
                         f"Your UI changes in app/static caused these problems. Fix them by editing app/static only, "
                         f"keep the design and keep every element the demo uses. Screenshots of the result: "
                         f"{shot_list(after) if after else 'none (tests fail)'}\nProblems: {json.dumps(breaking + flaws)}",
                         schema)

    if breaking:  # ürünü bozdu → hepsini geri al
        await git(project, "checkout", "HEAD", "--", STATIC)
        await git(project, "clean", "-fdq", "--", STATIC)
        status = "reverted"
    else:
        await git(project, "add", "-A", "--", STATIC)
        await git(project, "commit", "-qm", UI_COMMIT, "--allow-empty")
        status = "done"

    shots_dir = run.dir / "ui"  # arayüz önce/sonra görüntülerini buradan sunar
    shutil.rmtree(shots_dir, ignore_errors=True)
    shots_dir.mkdir()
    shots = []
    for name in before["shots"] + (after["shots"] if after else []):
        shutil.copy(project / SHOTS / name, shots_dir / name)
        shots.append(name)
    result = {"status": status, "summary": report.get("summary", ""), "problems": breaking + flaws,
              "fix_round": fixed, "shots": shots, "demo_steps_run": f"{before['completed']}/{len(steps)}"}
    run.emit("ui", result)
    return result


MAC_LAUNCHER = """#!/bin/zsh
# Çift tıkla: uygulamayı başlatır ve tarayıcıda açar. Kapatmak için bu Terminal penceresini kapat.
cd "${0:A:h}"
URL="http://127.0.0.1:__PORT__"
if curl -s -o /dev/null "$URL"; then open "$URL"; exit 0; fi
if [ ! -x .venv/bin/python ]; then
  echo "İlk açılış: Python ortamı kuruluyor…"
  python3 -m venv .venv && .venv/bin/python -m pip install -q -r requirements.txt || { echo "Kurulum başarısız."; read; exit 1; }
fi
(until curl -s -o /dev/null "$URL"; do sleep 0.5; done; open "$URL") &
echo "Uygulama başlıyor… Kapatmak için bu pencereyi kapat."
.venv/bin/python -m uvicorn app.main:app --port __PORT__
"""

WIN_LAUNCHER = """@echo off
rem Cift tikla: uygulamayi baslatir ve tarayicida acar. Kapatmak icin bu pencereyi kapat.
cd /d "%~dp0"
set URL=http://127.0.0.1:__PORT__
if not exist .venv\\Scripts\\python.exe (
  echo Ilk acilis: Python ortami kuruluyor...
  py -3 -m venv .venv 2>nul || python -m venv .venv
  if not exist .venv\\Scripts\\python.exe (
    echo Python bulunamadi. https://www.python.org adresinden kurun, "Add to PATH" kutusunu isaretleyin.
    pause
    exit /b 1
  )
  .venv\\Scripts\\python -m pip install -q -r requirements.txt
)
start "" /min powershell -NoProfile -Command "while($true){try{Invoke-WebRequest -UseBasicParsing '%URL%' | Out-Null; break}catch{Start-Sleep -Milliseconds 500}}; Start-Process '%URL%'"
echo Uygulama basliyor... Kapatmak icin bu pencereyi kapat.
.venv\\Scripts\\python -m uvicorn app.main:app --port __PORT__
pause
"""


def app_requirements(project: Path, packages: list[str]) -> list[str]:
    """app/ kodunun import ettiği dış paketler. Proje venv'i sistem paketlerini görür (--system-site-packages),
    kodlayıcı onaysız bir paket kullanmış olabilir: başka bilgisayarda kurulum için hepsi yazılmalı."""
    mods = set()
    for f in (project / "app").rglob("*.py"):
        for node in ast.walk(ast.parse(f.read_text())):
            if isinstance(node, ast.Import):
                mods |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                mods.add(node.module.split(".")[0])
    dists = importlib.metadata.packages_distributions()  # modül → pip paketi (PIL → pillow)
    reqs = {"fastapi", "uvicorn", *packages}
    for m in mods - set(sys.stdlib_module_names) - {"app"}:
        reqs.update(dists.get(m, [m]))
    return sorted(reqs, key=str.lower)


async def add_launchers(project: Path, packages: list[str]) -> list[str]:
    """Tek tıkla açma: macOS .command + Windows .bat (+ başka bilgisayarda kurulum için requirements.txt).
    LLM'e değil koda yazdırılır: her projede aynı, test edilmiş dosyalar."""
    req = project / "requirements.txt"  # kodlayıcı yazdıysa eksik paketler eklenir
    lines = req.read_text().splitlines() if req.exists() else []
    have = {l.split("=")[0].split("<")[0].split(">")[0].strip().lower() for l in lines}
    lines += [r for r in app_requirements(project, packages) if r.lower() not in have]
    req.write_text("\n".join(lines) + "\n")
    mac, win = project / "Baslat-Mac.command", project / "Baslat-Windows.bat"
    mac.write_text(MAC_LAUNCHER.replace("__PORT__", str(PORT)))
    mac.chmod(0o755)
    win.write_bytes(WIN_LAUNCHER.replace("__PORT__", str(PORT)).replace("\n", "\r\n").encode())
    await git(project, "add", "-A")
    if (await git(project, "status", "--porcelain")).strip():
        await git(project, "commit", "-qm", "Tek tıkla açma: Baslat-Mac.command ve Baslat-Windows.bat")
    return [mac.name, win.name]


async def finish(run: Run, project: Path, plan: Plan, results: list[dict], packages: list[str]) -> dict:
    try:
        ui = await polish_ui(run, project, plan)
    except Exception as e:  # cila isteğe bağlı: kota/tarayıcı hatası ürünü bitirmeyi engellemez
        await git(project, "checkout", "HEAD", "--", STATIC)
        await git(project, "clean", "-fdq", "--", STATIC)
        run.emit("error", {"stage": "build_ui", "model": "ui", "error": str(e)})
        ui = {"status": "failed", "summary": "", "problems": [str(e)[:300]], "fix_round": False, "shots": []}
    launchers = await add_launchers(project, packages)
    ok, out = await run_tests(project)
    result = {"project": str(project), "tasks": results, "all_tests_ok": ok, "final_test_output": out[-1500:],
              "run_command": f"{RUN_PY} -m uvicorn app.main:app --port {PORT}", "launchers": launchers, "ui": ui,
              "demo_steps": plan.demo_steps}
    run.save("build", result)
    total, stages = run.save_timings("build_timings")
    run.emit("build", result)
    run.emit("done", {"run_dir": run.dir.name, "total": total, "stages": stages})
    return result


# ---------- terminal ----------

async def terminal_approve(kind: str, data: dict) -> dict:
    if kind == "plan":
        print(f"\n📋 PLAN: {data['summary']}")
        for t in data["tasks"]:
            print(f"  {t['id']} {t['title']} — {t['goal']}")
        print(f"  paketler: {data['packages'] or 'yok'} · kodlayıcı: {data['coder']}")
        if not data["sandboxed"]:
            print("  ⚠ Bu sistemde sandbox yok: kodlayıcı yalnızca kendi izin kısıtlarıyla çalışır, "
                  "üretilen testler doğrudan bilgisayarında koşar.")
    else:
        print(f"\n📦 Kurulacak pip paketleri (internetten indirilecek): {data['packages']}")
    ans = (await asyncio.to_thread(input, "Onaylıyor musun? (e = evet / not yaz = düzelt / boş = hayır): ")).strip()
    if ans.lower() in ("e", "evet", "y", "yes"):
        if kind == "plan":
            lvl = (await asyncio.to_thread(
                input, "Düzeltilecek güvenlik bulguları? (high / medium = high+medium / low = hepsi) [medium]: ")).strip()
            return {"ok": True, "note": "", "fix": lvl if lvl in FIX_LEVELS else "medium"}
        return {"ok": True, "note": ""}
    return {"ok": False, "note": ans}


def print_event(event: str, d: dict):
    if event == "stage":
        print(f"\n▶ {d['stage']}")
    elif event == "project":
        print(f"  📁 {d['path']}")
    elif event == "task":
        print(f"  [{d['id']}] {d['title']} — {d['status']}")
    elif event == "test":
        print(f"    {'✓' if d['ok'] else '✗'} testler (deneme {d['attempt']})")
    elif event == "security":
        if not d["reviewed"]:
            print("    🔒 ⚠ güvenlik incelemesi YAPILAMADI")
        else:
            sev = [f["severity"] for f in d["findings"]]
            print(f"    🔒 {len(sev)} bulgu {sev if sev else ''}")
    elif event == "resume":
        print(f"  ↻ devam: biten görevler {d['done']}")
    elif event == "timing":
        print(f"    ⏱ {d['model']} {d['seconds']:.0f}s {'' if d['ok'] else '✗'}")
    elif event == "error":
        print(f"    ✗ {d['stage']} / {d['model']}: {d['error'][:200]}")
    elif event == "fatal":
        print(f"\n✗ DURDU: {d['error']}")
        if d.get("resumable"):
            print("  Kaldığı yerden devam: python -m backend.builder <tur> --resume")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", help="decision.json içeren tur klasörü")
    ap.add_argument("--resume", action="store_true", help="kota dolup durduysa kaldığı yerden devam et")
    a = ap.parse_args()
    run_dir = Path(a.run_dir)
    if not run_dir.exists():
        run_dir = RUNS / a.run_dir
    if not (run_dir / "decision.json").exists():
        raise SystemExit(f"{run_dir}/decision.json yok. Önce bir fikir seç.")
    r = asyncio.run(run_build(run_dir, print_event, terminal_approve, resume=a.resume))
    print(f"\n🏁 {sum(t['tests_ok'] for t in r['tasks'])}/{len(r['tasks'])} görev testleri geçti · "
          f"son test: {'✓' if r['all_tests_ok'] else '✗'}")
    print(f"📁 {r['project']}\n▶ çift tıkla: {r['launchers'][0]} (Windows: {r['launchers'][1]})"
          f"\n▶ ya da: cd {r['project']} && {r['run_command']}")


if __name__ == "__main__":
    main()
