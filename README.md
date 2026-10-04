# HackathonBuilder

Hackathon konusunu gir. Claude, GPT ve Gemini'den oluşan bir konsey fikir üretir ve birbirinin fikirlerini eleştirir. Bir jüri modeli fikirleri puanlar, son kararı sen verirsin. Seçtiğin fikir için makale, repo, web ve video kaynakları toplanır. Jüriye gösterebileceğin, kaynağı doğrulanmış sayılar ve eklenebilecek özellikler çıkarılır. Sonra ajanlar fikri koda döker: plan, görev görev kod, test ve güvenlik incelemesi.

**API key gerekmez.** Uygulama modelleri kendi aboneliklerinle, resmi CLI'lar üzerinden çağırır: Claude Code, Codex CLI ve Antigravity (`agy`). Her şey senin bilgisayarında çalışır.

> Durum: **V1** (fikir konseyi), **V2** (araştırma), **V3** (kodlama döngüsü) ve **V4'ün UI/UX ajanı** çalışıyor. Jüri sunumu yol haritasında.

## Nasıl çalışır

```
Konu ──▶ Netleştirme ──▶ Konsey I ──▶ Konsey II ──▶ Jüri ──▶ 👤 Karar
         (Claude)        3 model,     herkes diğer-  fikirler
                         birbirini    lerini eleş-   anonim
                         görmeden     tirir + gelişti- puanlanır
                         2'şer fikir  rilmiş 1 fikir
```

- **Konsey I:** Modeller birbirinin fikrini görmeden yazar, böylece birbirlerini etkilemezler (anchoring).
- **Jüri:** Fikirleri yazarını bilmeden puanlar. Toplam puanı model değil kod hesaplar (ağırlıklı ortalama).
- **Model düşerse:** Bir model hata verirse konsey kalan modellerle devam eder. Netleştirme ve jüri adımlarında sıradaki modele geçilir.
- Bir tur genelde **1.5-3 dakika** sürer (süre servislerin anlık yüküne göre değişir).

### Araştırma (V2)

```
Seçtiğin fikir ──▶ Arama sorguları ──▶ Makaleler (OpenAlex)      ──▶ Link       ──▶ Jüri için sayılar
                   (LLM)               Repolar (GitHub + README)     doğrulama      (her sayı kaynaklı)
                                       Web (GPT web araması)         (kod)       ──▶ Önerilen özellikler
                                       Videolar (Claude web araması)                  ──▶ 👤 Seçim
```

- **Uydurma kaynak üretilemez:** Makale ve repolar resmi API'lerden gelir. LLM sadece sorgu yazar, seçer ve analiz eder.
- **Her link kodla doğrulanır:** ✓ doğrulandı, ? site erişimi engelledi, ✗ ulaşılamadı (listeden çıkarılır).
- **Kaynak filtresi:** Bir sayı veya özellik, toplanan listede olmayan bir linke dayanıyorsa kodla atılır.
- **Gemini sadece analiz yapar**, web'e çıkmaz. Web araması Claude ve GPT'de.
- Bir araştırma turu genelde **1.5-2.5 dakika** sürer. Web araması Claude kotasını normal çağrılardan hızlı harcar.

### Kodlama (V3)

```
Fikir + seçili özellikler ──▶ Plan ──▶ 👤 Plan onayı ──▶ 👤 Paket onayı ──▶ Görev döngüsü (en fazla 8 görev)
                              (LLM)                                         kod ──▶ test ──▶ güvenlik ──▶ commit
                                                                                  (≤3 düzeltme)  (ciddi bulgu → düzelt)
```

