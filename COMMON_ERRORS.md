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
| Test commit'ini `reset --hard` ile geri almak | Commit edilmemiş değişiklikler de silindi | Önce gerçek değişiklikleri commit'le, ya da `git reset --soft HEAD~1` + test dosyasını elle sil |
| Paralel aşama en yavaş model kadar sürer | 2 model 15s'de bitip Gemini'yi 84s bekledi | Darboğazı `timings.json`'dan bul; o modeli hızlandır |
| Uzun model çıktısı her şeyi yavaşlatır | Fikir ~3200 karakter → tur 2 ve jüri girdisi şişti | Skill'lere kelime/madde sınırı koy |
| Arka plan izleyicisi sonsuza kadar bekledi | "Yeni klasör açılsın" beklerken klasör zaten açılmıştı | Tetikleyiciden SONRA değil, bilinen hedefi izle |
| Claude Code `Write` klasör dışına yazar | `acceptEdits` modunda `../outside.txt` izinsiz oluştu | Kod yazdırma SADECE Codex `-s workspace-write`; Claude'a dosya aracı verme |
| `--allowedTools` prompt'u yuttu | `Input must be provided... when using --print` | Araçları virgülle tek argüman ver (`"Read,Edit"`) veya prompt'tan önce `--` koy |
| Codex kotası doldu | `usage limit. Upgrade to Plus... try again at Oct 2nd` | Kodlayıcı alternatifi: Claude Code OS sandbox içinde |
| İzin kuralı `Write(./**)` işe yaramaz | "not matched by file permission checks" | `Edit(./**)` kullan |
| `codex sandbox claude` durdurulunca claude yetim kalır | Üst süreç öldü, claude PPID=1 ile çalışıp kota yemeye devam etti | `start_new_session=True` + `kill_tree()` (os.killpg); timeout ve iptal ikisinde de |
| Sandbox'ta sunucu port açamıyor | `[Errno 1] error while attempting to bind ... operation not permitted` | `codex sandbox` ağ kapalıyken localhost'a bile bind yok → `sandbox_workspace_write.network_access=true` (yazma yine proje içiyle sınırlı) |
| agy uzun işte timeout | Yarım çıktı | Tek çağrıya tek iş, `--print-timeout` ver |
| GitHub arama 403 | `search/repositories` 403, `/rate_limit` ise 10/10 gösteriyor | Key'siz arama limiti DAKİKADA 10 (saatte 60 değil). `/rate_limit` eski değer gösterebilir; gerçek kalan `x-ratelimit-remaining` başlığında. Araştırma toplam ≤10 arama yapar; testleri arka arkaya koşma |
| Genişletilmiş arama alakasız popüler repo getirdi | `in:readme` + yıldız sırası → `public-apis` (500k★) | Genişletmede README arama yok, `sort` yok (en iyi eşleşme), ek sonuçlar ilk aramanın ARKASINA eklenir |

## Her Değişiklik Sonrası Kontrol Listesi
- [ ] Kodda key/token/şifre/kişisel yol yok
- [ ] Yeni gizli dosya türü varsa `.gitignore`'a eklendi
- [ ] Her CLI çağrısında timeout var
- [ ] Bir model düşerse pipeline çökmüyor
- [ ] Model çıktısı DOM'a sadece textContent ile yazılıyor (innerHTML yok)
- [ ] Model'den gelen link sadece `link()` ile (http/https kontrolü) — `a.href = url` doğrudan YASAK
- [ ] PROJECT_MEMORY.md "Kaldığımız Yer" + tasks.md güncel
