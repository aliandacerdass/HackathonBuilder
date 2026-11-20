# COMMON_ERRORS — Hata Bankası

## Bilinen Hatalar
| Hata | Belirti | Çözüm |
|---|---|---|
| codex stdin bekliyor | Süreç canlı, CPU ~0, cevap yok | Komut sonuna `< /dev/null` |
| codex Türkçe karakter düşürüyor | "cuzdan" (cüzdan yerine) | Dil TR ise GPT çıktısı `fix_turkish()` ile Claude'dan geçer (başarısızsa GPT cevabı aynen kalır) |
| agy görevi yanlış anlıyor | CLI dokümantasyonu araştırmaya gidiyor | Tüm bayraklar `--print`'ten ÖNCE |
| agy sistem temp'te 503 | `Eligibility check failed: UNAVAILABLE (code 503)` — servis ayakta olsa bile | CLI'ı `/var/folders` yerine `~/.cache/hackathonbuilder/` altında çalıştır |
| claude stdin uyarısı | `no stdin data received in 3s` | `stdin=DEVNULL` |
| CLI proje içinde çalışırsa | CLAUDE.md/AGENTS.md'yi okur, konsey context'i kirlenir | Çalışma klasörü proje DIŞINDA |
| Şema çevirici alan adını sildi | `Idea.title` şemadan kayboldu | `title` meta verisini silerken `properties` içindeki alan adlarına dokunma — şemayı modele vermeden önce `required` listesini kontrol et |
| EventSource otomatik yeniden bağlanır | Kopunca aynı isteği tekrar atar | Başlatma POST ile, akış GET ile ayrı; sunucu Last-Event-ID'den devam eder (yeni tur BAŞLAMAZ) |
| CSS grid `auto` sütun genişler | Puan sayıları cetvelden kopup en sağa kaydı | `max-content` + `justify-content: start` |
| Hook e-posta yanlış alarmı | `+@app.get` e-posta sanıldı, push durdu | Diff'in baştaki `+` işaretini sil; e-posta kalıbı harf/rakamla başlasın |
| Paralel aşama en yavaş model kadar sürer | 2 model 15s'de bitip Gemini'yi 84s bekledi | Darboğazı `timings.json`'dan bul; o modeli hızlandır |
| Uzun model çıktısı her şeyi yavaşlatır | Fikir ~3200 karakter → tur 2 ve jüri girdisi şişti | Skill'lere kelime/madde sınırı koy |
| Claude Code `Write` klasör dışına yazar | `acceptEdits` modunda `../outside.txt` izinsiz oluştu | Kodlayıcı SADECE işletim sistemi sandbox'ında: macOS `sandbox-exec` (`runners.sandbox()`) ya da Codex `-s workspace-write` |
| `--allowedTools` prompt'u yuttu | `Input must be provided... when using --print` | Araçları virgülle tek argüman ver (`"Read,Edit"`) veya prompt'tan önce `--` koy |
| Codex kotası doldu | `usage limit. Upgrade to Plus... try again at Oct 2nd` | Kota dolunca **Kaldığı yerden devam et**; ya da `HB_CODER` ile kodu başka model yazsın |
| İzin kuralı `Write(./**)` işe yaramaz | "not matched by file permission checks" | `Edit(./**)` kullan |
| Sandbox'taki claude durdurulunca yetim kalır | Üst süreç öldü, claude PPID=1 ile çalışıp kota yemeye devam etti | Kendi süreç grubu (`PROC_GROUP`) + `kill_tree()` (macOS: os.killpg, Windows: taskkill /T); timeout ve iptal ikisinde de |
| Sandbox'ta sunucu port açamıyor | `[Errno 1] error while attempting to bind ... operation not permitted` | Ağ kapalı sandbox localhost'a bile bind ettirmiyor → sunucu `sandbox(..., network=True)` ile (yazma yine proje içiyle sınırlı) |
| agy uzun işte timeout | Yarım çıktı | Tek çağrıya tek iş, `--print-timeout` ver |
| GitHub arama 403 | `search/repositories` 403, `/rate_limit` ise 10/10 gösteriyor | Key'siz arama limiti DAKİKADA 10 (saatte 60 değil). `/rate_limit` eski değer gösterebilir; gerçek kalan `x-ratelimit-remaining` başlığında. Araştırma toplam ≤10 arama yapar; testleri arka arkaya koşma |
| Genişletilmiş arama alakasız popüler repo getirdi | `in:readme` + yıldız sırası → `public-apis` (500k★) | Genişletmede README arama yok, `sort` yok (en iyi eşleşme), ek sonuçlar ilk aramanın ARKASINA eklenir |
| agy komut reddedilince rapor vermiyor | Dosyalar yazıldı ama `structured_output` yok, `denied_actions: Bash` | Gemini kodlayıcı prompt'unun başına "terminalin yok, sadece dosya düzenle" (`GEMINI_NO_TERMINAL`) |
| agy prompt'u stdin'den okumuyor | `--print -` boş cevap | agy'ye prompt argüman olarak gider (tek .exe, cmd.exe'den geçmez) |
| Homebrew Python'da `pip install` reddedilir | `externally-managed-environment` | `Kurulum-Mac.command` kendi `.venv`'ini kurar |
| Ürün venv'inde fastapi yok | HackathonBuilder kendi `.venv`'inden çalışınca `--system-site-packages` temel paketleri getirmez | `setup_project` eksikse `BASE_PACKAGES`'ı kurar |
| Windows npm kısayolu (`.cmd`) | cmd.exe argümandaki `" & %` karakterlerini bozar ya da komut sanar; 8191 karakter sınırı | `_exe()` kısayolun node betiğini doğrudan çalıştırır; Claude/Codex prompt'u stdin'den |
| Windows varsayılan kodlaması | Türkçe skill/kayıt dosyaları cp1254 ile okunur, bozulur | `backend/__init__.py` Windows'ta UTF-8 modunda yeniden başlatır |
| `hidden` niteliği çalışmadı | Ray giriş ekranında göründü | CSS'teki `display:flex` UA'nın `[hidden]{display:none}` kuralını ezer → global `[hidden] { display: none !important; }` |
| Tam sayfa ekran görüntüsünde resim boş | UI önce/sonra kutuları sadece başlıkla çıktı | `loading=lazy` resimler ekran dışında yüklenmez → görüntüden önce `loading='eager'` + `complete` bekle |

## Her Değişiklik Sonrası Kontrol Listesi
- [ ] Kodda key/token/şifre/kişisel yol yok
- [ ] Yeni gizli dosya türü varsa `.gitignore`'a eklendi
- [ ] Her CLI çağrısında timeout var
- [ ] Bir model düşerse pipeline çökmüyor
- [ ] Model çıktısı DOM'a sadece textContent ile yazılıyor (innerHTML yok)
- [ ] Model'den gelen link sadece `link()` ile (http/https kontrolü) — `a.href = url` doğrudan YASAK
