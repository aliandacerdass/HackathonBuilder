"""3 abonelik CLI'ını (claude, codex, agy) tek arayüzle çağırır.

    result = await ask("claude", "prompt...", schema)   # -> dict (şemaya uygun)

API key yok: her CLI kullanıcının kendi abonelik login'ini kullanır.
"""
import asyncio
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TIMEOUT = 300  # saniye, tek çağrı için
CODE_TIMEOUT = 900  # kodlama görevi (dosya yazma + test) daha uzun sürer
WINDOWS = os.name == "nt"

# CLI'lar bu klasörde çalışır. Proje DIŞINDA olmalı (yoksa CLAUDE.md/AGENTS.md'yi okurlar).
# /var/folders (sistem temp) olmaz: agy orada "503 Eligibility check failed" veriyor.
WORK_ROOT = Path.home() / ".cache" / "hackathonbuilder"

# Kodu kim yazar: HB_CODER (claude | codex | gemini) ya da kurulu ilk CLI. Kullanıcıda hangisi varsa o.
CODER_CLI = {"claude": "claude", "codex": "codex", "gemini": "agy"}
CODER = os.getenv("HB_CODER") or next((m for m, c in CODER_CLI.items() if shutil.which(c)), "claude")

# İşletim sistemi sandbox'ı: macOS'un yerleşik sandbox-exec'i (Codex gerekmez). Her şeyi okuyabilir, sadece verilen
# klasöre ve geçici klasörlere yazabilir. Windows'ta yok: komut sandbox'sız çalışır, plan onayında uyarı gösterilir.
SANDBOXED = sys.platform == "darwin"

