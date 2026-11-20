@echo off
rem Cift tikla: HackathonBuilder'i baslatir ve tarayicida acar. Kapatmak icin bu pencereyi kapatin.
rem Bu dosya Windows'ta henuz denenmedi.
cd /d "%~dp0"
set URL=http://127.0.0.1:8000
if not exist .venv\Scripts\python.exe (
  echo Once Kurulum-Windows.bat dosyasina cift tiklayin.
  pause
  exit /b 1
)
set PYTHONUTF8=1
start "" /min powershell -NoProfile -Command "while($true){try{Invoke-WebRequest -UseBasicParsing '%URL%' | Out-Null; break}catch{Start-Sleep -Milliseconds 500}}; Start-Process '%URL%'"
echo HackathonBuilder basliyor... Kapatmak icin bu pencereyi kapatin.
.venv\Scripts\python -m backend.app
pause
