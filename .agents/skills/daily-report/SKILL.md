---
name: daily-report
description: Elif’in belirli bir gün veya tarih aralığı için günlük iş raporunu Conductor, Orca, Slack müşteri talepleri, Linear, git/PR ve Fireflies kayıtlarını birleştirerek hazırla. Günlük rapor hazırlama, geçmiş günün işlerini çıkarma ve rapor kapsamını kontrol etme isteklerinde kullan; müşteri raporu veya otomatik görev başlatma için kullanma.
---

# Daily report — Elif

Bu kişisel skill’in asıl dosyaları `elif` reposundaki `.agents/skills/daily-report/` içindedir. Çıktıyı **aynı elif reposunun `reports/` klasörüne** yaz. Başka projede olsan da müşteri reposuna rapor kaydetme. Kullanıcının verdiği notlar ve düzeltmeler önceliklidir. CLI/API/connector ve dosya işlemleri kullan; arayüz kullanma. Raporu burada taslak olarak göster; başka workspace/ajan açmak gerekmez.

## Tarih ve kapsam

Tarih belirtilmemişse Europe/Istanbul’a göre bugün. Göreli tarihleri (“pazartesi ve salı”) kesin tarihlere çevirip belirt. Birden çok gün için ayrı rapor. Gün sınırı yerel 00:00 dahil, sonraki gün 00:00 hariçtir; UTC tarihine veya dosya değiştirilme tarihine göre sınıflandırma.

İki farklı şeyi ayır:
- **O gün yapılanlar:** o güne ait konuşma/işlem, commit, PR veya issue geçmişiyle desteklenen çalışma.
- **Şu an bekleyenler:** yalnız kullanıcı isterse güncel Follow-Ups ve Todo listesi; geçmiş tarih raporunda sorgulama tarihiyle etiketle. Bugünkü durumu geçmiş günün durumu gibi gösterme.

## Veri toplama

Skill klasörünü çöz ve buradaki scriptleri çalıştır. Örnek (cwd elif kökü):

```bash
python3 .agents/skills/daily-report/scripts/collect_activity.py 2026-11-16 --include-legacy --output .assistant/daily-report/2026-11-16/evidence.json
```

### Orca ve Conductor

Collector, yerel Codex indeksindeki aday oturumların **mesaj zamanlarını** gün sınırında filtreler. Böylece Salı tekrar açılan Pazartesi oturumu kaybolmaz; gün içinde açılan ama konuşulmayan workspace çalışma sayılmaz. Codex konuşmaları hem Orca hem Conductor klasörleri için okunur. Çıktıda raw konuşma metni vardır: yalnızca yerel kanıt olarak kullan; commit etme, paylaşma, rapora ham biçimde yapıştırma. Gizli anahtarlar veya özel konuşmalar rapora girmesin.

Kapsam: collector yerel Codex konuşmalarını kapsar; başka agent/runtime/remote makineyi kapsadığını iddia etme. Orca CLI `worktree list --json` ile envanteri, `search --help` / `search` ile eksik diğer agent oturumlarını araştır. Search `--since` **session updatedAt** filtresidir, her hit’in ilgili gün çalışıldığını kanıtlamaz; kaynak dosyadaki mesaj zamanını doğrula. SQLite yalnızca read-only URI ile okunur. Şema veya dosya yoksa kaynağı erişilemedi diye belirt; uygulama DB’sini değiştirme.

`--include-legacy` eski Conductor workspace ve merged-PR kolektörlerini de çalıştırır. Bunlar ek sinyaldir: workspace `updated_at`/archive tek başına çalışma veya bitirme kanıtı değildir. Sonraki günlerde yeniden kullanılmış/arşivlenmiş workspace önceki günün tarihsel durumunu taşımaz. Eski collector bazı `gh` hatalarını boş sonuç olarak gizler; forge auth/repo erişimini ayrıca doğrula, “0 PR = hiç kapanan iş yok” deme.

Konuşmada “yaptım” denmesi tek başına başarılı deployment/backfill/merge kanıtı değildir. Sonuç, PR veya test kanıtıyla doğrula; yalnızca ajan beyanıysa bunu belirt. Otomasyonun işleri keşfetmesi, onay beklemesi veya task açması, işin uygulanmasıyla aynı şey değildir.

### Git ve PR

Conductor envanterine ek olarak Orca’nın kayıtlı Git projelerini de kapsa; yeni Orca-only projeler eski GitHub collector’ında yoktur. Her ilgili repo/branch için gerçek remote hostunu kullan. GitHub’da `gh` ile PR `createdAt/mergedAt/closedAt` alanlarını sorgula. Bitbucket/GitLab için mevcut API/CLI varsa tercih et; yoksa eski `_common.py` merge-commit fallback’i kullanılabilir. Fallback yalnızca yerel merge izlerini görür, açık PR’ların yokluğunu veya eksiksizliği kanıtlamaz.