- **Sabit stack:** FastAPI + HTML/JS. Testler `unittest`.
- **Ürün HackathonBuilder'ın dışına yazılır:** `~/HackathonBuilderProjects/<tur-klasörü>/`. Her ürün kendi git reposudur, her görev ayrı commit olur. Sızıntı kontrolü hook'u ürüne de kurulur.
- **Kodlayıcı sandbox'ta çalışır:** Kod `codex sandbox` (macOS işletim sistemi sandbox'ı) içinde yazılır ve proje klasörü dışına yazamaz. Varsayılan kodlayıcı Claude'dur (`codex sandbox` Codex kotası harcamaz). Claude'un ağ bağlantısı açıktır, çünkü kendi sunucusuna ulaşması gerekir; ama ona sadece dosya okuma/düzenleme araçları verilir, komut çalıştıramaz ve web'e çıkamaz. `HB_CODER=codex` ile kodu Codex yazar; Codex'in sandbox'ında internet tamamen kapalıdır.
- **Testleri ajan değil uygulama çalıştırır.** Ajanın "testler geçti" demesine güvenilmez.
- **Güvenlik incelemesi:** Her görevin diff'ini Claude inceler. Hangi bulguların düzeltileceğini plan onayında seçersin: sadece high, high + medium (varsayılan) veya hepsi. Kalanlar raporda görünür.
- **UI/UX cilası (V4):** Görevler bitince bir ajan kodu okuyup jüri demosunu tarayıcı adımlarına çevirir (tıkla, doldur, seç, dosya yükle, bekle). Bu adımlar kod değil, JSON listesidir; uygulamayı bizim kod yapar ve proje dışından dosya yüklenemez. Uygulama sandbox'ta açılır, demo adımlarıyla gezilir ve ilk ekranla birlikte demo ekranları masaüstünde ve mobilde çekilir. UI ajanı görüntülere bakıp sadece `app/static/`'i (HTML/CSS/JS) iyileştirir: ilk izlenim, hiyerarşi, renk paleti, mobil, erişilebilirlik. Sonra testler çalışır ve sayfa yeniden çekilip konsol hataları ve mobilde yatay taşma kodla kontrol edilir. Sorun çıkarsa ajana bir kez düzelttirilir. Test kırılırsa, yeni JS hatası çıkarsa veya önce çalışan bir demo adımı artık çalışmıyorsa cila tamamen geri alınır, yani ürünü bozamaz. Cila ayrı bir commit'tir, sonuçta her ekranın önce/sonra görüntüleri gösterilir.
- **Tek tıkla açma:** Kodlama bitince projeye `Baslat-Mac.command` (macOS) ve `Baslat-Windows.bat` (Windows) eklenir. Çift tıklayınca uygulama başlar ve tarayıcıda açılır. Başka bir bilgisayarda ilk açılışta Python ortamını kendisi kurar; bunun için `requirements.txt` kodun import ettiği paketlerden çıkarılır. Windows'ta Python kurulu olmalı.
- **Paketler:** Kodlayıcı paket kuramaz. Onayladığın paketleri uygulama, projenin `.venv`'ine kurar.
- **Durdur / devam et:** Kota dolarsa veya durdurursan, biten görevler commit'lerden bulunur ve kalanlardan devam edilir.

## Gereksinimler

- macOS veya Linux, **Python 3.10+**
- Aşağıdaki üç CLI, **kurulu ve kendi hesabınla giriş yapılmış** olmalı:

