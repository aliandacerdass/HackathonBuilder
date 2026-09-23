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
| agy uzun işte timeout | Yarım çıktı | Tek çağrıya tek iş, `--print-timeout` ver |

## Her Değişiklik Sonrası Kontrol Listesi
- [ ] Kodda key/token/şifre/kişisel yol yok
- [ ] Yeni gizli dosya türü varsa `.gitignore`'a eklendi
- [ ] Her CLI çağrısında timeout var
- [ ] Bir model düşerse pipeline çökmüyor
- [ ] PROJECT_MEMORY.md "Kaldığımız Yer" + tasks.md güncel