PR hangi gün merge/closed olmuşsa o günün kapananlarına al. Closed-unmerged iptaldir; merge değildir. Bir branch’te birden çok PR varsa ilgili bütün PR linklerini koru; eski PR merge’ini aynı branch’in bugünkü devam işinin bitişi sayma. Yerel uncommitted çalışma için PR bulunmaması işi düşürme nedeni değildir. Subject’i okuyanın anlayacağı somut iş tanımına çevir.

### Linear

Bağlantıdan Elif’e atanmış issue’ları getir, sayfalama yap. Gün için updated-after + yerel gün sonu filtresini uygula, ama bunun sonradan güncellenmiş issue’ları kaçırabileceğini unutma. İlgili issue’larda history/activity mevcutsa o günkü geçişi yeniden kur; yoksa historical status bilinmiyor de. Şirketi team’den değil project’ten çıkar; projectsiz yapılan iş Genel’dir.

Kullanıcının rapor kuralı: Linear **In Review** ve completed, Elif’in işi açısından kapalıdır; GitHub açık PR review ise ayrı teknik durum olarak Review’da kalır. İki durumu birbirine ezdirme. canceled → iptal. Todo yapılan iş değildir.

Kullanıcı güncel takip/To Do isterse ayrıca `assignee: me`, tam durum adı **Follow-Ups**, tarih filtresiz sorgula. Varsa parent başlığını getir; yoksa “Bekleyen takip yok.” Yalnız bu listede göster. Todo’ları da tarih filtresiz al: project şart; priority 1,2,3,4, sonra 0; eşit öncelikte dueDate artan, tarihsiz son. Geçmiş gün raporlarında her ikisini “Güncel takip — <sorgu tarihi>” olarak ayır; tarihsel backlog uydurma.

### Slack’te özel mesajdan gelen ilk task isteği

Raporu kısa tut: **özel mesajdan (DM veya ilgili grup DM) gelen ilk somut task isteğini ve devam konuşmasında gelen yeni iş/ek kapsam taleplerini** alıntıla. Kanal mesajları raporu okuyanlarca zaten görülebildiğinden bunları tekrar alıntılama. Kanal kaynaklı yapılan işi atlama; yalnız şirket/konu, durum ve varsa PR/issue linkiyle göster.

- İlgili DM konuşmasını ve gerekli devamını bağlam/doğrulama için oku; çıktıya her mesajı taşıma. Selamlaşma, yalnız açıklama yapan mesajlar, durum sorguları, hatırlatmalar ve teslim bildirimi alıntılanmaz. Ancak devam/follow-up mesajı yeni bir iş, değişiklik veya ek kapsam istiyorsa onu atlama: yalnız o yeni isteği tarih ve kaynak linkiyle ayrı talep olarak ekle; aynı işe ek kapsam ise aynı iş başlığında kısa bir “Ek talep” olarak göster. Önceki konuşmayı tekrar alıntılama.
- İlk somut task isteği mesajını aynen koru; gönderen, yalnız orijinal takvim tarihi ve permalink ekle; özel mesaj başlığında saat gösterme. Eski isteğe bugün çalışıldıysa eski tarihi koru; yeni ek talebin kendi tarihini ayrıca göster. Mesajın kendisi uzun teknik bir listeyse ilk talebin metni korunur; devam mesajları eklenmez. Hassas değerleri maskele ve belirt.
- Altına tek kısa **Durum** satırı: “Talep alındı; başlanmadı”, “Başlandı / devam ediyor”, “Tamamlandı” veya “Bekliyor — <somut engel>”. Gerçek çalışma kanıtı olmadan “başlandı”, yalnız planla “tamamlandı” deme.
- PR varsa aynı satıra veya hemen altına ekle; açık/review/merged/closed-unmerged durumunu doğru yaz. İş tamamlandı ama PR yoksa uydurma; “PR gerekmiyor” ancak gerçekten gerekmediği biliniyorsa söylenir. Tek işin birden fazla ilgili PR’ını koru.
- Toplantıları otomatik olarak her task’ın altına uzunca dökme. Bağlantısı doğrulanmış ve sonucu etkileyen karar varsa durum satırına bir cümle ekle. Kullanıcı ayrıntı isterse notları aç. Diğer toplantılar ayrı bölümde en çok bir kısa satır + linktir; transcript veya uzun not listesi değil.
- İlk DM talebi doğrulanamıyorsa uydurma; normal kısa iş kaydıyla devam et. Kullanıcı mesaj metnini verdiyse kaynak/tarih henüz doğrulanmadığını belirt. Slack geçmişini okumak, yeni task başlatma veya yanıt gönderme yetkisi değildir.

