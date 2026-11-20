#!/bin/zsh
# Çift tıkla: HackathonBuilder'ı kurar (Python ortamı + paketler + tarayıcı) ve model CLI'larını kontrol eder.
# Tekrar çalıştırmak güvenli: kurulu olanı atlar.
cd "${0:A:h}"
echo "== HackathonBuilder kurulumu\n"

# 1) Python 3.10+ (macOS'un hazır python3'ü 3.9: yetmez)
PY=""
for c in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v $c >/dev/null && $c -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
    PY=$c; break
  fi
done
if [ -z "$PY" ]; then
  echo "✗ Python 3.10 veya üstü bulunamadı. python.org'dan kurup bu dosyayı tekrar çalıştır."
  open "https://www.python.org/downloads/"
  read "?Kapatmak için Enter'a bas."; exit 1
fi
echo "✓ $($PY --version)"

# 2) Kendi Python ortamı (.venv) + paketler: sistem Python'una dokunmaz
if [ ! -x .venv/bin/python ]; then
  $PY -m venv .venv || { echo "✗ Python ortamı kurulamadı."; read "?Enter'a bas."; exit 1; }
fi
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -r requirements.txt \
  || { echo "✗ Paketler kurulamadı. İnternet bağlantını kontrol et."; read "?Enter'a bas."; exit 1; }
echo "✓ Paketler kuruldu"

# 3) UI cilası için ekran görüntüsü tarayıcısı (isteğe bağlı)
read "ans?UI cilası için Chromium indirilsin mi? Yaklaşık 200 MB yer kaplar. [E/h] "
if [[ "$ans" == [hHnN]* ]]; then
  echo "– Chromium atlandı: UI cilası adımı çalışmaz, gerisi çalışır."
else
  .venv/bin/python -m playwright install --only-shell chromium && echo "✓ Chromium"
fi

# 4) Model CLI'ları: en az biri gerekli, hangisi varsa o kullanılır
echo "\n== Model CLI'ları (en az biri gerekli)"
n=0
check() {  # $1 komut, $2 ad, $3 kurulum sayfası
  if command -v $1 >/dev/null; then echo "✓ $2"; n=$((n + 1)); else echo "– $2 yok: $3"; fi
}
check claude "Claude Code" "https://docs.anthropic.com/en/docs/claude-code"
check codex "Codex CLI (GPT)" "https://github.com/openai/codex"
check agy "Antigravity CLI (Gemini)" "https://antigravity.google"
command -v git >/dev/null || echo "! git yok: kodlama aşaması için gerekli (xcode-select --install)"

if [ $n -eq 0 ]; then
  echo "\n✗ Hiçbir model CLI'ı yok. Birini kurup kendi hesabınla giriş yap, sonra bu dosyayı tekrar çalıştır."
  read "?Kapatmak için Enter'a bas."; exit 1
fi

read "ans?Giriş yapılmış mı diye modellere kısa bir soru sorayım mı? (biraz kota harcar) [E/h] "
[[ "$ans" == [hHnN]* ]] || .venv/bin/python -m backend.runners --smoke

echo "\n✓ Kurulum bitti. Başlatmak için HackathonBuilder.command dosyasına çift tıkla."
read "?Kapatmak için Enter'a bas."