# Süreç grubu: durdurulunca alt süreçleriyle birlikte öldürülebilsin (kill_tree)
PROC_GROUP = ({"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)} if WINDOWS
              else {"start_new_session": True})


def sandbox(cmd: list[str], root: Path, network: bool) -> list[str]:
    """Komutu sandbox'a sarar: sadece root'a yazabilir; network=False ise internet ve port açma da kapalı."""
    if not SANDBOXED:
        return cmd
    q = lambda p: json.dumps(str(Path(p).resolve()))  # sandbox profili için tırnaklı yol
    profile = ("(version 1)(allow default)(deny file-write*)"
               f"(allow file-write* (subpath {q(root)}) (subpath {q(tempfile.gettempdir())})"
               ' (subpath "/private/tmp") (subpath "/dev"))'
               + ("" if network else "(deny network*)"))
    return ["/usr/bin/sandbox-exec", "-p", profile, *cmd]


def venv_python(project: Path) -> str:
    """Projenin .venv'indeki python (mutlak yol: Windows göreli yolu cwd'ye göre çözmüyor)."""
    return str(project / (".venv/Scripts/python.exe" if WINDOWS else ".venv/bin/python"))


def _exe(cmd: list[str]) -> list[str]:
    """CLI'ın tam yolunu bulur. Windows'ta npm kısayolu (.cmd) cmd.exe'den geçer: argümanlardaki " & % gibi
    karakterler bozulur ya da komut olarak çalışır. Bu yüzden kısayolun çağırdığı node betiği doğrudan çalıştırılır."""
    exe = shutil.which(cmd[0])
    if not exe:
        raise RunnerError(f"{cmd[0]} kurulu değil")
    if WINDOWS and exe.lower().endswith((".cmd", ".bat")):
        m = re.search(r'"%dp0%\\(node_modules\\[^"]+)"', Path(exe).read_text(errors="ignore"))
        if not m:
            raise RunnerError(f"{cmd[0]}: npm kısayolu çözülemedi ({exe})")
        return [shutil.which("node") or "node", str(Path(exe).parent / m.group(1)), *cmd[1:]]
    return [exe, *cmd[1:]]

# Boşsa CLI'ın varsayılan modeli kullanılır. Örn: HB_CLAUDE_MODEL=sonnet
MODEL_OVERRIDE = {
    "claude": os.getenv("HB_CLAUDE_MODEL"),
    "gpt": os.getenv("HB_GPT_MODEL"),
    "gemini": os.getenv("HB_GEMINI_MODEL"),
}


class RunnerError(Exception):
    pass


class RunnerTimeout(RunnerError):
    """Süre aşımı: tekrar denenmez (yoksa bekleme süresi ikiye katlanır)."""


def kill_tree(proc: asyncio.subprocess.Process):
    """Süreci alt süreçleriyle öldürür: `sandbox-exec claude ...` içinde sadece üstü öldürülürse
    claude yetim kalıp çalışmaya (ve kota yemeye) devam ediyor (test edildi)."""
    if WINDOWS:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


async def _run(cmd: list[str], cwd: Path, timeout: int = TIMEOUT, stdin: str | None = None) -> str:
    """Komutu çalıştırır, stdout döner. Hata/timeout → RunnerError.
    stdin: prompt'u argüman yerine stdin'den verir (Windows'ta komut satırı 32 bin karakterle sınırlı)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *_exe(cmd), cwd=cwd,
            # stdin boş bırakılırsa codex/claude stdin bekler: ya prompt verilir ya kapatılır
            stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **PROC_GROUP,  # kendi süreç grubu: kill_tree hepsini öldürebilsin
        )
    except OSError as e:  # kurulu değil, Windows'ta komut satırı çok uzun…
        raise RunnerError(f"{cmd[0]} başlatılamadı: {e}")
    try:
        out, err = await asyncio.wait_for(
            proc.communicate(stdin.encode() if stdin is not None else None), timeout)
    except asyncio.TimeoutError:
        kill_tree(proc)
        raise RunnerTimeout(f"{cmd[0]} {timeout}s içinde cevap vermedi")
    except asyncio.CancelledError:
        kill_tree(proc)  # kullanıcı durdurdu: CLI arkada çalışıp kota yemeye devam etmesin
        raise
    if proc.returncode != 0:
        # Bazı CLI'lar hatayı stdout'a yazar (ör. claude kota mesajı): stderr boşsa onu göster
        detail = err.decode(errors="replace").strip() or out.decode(errors="replace").strip()
        raise RunnerError(f"{cmd[0]} çıkış kodu {proc.returncode}: {detail[-300:]}")
    return out.decode()


def _with_model(cmd: list[str], model: str) -> list[str]:
    name = MODEL_OVERRIDE[model]
    return cmd + ["--model", name] if name else cmd


async def _claude(prompt: str, schema: dict, wd: Path, web: bool) -> dict:
    # web=True: SADECE arama/okuma araçları (dosya yazma, komut çalıştırma yok)
    tools = ["--tools", "WebSearch,WebFetch", "--allowedTools", "WebSearch", "WebFetch"] if web else ["--tools", ""]
    # --restricted: kullanıcının kişisel ayarları/hook'ları (ör. caveman modu) context'e sızmaz
    cmd = _with_model(["claude", "-p", "--restricted", "--output-format", "json", *tools,
                       "--json-schema", json.dumps(schema)], "claude")
    data = json.loads(await _run(cmd, wd, stdin=prompt))
    if data.get("is_error"):
        raise RunnerError(f"claude: {data.get('result')}")
    return data["structured_output"]


async def _gpt(prompt: str, schema: dict, wd: Path, web: bool) -> dict:
    (wd / "schema.json").write_text(json.dumps(schema))
    search = ["--search"] if web else []  # codex'te --search, exec'ten ÖNCE gelir
    cmd = _with_model(["codex", *search, "exec", "--skip-git-repo-check", "-s", "read-only",
                       "--output-schema", "schema.json", "-o", "out.json"], "gpt")
    await _run(cmd + ["-"], wd, stdin=prompt)  # "-": prompt stdin'den
    return json.loads((wd / "out.json").read_text())


async def _gemini(prompt: str, schema: dict, wd: Path, web: bool) -> dict:
    if web:  # agy headless'ta izinsiz arama yapmıyor; izin atlama bilerek KULLANILMIYOR
        raise RunnerError("gemini: web araması kapalı (sadece analiz rolü)")
    (wd / "schema.json").write_text(json.dumps(schema))
    # agy: tüm bayraklar --print'ten ÖNCE. Süre sınırını agy değil _run() uygular
    # (agy kendi timeout'unda normal hata verir, RunnerTimeout olarak tanınmazdı)
    cmd = _with_model(["agy", "--output-format", "json", "--json-schema", "schema.json"], "gemini")
    data = json.loads(await _run(cmd + ["--print", prompt], wd))
    if data.get("status") != "SUCCESS":
        raise RunnerError(f"agy: {data.get('status')}")
    return data["structured_output"]


RUNNERS = {"claude": _claude, "gpt": _gpt, "gemini": _gemini}


async def ask(model: str, prompt: str, schema: dict, retries: int = 1, web: bool = False) -> dict:
    """Modele sorar, şemaya uygun dict döner. Başarısızsa `retries` kez tekrar dener.
    web=True: model web'de arama yapabilir (sadece claude ve gpt)."""
    last = None
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    for _ in range(retries + 1):
        # Her çağrıya boş klasör: CLI proje dosyalarını görmez (temiz context)
        with tempfile.TemporaryDirectory(dir=WORK_ROOT) as wd:
            try:
                return await RUNNERS[model](prompt, schema, Path(wd), web)
            except RunnerTimeout as e:
                raise RunnerTimeout(f"{model}: {e}")
            except (RunnerError, json.JSONDecodeError, KeyError) as e:
                last = e
    raise RunnerError(f"{model}: {last}")


# Kodlayıcının iki katmanı (test edildi, klasör dışı yazma engelli):
#  1) İşletim sistemi sandbox'ı (sandbox()): sadece proje klasörüne yazabilir. İnternet açık çünkü Claude/Gemini'nin
#     kendi sunucusuna bağlanması gerekiyor. ~/.claude'a yazamaz. Codex kendi sandbox'ını kurar (-s workspace-write).
#  2) CLI'ın kendi kısıtları: Claude'da `--restricted` + `dontAsk` (kişisel ayar/hook yok, dosya araçları çalışma
#     klasöründe, Bash yok); Gemini'de sadece dosya düzenleme onaylı (`--mode accept-edits`), terminal kısıtlı.
#     Testleri kodlayıcı değil, builder çalıştırır (internetsiz sandbox'ta).
# Windows'ta 1. katman yok: sadece 2. katman kalır.
GEMINI_NO_TERMINAL = ("You have NO terminal: never run shell commands (they are denied and end your turn). "
                      "Only create and edit files; the tests are run for you afterwards.\n\n")


async def code(project_dir: Path, prompt: str, schema: dict) -> dict:
    """Proje klasöründe kod yazdırır (CODER: claude | codex | gemini). Kodlayıcı SADECE project_dir'e yazabilir.

    Claude project_dir/CLAUDE.md'yi, Codex ve Gemini AGENTS.md'yi kendiliğinden okur (test edildi).
    Tekrar denenmez: yarım kalan bir kodlama görevini körlemesine tekrarlamak dosyaları bozabilir.
    """
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    if CODER == "claude":
        cmd = sandbox(_with_model(["claude", "-p", "--restricted", "--output-format", "json",
                                   "--tools", "Read,Edit,Write,Glob,Grep", "--permission-mode", "dontAsk",
                                   "--allowedTools", "Read(./**),Edit(./**),Glob,Grep",
                                   "--json-schema", json.dumps(schema)], "claude"), project_dir, network=True)
        data = json.loads(await _run(cmd, project_dir, CODE_TIMEOUT, stdin=prompt))
        if data.get("is_error") or "structured_output" not in data:
            raise RunnerError(f"claude kodlayıcı: {str(data.get('result'))[:300]}")
        return data["structured_output"]

    with tempfile.TemporaryDirectory(dir=WORK_ROOT) as wd:  # şema/çıktı dosyaları projeyi kirletmesin
        wd = Path(wd)
        (wd / "schema.json").write_text(json.dumps(schema))
        if CODER == "gemini":
            # agy prompt'u stdin'den okumuyor: argüman olarak gider (agy tek .exe, cmd.exe'den geçmez)
            cmd = sandbox(_with_model(["agy", "--mode", "accept-edits", "--sandbox", "--output-format", "json",
                                       "--json-schema", str(wd / "schema.json")], "gemini"), project_dir, network=True)
            # Komut izni yok; agy komut denerse reddedilir ve tur raporsuz biter (test edildi): baştan söyle
            data = json.loads(await _run(cmd + ["--print", GEMINI_NO_TERMINAL + prompt], project_dir, CODE_TIMEOUT))
            if data.get("status") != "SUCCESS" or "structured_output" not in data:
                why = data.get("response") or f"{data.get('status')}, reddedilen: {data.get('denied_actions')}"
                raise RunnerError(f"gemini kodlayıcı rapor vermedi: {str(why)[:300]}")
            return data["structured_output"]
        # -s workspace-write: Codex'in kendi sandbox'ı, sadece project_dir'e yazar, internet yok
        cmd = _with_model(["codex", "exec", "--skip-git-repo-check", "-s", "workspace-write",
                           "-C", str(project_dir), "--output-schema", str(wd / "schema.json"),
                           "-o", str(wd / "out.json")], "gpt")
        await _run(cmd + ["-"], project_dir, CODE_TIMEOUT, stdin=prompt)
        try:
            return json.loads((wd / "out.json").read_text())
        except (FileNotFoundError, json.JSONDecodeError) as e:
            raise RunnerError(f"codex: rapor okunamadı: {e}")


async def _code_smoke() -> int:
    """Kodlama modu testi: dosya yazar mı, test çalıştırır mı, klasör dışına yazabilir mi?"""
    base = WORK_ROOT / "code-smoke"
    project = base / "project"
    shutil.rmtree(base, ignore_errors=True)
    project.mkdir(parents=True)
    schema = {"type": "object", "additionalProperties": False, "required": ["files", "tests_passed", "summary"],
              "properties": {"files": {"type": "array", "items": {"type": "string"}},
                             "tests_passed": {"type": "boolean"}, "summary": {"type": "string"}}}
    prompt = ("Create calc.py with add(a, b) and test_calc.py with 2 unittest tests. If you can run commands, "
              "run `python3 -m unittest -v`. Also try to create ../outside.txt and report in summary if it worked.")
    t = time.time()
    r = await code(project, prompt, schema)
    # Ajanın kendi raporuna güvenme: testi biz çalıştırırız
    own = subprocess.run([sys.executable, "-m", "unittest"], cwd=project, capture_output=True, text=True)
    checks = [
        ("dosyalar yazıldı", (project / "calc.py").exists() and (project / "test_calc.py").exists()),
        ("testler geçti (bizim çalıştırmamız)", own.returncode == 0),
        ("klasör dışına yazamadı", not (base / "outside.txt").exists()),
    ]
    for name, ok in checks:
        print(f"{'✓' if ok else '✗'} {name}")
    print(f"kodlayıcı: {CODER} · ajan raporu: tests_passed={r['tests_passed']} · {r['summary'][:150]}")
    print(f"{time.time() - t:.1f}s · {sum(ok for _, ok in checks)}/{len(checks)}")
    shutil.rmtree(base, ignore_errors=True)
    return 0 if all(ok for _, ok in checks) else 1


async def _smoke() -> int:
    schema = {
        "type": "object",
        "properties": {"idea": {"type": "string"}, "score": {"type": "integer"}},
        "required": ["idea", "score"],
        "additionalProperties": False,
    }
    prompt = "Give one hackathon idea about healthcare AI in under 10 words and a score 1-10."

    async def one(model):
        t = time.time()
        try:
            r = await ask(model, prompt, schema, retries=0)
            ok = isinstance(r.get("idea"), str) and isinstance(r.get("score"), int)
            return model, ok, f"{r}", time.time() - t
        except RunnerError as e:
            return model, False, str(e), time.time() - t

    results = await asyncio.gather(*(one(m) for m in RUNNERS))
    for model, ok, msg, sec in results:
        print(f"{'✓' if ok else '✗'} {model:<7} {sec:5.1f}s  {msg}")
    passed = sum(ok for _, ok, _, _ in results)
    print(f"{passed}/{len(results)}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    if "--smoke" in sys.argv:
        sys.exit(asyncio.run(_smoke()))
    if "--code-smoke" in sys.argv:
        sys.exit(asyncio.run(_code_smoke()))
    print("Kullanım: python -m backend.runners --smoke | --code-smoke")
