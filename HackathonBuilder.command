#!/bin/zsh
# Çift tıkla: sunucuyu başlatır ve tarayıcıda açar. Kapatmak için bu Terminal penceresini kapat.
cd "${0:A:h}"  # masaüstü kısayolundan açılsa da proje klasörüne gider
URL="http://127.0.0.1:8000"

if curl -s -o /dev/null "$URL"; then
  echo "Zaten çalışıyor, tarayıcıda açılıyor."
  open "$URL"
  exit 0
fi

PY=.venv/bin/python  # Kurulum-Mac.command'ın kurduğu ortam; yoksa sistemdeki python3
[ -x "$PY" ] || PY=python3

# Sunucu hazır olunca tarayıcıyı aç
(until curl -s -o /dev/null "$URL"; do sleep 0.5; done; open "$URL") &
echo "HackathonBuilder başlıyor… Kapatmak için bu pencereyi kapat."
$PY -m backend.app
