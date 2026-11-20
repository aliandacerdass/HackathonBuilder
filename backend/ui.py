"""V4 UI cilası için göz: üretilen uygulamayı sandbox'ta açar, Playwright ile ekran görüntüsü alır.

Sunucu sandbox içinde çalışır (proje dışına yazamaz; Windows'ta sandbox yok). Ağ kapalı sandbox'ta port
açılamadığı için ağ açık modda çalışır. Tarayıcı bizim tarafta, sadece localhost'a gider.

Demo adımları (DemoScript) LLM'den JSON olarak gelir, kod değildir: sadece sabit eylemler (click, fill, select,
upload, wait) uygulanır. Aynı adımlar cila öncesi ve sonrası koşar: önce çalışan adım sonra kırılırsa cila bozmuştur.
"""
import asyncio
import socket
from pathlib import Path

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright

from .pipeline import RunnerError
from .runners import PROC_GROUP, kill_tree, sandbox, venv_python

SHOTS = ".hb/ui"  # proje içinde, git dışında (.git/info/exclude)
VIEWPORTS = {"desktop": (1280, 900), "mobile": (390, 844)}
START_TIMEOUT = 30
ACTIONS = {"click", "fill", "select", "upload", "wait"}
MAX_STEPS, MAX_SHOTS = 15, 3
STEP_TIMEOUT = 5000  # ms


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def clean_steps(steps: list[dict]) -> list[dict]:
    """Bilinmeyen eylemleri at, adım ve ekran görüntüsü sayısını sınırla."""
    out, shots = [], 0
    for s in steps:
        if s["action"] not in ACTIONS or (s["action"] != "wait" and not s["selector"].strip()):
            continue
        shot = s["screenshot"] and shots < MAX_SHOTS
        shots += shot
        out.append({**s, "screenshot": shot})
    return out[:MAX_STEPS]


async def wait_up(port: int, proc) -> None:
    for _ in range(START_TIMEOUT * 4):
        if proc.returncode is not None:
            raise RunnerError("uygulama açılmadı (sunucu kapandı)")
        try:
            _, w = await asyncio.open_connection("127.0.0.1", port)
            w.close()
            return
        except OSError:
            await asyncio.sleep(0.25)
    raise RunnerError(f"uygulama {START_TIMEOUT}s içinde açılmadı")


async def run_step(page, project: Path, s: dict) -> None:
    a = s["action"]
    if a == "wait":
        try:
            ms = int(s["value"])
        except ValueError:
            ms = 1000
        await page.wait_for_timeout(max(0, min(ms, 5000)))
        return
    loc = page.locator(s["selector"]).first
    if a == "click":
        await loc.click(timeout=STEP_TIMEOUT)
    elif a == "fill":
        await loc.fill(s["value"], timeout=STEP_TIMEOUT)
    elif a == "select":
        await loc.select_option(s["value"], timeout=STEP_TIMEOUT)
    elif a == "upload":  # sadece proje içindeki dosyalar
        f = (project / s["value"]).resolve()
        if not f.is_relative_to(project.resolve()) or not f.is_file():
            raise RunnerError(f"yüklenecek dosya proje içinde yok: {s['value']}")
        await loc.set_input_files(f, timeout=STEP_TIMEOUT)
    await page.wait_for_timeout(800)  # tepki (fetch, çizim) otursun


async def capture(project: Path, tag: str, steps: list[dict] = ()) -> dict:
    """Her viewport'ta: ilk açılışı çek → demo adımlarını uygula, işaretli adımlardan sonra çek.
    → .hb/ui/<tag>-<viewport>.png, <tag>-<viewport>-<n>.png
    Kodla kontrol: konsol/sayfa hataları, her görüntüde yatay taşma, kaç adımın çalıştığı."""
    out = project / SHOTS
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob(f"{tag}-*.png"):
        old.unlink()
    port = free_port()
    serve = [venv_python(project), "-m", "uvicorn", "app.main:app", "--port", str(port)]
    proc = await asyncio.create_subprocess_exec(
        *sandbox(serve, project, network=True), cwd=project, stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL, **PROC_GROUP)
    errors, overflow, shots, completed, failed = [], [], [], len(steps), None
    try:
        await wait_up(port, proc)
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            try:
                for vp, (w, h) in VIEWPORTS.items():
                    page = await browser.new_page(viewport={"width": w, "height": h})
                    page.on("console", lambda m: m.type == "error" and errors.append(m.text[:300]))
                    page.on("pageerror", lambda e: errors.append(str(e)[:300]))

                    async def shoot(name: str):
                        await page.screenshot(path=out / f"{name}.png", full_page=True)
                        shots.append(f"{name}.png")
                        if await page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1"):
                            overflow.append(name.removeprefix(f"{tag}-"))

                    await page.goto(f"http://127.0.0.1:{port}/", wait_until="load")
                    await page.wait_for_timeout(1500)  # ilk fetch'ler dolsun
                    await shoot(f"{tag}-{vp}")
                    n = 0
                    for i, s in enumerate(steps):
                        try:
                            await run_step(page, project, s)
                        except (PlaywrightError, RunnerError) as e:
                            if i < completed:
                                completed = i
                                failed = f"step {i + 1} ({s['action']} {s['selector']}) on {vp}: " \
                                         f"{str(e).splitlines()[0][:200]}"
                            break
                        if s["screenshot"]:
                            n += 1
                            await shoot(f"{tag}-{vp}-{n}")
                    await page.close()
            finally:
                await browser.close()
    finally:
        kill_tree(proc)
        await proc.wait()
    return {"errors": sorted(set(errors)), "overflow": overflow, "shots": shots,
            "completed": completed, "failed": failed}