| Model | CLI | Abonelik | Giriş |
|---|---|---|---|
| Claude | [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (`claude`) | Claude Pro/Max | `claude` çalıştır → `/login` |
| GPT | [Codex CLI](https://github.com/openai/codex) (`codex`) | ChatGPT | `codex login` |
| Gemini | Antigravity CLI (`agy`) | Google/Gemini | `agy` çalıştır → hesabınla giriş |

- Push öncesi sızıntı taraması için: [`gitleaks`](https://github.com/gitleaks/gitleaks) (`brew install gitleaks`)

## Kurulum

```bash
git clone https://github.com/aliandacerdass/HackathonBuilder.git
cd HackathonBuilder
pip install -r requirements.txt
playwright install chromium             # UI cilası için ekran görüntüsü tarayıcısı
git config core.hooksPath .githooks     # push öncesi sızıntı kontrolünü açar
```

CLI'ların çalıştığını kontrol et:

```bash
python -m backend.runners --smoke
```

Beklenen çıktı `3/3`. Bir model ✗ verirse o CLI'ın girişini kontrol et. Bilinen hatalar için [COMMON_ERRORS.md](COMMON_ERRORS.md).

Araştırma API'lerini (OpenAlex, GitHub, YouTube) kontrol et:

```bash
python -m backend.tools --selftest
```

Beklenen çıktı `10/10`. GitHub, key olmadan saatte 60 isteğe izin veriyor.

## Kullanım

**Tarayıcıda:** macOS'ta `HackathonBuilder.command` dosyasına çift tıkla: sunucu başlar, tarayıcı kendiliğinden açılır. Kapatmak için açılan Terminal penceresini kapat. Ya da terminalden:

```bash
python -m backend.app
```

**http://127.0.0.1:8000** adresini aç. Konuyu, süreyi ve ekibi gir, sonra **Konseyi topla**'ya bas. Tur bitince istediğin fikrin kartında **Bu fikri seç**'e bas, istersen not ekle.

Konuyu girerken **Sonuç dili**ni seç (Türkçe/İngilizce). Fikirler, araştırma ve plan bu dilde yazılır, tur içinde değişmez.

Kararı kaydettikten sonra **Bu fikir için araştırma yap**'a bas. Araştırma bitince eklemek istediğin özellikleri işaretleyip **Seçili özellikleri kaydet**'e bas.

Sonra **Kodlamaya başla**'ya bas. Planı onaylarken hangi güvenlik bulgularının düzeltileceğini seç, sonra kurulacak paketleri onayla (reddedersen not yazarak planı bir kez yeniden yazdırabilirsin). Görevler canlı akar, **Durdur** ile kesebilir, **Kaldığı yerden devam et** ile sürdürebilirsin. Bitince ürünün nasıl çalıştırılacağı ve test/güvenlik raporu gösterilir.

**Terminalde:**

```bash
python -m backend.pipeline "Sağlıkta yapay zeka" --hours 24 --team "2 kişi, Python ve Flutter"
python -m backend.research runs/<tur-klasörü>      # decision.json olan bir tur için araştırma
python -m backend.builder runs/<tur-klasörü>       # kodlama (onaylar terminalden sorulur)
python -m backend.builder runs/<tur-klasörü> --resume   # durduysa kaldığı yerden devam
```

Üretilen ürünü açmak için proje klasöründe `Baslat-Mac.command` (Windows'ta `Baslat-Windows.bat`) dosyasına çift tıkla. Ya da terminalden:

```bash
cd ~/HackathonBuilderProjects/<tur-klasörü>
.venv/bin/python -m uvicorn app.main:app --port 8001
```

### Çıktılar

Her tur `runs/<tarih>-<konu>/` klasörüne kaydedilir:

| Dosya | İçerik |
|---|---|
| `input.json` | Girdiğin konu, süre, ekip |
| `refined.json` | Netleştirilmiş konu ve jüri kriterleri |
| `round1.json`, `round2.json` | Fikirler ve eleştiriler |
| `ranking.json` | Jüri puanları ve sıralama |
| `timings.json` | Aşama ve model süreleri |
| `decision.json` | Seçtiğin fikir ve notun |
| `research.json` | Sorgular, makaleler, repolar, web/video kaynakları, sayılar, özellikler |
| `research_timings.json` | Araştırma aşama ve model süreleri |
| `research_decision.json` | Seçtiğin özellikler ve notun |
| `plan.json` | Onaylanan kodlama planı: görevler, paketler, dosya ağacı |
| `build_options.json` | Plan onayındaki güvenlik düzeltme seviyesi ve kurulan paketler (`--resume` bunları kullanır) |
| `build.json` | Görev sonuçları, son test çıktısı, çalıştırma komutu, demo adımları |
| `build_timings.json` | Kodlama aşama süreleri |
| `ui/*.png` | UI cilası önce/sonra ekran görüntüleri: ilk ekran + en fazla 3 demo ekranı, masaüstü + mobil |

`runs/` git'e gönderilmez, fikirlerin bilgisayarında kalır. Ürünün kodu `~/HackathonBuilderProjects/<tur-klasörü>/` içindedir.

### Model seçimi (isteğe bağlı)

Boş bırakılırsa her CLI'ın varsayılan modeli kullanılır.

```bash
HB_CLAUDE_MODEL=sonnet python -m backend.app      # Claude kotan zorlanıyorsa
HB_GPT_MODEL=...  HB_GEMINI_MODEL=...
HB_CODER=codex python -m backend.app             # kodu Claude yerine Codex yazsın
```

Gemini için kullanılabilir modelleri görmek için: `agy models`

## Güvenlik

- **Sadece yerel:** Sunucu yalnızca `127.0.0.1`'de dinler, aynı ağdaki başka cihazlar erişemez. Başka sitelerden gelen istekler reddedilir (Origin kontrolü).
- **Temiz context:** Modeller proje dışındaki boş bir klasörde çalışır, proje dosyalarını görmez.
- **Güvenli gösterim:** Model çıktıları sayfaya düz metin olarak yazılır (`textContent`). Çıktının içindeki HTML/script çalışmaz. Model linklerinden sadece `http`/`https` olanlar tıklanabilir.
- **Kısıtlı web erişimi:** Araştırmada Claude'a sadece arama ve okuma araçları verilir. GPT salt okunur sandbox'ta çalışır. Skill'ler, kaynak metnindeki talimatların yok sayılmasını söyler (prompt injection).
- **Kodlama sandbox'ı:** Kodlayıcı, üretilen testler ve UI cilası sırasında açılan uygulama işletim sistemi sandbox'ında çalışır ve proje klasörü dışına yazamaz. Testler internetsiz çalışır. Claude kodlayıcı ile UI cilası sunucusunun ağ bağlantısı açıktır: Claude'un kendi sunucusuna ulaşması, uygulamanın da port açabilmesi için gerekir (ağsız sandbox localhost'ta bile port açtırmıyor). Sandbox dosya *okumayı* engellemez; bu yüzden üretilen projeye de push öncesi sızıntı taraması kurulur. Paket kurulumu ve her plan senin onayınla yapılır.
- **Push öncesi tarama:** Her push'tan önce `scripts/pre-push-check.sh` çalışır: gitleaks, API key, kişisel yol ve e-posta taraması. Bulgu varsa push iptal edilir.

## Proje dosyaları

| Dosya | Ne işe yarar |
|---|---|
| `RULES.md` | Bu projede çalışan herkes (insan ve ajan) için zorunlu kurallar |
| `PROJECT_MEMORY.md` | Kararlar, mimari, **kaldığımız yer** |
| `tasks.md` | Fazlara göre yapılacaklar |
| `COMMON_ERRORS.md` | Bilinen hatalar ve kontrol listesi |
| `skills/*.md` | Ajan rolleri (netleştirici, konsey üyesi, jüri, sorgu yazıcı, web araştırmacı, repo inceleyici, sayı ve özellik çıkarıcı, planlayıcı, kodlayıcı, güvenlik inceleyici, demo adımı yazıcı, UI tasarımcısı) |

## Yol haritası

- [x] **V1:** Fikir konseyi (netleştirme → 2 turlu konsey → jüri → karar)
- [x] **V2:** Araştırma ajanları (makale, sayısal veri, özellik, GitHub, web/YouTube)
- [x] **V3:** Kodlama döngüsü (kod → güvenlik → test → hata raporu, kullanıcı onay noktalarıyla)
- [x] **V4a:** UI/UX iyileştirme ajanı (ekran görüntüsüyle)
- [ ] **V4b:** Jüri sunumu

## Lisans

[MIT](LICENSE)