Örnek çıktı (şablon):

```markdown
### Birch — Offer Level raporu
**Rudi · <tarih>** · [Özel mesaj](<Slack permalink>)
> <Yalnız ilk somut task isteği mesajı>

**Durum:** Başlandı; dashboard sorguları inceleniyor.
**PR:** [#N](<url>) — review’da. <!-- Yalnız gerçek PR varsa -->
```

### Toplantılar

Kullanıcı not verdiyse onu kullan. Aksi halde yetkili Fireflies bağlantısından tarih aralığını + katılımı doğrula, toplantı özetlerini ve gerekli transcript bölümlerini oku. Bağlantı erişilemiyorsa ancak o zaman kullanıcıdan eksik notları iste; diğer kaynakları toplamaya devam et. Sıfır sonuç veya kaynak hatasıyla “toplantı yoktu” deme; yalnızca doğrulanmışsa söyle. Toplantıdaki plan/atama ile gerçekleştirilen işi ayır.

Birleşik veya özel/müşteri karışık kayıt varsa bölüm sınırlarıyla ayır; özel içeriği müşteri toplantısına taşıma. Bilinen özel sınır için [privacy.md](references/privacy.md) oku (yalnız 16 Kasım 2026 raporu hazırlanıyorsa). Kaydı yeniden paylaşma, e-posta/erişim ayarlarını değiştirme.

## Birleştirme ve çıktı

Aynı repo/branch/PR/Linear issue/konu Conductor ve Orca’da varsa tek iş olarak birleştir, kaynakları koru. Konu benzerliği tek başına eşleşme değildir: çıkarımsa belirt. Otomasyon tekrarı veya import edilmiş aynı konuşma iki iş sayılmaz. Açılan task, yapılan iş, biten iş, follow-up ve önerilen Todo ayrı kalır.

Her raporda şu kısa yapıyı kullan:

1. `# Günlük Rapor — YYYY-MM-DD`
2. `## Özelden Gelen Task İstekleri` — DM’deki ilk somut istek ve devamında gelen yeni iş/ek kapsam alıntısı + gönderen/yalnız tarih/link, ardından kısa durum ve varsa PR. Saat, sıradan takip konuşması ve kanal mesajı alıntısı ekleme.
3. `## Diğer Yapılan İşler` — kanal/Linear/Orca/Conductor kaynaklı işler şirket ve konu başına tek kısa madde: durum + varsa PR. DM bölümündeki işi tekrarlama.
4. `## Toplantılar` — varsa toplantı başına bir kısa sonuç cümlesi ve Fireflies linki. Ayrıntılı toplantı notları yalnız kullanıcı isterse.
5. `## Güncel Takip ve To Do` — varsayılan olarak ekleme. Yalnız kullanıcı isterse Follow-Ups ve sıralı Todo göster; sorgu tarihini belirt. Kullanıcının rapordan çıkardığı sunum maddesini tekrar ekleme.
6. `## Kaynak Kapsamı` — yalnız sonucu etkileyen erişim/tarihsel eksikler, en fazla birkaç cümle. Uzun doğrulama anlatısı ve ham kanıtlar rapora girmez; yerel evidence dosyalarında kalır.

Kullanıcı eski tablo formatını isterse [legacy-workflow.md](references/legacy-workflow.md) adım 5’i kullan; yukarıdaki tarih/doğrulama ve tekilleştirme kuralları yine geçerli. Eski referanstaki notları mutlaka kullanıcıdan isteme ve yalnız Conductor’a dayanma adımları burada güncellenmiştir.

`reports/YYYY-MM-DD.md` yoksa oluştur; varsa oku, kullanıcının düzenlemelerini koru ve açıkça yeniden üretme istemediyse `YYYY-MM-DD.draft.md` yaz. Kanıtları `.assistant/daily-report/` içinde private tut, git’e ekleme. Link ve tarihleri kontrol edip raporu bu sohbette göster. Birden fazla uzun rapor için dosya linki ve kısa iş özeti sun; kullanıcı tüm metni isterse göster.

## Gönderim sınırı

Skill’i çalıştırma, raporu hazırlama veya onaylama Slack’e gönderme yetkisi değildir. Yalnız açık “gönder” talimatı ve hangi rapor olduğu netse, önce raporu gösterip sonra Slack Canvas ve `#elif-onboarding` (`C07QXSJQ8RG`) link mesajı oluştur. Eksik yetki/araç varsa gönderildi deme. Normal rapor çalıştırmada Slack/Linear/PR mutasyonu, merge/deploy veya yeni proje işi başlatma.
