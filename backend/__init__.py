import os
import sys

# Windows'ta Python dosyaları varsayılan olarak cp1254/cp1252 ile okur: Türkçe skill'ler ve tur kayıtları bozulur.
# UTF-8 modunda yeniden başlat (alt süreçler de PYTHONUTF8'i miras alır: testler, ürün sunucusu).
if os.name == "nt" and not sys.flags.utf8_mode:
    import subprocess

    os.environ["PYTHONUTF8"] = "1"
    sys.exit(subprocess.call([sys.executable, *sys.orig_argv[1:]]))
