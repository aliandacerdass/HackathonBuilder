"""V4 UI cilası için göz: üretilen uygulamayı sandbox'ta açar, Playwright ile ekran görüntüsü alır.

Sunucu `codex sandbox` içinde çalışır (proje dışına yazamaz). Ağ kapalı sandbox'ta port açılamadığı için
ağ açık modda çalışır. Tarayıcı bizim tarafta, sadece localhost'a gider.
"""
import asyncio
import socket
from pathlib import Path

from playwright.async_api import async_playwright

from .pipeline import RunnerError
from .runners import kill_tree

SHOTS = ".hb/ui"  # proje içinde, git dışında (.git/info/exclude)
VIEWPORTS = {"desktop": (1280, 900), "mobile": (390, 844)}
SERVE = ["codex", "sandbox", "-c", 'sandbox_mode="workspace-write"',
         "-c", "sandbox_workspace_write.network_access=true",
         ".venv/bin/python", "-m", "uvicorn", "app.main:app", "--port"]
START_TIMEOUT = 30


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


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


async def capture(project: Path, tag: str) -> dict:
    """Ana sayfayı masaüstü + mobilde çeker → .hb/ui/<tag>-<viewport>.png.
    Kodla kontrol: konsol/sayfa hataları, mobilde yatay taşma."""
    out = project / SHOTS
    out.mkdir(parents=True, exist_ok=True)
    port = free_port()
    proc = await asyncio.create_subprocess_exec(
        *SERVE, str(port), cwd=project, stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL, start_new_session=True)
    errors, overflow = [], []
    try:
        await wait_up(port, proc)
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            try:
                for name, (w, h) in VIEWPORTS.items():
                    page = await browser.new_page(viewport={"width": w, "height": h})
                    page.on("console", lambda m: m.type == "error" and errors.append(m.text[:300]))
                    page.on("pageerror", lambda e: errors.append(str(e)[:300]))
                    await page.goto(f"http://127.0.0.1:{port}/", wait_until="load")
                    await page.wait_for_timeout(1500)  # ilk fetch'ler dolsun
                    await page.screenshot(path=out / f"{tag}-{name}.png", full_page=True)
                    if await page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1"):
                        overflow.append(name)
                    await page.close()
            finally:
                await browser.close()
    finally:
        kill_tree(proc)
        await proc.wait()
    return {"errors": sorted(set(errors)), "overflow": overflow,
            "shots": [f"{tag}-{n}.png" for n in VIEWPORTS]}
