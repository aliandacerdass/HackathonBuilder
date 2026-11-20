@echo off
rem Cift tikla: HackathonBuilder'i kurar (Python ortami + paketler + tarayici) ve model CLI'larini kontrol eder.
rem Tekrar calistirmak guvenli: kurulu olani atlar. Bu dosya Windows'ta henuz denenmedi.
cd /d "%~dp0"
echo == HackathonBuilder kurulumu
echo.

rem 1) Python 3.10+
set "PY="
py -3 -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1 && set "PY=py -3"
if not defined PY (
  python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo [X] Python 3.10 veya ustu bulunamadi. python.org'dan kurun, kurulumda "Add python.exe to PATH" kutusunu isaretleyin.
  start "" https://www.python.org/downloads/
  pause
  exit /b 1
)
echo [OK] Python bulundu: %PY%

rem 2) Kendi Python ortami (.venv) + paketler
if not exist .venv\Scripts\python.exe %PY% -m venv .venv
if not exist .venv\Scripts\python.exe (
  echo [X] Python ortami kurulamadi.
  pause
  exit /b 1
)
.venv\Scripts\python -m pip install -q --upgrade pip
.venv\Scripts\python -m pip install -q -r requirements.txt
if errorlevel 1 (
  echo [X] Paketler kurulamadi. Internet baglantinizi kontrol edin.
  pause
  exit /b 1
)
echo [OK] Paketler kuruldu

rem 3) UI cilasi icin ekran goruntusu tarayicisi (istege bagli)
set "ANS="
set /p ANS=UI cilasi icin Chromium indirilsin mi? Yaklasik 200 MB yer kaplar. [E/h]
if /i "%ANS%"=="h" (
  echo - Chromium atlandi: UI cilasi adimi calismaz, gerisi calisir.
) else (
  .venv\Scripts\python -m playwright install --only-shell chromium
)

rem 4) Model CLI'lari: en az biri gerekli, hangisi varsa o kullanilir
echo.
echo == Model CLI'lari (en az biri gerekli)
set N=0
where claude >nul 2>&1 && (echo [OK] Claude Code& set /a N+=1 >nul) || echo [-] Claude Code yok: https://docs.anthropic.com/en/docs/claude-code
where codex >nul 2>&1 && (echo [OK] Codex CLI - GPT& set /a N+=1 >nul) || echo [-] Codex CLI yok: https://github.com/openai/codex
where agy >nul 2>&1 && (echo [OK] Antigravity CLI - Gemini& set /a N+=1 >nul) || echo [-] Antigravity CLI yok: https://antigravity.google
where git >nul 2>&1 || echo [!] Git yok: kodlama asamasi icin gerekli: https://git-scm.com/download/win

if %N%==0 (
  echo.
  echo [X] Hicbir model CLI'i yok. Birini kurup kendi hesabinizla giris yapin, sonra bu dosyayi tekrar calistirin.
  pause
  exit /b 1
)

set "ANS="
set /p ANS=Giris yapilmis mi diye modellere kisa bir soru sorayim mi? Biraz kota harcar. [E/h]
if /i not "%ANS%"=="h" .venv\Scripts\python -m backend.runners --smoke

echo.
echo [OK] Kurulum bitti. Baslatmak icin HackathonBuilder.bat dosyasina cift tiklayin.
echo Not: Windows'ta sandbox yok. Kodlama asamasi uretilen kodu dogrudan bilgisayarinizda calistirir.
pause
