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


async def _run(cmd: list[str], cwd: Path) -> str:
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
        out, err = await asyncio.wait_for(proc.communicate(), TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        raise RunnerError(f"{cmd[0]} {TIMEOUT}s içinde cevap vermedi")
    if proc.returncode != 0:
        raise RunnerError(f"{cmd[0]} çıkış kodu {proc.returncode}: {err.decode()[-300:]}")
    return out.decode()


def _with_model(cmd: list[str], model: str) -> list[str]:
    name = MODEL_OVERRIDE[model]
    return cmd + ["--model", name] if name else cmd


async def _claude(prompt: str, schema: dict, wd: Path) -> dict:
    cmd = _with_model(["claude", "-p", "--output-format", "json", "--tools", "",
                       "--json-schema", json.dumps(schema)], "claude")
    data = json.loads(await _run(cmd + [prompt], wd))
    if data.get("is_error"):
        raise RunnerError(f"claude: {data.get('result')}")
    return data["structured_output"]


async def _gpt(prompt: str, schema: dict, wd: Path) -> dict:
    (wd / "schema.json").write_text(json.dumps(schema))
    cmd = _with_model(["codex", "exec", "--skip-git-repo-check", "-s", "read-only",
                       "--output-schema", "schema.json", "-o", "out.json"], "gpt")
    await _run(cmd + [prompt], wd)
    return json.loads((wd / "out.json").read_text())


async def _gemini(prompt: str, schema: dict, wd: Path) -> dict:
    (wd / "schema.json").write_text(json.dumps(schema))
    # agy: tüm bayraklar --print'ten ÖNCE
    cmd = _with_model(["agy", "--output-format", "json", "--json-schema", "schema.json",
                       "--print-timeout", f"{TIMEOUT}s"], "gemini")
    data = json.loads(await _run(cmd + ["--print", prompt], wd))
    if data.get("status") != "SUCCESS":
        raise RunnerError(f"agy: {data.get('status')}")
    return data["structured_output"]


RUNNERS = {"claude": _claude, "gpt": _gpt, "gemini": _gemini}


async def ask(model: str, prompt: str, schema: dict, retries: int = 1) -> dict:
    """Modele sorar, şemaya uygun dict döner. Başarısızsa `retries` kez tekrar dener."""
    last = None
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    for _ in range(retries + 1):
        # Her çağrıya boş klasör: CLI proje dosyalarını görmez (temiz context)
        with tempfile.TemporaryDirectory(dir=WORK_ROOT) as wd:
            try:
                return await RUNNERS[model](prompt, schema, Path(wd))
            except (RunnerError, json.JSONDecodeError, KeyError) as e:
                last = e
    raise RunnerError(f"{model}: {last}")


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
    print("Kullanım: python -m backend.runners --smoke")
