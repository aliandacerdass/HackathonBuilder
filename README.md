# HackathonBuilder

Hackathon konusunu gir. Claude, GPT ve Gemini'den oluşan bir konsey fikir üretir ve birbirinin fikirlerini eleştirir. Bir jüri modeli fikirleri puanlar, son kararı sen verirsin. Seçtiğin fikir için makale, repo, web ve video kaynakları toplanır. Jüriye gösterebileceğin, kaynağı doğrulanmış sayılar ve eklenebilecek özellikler çıkarılır.

**API key gerekmez.** Uygulama modelleri kendi aboneliklerinle, resmi CLI'lar üzerinden çağırır: Claude Code, Codex CLI ve Antigravity (`agy`). Her şey senin bilgisayarında çalışır.

> Durum: **V1** (fikir konseyi) ve **V2** (araştırma) çalışıyor. Kodlama döngüsü ve UI/UX ajanı yol haritasında.

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

**Tarayıcıda:**

```bash
python -m backend.app
```

**http://127.0.0.1:8000** adresini aç. Konuyu, süreyi ve ekibi gir, sonra **Konseyi topla**'ya bas. Tur bitince istediğin fikrin kartında **Bu fikri seç**'e bas, istersen not ekle.

Kararı kaydettikten sonra **Bu fikir için araştırma yap**'a bas. Araştırma bitince eklemek istediğin özellikleri işaretleyip **Seçili özellikleri kaydet**'e bas.

**Terminalde:**

```bash
python -m backend.pipeline "Sağlıkta yapay zeka" --hours 24 --team "2 kişi, Python ve Flutter"
python -m backend.research runs/<tur-klasörü>      # decision.json olan bir tur için araştırma
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

`runs/` git'e gönderilmez, fikirlerin bilgisayarında kalır.

### Model seçimi (isteğe bağlı)

Boş bırakılırsa her CLI'ın varsayılan modeli kullanılır.

```bash
HB_CLAUDE_MODEL=sonnet python -m backend.app      # Claude kotan zorlanıyorsa
HB_GPT_MODEL=...  HB_GEMINI_MODEL=...
```

Gemini için kullanılabilir modelleri görmek için: `agy models`

## Güvenlik

- **Sadece yerel:** Sunucu yalnızca `127.0.0.1`'de dinler, aynı ağdaki başka cihazlar erişemez. Başka sitelerden gelen istekler reddedilir (Origin kontrolü).
- **Temiz context:** Modeller proje dışındaki boş bir klasörde çalışır, proje dosyalarını görmez.
- **Güvenli gösterim:** Model çıktıları sayfaya düz metin olarak yazılır (`textContent`). Çıktının içindeki HTML/script çalışmaz. Model linklerinden sadece `http`/`https` olanlar tıklanabilir.
- **Kısıtlı web erişimi:** Araştırmada Claude'a sadece arama ve okuma araçları verilir. GPT salt okunur sandbox'ta çalışır. Skill'ler, kaynak metnindeki talimatların yok sayılmasını söyler (prompt injection).
- **Push öncesi tarama:** Her push'tan önce `scripts/pre-push-check.sh` çalışır: gitleaks, API key, kişisel yol ve e-posta taraması. Bulgu varsa push iptal edilir.

## Proje dosyaları

| Dosya | Ne işe yarar |
|---|---|
| `RULES.md` | Bu projede çalışan herkes (insan ve ajan) için zorunlu kurallar |
| `PROJECT_MEMORY.md` | Kararlar, mimari, **kaldığımız yer** |
| `tasks.md` | Fazlara göre yapılacaklar |
| `COMMON_ERRORS.md` | Bilinen hatalar ve kontrol listesi |
| `skills/*.md` | Ajan rolleri (netleştirici, konsey üyesi, jüri, sorgu yazıcı, web araştırmacı, repo inceleyici, sayı ve özellik çıkarıcı) |

## Yol haritası

- [x] **V1:** Fikir konseyi (netleştirme → 2 turlu konsey → jüri → karar)
- [x] **V2:** Araştırma ajanları (makale, sayısal veri, özellik, GitHub, web/YouTube)
- [ ] **V3:** Kodlama döngüsü (kod → güvenlik → test → hata raporu, kullanıcı onay noktalarıyla)
- [ ] **V4:** UI/UX iyileştirme ve jüri sunumu

## Lisans

[MIT](LICENSE)
