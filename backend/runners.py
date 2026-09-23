"""3 abonelik CLI'ını (claude, codex, agy) tek arayüzle çağırır.

    result = await ask("claude", "prompt...", schema)   # -> dict (şemaya uygun)

API key yok: her CLI kullanıcının kendi abonelik login'ini kullanır.
"""
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

TIMEOUT = 300  # saniye, tek çağrı için
CODE_TIMEOUT = 900  # kodlama görevi (dosya yazma + test) daha uzun sürer

# CLI'lar bu klasörde çalışır. Proje DIŞINDA olmalı (yoksa CLAUDE.md/AGENTS.md'yi okurlar).
# /var/folders (sistem temp) olmaz: agy orada "503 Eligibility check failed" veriyor.
WORK_ROOT = Path.home() / ".cache" / "hackathonbuilder"

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


async def _run(cmd: list[str], cwd: Path, timeout: int = TIMEOUT) -> str:
    """Komutu çalıştırır, stdout döner. Hata/timeout → RunnerError."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=cwd,
            stdin=asyncio.subprocess.DEVNULL,  # yoksa codex/claude stdin bekler
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        raise RunnerError(f"{cmd[0]} kurulu değil")
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise RunnerTimeout(f"{cmd[0]} {timeout}s içinde cevap vermedi")
    if proc.returncode != 0:
        raise RunnerError(f"{cmd[0]} çıkış kodu {proc.returncode}: {err.decode()[-300:]}")
    return out.decode()


def _with_model(cmd: list[str], model: str) -> list[str]:
    name = MODEL_OVERRIDE[model]
    return cmd + ["--model", name] if name else cmd


async def _claude(prompt: str, schema: dict, wd: Path, web: bool) -> dict:
    # web=True: SADECE arama/okuma araçları (dosya yazma, komut çalıştırma yok)
    tools = ["--tools", "WebSearch,WebFetch", "--allowedTools", "WebSearch", "WebFetch"] if web else ["--tools", ""]
    cmd = _with_model(["claude", "-p", "--output-format", "json", *tools,
                       "--json-schema", json.dumps(schema)], "claude")
    data = json.loads(await _run(cmd + [prompt], wd))
    if data.get("is_error"):
        raise RunnerError(f"claude: {data.get('result')}")
    return data["structured_output"]


async def _gpt(prompt: str, schema: dict, wd: Path, web: bool) -> dict:
    (wd / "schema.json").write_text(json.dumps(schema))
    search = ["--search"] if web else []  # codex'te --search, exec'ten ÖNCE gelir
    cmd = _with_model(["codex", *search, "exec", "--skip-git-repo-check", "-s", "read-only",
                       "--output-schema", "schema.json", "-o", "out.json"], "gpt")
    await _run(cmd + [prompt], wd)
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


async def code(project_dir: Path, prompt: str, schema: dict) -> dict:
    """Codex'e proje klasöründe kod yazdırır ve çalıştırır.

    Güvenlik: `-s workspace-write` = işletim sistemi sandbox'ı. Sadece project_dir'e yazabilir,
    internet yok. Claude Code bu iş için KULLANILMAZ (Write aracı klasör dışına yazabiliyor).
    Codex, project_dir/AGENTS.md'deki kuralları kendiliğinden okur.
    Tekrar denenmez: yarım kalan bir kodlama görevini körlemesine tekrarlamak dosyaları bozabilir.
    """
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=WORK_ROOT) as wd:  # şema/çıktı dosyaları projeyi kirletmesin
        wd = Path(wd)
        (wd / "schema.json").write_text(json.dumps(schema))
        cmd = _with_model(["codex", "exec", "--skip-git-repo-check", "-s", "workspace-write",
                           "-C", str(project_dir), "--output-schema", str(wd / "schema.json"),
                           "-o", str(wd / "out.json")], "gpt")
        await _run(cmd + [prompt], project_dir, CODE_TIMEOUT)
        try:
            return json.loads((wd / "out.json").read_text())
        except (FileNotFoundError, json.JSONDecodeError) as e:
            raise RunnerError(f"codex: rapor okunamadı: {e}")


async def _code_smoke() -> int:
    """Kodlama modu testi: dosya yazar mı, test çalıştırır mı, klasör dışına yazabilir mi?"""
    import subprocess
    base = WORK_ROOT / "code-smoke"
    project = base / "project"
    subprocess.run(["rm", "-rf", str(base)])
    project.mkdir(parents=True)
    schema = {"type": "object", "additionalProperties": False, "required": ["files", "tests_passed", "summary"],
              "properties": {"files": {"type": "array", "items": {"type": "string"}},
                             "tests_passed": {"type": "boolean"}, "summary": {"type": "string"}}}
    prompt = ("Create calc.py with add(a, b) and test_calc.py with 2 unittest tests, then run "
              "`python3 -m unittest -v`. Also try to create ../outside.txt and report in summary if it worked.")
    t = time.time()
    r = await code(project, prompt, schema)
    # Ajanın kendi raporuna güvenme: testi biz çalıştırırız
    own = subprocess.run(["python3", "-m", "unittest"], cwd=project, capture_output=True, text=True)
    checks = [
        ("dosyalar yazıldı", (project / "calc.py").exists() and (project / "test_calc.py").exists()),
        ("testler geçti (bizim çalıştırmamız)", own.returncode == 0),
        ("klasör dışına yazamadı", not (base / "outside.txt").exists()),
    ]
    for name, ok in checks:
        print(f"{'✓' if ok else '✗'} {name}")
    print(f"ajan raporu: tests_passed={r['tests_passed']} · {r['summary'][:150]}")
    print(f"{time.time() - t:.1f}s · {sum(ok for _, ok in checks)}/{len(checks)}")
    subprocess.run(["rm", "-rf", str(base)])
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
