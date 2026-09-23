# COMMON_ERRORS — Hata Bankası

## Bilinen Hatalar
| Hata | Belirti | Çözüm |
|---|---|---|
| codex stdin bekliyor | Süreç canlı, CPU ~0, cevap yok | Komut sonuna `< /dev/null` |
| codex Türkçe karakter düşürüyor | "cuzdan" (cüzdan yerine) | Model çıktıları İngilizce istenir; Türkçe metni Claude/Gemini yazar |
| agy görevi yanlış anlıyor | CLI dokümantasyonu araştırmaya gidiyor | Tüm bayraklar `--print`'ten ÖNCE |
| agy sistem temp'te 503 | `Eligibility check failed: UNAVAILABLE (code 503)` — servis ayakta olsa bile | CLI'ı `/var/folders` yerine `~/.cache/hackathonbuilder/` altında çalıştır |
| claude stdin uyarısı | `no stdin data received in 3s` | `stdin=DEVNULL` |
| CLI proje içinde çalışırsa | CLAUDE.md/AGENTS.md'yi okur, konsey context'i kirlenir | Çalışma klasörü proje DIŞINDA |
| Şema çevirici alan adını sildi | `Idea.title` şemadan kayboldu | `title` meta verisini silerken `properties` içindeki alan adlarına dokunma — şemayı modele vermeden önce `required` listesini kontrol et |
| EventSource otomatik yeniden bağlanır | Kopunca aynı isteği tekrar atar | Başlatma POST ile, akış GET ile ayrı; sunucu Last-Event-ID'den devam eder (yeni tur BAŞLAMAZ) |
| CSS grid `auto` sütun genişler | Puan sayıları cetvelden kopup en sağa kaydı | `max-content` + `justify-content: start` |
| Hook e-posta yanlış alarmı | `+@app.get` e-posta sanıldı, push durdu | Diff'in baştaki `+` işaretini sil; e-posta kalıbı harf/rakamla başlasın |
| Test commit'ini `reset --hard` ile geri almak | Commit edilmemiş değişiklikler de silindi | Önce gerçek değişiklikleri commit'le, ya da `git reset --soft HEAD~1` + test dosyasını elle sil |
| agy uzun işte timeout | Yarım çıktı | Tek çağrıya tek iş, `--print-timeout` ver |

## Her Değişiklik Sonrası Kontrol Listesi
- [ ] Kodda key/token/şifre/kişisel yol yok
- [ ] Yeni gizli dosya türü varsa `.gitignore`'a eklendi
- [ ] Her CLI çağrısında timeout var
- [ ] Bir model düşerse pipeline çökmüyor
- [ ] Model çıktısı DOM'a sadece textContent ile yazılıyor (innerHTML yok)
- [ ] PROJECT_MEMORY.md "Kaldığımız Yer" + tasks.md güncel
